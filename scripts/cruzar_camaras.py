"""Cruza los registros de dos camaras y reconstruye el recorrido de cada vehiculo.

Una camara vigila un extremo de la via y la otra el opuesto. Un vehiculo que
aparece en una debe aparecer en la otra dentro de un intervalo conocido. El
cruce responde tres preguntas: quien completo el recorrido, quien aparecio en
la primera y nunca en la segunda, y quien aparecio solo en la segunda.

Uso:
    python scripts/cruzar_camaras.py <excel_lastre> <zip_o_carpeta_anpr> [--out <ruta.xlsx>]

La segunda camara entrega su informacion en el nombre de cada imagen, con el
formato AAAAMMDDHHMMSS_PLACA_Tipo.jpg
"""

import argparse
from datetime import datetime
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from lastre.cruce import CruceError, Paso, consolidar_capturas, emparejar

PATRON_ARCHIVO = re.compile(r"(\d{14})_([A-Z0-9]+)_(\w+)\.jpg$", re.IGNORECASE)

COLOR_ENCABEZADO = "1F3864"
COLOR_COMPLETO = "E2EFDA"
COLOR_SOLO_A = "FFF2CC"
COLOR_SOLO_B = "FCE4E4"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Cruza los registros de dos camaras por placa y tiempo.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("lastre", type=str, help="Excel generado para la via de lastre.")
    parser.add_argument("anpr", type=str, help="Zip o carpeta con las imagenes de la otra camara.")
    parser.add_argument("--out", type=str, default="cruce_camaras.xlsx",
                        help="Archivo Excel de salida.")
    parser.add_argument("--minutos-min", type=float, default=5.0,
                        help="Tiempo minimo de recorrido entre camaras.")
    parser.add_argument("--minutos-max", type=float, default=20.0,
                        help="Tiempo maximo de recorrido entre camaras.")
    parser.add_argument("--distancia", type=float, default=1.5,
                        help="Diferencia maxima tolerada entre dos lecturas de placa.")
    parser.add_argument("--agrupar", type=int, default=180,
                        help="Segundos dentro de los cuales varias capturas son un mismo paso.")
    return parser.parse_args()


def leer_anpr(ruta):
    """Extrae fecha, placa y tipo del nombre de cada imagen de la otra camara."""
    ruta = Path(ruta)
    if ruta.suffix.lower() == ".zip":
        with zipfile.ZipFile(ruta) as z:
            nombres = z.namelist()
    elif ruta.is_dir():
        nombres = [str(p) for p in ruta.rglob("*.jpg")]
    else:
        raise CruceError(f"'{ruta}' no es un zip ni una carpeta")

    capturas = []
    ignorados = 0
    for nombre in nombres:
        m = PATRON_ARCHIVO.search(nombre)
        if not m:
            ignorados += 1
            continue
        marca, placa, tipo = m.groups()
        try:
            momento = datetime.strptime(marca, "%Y%m%d%H%M%S")
        except ValueError:
            ignorados += 1
            continue
        capturas.append({"placa": placa.upper(), "momento": momento,
                         "tipo": tipo.lower(), "origen": "ANPR"})

    return capturas, ignorados


def leer_lastre(ruta):
    """Lee los pasos registrados en el Excel de la via de lastre."""
    libro = load_workbook(ruta, read_only=True)
    hoja = libro["Placas"]
    filas = hoja.iter_rows(values_only=True)
    encabezado = next(filas)
    col = {n: j for j, n in enumerate(encabezado)}

    pasos, sin_datos = [], 0
    for fila in filas:
        placa = fila[col["Placa"]]
        hora = fila[col["Hora de paso"]]
        if not placa or not hora:
            sin_datos += 1
            continue
        try:
            momento = datetime.strptime(str(hora), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            sin_datos += 1
            continue
        pasos.append(Paso(
            placa=str(placa).upper(), momento=momento,
            tipo=fila[col["Tipo"]] or "", origen="LASTRE",
        ))

    return tuple(sorted(pasos, key=lambda p: p.momento)), sin_datos


def _encabezar(hoja, columnas):
    relleno = PatternFill("solid", fgColor=COLOR_ENCABEZADO)
    for j, (titulo, ancho) in enumerate(columnas, start=1):
        celda = hoja.cell(row=1, column=j, value=titulo)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = relleno
        celda.alignment = Alignment(horizontal="center")
        hoja.column_dimensions[get_column_letter(j)].width = ancho
    hoja.freeze_panes = "A2"


def escribir(destino, parejas, solo_lastre, solo_anpr, resumen):
    """Escribe el resultado del cruce en tres hojas mas el resumen."""
    libro = Workbook()

    hoja = libro.active
    hoja.title = "Recorrido completo"
    _encabezar(hoja, [("Placa lastre", 15), ("Placa otra camara", 18),
                      ("Lectura", 12), ("Sentido del recorrido", 24),
                      ("Hora lastre", 20), ("Hora otra camara", 20),
                      ("Minutos", 10), ("Tipo", 13), ("Capturas", 10)])
    relleno = PatternFill("solid", fgColor=COLOR_COMPLETO)
    for i, e in enumerate(parejas, start=2):
        sentido = "lastre -> otra camara" if e.minutos >= 0 else "otra camara -> lastre"
        valores = [e.paso_a.placa, e.paso_b.placa,
                   "identica" if e.placa_coincide_exacta else "difiere",
                   sentido, e.paso_a.fecha_hora, e.paso_b.fecha_hora,
                   abs(e.minutos), e.paso_a.tipo or e.paso_b.tipo, e.paso_b.capturas]
        for j, v in enumerate(valores, start=1):
            c = hoja.cell(row=i, column=j, value=v)
            c.fill = relleno
            c.alignment = Alignment(horizontal="center")

    for titulo, pasos, color in (("Solo en lastre", solo_lastre, COLOR_SOLO_A),
                                 ("Solo en otra camara", solo_anpr, COLOR_SOLO_B)):
        h = libro.create_sheet(titulo)
        _encabezar(h, [("Placa", 15), ("Hora", 20), ("Tipo", 13), ("Capturas", 10)])
        relleno = PatternFill("solid", fgColor=color)
        for i, p in enumerate(pasos, start=2):
            for j, v in enumerate([p.placa, p.fecha_hora, p.tipo, p.capturas], start=1):
                c = h.cell(row=i, column=j, value=v)
                c.fill = relleno
                c.alignment = Alignment(horizontal="center")

    h = libro.create_sheet("Resumen")
    h.column_dimensions["A"].width = 42
    h.column_dimensions["B"].width = 22
    h.cell(row=1, column=1, value="Cruce entre camaras").font = Font(bold=True, size=14)
    for i, (k, v) in enumerate(resumen.items(), start=3):
        h.cell(row=i, column=1, value=k).font = Font(bold=True)
        h.cell(row=i, column=2, value=v)

    libro.save(destino)
    return destino


def main():
    args = parse_args()

    try:
        capturas, ignorados = leer_anpr(args.anpr)
        pasos_lastre, sin_hora = leer_lastre(args.lastre)
    except (CruceError, OSError, KeyError) as err:
        print(f"Error al leer los datos: {err}", file=sys.stderr)
        sys.exit(1)

    pasos_anpr = consolidar_capturas(capturas, ventana_segundos=args.agrupar)

    print("=" * 74)
    print("CRUCE ENTRE CAMARAS")
    print("=" * 74)
    print(f"Lastre       : {len(pasos_lastre)} pasos con hora  ({sin_hora} descartados sin hora)")
    print(f"Otra camara  : {len(capturas)} capturas -> {len(pasos_anpr)} pasos")
    if ignorados:
        print(f"               {ignorados} archivos con nombre no reconocible")
    print(f"Ventana      : {args.minutos_min} a {args.minutos_max} minutos")
    print("=" * 74, flush=True)

    parejas, solo_lastre, solo_anpr = emparejar(
        pasos_lastre, pasos_anpr,
        minutos_min=args.minutos_min, minutos_max=args.minutos_max,
        distancia_maxima=args.distancia,
    )

    exactas = sum(1 for e in parejas if e.placa_coincide_exacta)
    # La via es de doble sentido: el signo indica cual camara vio primero
    hacia_otra = sum(1 for e in parejas if e.minutos >= 0)
    minutos = [abs(e.minutos) for e in parejas]

    resumen = {
        "Pasos en la via de lastre": len(pasos_lastre),
        "Descartados por falta de hora": sin_hora,
        "Capturas de la otra camara": len(capturas),
        "Pasos de la otra camara": len(pasos_anpr),
        "Recorrido completo (emparejados)": len(parejas),
        "  con placa identica": exactas,
        "  con placa que difiere": len(parejas) - exactas,
        "  lastre primero": hacia_otra,
        "  otra camara primero": len(parejas) - hacia_otra,
        "Solo en la via de lastre": len(solo_lastre),
        "Solo en la otra camara": len(solo_anpr),
        "Minutos: minimo": round(min(minutos), 1) if minutos else "",
        "Minutos: promedio": round(sum(minutos) / len(minutos), 1) if minutos else "",
        "Minutos: maximo": round(max(minutos), 1) if minutos else "",
        "Generado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    destino = escribir(args.out, parejas, solo_lastre, solo_anpr, resumen)

    print()
    for k, v in resumen.items():
        print(f"  {k:36s} {v}")
    print("-" * 74)
    print(f"  Excel: {destino}")
    print("=" * 74)


if __name__ == "__main__":
    main()
