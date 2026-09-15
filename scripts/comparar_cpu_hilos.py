"""Comparación experimental de configuraciones de hilos y lectura adelantada en CPU.

Compara configuraciones candidatas repitiendo 3 veces y alternando el orden:
1. default_adelanto (hilos auto/default, lectura adelantada)
2. hilos2_adelanto (hilos=2, lectura adelantada)
3. default_secuencial (hilos auto/default, lectura secuencial directa)

Mide tiempo total, tiempo de inferencia, tiempo de decodificación y memoria máxima (RSS).
Verifica que las detecciones producidas sean equivalentes.
"""

import argparse
import gc
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
from typing import Dict, List
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from lastre.adelanto import cuadros_adelantados
from lastre.config import cargar_configuracion
from lastre.deteccion import DetectorMovimiento
from lastre.medicion import Medidor
from lastre.seguimiento import SeguidorTrayectorias
from lastre.vehiculos import DetectorHibrido, DetectorVehiculos
from lastre.video import iterar_cuadros


def _obtener_memoria_max_mb() -> float:
    """Devuelve el pico de memoria RSS en megabytes."""
    rusage = resource.getrusage(resource.RUSAGE_SELF)
    # En macOS ru_maxrss viene en bytes; en Linux en kilobytes.
    import platform
    if platform.system() == "Darwin":
        return rusage.ru_maxrss / (1024 * 1024)
    return rusage.ru_maxrss / 1024


def cuadros_medidos(origen, medidor):
    """Cronometra la lectura, excluyendo trabajo del consumidor."""
    while True:
        inicio = time.perf_counter()
        try:
            elemento = next(origen)
        except StopIteration:
            return
        medidor.anotar("decodificar video", time.perf_counter() - inicio)
        yield elemento


def ejecutar_corrida(
    video_path: Path,
    config,
    desde_cuadro: int,
    hasta_cuadro: int,
    hilos: int | None,
    usar_adelanto: bool,
    paso: int = 3,
) -> Dict:
    """Ejecuta una pasada sobre el rango de cuadros indicado y devuelve las métricas."""
    gc.collect()
    medidor = Medidor()
    detector_vehiculos = DetectorVehiculos(
        config,
        modelo="rf-detr-nano-384-coco",
        proveedores=["CPUExecutionProvider"],
        hilos=hilos,
    )
    detector = DetectorHibrido(
        DetectorMovimiento(config, factor_escala=0.25),
        detector_vehiculos,
        paso=paso,
        paso_movimiento=1,
        medidor=medidor,
    )
    seguidor = SeguidorTrayectorias(config)
    trayectorias = []
    conteo_detecciones = 0
    firma = hashlib.sha256()

    origen = iterar_cuadros(video_path, desde_cuadro=desde_cuadro, hasta_cuadro=hasta_cuadro)
    if usar_adelanto:
        generador = cuadros_adelantados(
            origen,
            al_leer=lambda s: medidor.anotar("decodificar video", s),
        )
    else:
        generador = cuadros_medidos(origen, medidor)

    t_inicio = time.perf_counter()
    cuadros_vistos = 0
    while True:
        try:
            numero, cuadro = next(generador)
        except StopIteration:
            break
        cuadros_vistos += 1
        originales = detector.detectar(cuadro)
        firma.update(json.dumps([numero, [asdict(d) for d in originales]], sort_keys=True).encode())
        dets = tuple(d.como_deteccion for d in originales)
        if dets:
            conteo_detecciones += len(dets)
        with medidor.fase("seguimiento"):
            trayectorias.extend(seguidor.actualizar(numero, dets))

    tiempo_total = time.perf_counter() - t_inicio
    mem_max = _obtener_memoria_max_mb()

    # Finalizar cualquier remanente del seguidor
    trayectorias.extend(seguidor.finalizar())

    t_inferencia = medidor.etapas.get("modelo de vehiculos").segundos if "modelo de vehiculos" in medidor.etapas else 0.0
    t_movimiento = medidor.etapas.get("filtro de movimiento").segundos if "filtro de movimiento" in medidor.etapas else 0.0
    t_decodificacion = medidor.etapas.get("decodificar video").segundos if "decodificar video" in medidor.etapas else 0.0

    return {
        "cuadros_vistos": cuadros_vistos,
        "tiempo_total_s": round(tiempo_total, 3),
        "tiempo_inferencia_s": round(t_inferencia, 3),
        "tiempo_movimiento_s": round(t_movimiento, 3),
        "tiempo_decodificacion_s": round(t_decodificacion, 3),
        "memoria_max_mb": round(mem_max, 1),
        "detecciones_totales": conteo_detecciones,
        "total_trayectorias": len(trayectorias),
        "firma_detecciones": firma.hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=Path("Camara Placas 2_20260909105651-20260909163038(60).mp4"))
    parser.add_argument("--desde-cuadro", type=int, default=650, help="Cuadro inicial del segmento")
    parser.add_argument("--hasta-cuadro", type=int, default=950, help="Cuadro final del segmento")
    parser.add_argument("--out", type=Path, default=Path("validacion/comparacion_cpu_hilos.json"))
    args = parser.parse_args()

    config = cargar_configuracion("config/zona.json")

    configuraciones = {
        "candidato_actual": {
            "nombre": "hilos=auto (0) + adelanto",
            "hilos": None,
            "usar_adelanto": True,
        },
        "candidato_hilos_2": {
            "nombre": "hilos=2 + adelanto",
            "hilos": 2,
            "usar_adelanto": True,
        },
        "candidato_secuencial": {
            "nombre": "hilos=auto (0) + secuencial (sin adelanto)",
            "hilos": None,
            "usar_adelanto": False,
        },
    }

    # Órdenes alternados para evitar sesgo de calentamiento de caché
    ordenes = [
        ["candidato_actual", "candidato_hilos_2", "candidato_secuencial"],
        ["candidato_hilos_2", "candidato_secuencial", "candidato_actual"],
        ["candidato_secuencial", "candidato_actual", "candidato_hilos_2"],
    ]

    historial_corridas: List[Dict] = []
    resultados_por_candidato: Dict[str, List[Dict]] = {k: [] for k in configuraciones}

    print(f"=== Iniciando comparación de CPU ({args.desde_cuadro} a {args.hasta_cuadro}, 3 repeticiones) ===")
    
    # Warmup inicial corto para que el modelo se cargue en caché
    print("Ejecutando warmup inicial...")
    ejecutar_corrida(args.video, config, desde_cuadro=args.desde_cuadro, hasta_cuadro=args.desde_cuadro + 20, hilos=None, usar_adelanto=True)
    print("Warmup completado.\n")

    for ronda_idx, ronda in enumerate(ordenes, start=1):
        print(f"--- Ronda {ronda_idx}/3 (Orden: {', '.join(ronda)}) ---")
        for clave in ronda:
            cfg = configuraciones[clave]
            print(f"  Ejecutando: {cfg['nombre']} ...", flush=True)
            res = ejecutar_corrida(
                args.video,
                config,
                desde_cuadro=args.desde_cuadro,
                hasta_cuadro=args.hasta_cuadro,
                hilos=cfg["hilos"],
                usar_adelanto=cfg["usar_adelanto"],
            )
            res["candidato"] = clave
            res["ronda"] = ronda_idx
            historial_corridas.append(res)
            resultados_por_candidato[clave].append(res)
            print(f"    -> Total: {res['tiempo_total_s']}s | Infer: {res['tiempo_inferencia_s']}s | Decod: {res['tiempo_decodificacion_s']}s | RSS: {res['memoria_max_mb']}MB | Dets: {res['detecciones_totales']}")

    resumen = {}
    for clave, corridas in resultados_por_candidato.items():
        tiempos = [c["tiempo_total_s"] for c in corridas]
        infers = [c["tiempo_inferencia_s"] for c in corridas]
        mems = [c["memoria_max_mb"] for c in corridas]
        dets = [c["detecciones_totales"] for c in corridas]
        trays = [c["total_trayectorias"] for c in corridas]
        resumen[clave] = {
            "nombre": configuraciones[clave]["nombre"],
            "tiempo_total_medio_s": round(float(np.mean(tiempos)), 3),
            "tiempo_total_std_s": round(float(np.std(tiempos)), 3),
            "tiempo_inferencia_medio_s": round(float(np.mean(infers)), 3),
            "tiempo_inferencia_std_s": round(float(np.std(infers)), 3),
            "memoria_max_mb": max(mems),
            "detecciones_promedio": float(np.mean(dets)),
            "trayectorias_promedio": float(np.mean(trays)),
            "corridas": corridas,
        }

    salida_final = {
        "advertencias": ["RSS es el máximo acumulado del proceso, no un pico independiente por variante", "El segmento inicia MOG2 sin el historial anterior; no certifica conteo ni OCR del video completo"],
        "detecciones_identicas": len({r["firma_detecciones"] for r in historial_corridas}) == 1,
        "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
        "desde_cuadro": args.desde_cuadro,
        "hasta_cuadro": args.hasta_cuadro,
        "cuadros_evaluados": args.hasta_cuadro - args.desde_cuadro + 1,
        "resumen": resumen,
        "historial": historial_corridas,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(salida_final, f, indent=2)

    print("\n=== Resumen Final ===")
    for clave, r in resumen.items():
        print(f"{r['nombre']}:")
        print(f"  Tiempo total: {r['tiempo_total_medio_s']} s ± {r['tiempo_total_std_s']} s")
        print(f"  Inferencia:   {r['tiempo_inferencia_medio_s']} s ± {r['tiempo_inferencia_std_s']} s")
        print(f"  Memoria max:  {r['memoria_max_mb']} MB")
        print(f"  Detecciones:  {r['detecciones_promedio']}")


if __name__ == "__main__":
    main()
