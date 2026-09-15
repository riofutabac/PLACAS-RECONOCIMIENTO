"""Evaluación comparativa de paso=3 frente a paso=4.

Compara:
- Tiempo total y tiempo de inferencia
- Número de inferencias ejecutadas
- Conteo de vehículos y preservación de eventos individuales
- Oportunidades OCR (recortes con área >= 40000) por vehículo
- Posible fragmentación o duplicación de pistas
- Placa leída, confianza y estado de validación

Salidas y checkpoints completamente separados:
- validacion/evaluacion_paso3/
- validacion/evaluacion_paso4/
"""

import argparse
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lastre.config import cargar_configuracion
from lastre.medicion import Medidor
from lastre.placa import LectorPlacas
from lastre.vehiculos import DetectorVehiculos
import scripts.procesar_lote as lote


def evaluar_variante(
    video_path: Path,
    paso: int,
    dir_salida: Path,
    config,
    lector,
    detector_vehiculos,
    args_base,
    hasta_cuadro: int = None,
) -> Dict:
    """Ejecuta una variante (paso=3 o paso=4) sobre el video especificado."""
    dir_salida.mkdir(parents=True, exist_ok=True)
    dir_recortes = dir_salida / "recortes"
    dir_recortes.mkdir(parents=True, exist_ok=True)

    args = NS(
        paso=paso,
        paso_movimiento=args_base.paso_movimiento,
        escala_movimiento=args_base.escala_movimiento,
        umbral=args_base.umbral,
        minimo_lecturas=args_base.minimo_lecturas,
        observaciones_minimas=args_base.observaciones_minimas,
        solo_salidas=False,
        hilos=args_base.hilos,
    )

    progreso = NS(avanzar=lambda *a: None, linea=lambda *a: "")
    medidor = Medidor()

    t_inicio = time.perf_counter()
    filas = lote.procesar_video(
        video_path,
        config,
        lector,
        progreso,
        args,
        dir_recortes,
        ["CPUExecutionProvider"],
        medidor=medidor,
        detector_vehiculos=detector_vehiculos,
    )
    tiempo_total = time.perf_counter() - t_inicio

    t_inferencia = medidor.etapas.get("modelo de vehiculos").segundos if "modelo de vehiculos" in medidor.etapas else 0.0
    n_inferencias = medidor.etapas.get("modelo de vehiculos").llamadas if "modelo de vehiculos" in medidor.etapas else 0
    t_movimiento = medidor.etapas.get("filtro de movimiento").segundos if "filtro de movimiento" in medidor.etapas else 0.0
    t_decodificacion = medidor.etapas.get("decodificar video").segundos if "decodificar video" in medidor.etapas else 0.0

    return {
        "paso": paso,
        "video": video_path.name,
        "tiempo_total_s": round(tiempo_total, 3),
        "tiempo_inferencia_s": round(t_inferencia, 3),
        "inferencias_rf_detr": n_inferencias,
        "tiempo_movimiento_s": round(t_movimiento, 3),
        "tiempo_decodificacion_s": round(t_decodificacion, 3),
        "total_filas": len(filas),
        "filas": filas,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=Path("Camara Placas 2_20260909105651-20260909163038(60).mp4"))
    parser.add_argument("--out", type=Path, default=Path("validacion/comparacion_paso3_vs_paso4.json"))
    args_cli = parser.parse_args()

    config = cargar_configuracion("config/zona.json")
    detector = DetectorVehiculos(config, modelo="rf-detr-nano-384-coco", proveedores=["CPUExecutionProvider"])
    lector = LectorPlacas(proveedores=["CPUExecutionProvider"])

    args_base = NS(
        paso_movimiento=1,
        escala_movimiento=0.25,
        umbral=0.75,
        minimo_lecturas=2,
        observaciones_minimas=10,
        hilos=None,
    )

    print(f"=== Evaluando paso=3 vs paso=4 en {args_cli.video.name} ===")

    print("\n--- Ejecutando paso=3 (Base) ---")
    res_paso3 = evaluar_variante(
        args_cli.video,
        paso=3,
        dir_salida=Path("validacion/evaluacion_paso3"),
        config=config,
        lector=lector,
        detector_vehiculos=detector,
        args_base=args_base,
    )
    print(f"Paso=3 terminado en {res_paso3['tiempo_total_s']}s | Inferencias: {res_paso3['inferencias_rf_detr']} ({res_paso3['tiempo_inferencia_s']}s) | Vehículos: {res_paso3['total_filas']}")

    print("\n--- Ejecutando paso=4 (Candidato) ---")
    res_paso4 = evaluar_variante(
        args_cli.video,
        paso=4,
        dir_salida=Path("validacion/evaluacion_paso4"),
        config=config,
        lector=lector,
        detector_vehiculos=detector,
        args_base=args_base,
    )
    print(f"Paso=4 terminado en {res_paso4['tiempo_total_s']}s | Inferencias: {res_paso4['inferencias_rf_detr']} ({res_paso4['tiempo_inferencia_s']}s) | Vehículos: {res_paso4['total_filas']}")

    # Comparación detallada de vehículos
    comparacion = {
        "video": args_cli.video.name,
        "metricas": {
            "paso3": {
                "tiempo_total_s": res_paso3["tiempo_total_s"],
                "tiempo_inferencia_s": res_paso3["tiempo_inferencia_s"],
                "inferencias": res_paso3["inferencias_rf_detr"],
                "vehiculos_registrados": res_paso3["total_filas"],
            },
            "paso4": {
                "tiempo_total_s": res_paso4["tiempo_total_s"],
                "tiempo_inferencia_s": res_paso4["tiempo_inferencia_s"],
                "inferencias": res_paso4["inferencias_rf_detr"],
                "vehiculos_registrados": res_paso4["total_filas"],
            },
            "diferencia": {
                "ahorro_tiempo_total_s": round(res_paso3["tiempo_total_s"] - res_paso4["tiempo_total_s"], 3),
                "ahorro_tiempo_total_pct": round((res_paso3["tiempo_total_s"] - res_paso4["tiempo_total_s"]) / res_paso3["tiempo_total_s"] * 100, 2),
                "reduccion_inferencias": res_paso3["inferencias_rf_detr"] - res_paso4["inferencias_rf_detr"],
                "reduccion_inferencias_pct": round((res_paso3["inferencias_rf_detr"] - res_paso4["inferencias_rf_detr"]) / res_paso3["inferencias_rf_detr"] * 100, 2),
            },
        },
        "filas_paso3": res_paso3["filas"],
        "filas_paso4": res_paso4["filas"],
    }

    args_cli.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args_cli.out, "w", encoding="utf-8") as f:
        json.dump(comparacion, f, indent=2)

    print("\n=== Resumen Comparativo ===")
    print(f"Tiempo Total:     Paso 3 = {res_paso3['tiempo_total_s']}s vs Paso 4 = {res_paso4['tiempo_total_s']}s (Ahorro: {comparacion['metricas']['diferencia']['ahorro_tiempo_total_pct']}%)")
    print(f"Inferencias:      Paso 3 = {res_paso3['inferencias_rf_detr']} vs Paso 4 = {res_paso4['inferencias_rf_detr']} (Reducción: {comparacion['metricas']['diferencia']['reduccion_inferencias_pct']}%)")
    print(f"Vehículos Paso 3: {res_paso3['total_filas']} registros")
    for f in res_paso3["filas"]:
        print(f"  ID {f.get('trayectoria_id')}: {f.get('placa')} ({f.get('tiempo_video')}) - {f.get('estado')}, conf={f.get('confianza')}, lecturas={f.get('lecturas')}")
    print(f"Vehículos Paso 4: {res_paso4['total_filas']} registros")
    for f in res_paso4["filas"]:
        print(f"  ID {f.get('trayectoria_id')}: {f.get('placa')} ({f.get('tiempo_video')}) - {f.get('estado')}, conf={f.get('confianza')}, lecturas={f.get('lecturas')}")


if __name__ == "__main__":
    main()
