"""Comparación integral antes/después entre la versión anterior (bc0859f)
y la versión optimizada actual (1cc0b11).

Ejecuta los videos 60 y 61 completos (16.454 cuadros por corrida),
tres veces por versión y alternando el orden:
  Ronda 1: anterior -> actual
  Ronda 2: actual -> anterior
  Ronda 3: anterior -> actual

Mide desde la carga de modelos hasta la entrega del Excel, además de memoria
pico RSS en procesos aislados, y compara cada vehículo, su dirección,
placa y evidencia.
"""

from dataclasses import asdict, dataclass, field
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional


REPO_DIR = Path(__file__).resolve().parent.parent
WORKTREE_ANTERIOR = REPO_DIR / ".worktree_bc0859f"
PYTHON_EXE = REPO_DIR / ".venv312" / "bin" / "python"
VIDEOS_DIR = REPO_DIR / "conjunto_evaluacion"
CONFIG_ZONA = REPO_DIR / "config" / "zona.json"
BASE_OUT_DIR = REPO_DIR / "validacion" / "comparacion_antes_despues"
REF_BASE_PATH = REPO_DIR / "validacion" / "referencia_base.json"

COMMIT_ANTERIOR = "bc0859f"


def obtener_commit_actual() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_DIR,
            text=True
        ).strip()
    except Exception:
        return "e811672"


COMMIT_ACTUAL = obtener_commit_actual()


@dataclass
class ResultadoCorrida:
    ronda: str
    version: str
    commit: str
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
    errores: List[str] = field(default_factory=list)


def asegurar_entorno():
    """Verifica que el ejecutable de python, videos y worktree existan."""
    if not PYTHON_EXE.is_file():
        raise RuntimeError(f"Intérprete no encontrado en {PYTHON_EXE}")
    if not VIDEOS_DIR.is_dir():
        raise RuntimeError(f"Carpeta de videos no encontrada en {VIDEOS_DIR}")
    if not WORKTREE_ANTERIOR.is_dir():
        raise RuntimeError(f"Worktree anterior no encontrado en {WORKTREE_ANTERIOR}")

    videos = sorted(v for v in VIDEOS_DIR.iterdir() if v.suffix.lower() == ".mp4")
    if len(videos) < 2:
        raise RuntimeError(f"Se esperaban al menos 2 videos en {VIDEOS_DIR}, se hallaron {len(videos)}")


def parsear_tiempo_l(salida_stderr: str) -> Dict[str, Any]:
    """Parsea el reporte de /usr/bin/time -l en macOS."""
    metricas = {
        "real": 0.0,
        "user": 0.0,
        "sys": 0.0,
        "max_rss_bytes": 0,
        "max_rss_mb": 0.0,
    }
    # Formato típico macOS:
    #         860.12 real       1240.50 user         45.30 sys
    #      598472704  maximum resident set size
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
        if "ETAPA" in linea and "TIEMPO" in linea and "LLAMADAS" in linea:
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
            # Ejemplo: "  detectar vehiculos         596.5   56.7%         831         717.8"
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
    version: str,
    commit: str,
    workdir: Path,
    out_dir: Path,
) -> ResultadoCorrida:
    """Ejecuta una corrida de lote completa en un subproceso aislado."""
    print("\n" + "=" * 80)
    print(f"INICIANDO CORRIDA: Ronda {ronda} | Versión: {version} (Commit {commit})")
    print(f"Directorio de trabajo: {workdir}")
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
        cwd=workdir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    stdout_acumulado = []
    stderr_acumulado = []

    # Leemos stdout en vivo para informar progreso
    assert proceso.stdout is not None
    for linea in iter(proceso.stdout.readline, ""):
        stdout_acumulado.append(linea)
        # Mostrar líneas clave de progreso
        linea_str = linea.strip()
        if (
            "---" in linea_str
            or "%" in linea_str
            or "vehiculos registrados" in linea_str
            or "TOTAL" in linea_str
            or "Excel:" in linea_str
        ):
            print(f"[{version.upper()}] {linea_str}", flush=True)

    proceso.stdout.close()
    stderr_raw = proceso.stderr.read() if proceso.stderr else ""
    stderr_acumulado.append(stderr_raw)
    proceso.wait()
    t1 = time.perf_counter()

    duracion_total = t1 - t0
    stdout_texto = "".join(stdout_acumulado)
    stderr_texto = "".join(stderr_acumulado)

    metricas_tiempo = parsear_tiempo_l(stderr_texto)
    desglose_etapas = parsear_desglose_medidor(stdout_texto)

    # Verificar avance.json y placas_lastre.xlsx
    ruta_avance = out_dir / "avance.json"
    ruta_excel = out_dir / "placas_lastre.xlsx"
    dir_recortes = out_dir / "recortes"

    vehiculos_por_video = {}
    cuadros_totales = 0
    vehiculos_totales = 0
    errores = []

    if ruta_avance.is_file():
        try:
            avance_data = json.loads(ruta_avance.read_text(encoding="utf-8"))
            for v_nom, v_info in avance_data.items():
                cuadros_totales += v_info.get("cuadros", 0)
                filas = v_info.get("filas", [])
                vehiculos_totales += len(filas)
                vehiculos_limpios = []
                for fila in filas:
                    img_rel = fila.get("imagen")
                    img_existe = False
                    img_tamano = 0
                    if img_rel:
                        ruta_img = out_dir / img_rel
                        if ruta_img.is_file():
                            img_existe = True
                            img_tamano = ruta_img.stat().st_size
                    vehiculos_limpios.append({
                        "video": fila.get("video"),
                        "registro": fila.get("registro"),
                        "hora_paso": fila.get("hora_paso"),
                        "tiempo_video": fila.get("tiempo_video"),
                        "sentido": fila.get("sentido"),
                        "tipo": fila.get("tipo"),
                        "placa_leida": fila.get("placa_leida"),
                        "confianza": fila.get("confianza"),
                        "consenso": fila.get("consenso"),
                        "estado": fila.get("estado"),
                        "lecturas": fila.get("lecturas"),
                        "imagen_rel": img_rel,
                        "imagen_existe": img_existe,
                        "imagen_tamano": img_tamano,
                    })
                vehiculos_por_video[v_nom] = vehiculos_limpios
        except Exception as e:
            errores.append(f"Error parseando avance.json: {e}")
    else:
        errores.append(f"avance.json no fue generado en {out_dir}")

    excel_existe = ruta_excel.is_file()
    excel_tamano = ruta_excel.stat().st_size if excel_existe else 0
    if not excel_existe or excel_tamano == 0:
        errores.append("placas_lastre.xlsx no existe o está vacío")

    resultado = ResultadoCorrida(
        ronda=ronda,
        version=version,
        commit=commit,
        directorio_salida=str(out_dir),
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
        errores=errores,
    )

    # Guardar métricas individuales en el directorio de salida
    (out_dir / "metricas_corrida.json").write_text(
        json.dumps(asdict(resultado), indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("-" * 80)
    print(f"RESULTADO: {version.upper()} en {duracion_total:.2f} s | RSS: {resultado.pico_rss_mb} MB | "
          f"Vehículos: {vehiculos_totales} | Excel: {excel_tamano:,} bytes")
    print("=" * 80 + "\n", flush=True)

    return resultado


def generar_auditoria_vehiculos(
    resultados: List[ResultadoCorrida],
    ref_base: Dict[str, Any],
) -> Dict[str, Any]:
    """Compara vehículo por vehículo entre todas las corridas y contra la referencia."""
    ref_videos = ref_base.get("videos", {})
    matriz = {}

    for vid_nom, v_info in ref_videos.items():
        vehiculos_ref = v_info.get("vehiculos", [])
        matriz[vid_nom] = []
        for ref_veh in vehiculos_ref:
            fila_auditoria = {
                "indice": ref_veh["indice"],
                "hora_reloj_esperada": ref_veh["hora_reloj"],
                "sentido_esperado": ref_veh["sentido"],
                "placa_esperada": ref_veh["placa_leida"],
                "placa_real": ref_veh.get("placa_real_legible"),
                "estado_esperado": ref_veh["estado"],
                "corridas": {},
            }

            # Buscar en cada corrida el vehículo correspondiente por proximidad horaria / sentido
            for r in resultados:
                clave_corrida = f"{r.ronda}_{r.version}"
                filas_corrida = r.vehiculos_por_video.get(vid_nom, [])
                # Hallar coincidencia
                veh_hallado = None
                for c_veh in filas_corrida:
                    # Coincidencia por hora exacta o minuto cercano
                    if c_veh.get("hora_paso") == ref_veh["hora_reloj"] or (
                        ref_veh["hora_reloj"][:5] in (c_veh.get("hora_paso") or "")
                    ):
                        veh_hallado = c_veh
                        break

                if veh_hallado:
                    fila_auditoria["corridas"][clave_corrida] = {
                        "hallado": True,
                        "registro": veh_hallado.get("registro"),
                        "hora_paso": veh_hallado.get("hora_paso"),
                        "sentido": veh_hallado.get("sentido"),
                        "placa_leida": veh_hallado.get("placa_leida"),
                        "confianza": veh_hallado.get("confianza"),
                        "consenso": veh_hallado.get("consenso"),
                        "estado": veh_hallado.get("estado"),
                        "lecturas": veh_hallado.get("lecturas"),
                        "evidencia_valida": veh_hallado.get("imagen_existe") and veh_hallado.get("imagen_tamano", 0) > 1000,
                    }
                else:
                    fila_auditoria["corridas"][clave_corrida] = {
                        "hallado": False,
                    }

            matriz[vid_nom].append(fila_auditoria)

    return matriz


def compilar_estadisticas(resultados: List[ResultadoCorrida]) -> Dict[str, Any]:
    """Calcula medias, desviaciones, picos de memoria y porcentajes de mejora."""
    tiempos_anterior = [r.tiempo_total_segundos for r in resultados if r.version == "anterior"]
    tiempos_actual = [r.tiempo_total_segundos for r in resultados if r.version == "actual"]

    rss_anterior = [r.pico_rss_mb for r in resultados if r.version == "anterior"]
    rss_actual = [r.pico_rss_mb for r in resultados if r.version == "actual"]

    import statistics
    media_t_ant = statistics.mean(tiempos_anterior) if tiempos_anterior else 0.0
    std_t_ant = statistics.stdev(tiempos_anterior) if len(tiempos_anterior) > 1 else 0.0
    media_t_act = statistics.mean(tiempos_actual) if tiempos_actual else 0.0
    std_t_act = statistics.stdev(tiempos_actual) if len(tiempos_actual) > 1 else 0.0

    ahorro_tiempo_segundos = media_t_ant - media_t_act
    ahorro_tiempo_pct = (ahorro_tiempo_segundos / media_t_ant * 100.0) if media_t_ant > 0 else 0.0

    media_rss_ant = statistics.mean(rss_anterior) if rss_anterior else 0.0
    media_rss_act = statistics.mean(rss_actual) if rss_actual else 0.0

    return {
        "anterior": {
            "tiempos": tiempos_anterior,
            "media_segundos": round(media_t_ant, 2),
            "desviacion_segundos": round(std_t_ant, 2),
            "pico_rss_mb_lista": rss_anterior,
            "media_rss_mb": round(media_rss_ant, 2),
        },
        "actual": {
            "tiempos": tiempos_actual,
            "media_segundos": round(media_t_act, 2),
            "desviacion_segundos": round(std_t_act, 2),
            "pico_rss_mb_lista": rss_actual,
            "media_rss_mb": round(media_rss_act, 2),
        },
        "comparacion": {
            "ahorro_segundos": round(ahorro_tiempo_segundos, 2),
            "ahorro_porcentaje": round(ahorro_tiempo_pct, 2),
            "variacion_memoria_mb": round(media_rss_act - media_rss_ant, 2),
        }
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Benchmark integral antes/después 3 rondas alternadas")
    parser.add_argument("--reiniciar", action="store_true", help="Forzar re-ejecución de todas las corridas")
    parser.add_argument("--rondas", type=int, default=3, help="Número de rondas alternadas (1 a 3)")
    args = parser.parse_args()

    asegurar_entorno()
    BASE_OUT_DIR.mkdir(parents=True, exist_ok=True)

    ref_base = {}
    if REF_BASE_PATH.is_file():
        ref_base = json.loads(REF_BASE_PATH.read_text(encoding="utf-8"))

    # Definición de las rondas alternadas
    todos_pasos = [
        ("ronda_1", "anterior", COMMIT_ANTERIOR, WORKTREE_ANTERIOR),
        ("ronda_1", "actual", COMMIT_ACTUAL, REPO_DIR),
        ("ronda_2", "actual", COMMIT_ACTUAL, REPO_DIR),
        ("ronda_2", "anterior", COMMIT_ANTERIOR, WORKTREE_ANTERIOR),
        ("ronda_3", "anterior", COMMIT_ANTERIOR, WORKTREE_ANTERIOR),
        ("ronda_3", "actual", COMMIT_ACTUAL, REPO_DIR),
    ]

    rondas_activas = {f"ronda_{r}" for r in range(1, args.rondas + 1)}
    protocolo = [p for p in todos_pasos if p[0] in rondas_activas]

    resultados: List[ResultadoCorrida] = []

    print("=" * 80)
    print("BENCHMARK INTEGRAL ANTES/DESPUÉS — RONDAS ALTERNADAS")
    print(f"Rondas a evaluar: {args.rondas} ({len(protocolo)} corridas en total)")
    print(f"Videos evaluados: {sorted(v.name for v in VIDEOS_DIR.iterdir() if v.suffix.lower() == '.mp4')}")
    print(f"Versión anterior: commit {COMMIT_ANTERIOR} (Worktree)")
    print(f"Versión actual:   commit {COMMIT_ACTUAL} (Branch codex/base-rapida-paso1)")
    print(f"Salidas en:       {BASE_OUT_DIR}")
    print("=" * 80)

    for i, (ronda, version, commit, workdir) in enumerate(protocolo, start=1):
        nombre_corrida = f"{ronda}_{version}"
        out_dir = BASE_OUT_DIR / nombre_corrida
        ruta_metricas = out_dir / "metricas_corrida.json"

        if not args.reiniciar and ruta_metricas.is_file():
            print(f"\n>>> Paso {i}/{len(protocolo)}: {nombre_corrida} (Ya completado, cargando datos)")
            try:
                datos_guardados = json.loads(ruta_metricas.read_text(encoding="utf-8"))
                res_cargado = ResultadoCorrida(**datos_guardados)
                if res_cargado.codigo_salida == 0 and res_cargado.excel_existe:
                    resultados.append(res_cargado)
                    print(f"    Cargado: {res_cargado.tiempo_total_segundos} s | RSS {res_cargado.pico_rss_mb} MB")
                    continue
            except Exception as e:
                print(f"    No se pudo reciclar corrida previa ({e}), reejecutando...")

        print(f"\n>>> Paso {i}/{len(protocolo)}: {nombre_corrida}")

        resultado = ejecutar_corrida(
            ronda=ronda,
            version=version,
            commit=commit,
            workdir=workdir,
            out_dir=out_dir,
        )
        resultados.append(resultado)

        # Guardar resultados consolidados incrementales tras cada corrida
        estadisticas = compilar_estadisticas(resultados)
        auditoria_vehiculos = generar_auditoria_vehiculos(resultados, ref_base)

        informe_consolidado = {
            "fecha": datetime.datetime.now().isoformat(),
            "commit_anterior": COMMIT_ANTERIOR,
            "commit_actual": COMMIT_ACTUAL,
            "estadisticas": estadisticas,
            "auditoria_vehiculos": auditoria_vehiculos,
            "corridas": [asdict(r) for r in resultados],
        }

        ruta_informe = BASE_OUT_DIR / "resultados_comparacion.json"
        ruta_informe.write_text(
            json.dumps(informe_consolidado, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"[Checkpoint guardado en {ruta_informe}]")

        # Pausa de enfriamiento térmico entre corridas (10s)
        if i < len(protocolo):
            print("Pausa de estabilización térmica (10 s)...", flush=True)
            time.sleep(10)

    print("\n" + "=" * 80)
    print("BENCHMARK FINALIZADO CON ÉXITO")
    print("=" * 80)
    stats = compilar_estadisticas(resultados)
    print(f"Versión Anterior: {stats['anterior']['media_segundos']} s ± {stats['anterior']['desviacion_segundos']} s | RSS: {stats['anterior']['media_rss_mb']} MB")
    print(f"Versión Actual:   {stats['actual']['media_segundos']} s ± {stats['actual']['desviacion_segundos']} s | RSS: {stats['actual']['media_rss_mb']} MB")
    print(f"Ahorro neto:      {stats['comparacion']['ahorro_segundos']} s ({stats['comparacion']['ahorro_porcentaje']} %)")
    print("=" * 80)


if __name__ == "__main__":
    main()
