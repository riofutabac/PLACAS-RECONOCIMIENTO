"""Procesa una carpeta completa de videos y entrega un único informe en Excel.

Uso:
    python scripts/procesar_lote.py <carpeta_videos> [--out-dir <ruta>]

Recorre cada video, detecta los vehículos que circulan por la vía de lastre,
determina su sentido, lee su placa y acumula todo en un solo listado con la
foto de respaldo de cada registro incrustada en la fila.
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import re
import sys
import time

# Permite ejecutar el script sin instalar el paquete
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from lastre.aceleracion import AceleracionError, describir, elegir_proveedores
from lastre.checkpoint import Checkpoint
from lastre.config import cargar_configuracion, ConfiguracionError
from lastre.deduplicacion import deduplicar_por_placa
from lastre.deteccion import DetectorMovimiento
from lastre.excel import escribir_listado
from lastre.lectura import Lectura, consolidar_lecturas
from lastre.placa import LectorPlacas, PlacaError
from lastre.progreso import Progreso
from lastre.registro import registrar_vehiculos
from lastre.reloj import RelojError, cargar_plantillas, leer_marca, rango_de_nombre
from lastre.seguimiento import SeguidorTrayectorias
from lastre.vehiculos import DetectorHibrido, DetectorVehiculos
from lastre.video import iterar_cuadros, obtener_metadatos_video, VideoLecturaError

EXTENSIONES = (".mp4", ".avi", ".mkv", ".mov")

# Un vehículo demasiado pequeño en pantalla nunca tendrá una placa legible
AREA_MINIMA_PARA_LEER = 40000

# El nombre de archivo de la cámara codifica el inicio de la grabación
PATRON_FECHA = re.compile(r"(\d{14})-(\d{14})")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Procesa una carpeta de videos y genera el listado de placas en Excel.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("carpeta", type=str, help="Carpeta que contiene los videos.")
    parser.add_argument("--out-dir", type=str, default="informe",
                        help="Carpeta donde se escriben el Excel y los recortes.")
    parser.add_argument("--config", type=str, default="config/zona.json",
                        help="Archivo de configuración de la zona.")
    parser.add_argument("--paso", type=int, default=3,
                        help="Analizar 1 de cada N cuadros con movimiento.")
    parser.add_argument("--umbral", type=float, default=0.75,
                        help="Confianza mínima para dar una placa por validada.")
    parser.add_argument("--minimo-lecturas", type=int, default=2,
                        help="Lecturas coincidentes mínimas para validar una placa.")
    parser.add_argument("--observaciones-minimas", type=int, default=10,
                        help="Detecciones mínimas para considerar que hubo un vehículo.")
    parser.add_argument("--solo-salidas", action="store_true",
                        help="Incluir únicamente los vehículos que salen por el lastre.")
    parser.add_argument("--acelerador", choices=("auto", "gpu", "cpu"), default="auto",
                        help="Usar GPU si esta disponible, forzarla, o forzar procesador.")
    parser.add_argument("--reiniciar", action="store_true",
                        help="Ignorar el avance guardado y procesar todos los videos de nuevo.")
    parser.add_argument("--solo-informe", action="store_true",
                        help="No procesar nada: regenerar el Excel con el avance ya guardado.")
    parser.add_argument("--limite", type=int, default=None,
                        help="Procesar solo los primeros N videos (útil para probar).")
    return parser.parse_args()


def listar_videos(carpeta: Path, limite=None):
    """Devuelve los videos de la carpeta en orden alfabético."""
    videos = sorted(v for v in carpeta.iterdir() if v.suffix.lower() in EXTENSIONES)
    return videos[:limite] if limite else videos


def inicio_de_grabacion(nombre: str):
    """Extrae del nombre de archivo la fecha y hora de inicio de la grabación."""
    coincidencia = PATRON_FECHA.search(nombre)
    if not coincidencia:
        return None
    try:
        return datetime.strptime(coincidencia.group(1), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def procesar_video(ruta, config, lector, progreso, args, dir_recortes, proveedores,
                   plantillas_reloj=None):
    """Detecta, sigue y lee las placas de un video. Devuelve sus filas."""
    metadatos = obtener_metadatos_video(ruta)
    fps = metadatos.fps or 25.0

    detector = DetectorHibrido(
        DetectorMovimiento(config, factor_escala=0.25),
        DetectorVehiculos(config, modelo="rf-detr-nano-384-coco", proveedores=proveedores),
        paso=args.paso,
    )
    seguidor = SeguidorTrayectorias(config)

    trayectorias = []
    cuadros_guardados = {}
    ultimo_informe = time.time()
    marca_referencia = None

    for numero, cuadro in iterar_cuadros(ruta):
        # La hora real proviene del reloj impreso por la camara. El nombre del
        # archivo codifica el rango de toda la grabacion, no el inicio de este
        # fragmento, y usarlo desplazaba cada registro varias horas.
        if plantillas_reloj is not None and marca_referencia is None:
            momento = leer_marca(cuadro, plantillas_reloj)
            if momento is not None:
                marca_referencia = (numero, momento)

        detecciones = tuple(d.como_deteccion for d in detector.detectar(cuadro))
        trayectorias.extend(seguidor.actualizar(numero, detecciones))

        if detecciones or seguidor.hay_pistas_activas:
            ok, codificado = cv2.imencode(".jpg", cuadro, [cv2.IMWRITE_JPEG_QUALITY, 92])
            if ok:
                cuadros_guardados[numero] = codificado.tobytes()

        progreso.avanzar(1)
        if time.time() - ultimo_informe >= 5:
            print(progreso.linea(ruta.name), flush=True)
            ultimo_informe = time.time()

    trayectorias.extend(seguidor.finalizar())

    vehiculos = registrar_vehiculos(
        trayectorias,
        observaciones_minimas=args.observaciones_minimas,
        desplazamiento_minimo=150,
    )

    crudos = []

    for indice, vehiculo in enumerate(vehiculos):
        if args.solo_salidas and vehiculo.sentido != "sale":
            continue

        lecturas = []
        for trayectoria in trayectorias:
            if not (vehiculo.cuadro_inicio <= trayectoria.cuadro_inicio
                    and trayectoria.cuadro_fin <= vehiculo.cuadro_fin):
                continue
            for posicion in trayectoria.posiciones:
                if posicion.area < AREA_MINIMA_PARA_LEER:
                    continue
                codificado = cuadros_guardados.get(posicion.cuadro)
                if codificado is None:
                    continue
                import numpy as np
                imagen = cv2.imdecode(np.frombuffer(codificado, np.uint8), cv2.IMREAD_COLOR)
                try:
                    encontradas = lector.leer_vehiculo(imagen, posicion.caja)
                except PlacaError:
                    continue
                for encontrada in encontradas:
                    nombre = f"{ruta.stem}_v{indice + 1:02d}_f{posicion.cuadro}.jpg"
                    x, y, ancho, alto = posicion.caja
                    cv2.imwrite(str(dir_recortes / nombre),
                                imagen[y:y + alto, x:x + ancho],
                                [cv2.IMWRITE_JPEG_QUALITY, 95])
                    lecturas.append(Lectura(
                        cuadro=posicion.cuadro,
                        texto=encontrada.texto,
                        confianza=encontrada.confianza,
                        imagen_recorte=f"recortes/{nombre}",
                        confianza_minima=encontrada.confianza_minima,
                    ))

        resultado = consolidar_lecturas(lecturas, args.umbral, args.minimo_lecturas)
        crudos.append({
            "cuadro": vehiculo.cuadro_representativo,
            "placa": resultado.placa,
            "sentido": vehiculo.sentido,
            "confianza": resultado.confianza,
            "consenso": resultado.dominancia,
            "estado": resultado.estado,
            "imagen": resultado.imagen_recorte,
            "lecturas": resultado.lecturas_coincidentes,
        })

    finales = deduplicar_por_placa(crudos, ventana_cuadros=300)
    por_cuadro = {c["cuadro"]: c for c in crudos}

    filas = []
    for final in finales:
        segundos = final.cuadro / fps
        if marca_referencia is not None:
            cuadro_ref, momento_ref = marca_referencia
            hora = (momento_ref + timedelta(seconds=(final.cuadro - cuadro_ref) / fps)
                    ).strftime("%Y-%m-%d %H:%M:%S")
        else:
            hora = ""
        filas.append({
            "placa": final.placa or "",
            "hora_paso": hora,
            "tiempo_video": f"{int(segundos) // 60:02d}:{int(segundos) % 60:02d}",
            "video": ruta.name,
            "tipo_vehiculo": "",
            "sentido": final.sentido,
            "confianza": round(final.confianza, 3),
            "consenso": round(por_cuadro.get(final.cuadro, {}).get("consenso", 0.0), 3),
            "lecturas": por_cuadro.get(final.cuadro, {}).get("lecturas", 0),
            "estado": final.estado,
            "imagen": final.imagen,
        })

    return filas


def main():
    args = parse_args()

    carpeta = Path(args.carpeta)
    if not carpeta.is_dir():
        print(f"No es una carpeta: '{carpeta}'", file=sys.stderr)
        sys.exit(1)

    try:
        config = cargar_configuracion(args.config)
    except ConfiguracionError as err:
        print(f"Error de configuración: {err}", file=sys.stderr)
        sys.exit(1)

    try:
        proveedores = elegir_proveedores(args.acelerador)
    except AceleracionError as err:
        print(f"Error de aceleracion: {err}", file=sys.stderr)
        sys.exit(1)

    videos = listar_videos(carpeta, args.limite)
    if not videos:
        print(f"No se encontraron videos en '{carpeta}'", file=sys.stderr)
        sys.exit(1)

    dir_salida = Path(args.out_dir)
    dir_recortes = dir_salida / "recortes"
    dir_recortes.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("PROCESAMIENTO DE LOTE")
    print("=" * 78)
    print(f"Carpeta:  {carpeta}")
    print(f"Videos:   {len(videos)}")
    print(f"Computo:  {describir(proveedores)}")
    print("Midiendo duracion total del lote...", flush=True)

    total_cuadros = 0
    for video in videos:
        try:
            total_cuadros += obtener_metadatos_video(video).total_cuadros
        except VideoLecturaError as err:
            print(f"  Aviso: no se pudo leer '{video.name}': {err}", file=sys.stderr)

    avance = Checkpoint(dir_salida)
    if args.reiniciar:
        for nombre in list(avance.videos_hechos):
            avance.olvidar(nombre)

    progreso = Progreso(total_cuadros=total_cuadros, videos_totales=len(videos))
    progreso.avanzar(avance.cuadros_hechos())
    progreso.videos_hechos = sum(1 for v in videos if avance.esta_hecho(v.name))

    print(f"Cuadros totales: {total_cuadros:,}")
    if avance.videos_hechos:
        print(f"Reanudando: {len(avance.videos_hechos)} videos ya procesados")
    print(f"Avance: {avance.ruta}")
    print("=" * 78, flush=True)

    if args.solo_informe:
        todas_las_filas = avance.todas_las_filas()
        _entregar(todas_las_filas, dir_salida, carpeta, videos, total_cuadros, [], progreso)
        return

    try:
        plantillas_reloj = cargar_plantillas()
        print("Reloj: plantillas de digitos cargadas")
    except RelojError as err:
        plantillas_reloj = None
        print(f"Aviso: {err}", file=sys.stderr)
        print("Los registros quedaran sin hora real.", file=sys.stderr)

    try:
        lector = LectorPlacas(proveedores=proveedores)
    except PlacaError as err:
        print(f"Error al iniciar el lector de placas: {err}", file=sys.stderr)
        sys.exit(1)

    fallidos = []

    for video in videos:
        if avance.esta_hecho(video.name):
            print(f"\n--- {video.name} (ya procesado, se omite) ---", flush=True)
            progreso.terminar_video()
            continue

        print(f"\n--- {video.name} ---", flush=True)
        try:
            filas = procesar_video(video, config, lector, progreso, args,
                                   dir_recortes, proveedores, plantillas_reloj)
            cuadros = obtener_metadatos_video(video).total_cuadros
            avance.guardar_video(video.name, filas, cuadros=cuadros)
            print(f"    {len(filas)} vehiculos registrados y guardados", flush=True)
        except (VideoLecturaError, OSError) as err:
            fallidos.append((video.name, str(err)))
            print(f"    ERROR: {err}", file=sys.stderr)
        progreso.terminar_video()
        print(progreso.linea(), flush=True)

    todas_las_filas = avance.todas_las_filas()

    _entregar(todas_las_filas, dir_salida, carpeta, videos, total_cuadros, fallidos, progreso)


def _entregar(todas_las_filas, dir_salida, carpeta, videos, total_cuadros, fallidos, progreso):
    """Ordena los registros, arma el resumen y escribe el Excel final."""
    todas_las_filas = list(todas_las_filas)
    todas_las_filas.sort(key=lambda f: (f["hora_paso"] or "", f["video"]))
    for numero, fila in enumerate(todas_las_filas, start=1):
        fila["registro"] = f"V{numero:04d}"

    validados = sum(1 for f in todas_las_filas if f["estado"] == "validado")
    sin_placa = sum(1 for f in todas_las_filas if f["estado"] == "sin placa identificable")
    salidas = sum(1 for f in todas_las_filas if f["sentido"] == "sale")

    resumen = {
        "Carpeta procesada": str(carpeta),
        "Videos procesados": len(videos) - len(fallidos),
        "Videos con error": len(fallidos),
        "Cuadros analizados": total_cuadros,
        "Vehiculos registrados": len(todas_las_filas),
        "Vehiculos que salen": salidas,
        "Vehiculos que entran": len(todas_las_filas) - salidas,
        "Placas validadas": validados,
        "Pendientes de revision": len(todas_las_filas) - validados - sin_placa,
        "Sin placa identificable": sin_placa,
        "Tiempo total": progreso.linea().split("transcurrido")[1].split("falta")[0].strip(),
        "Generado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    ruta_excel = dir_salida / "placas_lastre.xlsx"
    escribir_listado(todas_las_filas, ruta_excel, dir_salida, resumen=resumen)

    print("\n" + "=" * 78)
    print("INFORME FINAL")
    print("=" * 78)
    for clave, valor in resumen.items():
        print(f"  {clave:26s} {valor}")
    if fallidos:
        print("\n  Videos con error:")
        for nombre, error in fallidos:
            print(f"    - {nombre}: {error}")
    print("-" * 78)
    print(f"  Excel: {ruta_excel}")
    print("=" * 78)


if __name__ == "__main__":
    main()
