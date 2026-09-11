"""Script para procesar un video, detectar y seguir vehículos, y contar salidas hacia la carretera principal.

Uso:
    python scripts/contar_salidas.py <video> [--config <ruta>] [--out-dir <ruta>] [--escala <float>]

Ejemplo:
    python scripts/contar_salidas.py "Camara Placas 2_20260909105651-20260909163038(60).mp4"
"""

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional, Tuple

# Asegurar que la raíz del proyecto esté en sys.path para importar lastre
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from lastre.config import cargar_configuracion, ConfiguracionError, ZonaConfig
from lastre.deteccion import DetectorMovimiento, DeteccionError
from lastre.vehiculos import DetectorHibrido, DetectorVehiculos
from lastre.salida import (
    CATEGORIA_ENTRADA,
    CATEGORIA_PERMANENCIA,
    CATEGORIA_RUIDO,
    CATEGORIA_SALIDA,
    ResultadoClasificacion,
    clasificar_trayectoria,
)
from lastre.seguimiento import SeguidorTrayectorias, SeguimientoError
from lastre.trayectoria import Trayectoria
from lastre.video import iterar_cuadros, obtener_metadatos_video, VideoLecturaError
from lastre.zona import superponer_zona


def parse_args():
    parser = argparse.ArgumentParser(
        description="Cuenta las salidas de vehículos desde la vía de lastre hacia la carretera principal.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "video",
        type=str,
        help="Ruta al archivo de video de entrada.",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default="config/zona.json",
        help="Ruta al archivo de configuración JSON de la zona.",
    )
    parser.add_argument(
        "--out-dir",
        "-o",
        type=str,
        default="out",
        help="Directorio donde se guardarán el reporte JSON y las imágenes de respaldo.",
    )
    parser.add_argument(
        "--escala",
        "-e",
        type=float,
        default=0.25,
        help="Factor de reducción para la detección MOG2 (0.25 = 740x416, ~110 fps). Coordenadas siempre a escala completa.",
    )
    parser.add_argument(
        "--desplazamiento-min",
        "-d",
        type=float,
        default=30.0,
        help="Desplazamiento neto mínimo en píxeles para considerar movimiento real (filtra estacionados).",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Límite de cuadros a procesar (útil para pruebas y muestreos rápidos).",
    )
    parser.add_argument(
        "--detector",
        choices=("movimiento", "vehiculos"),
        default="vehiculos",
        help="Motor de detección. 'vehiculos' reconoce el vehículo en sí e ignora las sombras.",
    )
    parser.add_argument(
        "--modelo",
        type=str,
        default="rf-detr-nano-384-coco",
        help="Modelo de detección de objetos a utilizar.",
    )
    parser.add_argument(
        "--confianza",
        type=float,
        default=0.5,
        help="Confianza mínima para aceptar una detección de vehículo.",
    )
    parser.add_argument(
        "--paso",
        type=int,
        default=5,
        help="Analizar 1 de cada N cuadros. Solo aplica al detector de vehículos.",
    )
    return parser.parse_args()


def _recuperar_cuadro(buffer_cuadros, numero_cuadro, respaldo):
    """Recupera del buffer el cuadro del cruce, descomprimiendolo.

    Si el cuadro ya no esta en el buffer devuelve el respaldo indicado, que
    produce una evidencia menos precisa pero nunca deja el registro sin imagen.
    """
    codificado = buffer_cuadros.get(numero_cuadro)
    if codificado is not None:
        return cv2.imdecode(np.frombuffer(codificado, np.uint8), cv2.IMREAD_COLOR)
    if respaldo is not None:
        return respaldo
    ultimo = max(buffer_cuadros) if buffer_cuadros else None
    if ultimo is None:
        return None
    return cv2.imdecode(np.frombuffer(buffer_cuadros[ultimo], np.uint8), cv2.IMREAD_COLOR)


def dibujar_evidencia_salida(
    cuadro_original: np.ndarray,
    config: ZonaConfig,
    resultado: ResultadoClasificacion,
    numero_salida: int,
) -> np.ndarray:
    """Genera una imagen anotada con el recuadro del vehículo saliente y la delimitación."""
    visual = superponer_zona(cuadro_original, config, alfa_zona=0.25)
    alto, ancho = visual.shape[:2]

    # Dibujar segmento de salida resaltado en naranja/rojo
    p_ini = config.segmento_salida.punto_inicio.tupla
    p_fin = config.segmento_salida.punto_fin.tupla
    cv2.line(visual, p_ini, p_fin, (0, 140, 255), 4, cv2.LINE_AA)

    # Dibujar la caja del vehículo en el cuadro de cruce
    if resultado.caja_cruce is not None:
        bx, by, bw, bh = resultado.caja_cruce
        cv2.rectangle(visual, (bx, by), (bx + bw, by + bh), (0, 255, 0), 3)

        # Punto centroide del cruce
        if resultado.centro_cruce is not None:
            cv2.circle(visual, resultado.centro_cruce, 6, (0, 0, 255), -1)

        # Rótulo sobre el vehículo
        texto_vehiculo = f"SALIDA #{numero_salida} (Trayectoria ID: {resultado.trayectoria_id})"
        cv2.putText(
            visual,
            texto_vehiculo,
            (bx, max(30, by - 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

    # Rótulo general en la parte inferior
    rotulo = f"Salida #{numero_salida} | Cuadro: {resultado.cuadro_cruce} | Trayectoria: {resultado.trayectoria_id}"
    cv2.putText(
        visual,
        rotulo,
        (30, alto - 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.1,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    return visual


def main():
    args = parse_args()

    # 1. Cargar configuración
    try:
        config = cargar_configuracion(args.config)
    except ConfiguracionError as err:
        print(f"Error de configuración: {err}", file=sys.stderr)
        sys.exit(1)

    # 2. Metadatos del video
    try:
        meta = obtener_metadatos_video(args.video)
    except VideoLecturaError as err:
        print(f"Error al abrir video: {err}", file=sys.stderr)
        sys.exit(1)

    total_esperado = args.max_frames if args.max_frames else meta.total_cuadros
    print("=" * 70)
    print("CONTEO DE SALIDAS EN VIA DE LASTRE")
    print("=" * 70)
    print(f"Video:              {meta.ruta.name}")
    print(f"Resolución:         {meta.ancho}x{meta.alto} @ {meta.fps:.2f} fps")
    print(f"Cuadros a procesar: {total_esperado}")
    print(f"Escala MOG2:        {args.escala} ({int(meta.ancho*args.escala)}x{int(meta.alto*args.escala)})")
    print(f"Área mínima:        {config.deteccion.area_minima} px")
    print(f"Segmento salida:    {config.segmento_salida.punto_inicio.tupla} -> {config.segmento_salida.punto_fin.tupla}")
    print("=" * 70)

    dir_salida = Path(args.out_dir)
    dir_imagenes = dir_salida / "salidas"
    dir_imagenes.mkdir(parents=True, exist_ok=True)

    # 3. Inicializar detector y seguidor
    if args.detector == "vehiculos":
        detector = DetectorHibrido(
            DetectorMovimiento(config, factor_escala=args.escala),
            DetectorVehiculos(config, modelo=args.modelo, confianza_minima=args.confianza),
            paso=args.paso,
        )
        print(f"Detector: movimiento como filtro + {args.modelo} como confirmacion (paso {args.paso})")
    else:
        detector = DetectorMovimiento(config, factor_escala=args.escala)
        print("Detector: movimiento (MOG2)")
    seguidor = SeguidorTrayectorias(config)

    # Buffer en memoria de cuadros recientes para capturar la imagen exacta del cruce
    # Mantenemos los últimos 45 cuadros en memoria (~1.8s)
    # Los cuadros se guardan comprimidos: la trayectoria puede cerrarse decenas
    # de cuadros despues del cruce, y mantenerlos sin comprimir consumiria
    # gigabytes de memoria.
    buffer_cuadros: Dict[int, bytes] = {}
    max_buffer = config.seguimiento.tolerancia_oclusion + 150

    todas_clasificaciones: List[ResultadoClasificacion] = []
    salidas_confirmadas: List[Dict] = []
    contador_salidas = 0

    t_inicio = time.time()
    ultimo_cuadro_proc = 0

    try:
        for num_cuadro, cuadro in iterar_cuadros(args.video, hasta_cuadro=args.max_frames):
            ultimo_cuadro_proc = num_cuadro

            # 1. Detectar vehículos dentro del polígono
            dets = detector.detectar(cuadro)
            if args.detector == "vehiculos":
                dets = tuple(d.como_deteccion for d in dets)

            # Archivar el cuadro comprimido solo mientras haya vehículos en
            # escena. La trayectoria se cierra decenas de cuadros después del
            # cruce, así que el buffer debe alcanzar hasta entonces.
            if dets or seguidor.hay_pistas_activas:
                ok, codificado = cv2.imencode(".jpg", cuadro, [cv2.IMWRITE_JPEG_QUALITY, 92])
                if ok:
                    buffer_cuadros[num_cuadro] = codificado.tobytes()
            for viejo_f in [f for f in buffer_cuadros if f < num_cuadro - max_buffer]:
                del buffer_cuadros[viejo_f]

            # 2. Actualizar trayectorias
            cerradas = seguidor.actualizar(num_cuadro, dets)

            # 3. Clasificar trayectorias cerradas en este cuadro
            for tray in cerradas:
                res = clasificar_trayectoria(tray, config, desplazamiento_minimo=args.desplazamiento_min)
                todas_clasificaciones.append(res)

                if res.es_salida and res.cuadro_cruce is not None:
                    contador_salidas += 1
                    # Recuperar cuadro de cruce del buffer si aún existe, o el actual
                    cuadro_ref = _recuperar_cuadro(buffer_cuadros, res.cuadro_cruce, cuadro)
                    img_anotada = dibujar_evidencia_salida(cuadro_ref, config, res, contador_salidas)

                    nombre_img = f"salida_{contador_salidas:02d}_f{res.cuadro_cruce}_id{res.trayectoria_id}.jpg"
                    ruta_img = dir_imagenes / nombre_img
                    cv2.imwrite(str(ruta_img), img_anotada, [cv2.IMWRITE_JPEG_QUALITY, 94])

                    salidas_confirmadas.append({
                        "numero_salida": contador_salidas,
                        "trayectoria_id": res.trayectoria_id,
                        "cuadro_cruce": res.cuadro_cruce,
                        "caja_cruce": list(res.caja_cruce) if res.caja_cruce else None,
                        "centro_cruce": list(res.centro_cruce) if res.centro_cruce else None,
                        "duracion_cuadros": tray.total_observaciones,
                        "desplazamiento_neto": round(tray.desplazamiento_neto, 2),
                        "imagen_evidencia": str(ruta_img.relative_to(dir_salida)),
                    })

                    print(
                        f"  -> [SALIDA #{contador_salidas:02d}] Detectada en cuadro {res.cuadro_cruce} "
                        f"(Trayectoria {res.trayectoria_id}, {tray.total_observaciones} cuadros, "
                        f"desplazamiento {tray.desplazamiento_neto:.1f}px). Guardada: {nombre_img}",
                        flush=True,
                    )

            # Reporte periódico de progreso
            if num_cuadro % 500 == 0 or num_cuadro == total_esperado:
                t_act = time.time() - t_inicio
                fps_act = num_cuadro / t_act if t_act > 0 else 0.0
                pct = (num_cuadro / total_esperado) * 100.0 if total_esperado > 0 else 0.0
                print(
                    f"Progreso: {num_cuadro}/{total_esperado} ({pct:.1f}%) | "
                    f"Velocidad: {fps_act:.1f} fps | Salidas acumuladas: {contador_salidas}",
                    flush=True,
                )

        # 4. Finalizar cualquier pista que continúe abierta
        finales = seguidor.finalizar()
        for tray in finales:
            res = clasificar_trayectoria(tray, config, desplazamiento_minimo=args.desplazamiento_min)
            todas_clasificaciones.append(res)
            if res.es_salida and res.cuadro_cruce is not None:
                contador_salidas += 1
                cuadro_ref = _recuperar_cuadro(buffer_cuadros, res.cuadro_cruce, None)
                img_anotada = dibujar_evidencia_salida(cuadro_ref, config, res, contador_salidas)
                nombre_img = f"salida_{contador_salidas:02d}_f{res.cuadro_cruce}_id{res.trayectoria_id}.jpg"
                ruta_img = dir_imagenes / nombre_img
                cv2.imwrite(str(ruta_img), img_anotada, [cv2.IMWRITE_JPEG_QUALITY, 94])
                salidas_confirmadas.append({
                    "numero_salida": contador_salidas,
                    "trayectoria_id": res.trayectoria_id,
                    "cuadro_cruce": res.cuadro_cruce,
                    "caja_cruce": list(res.caja_cruce) if res.caja_cruce else None,
                    "centro_cruce": list(res.centro_cruce) if res.centro_cruce else None,
                    "duracion_cuadros": tray.total_observaciones,
                    "desplazamiento_neto": round(tray.desplazamiento_neto, 2),
                    "imagen_evidencia": str(ruta_img.relative_to(dir_salida)),
                })

    except KeyboardInterrupt:
        print("\nProcesamiento interrumpido por el usuario.", file=sys.stderr)

    t_total = time.time() - t_inicio
    fps_promedio = ultimo_cuadro_proc / t_total if t_total > 0 else 0.0

    # Consolidar conteos
    conteo_categorias = {
        CATEGORIA_SALIDA: sum(1 for r in todas_clasificaciones if r.categoria == CATEGORIA_SALIDA),
        CATEGORIA_ENTRADA: sum(1 for r in todas_clasificaciones if r.categoria == CATEGORIA_ENTRADA),
        CATEGORIA_PERMANENCIA: sum(1 for r in todas_clasificaciones if r.categoria == CATEGORIA_PERMANENCIA),
        CATEGORIA_RUIDO: sum(1 for r in todas_clasificaciones if r.categoria == CATEGORIA_RUIDO),
    }

    # Guardar reporte JSON
    todas_trayectorias = seguidor.obtener_todas_las_trayectorias()
    reporte = {
        "video": str(meta.ruta.name),
        "total_cuadros_procesados": ultimo_cuadro_proc,
        "tiempo_procesamiento_segundos": round(t_total, 2),
        "fps_promedio": round(fps_promedio, 1),
        "resumen_conteos": conteo_categorias,
        "salidas": salidas_confirmadas,
        "todas_las_trayectorias": [t.como_dict() for t in todas_trayectorias],
    }

    ruta_reporte = dir_salida / "trayectorias.json"
    with ruta_reporte.open("w", encoding="utf-8") as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("RESULTADOS DEL CONTEO")
    print("=" * 70)
    print(f"Cuadros procesados:        {ultimo_cuadro_proc}")
    print(f"Tiempo total:              {t_total:.1f} s ({fps_promedio:.1f} cuadros/s)")
    print(f"Total trayectorias:        {len(todas_clasificaciones)}")
    print(f"  - Salidas confirmadas:   {conteo_categorias[CATEGORIA_SALIDA]}")
    print(f"  - Entradas descartadas:  {conteo_categorias[CATEGORIA_ENTRADA]}")
    print(f"  - Permanencias:          {conteo_categorias[CATEGORIA_PERMANENCIA]}")
    print(f"  - Ruido descartado:      {conteo_categorias[CATEGORIA_RUIDO]}")
    print("-" * 70)
    print(f"Archivo de trayectorias:   {ruta_reporte}")
    print(f"Imágenes de salidas en:    {dir_imagenes}")
    print("=" * 70)


if __name__ == "__main__":
    main()
