"""Prueba controlada de distribución de hilos para YOLO26n en CPU.

Evalúa combinaciones de hilos sobre 60 cuadros. Incluye la decodificación
previa hasta el segmento; no certifica rendimiento completo ni temperatura.
"""

from pathlib import Path
import time
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from lastre.config import cargar_configuracion
from lastre.vehiculos import DetectorHibrido, DetectorVehiculos
from lastre.deteccion import DetectorMovimiento
from lastre.medicion import Medidor
from lastre.video import iterar_cuadros
from lastre.adelanto import cuadros_adelantados


REPO_DIR = Path(__file__).resolve().parent.parent
CONFIG_ZONA = REPO_DIR / "config" / "zona.json"
VIDEO_PATH = REPO_DIR / "conjunto_evaluacion" / "Camara Placas 2_20260909105651-20260909163038(60).mp4"
RANGO_CUADROS = range(700, 760)


def probar_configuracion(hilos_onnx, hilos_opencv):
    anteriores = cv2.getNumThreads()
    try:
        return _probar_configuracion(hilos_onnx, hilos_opencv)
    finally:
        cv2.setNumThreads(anteriores)


def _probar_configuracion(hilos_onnx, hilos_opencv):
    config = cargar_configuracion(CONFIG_ZONA)

    # Configurar hilos de OpenCV
    if hilos_opencv is not None:
        cv2.setNumThreads(hilos_opencv)

    medidor = Medidor()
    detector_vehiculos = DetectorVehiculos(
        config,
        modelo="yolo26n",
        proveedores=["CPUExecutionProvider"],
        hilos=hilos_onnx,
    )
    detector = DetectorHibrido(
        DetectorMovimiento(config, factor_escala=0.25),
        detector_vehiculos,
        paso=3,
        paso_movimiento=1,
        medidor=medidor,
    )

    t0 = time.perf_counter()
    cuadros_vistos = 0
    origen = iterar_cuadros(VIDEO_PATH, desde_cuadro=RANGO_CUADROS.start,
                           hasta_cuadro=RANGO_CUADROS.stop - 1)
    for num, cuadro in cuadros_adelantados(origen):
        detector.detectar(cuadro)
        cuadros_vistos += 1
    t1 = time.perf_counter()

    duracion = t1 - t0
    tiempos = {k: e.segundos for k, e in medidor.etapas.items()}
    return {
        "hilos_onnx": str(hilos_onnx),
        "hilos_opencv": str(hilos_opencv),
        "opencv_efectivos": cv2.getNumThreads(),
        "cuadros_segmento": cuadros_vistos,
        "inferencias": detector.estadisticas["cuadros_confirmados"],
        "duracion_total": round(duracion, 3),
        "detector_vehiculos": round(tiempos.get("modelo de vehiculos", 0.0), 3),
        "movimiento": round(tiempos.get("filtro de movimiento", 0.0), 3),
    }


def main():
    print(f"Probando {RANGO_CUADROS.start} a {RANGO_CUADROS.stop} de Video 60...")
    configs = [
        (None, None),   # Predeterminado del sistema
        (2, 2),         # 2 hilos ONNX, 2 hilos OpenCV
        (2, 1),         # 2 hilos ONNX, 1 hilo OpenCV
        (3, 1),         # 3 hilos ONNX, 1 hilo OpenCV
    ]

    resultados = []
    for ronda in range(3):
        orden = configs if ronda % 2 == 0 else list(reversed(configs))
        for h_onnx, h_cv in orden:
            res = probar_configuracion(h_onnx, h_cv)
            res["ronda"] = ronda + 1
            print(res, flush=True)
            resultados.append(res)
    salida = REPO_DIR / "validacion/experimento_yolo26/hilos_corregidos.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(resultados, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
