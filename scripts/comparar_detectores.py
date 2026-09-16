"""Comparación controlada de detectores de vehículos (RF-DETR Nano vs YOLO26).

Ejecuta los videos 60 y 61 en procesos aislados, midiendo:
- Tiempo total desde carga hasta Excel
- Desglose por etapas (decodificación, movimiento, inferencia de vehículos, ALPR, OCR)
- Memoria máxima (pico RSS con /usr/bin/time -l en macOS)
- Auditoría evento por evento contra la referencia anotada (referencia_base.json)

Genera resultados_comparacion.json y tabla comparativa para respaldar la decisión.
"""

import argparse
from dataclasses import asdict, dataclass, field
import datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional


REPO_DIR = Path(__file__).resolve().parent.parent
PYTHON_EXE = REPO_DIR / ".venv312" / "bin" / "python"
VIDEOS_DIR = REPO_DIR / "conjunto_evaluacion"
CONFIG_ZONA = REPO_DIR / "config" / "zona.json"
BASE_OUT_DIR = REPO_DIR / "validacion" / "experimento_yolo26"
REF_BASE_PATH = REPO_DIR / "validacion" / "referencia_base.json"


@dataclass
class ResultadoCorrida:
    ronda: str
    modelo: str
    directorio_salida: str
    tiempo_total_segundos: float
    tiempo_real_segundos: float
    tiempo_usuario_segundos: float
    tiempo_sistema_segundos: float
    pico_rss_mb: float
    pico_rss_bytes: int
    codigo_salida: int
    cuadros_analizados: int
    vehiculos_totales: int
    excel_existe: bool
    excel_tamano_bytes: int
    desglose_etapas: Dict[str, Dict[str, float]] = field(default_factory=dict)
    vehiculos_por_video: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    manifiesto_checkpoint: Dict[str, Any] = field(default_factory=dict)
    errores: List[str] = field(default_factory=list)


def parsear_tiempo_l(salida_stderr: str) -> Dict[str, Any]:
    """Parsea el reporte de /usr/bin/time -l en macOS."""
    metricas = {
        "real": 0.0,
        "user": 0.0,
        "sys": 0.0,
        "max_rss_bytes": 0,
        "max_rss_mb": 0.0,
    }
    m_tiempos = re.search(r"([\d\.]+)\s+real\s+([\d\.]+)\s+user\s+([\d\.]+)\s+sys", salida_stderr)
    if m_tiempos:
        metricas["real"] = float(m_tiempos.group(1))
        metricas["user"] = float(m_tiempos.group(2))
        metricas["sys"] = float(m_tiempos.group(3))

    m_rss = re.search(r"(\d+)\s+maximum resident set size", salida_stderr)
    if m_rss:
        rss_bytes = int(m_rss.group(1))
        metricas["max_rss_bytes"] = rss_bytes
        metricas["max_rss_mb"] = round(rss_bytes / (1024 * 1024), 2)

    return metricas


def parsear_desglose_medidor(salida_stdout: str) -> Dict[str, Dict[str, float]]:
    """Extrae las etapas y tiempos del reporte del Medidor en stdout."""
    etapas = {}
    lineas = salida_stdout.splitlines()
    dentro_informe = False
    for linea in lineas:
        if "etapa" in linea.lower() and "llamadas" in linea.lower():
            dentro_informe = True
            continue
        if dentro_informe:
            if linea.strip().startswith("---"):
                continue
            if "TOTAL" in linea:
                m_tot = re.search(r"TOTAL\s+([\d\.]+)", linea)
                if m_tot:
                    etapas["TOTAL"] = {"segundos": float(m_tot.group(1))}
                break
            m = re.search(r"^\s+([a-zA-ZáéíóúÁÉÍÓÚ\s]+?)\s+([\d\.]+)\s+([\d\.]+)%\s+(\d+)\s+([\d\.]+)", linea)
            if m:
                nombre = m.group(1).strip()
                etapas[nombre] = {
                    "segundos": float(m.group(2)),
                    "porcentaje": float(m.group(3)),
                    "llamadas": int(m.group(4)),
                    "ms_llamada": float(m.group(5)),
                }
            else:
                m_sin = re.search(r"^\s+([a-zA-ZáéíóúÁÉÍÓÚ\s]+?)\s+([\d\.]+)\s+([\d\.]+)%", linea)
                if m_sin:
                    nombre = m_sin.group(1).strip()
                    etapas[nombre] = {
                        "segundos": float(m_sin.group(2)),
                        "porcentaje": float(m_sin.group(3)),
                    }
    return etapas


def ejecutar_corrida(
    ronda: str,
    modelo: str,
    out_dir: Path,
) -> ResultadoCorrida:
    """Ejecuta una corrida de lote completa para un modelo detector específico."""
    print("\n" + "=" * 80)
    print(f"INICIANDO CORRIDA: Ronda {ronda} | Modelo: {modelo}")
    print(f"Carpeta de salida:     {out_dir}")
    print(f"Inicio:                {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80, flush=True)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    comando = [
        "/usr/bin/time",
        "-l",
        str(PYTHON_EXE),
        "-u",
        "scripts/procesar_lote.py",
        str(VIDEOS_DIR),
        "--out-dir",
        str(out_dir),
        "--config",
        str(CONFIG_ZONA),
        "--modelo-vehiculos",
        modelo,
        "--paso",
        "3",
        "--paso-movimiento",
        "1",
        "--escala-movimiento",
        "0.25",
        "--umbral",
        "0.75",
        "--minimo-lecturas",
        "2",
        "--observaciones-minimas",
        "10",
        "--acelerador",
        "cpu",
    ]

    t0 = time.perf_counter()
    proceso = subprocess.Popen(
        comando,
        cwd=REPO_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    stdout_acumulado = []
    assert proceso.stdout is not None
    for linea in iter(proceso.stdout.readline, ""):
        stdout_acumulado.append(linea)
        linea_str = linea.strip()
        if (
            "---" in linea_str
            or "%" in linea_str
            or "inferencias de vehículos" in linea_str
            or "TOTAL" in linea_str
            or "Excel:" in linea_str
        ):
            print(f"[{modelo}] {linea_str}", flush=True)

    proceso.stdout.close()
    stderr_raw = proceso.stderr.read() if proceso.stderr else ""
    proceso.wait()
    t1 = time.perf_counter()

    duracion_total = t1 - t0
    stdout_texto = "".join(stdout_acumulado)
    stderr_texto = stderr_raw

    metricas_tiempo = parsear_tiempo_l(stderr_texto)
    desglose_etapas = parsear_desglose_medidor(stdout_texto)

    ruta_avance = out_dir / "avance.json"
    ruta_excel = out_dir / "placas_lastre.xlsx"
    dir_recortes = out_dir / "recortes"

    vehiculos_por_video = {}
    manifiesto_checkpoint = {}
    cuadros_totales = 0
    vehiculos_totales = 0
    errores = []

    if ruta_avance.is_file():
        try:
            with open(ruta_avance, encoding="utf-8") as f:
                datos_avance = json.load(f)
            manifiesto_checkpoint = datos_avance.get("manifiesto", {})
            if not manifiesto_checkpoint:
                errores.append(
                    f"El checkpoint en {ruta_avance} no tiene manifiesto de identidad."
                )
            elif manifiesto_checkpoint.get("modelo_vehiculos") != modelo:
                errores.append(
                    f"Conflicto en checkpoint: usa modelo '{manifiesto_checkpoint.get('modelo_vehiculos')}' "
                    f"pero la corrida solicitó '{modelo}'."
                )
            videos_dict = datos_avance.get("videos", {})
            for v_nombre, v_data in videos_dict.items():
                filas = v_data.get("filas", [])
                cuadros = v_data.get("cuadros", 0)
                cuadros_totales += cuadros
                vehiculos_totales += len(filas)
                vehiculos_por_video[v_nombre] = filas
        except Exception as e:
            errores.append(f"Error al leer avance.json: {e}")
    else:
        errores.append("avance.json no fue generado")

    excel_existe = ruta_excel.is_file()
    excel_tamano = ruta_excel.stat().st_size if excel_existe else 0
    if not excel_existe:
        errores.append("placas_lastre.xlsx no fue generado")

    if proceso.returncode != 0:
        errores.append(f"Proceso finalizó con código {proceso.returncode}")

    res = ResultadoCorrida(
        ronda=ronda,
        modelo=modelo,
        directorio_salida=str(out_dir.relative_to(REPO_DIR)),
        tiempo_total_segundos=round(duracion_total, 3),
        tiempo_real_segundos=metricas_tiempo["real"],
        tiempo_usuario_segundos=metricas_tiempo["user"],
        tiempo_sistema_segundos=metricas_tiempo["sys"],
        pico_rss_mb=metricas_tiempo["max_rss_mb"],
        pico_rss_bytes=metricas_tiempo["max_rss_bytes"],
        codigo_salida=proceso.returncode,
        cuadros_analizados=cuadros_totales,
        vehiculos_totales=vehiculos_totales,
        excel_existe=excel_existe,
        excel_tamano_bytes=excel_tamano,
        desglose_etapas=desglose_etapas,
        vehiculos_por_video=vehiculos_por_video,
        manifiesto_checkpoint=manifiesto_checkpoint,
        errores=errores,
    )

    with open(out_dir / "metricas_corrida.json", "w", encoding="utf-8") as f:
        json.dump(asdict(res), f, ensure_ascii=False, indent=2)

    return res


def auditar_vehiculos_contra_referencia(
    resultados: List[ResultadoCorrida],
    ref_base: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Audita individualmente cada vehículo de la referencia anotada con emparejamiento 1 a 1."""
    auditoria = {}
    detecciones_adicionales = {}

    for nombre_video, datos_video in ref_base.get("videos", {}).items():
        vehiculos_ref = datos_video.get("vehiculos", [])
        auditoria[nombre_video] = []
        detecciones_adicionales[nombre_video] = {}

        asignadas_por_corrida: Dict[str, set] = {
            f"ronda_{c.ronda}_{c.modelo}": set() for c in resultados
        }

        for ref_v in vehiculos_ref:
            idx = ref_v["indice"]
            hora_esperada = ref_v.get("hora_reloj")
            sentido_esperado = ref_v.get("sentido")
            placa_esperada = ref_v.get("placa_leida")
            placa_real = ref_v.get("placa_real_legible")
            estado_esperado = ref_v.get("estado")

            estado_por_corrida = {}

            for corrida in resultados:
                id_corrida = f"ronda_{corrida.ronda}_{corrida.modelo}"
                filas = corrida.vehiculos_por_video.get(nombre_video, [])
                asignadas = asignadas_por_corrida[id_corrida]

                hallado = None
                hallado_idx = None
                for i, fila in enumerate(filas):
                    if i in asignadas:
                        continue
                    coincide_sentido = fila.get("sentido") == sentido_esperado
                    hora_fila = fila.get("hora_paso", "")
                    coincide_hora = False
                    if hora_esperada and hora_fila:
                        if hora_esperada in hora_fila:
                            coincide_hora = True
                        else:
                            try:
                                t_esp = datetime.datetime.strptime(hora_esperada, "%H:%M:%S")
                                t_fila = datetime.datetime.strptime(hora_fila[-8:], "%H:%M:%S")
                                if abs((t_esp - t_fila).total_seconds()) <= 20:
                                    coincide_hora = True
                            except Exception:
                                pass

                    if coincide_sentido and coincide_hora:
                        hallado = fila
                        hallado_idx = i
                        break

                if hallado is None:
                    # Intento secundario por placa exacta si la hora tuviera leve desfase
                    for i, fila in enumerate(filas):
                        if i in asignadas:
                            continue
                        if fila.get("placa") and fila.get("placa") == placa_esperada:
                            hallado = fila
                            hallado_idx = i
                            break

                if hallado is not None and hallado_idx is not None:
                    asignadas.add(hallado_idx)
                    img_rel = hallado.get("imagen", "")
                    img_path = REPO_DIR / corrida.directorio_salida / img_rel
                    evidencia_valida = img_path.is_file() and img_path.stat().st_size > 0

                    coincide_resultado = (
                        hallado.get("sentido") == sentido_esperado
                        and hallado.get("placa") == placa_esperada
                    )

                    estado_por_corrida[id_corrida] = {
                        "hallado": True,
                        "resultado_coincide": coincide_resultado,
                        "hora_paso": hallado.get("hora_paso"),
                        "sentido": hallado.get("sentido"),
                        "placa_leida": hallado.get("placa"),
                        "confianza": hallado.get("confianza"),
                        "consenso": hallado.get("consenso"),
                        "estado": hallado.get("estado"),
                        "lecturas": hallado.get("lecturas"),
                        "imagen": img_rel,
                        "evidencia_valida": evidencia_valida,
                    }
                else:
                    estado_por_corrida[id_corrida] = {
                        "hallado": False,
                        "resultado_coincide": False,
                    }

            auditoria[nombre_video].append({
                "indice": idx,
                "hora_reloj_esperada": hora_esperada,
                "sentido_esperado": sentido_esperado,
                "placa_esperada": placa_esperada,
                "placa_real": placa_real,
                "estado_esperado": estado_esperado,
                "corridas": estado_por_corrida,
            })

        # Recopilar detecciones no emparejadas (falsos positivos)
        for corrida in resultados:
            id_corrida = f"ronda_{corrida.ronda}_{corrida.modelo}"
            filas = corrida.vehiculos_por_video.get(nombre_video, [])
            asignadas = asignadas_por_corrida[id_corrida]
            sobrantes = [
                {
                    "fila_indice": i,
                    "hora_paso": f.get("hora_paso"),
                    "sentido": f.get("sentido"),
                    "placa": f.get("placa"),
                    "confianza": f.get("confianza"),
                    "imagen": f.get("imagen"),
                }
                for i, f in enumerate(filas)
                if i not in asignadas
            ]
            detecciones_adicionales[nombre_video][id_corrida] = sobrantes

    return auditoria, detecciones_adicionales


def main():
    parser = argparse.ArgumentParser(description="Comparador controlable de detectores de vehículos.")
    parser.add_argument("--rondas", type=int, default=1, help="Número de rondas de comparación.")
    parser.add_argument("--modelos", nargs="+", default=["rf-detr-nano-384-coco", "yolo26n"],
                        help="Lista de modelos a comparar.")
    parser.add_argument("--out-dir", type=str, default=str(BASE_OUT_DIR),
                        help="Directorio base de salida.")
    args = parser.parse_args()

    out_base = Path(args.out_dir)
    out_base.mkdir(parents=True, exist_ok=True)

    with open(REF_BASE_PATH, encoding="utf-8") as f:
        ref_base = json.load(f)

    resultados: List[ResultadoCorrida] = []

    modelos = args.modelos
    for ronda_num in range(1, args.rondas + 1):
        # Alternar orden en cada ronda (A-B, B-A, A-B...)
        modelos_orden = list(modelos) if (ronda_num % 2 != 0) else list(reversed(modelos))

        for mod in modelos_orden:
            # Crear directorio aislado por ronda y modelo
            alias_mod = mod.replace("-coco", "").replace("-", "_")
            dir_corrida = out_base / f"ronda_{ronda_num}_{alias_mod}"
            res = ejecutar_corrida(str(ronda_num), mod, dir_corrida)
            resultados.append(res)

    # Auditar vehículos
    auditoria, detecciones_no_emparejadas = auditar_vehiculos_contra_referencia(resultados, ref_base)

    # Estadísticas por modelo
    stats_por_modelo = {}
    for mod in modelos:
        corridas_mod = [r for r in resultados if r.modelo == mod]
        tiempos = [r.tiempo_total_segundos for r in corridas_mod]
        rss_list = [r.pico_rss_mb for r in corridas_mod]
        stats_por_modelo[mod] = {
            "tiempos": tiempos,
            "media_segundos": round(sum(tiempos) / len(tiempos), 2) if tiempos else 0.0,
            "pico_rss_mb_lista": rss_list,
            "media_rss_mb": round(sum(rss_list) / len(rss_list), 2) if rss_list else 0.0,
        }

    informe_final = {
        "fecha": datetime.datetime.now().isoformat(),
        "modelos_evaluados": modelos,
        "rondas": args.rondas,
        "estadisticas": stats_por_modelo,
        "corridas": [asdict(r) for r in resultados],
        "auditoria_vehiculos": auditoria,
        "detecciones_no_emparejadas": detecciones_no_emparejadas,
    }

    ruta_informe = out_base / "resultados_comparacion.json"
    with open(ruta_informe, "w", encoding="utf-8") as f:
        json.dump(informe_final, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print("RESUMEN DE COMPARACIÓN DE DETECTORES")
    print("=" * 80)
    for mod, st in stats_por_modelo.items():
        print(f"Modelo: {mod}")
        print(f"  Tiempo medio: {st['media_segundos']} s (muestras: {st['tiempos']})")
        print(f"  Pico RSS medio: {st['media_rss_mb']} MB (muestras: {st['pico_rss_mb_lista']})")

    print(f"\nInforme detallado guardado en: {ruta_informe}")


if __name__ == "__main__":
    main()
