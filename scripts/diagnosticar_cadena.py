"""Diagnóstico detallado de la cadena de detección y lectura para YOLO26 vs RF-DETR.

Rastrea la cadena completa para los casos críticos:
1. Video 61, vehículo MZS872 (fotogramas 5070 a 5140)
2. Video 61, autobús en vía rápida (fotogramas 2030 a 2100)
3. Video 60, casos de variación de placa (Aveo, moto, camioneta)

Para cada caso analiza:
- Detección: cajas crudas, clases, confianza
- Filtro de zona / ROI: si el centro entra al polígono y pasa umbral
- Seguimiento: asignación de pistas, número de observaciones
- Recorte: tamaño de caja vehicular, margen
- ALPR / OCR: detección de placa y texto leído
"""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from lastre.config import cargar_configuracion
from lastre.vehiculos import DetectorVehiculos
from lastre.placa import LectorPlacas, PlacaError, recortar_vehiculo
from lastre.video import iterar_cuadros
from lastre.seguimiento import SeguidorTrayectorias
from lastre.registro import registrar_vehiculos
from lastre.evidencia import CALIDAD_JPEG


def recorte_para_ocr(frame, caja, margen=.10):
    """Reproduce recorte y compresión/decodificación del almacén de producción."""
    recorte = recortar_vehiculo(frame, caja, margen=margen)
    ok, datos = cv2.imencode('.jpg', recorte, [cv2.IMWRITE_JPEG_QUALITY, CALIDAD_JPEG])
    if not ok:
        raise RuntimeError('No se pudo codificar el recorte de diagnóstico')
    return cv2.imdecode(datos, cv2.IMREAD_COLOR)


REPO_DIR = Path(__file__).resolve().parent.parent
CONFIG_ZONA = REPO_DIR / "config" / "zona.json"
VIDEOS_DIR = REPO_DIR / "conjunto_evaluacion"
V60_PATH = VIDEOS_DIR / "Camara Placas 2_20260909105651-20260909163038(60).mp4"
V61_PATH = VIDEOS_DIR / "Camara Placas 2_20260909105651-20260909163038(61).mp4"


def diagnosticar_rango(
    ruta_video: Path,
    rango_cuadros: range,
    config,
    modelos=("rf-detr-nano-384-coco", "yolo26n"),
):
    print(f"\n=======================================================")
    print(f"DIAGNÓSTICO: {ruta_video.name}")
    print(f"Rango de cuadros: {rango_cuadros.start} a {rango_cuadros.stop - 1}")
    print(f"=======================================================")

    # Cargar cuadros específicos en memoria
    cuadros_memoria = {}
    for num, frame in iterar_cuadros(ruta_video):
        if num in rango_cuadros:
            cuadros_memoria[num] = frame
        elif num >= rango_cuadros.stop:
            break

    print(f"Cuadros cargados: {len(cuadros_memoria)}")

    lector = LectorPlacas(proveedores=["CPUExecutionProvider"], hilos=2)

    resultados = {}
    for mod in modelos:
        print(f"\n--- Analizando modelo: {mod} ---")
        detector = DetectorVehiculos(
            config,
            modelo=mod,
            proveedores=["CPUExecutionProvider"],
            hilos=2,
        )
        seguidor = SeguidorTrayectorias(config)
        trayectorias_cerradas = []

        total_detecciones = 0
        detecciones_por_cuadro = {}

        for num in sorted(cuadros_memoria.keys()):
            frame = cuadros_memoria[num]
            # Inferencia vehicular completa
            det_vehiculos = detector.detectar(frame)
            total_detecciones += len(det_vehiculos)

            det_obj = tuple(d.como_deteccion for d in det_vehiculos)
            cerradas = seguidor.actualizar(num, det_obj)
            trayectorias_cerradas.extend(cerradas)

            if det_vehiculos:
                info_dets = []
                for d in det_vehiculos:
                    x, y, w, h = d.caja
                    x1, y1, x2, y2 = x, y, x + w, y + h
                    recorte = recorte_para_ocr(frame, d.caja)

                    # OCR directo sobre recorte
                    ocr_res = []
                    if recorte.size > 0:
                        try:
                            ocr_res = lector.leer(recorte)
                        except PlacaError as error:
                            raise RuntimeError(f"OCR falló en cuadro {num}, modelo {mod}") from error

                    margenes = {"0.10": [(p.texto, round(p.confianza, 3)) for p in ocr_res]}
                    if rango_cuadros.start >= 5000:
                        for margen in (.15, .20):
                            lecturas = lector.leer(recorte_para_ocr(frame, d.caja, margen=margen))
                            margenes[f"{margen:.2f}"] = [(p.texto, round(p.confianza, 3)) for p in lecturas]
                    info_dets.append({
                        "clase": d.clase,
                        "conf": round(d.confianza, 3),
                        "caja": (x1, y1, w, h),
                        "area": d.area,
                        "centro": d.centro,
                        "ocr": [(p.texto, round(p.confianza, 3)) for p in ocr_res],
                        "ocr_por_margen": margenes,
                    })
                detecciones_por_cuadro[num] = info_dets

        trayectorias_cerradas.extend(seguidor.finalizar())
        vehiculos = registrar_vehiculos(trayectorias_cerradas, observaciones_minimas=10, desplazamiento_minimo=150)

        print(f"Total detecciones en zona: {total_detecciones}")
        print(f"Cuadros con detecciones: {len(detecciones_por_cuadro)}")
        print(f"Trayectorias totales: {len(trayectorias_cerradas)}")
        for t in trayectorias_cerradas:
            print(f"  Trayectoria {t.id}: cuadros {t.cuadro_inicio}-{t.cuadro_fin}, observaciones: {t.total_observaciones}")
        print(f"Vehículos registrados (>=10 obs): {len(vehiculos)}")
        for v in vehiculos:
            print(f"  Vehículo id={v.trayectoria_id}: sentido={v.sentido}, obs={v.observaciones}, dx={v.desplazamiento_x}")

        # Mostrar muestra de detecciones y OCR
        for num in sorted(detecciones_por_cuadro.keys())[::3]:
            print(f"  f{num}: {detecciones_por_cuadro[num]}")
        resultados[mod] = {"detecciones": detecciones_por_cuadro,
                           "trayectorias": [{"id": t.id, "observaciones": t.total_observaciones}
                                            for t in trayectorias_cerradas],
                           "vehiculos_segmento": len(vehiculos)}
    salida = REPO_DIR / "validacion/experimento_yolo26" / f"diagnostico_{rango_cuadros.start}_{rango_cuadros.stop}.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps({"alcance": "Modelo en todos los cuadros; no reproduce MOG2 ni paso=3 del video completo",
                                 "calidad_jpeg": CALIDAD_JPEG,
                                 "resultados": resultados}, indent=2), encoding="utf-8")


def main():
    config = cargar_configuracion(CONFIG_ZONA)

    # 1. Video 61: MZS872 (alrededor de cuadro 5100-5140)
    print("\n" + "#" * 70)
    print("# CASO 1: MZS872 en Video 61 (Fotogramas 5080 a 5140)")
    print("#" * 70)
    diagnosticar_rango(V61_PATH, range(5080, 5140), config)

    # 2. Video 61: Autobús en vía rápida (alrededor de cuadro 2030-2100)
    print("\n" + "#" * 70)
    print("# CASO 2: Autobús en vía rápida en Video 61 (Fotogramas 2030 a 2090)")
    print("#" * 70)
    diagnosticar_rango(V61_PATH, range(2030, 2090), config)


if __name__ == "__main__":
    main()
