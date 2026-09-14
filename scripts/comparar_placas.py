"""Compara las placas de ambas camaras sin filtrar por tiempo.

A diferencia del cruce, aqui no se descarta nada por el reloj: se listan todas
las correspondencias de placa y se informa el tiempo transcurrido para que el
analista juzgue. Una placa que coincide fuera del tiempo esperado puede ser un
segundo paso del mismo vehiculo, o una coincidencia casual.

Cada fila indica ademas en que difieren las dos lecturas, porque una
correspondencia donde solo cambia una letra y los numeros son identicos es
casi con certeza el mismo vehiculo, y casi con certeza no es certeza.

Uso:
    python scripts/comparar_placas.py <excel_lastre> <zip_anpr> [--out <ruta.xlsx>]
"""

import argparse
from datetime import datetime
import io
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as ImagenExcel
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import re

PATRON_ANPR = re.compile(r"(\d{14})_([A-Z0-9]+)_(\w+)\.jpg$", re.IGNORECASE)

from lastre.cruce import (
    COINCIDENCIA_EXACTA,
    COINCIDENCIA_LETRA,
    COINCIDENCIA_MIXTA,
    COINCIDENCIA_NUMERO,
    clasificar_coincidencia,
    consolidar_capturas,
    distancia_placa,
    requiere_revision,
)

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "cruzar_camaras", Path(__file__).resolve().parent / "cruzar_camaras.py")
_cruzar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cruzar)

# Tiempo de recorrido observado entre ambas camaras
MINUTOS_ESPERADO_MIN = 5.0
MINUTOS_ESPERADO_MAX = 20.0

DISTANCIA_MAXIMA = 1.5

COLOR_ENCABEZADO = "1F3864"
COLORES = {
    COINCIDENCIA_EXACTA: "E2EFDA",
    COINCIDENCIA_LETRA: "FFF2CC",
    COINCIDENCIA_NUMERO: "FCE4E4",
}
COLOR_OTRO = "EDEDED"

COLUMNAS = [
    ("Placa lastre", 15), ("Placa otra camara", 18), ("En que difieren", 26),
    ("Confianza", 14), ("Hora lastre", 20), ("Hora otra camara", 20),
    ("Minutos", 10), ("Tiempo esperado", 17), ("Tipo de vehiculo", 18),
    ("Estado lastre", 24), ("Advertencia", 46),
    ("Foto via de lastre", 30), ("Foto otra camara", 30),
]

# Alto de fila y de imagen para que las dos fotos se comparen sin ampliar
ALTO_FILA = 105
ALTO_IMAGEN = 135


def imagenes_del_excel(ruta):
    """Extrae las fotos incrustadas en el Excel del lastre, indexadas por placa.

    Las imagenes estan ancladas a su fila, de modo que la fila indica a que
    vehiculo pertenece cada una.
    """
    libro = load_workbook(ruta)
    hoja = libro["Placas"]
    encabezado = [hoja.cell(row=1, column=j).value for j in range(1, hoja.max_column + 1)]
    columna_placa = encabezado.index("Placa") + 1
    columna_hora = encabezado.index("Hora de paso") + 1

    por_clave = {}
    for imagen in hoja._images:
        fila = imagen.anchor._from.row + 1
        placa = hoja.cell(row=fila, column=columna_placa).value
        hora = hoja.cell(row=fila, column=columna_hora).value
        if placa and hora:
            por_clave[(str(placa).upper(), str(hora))] = imagen._data()
    return por_clave


def imagenes_del_zip(ruta):
    """Indexa las fotos de la otra camara por placa y momento."""
    if Path(ruta).suffix.lower() != ".zip":
        return {}
    por_clave = {}
    with zipfile.ZipFile(ruta) as z:
        for nombre in z.namelist():
            m = PATRON_ANPR.search(nombre)
            if m:
                por_clave[(m.group(2).upper(), m.group(1))] = nombre
    return por_clave


def _insertar(hoja, datos, fila, columna):
    """Incrusta una imagen escalada al alto de la fila."""
    if not datos:
        return
    try:
        imagen = ImagenExcel(io.BytesIO(datos))
    except Exception:
        return
    proporcion = imagen.width / imagen.height if imagen.height else 1.0
    imagen.height = ALTO_IMAGEN
    imagen.width = int(ALTO_IMAGEN * proporcion)
    hoja.add_image(imagen, f"{get_column_letter(columna)}{fila}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compara placas entre camaras informando el tiempo, sin filtrarlo.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("lastre", type=str, help="Excel de la via de lastre.")
    parser.add_argument("anpr", type=str,
                        help="Indice CSV de la otra camara, o el zip/carpeta de sus imagenes.")
    parser.add_argument("--imagenes", type=str, default=None,
                        help="Carpeta con las fotos de la otra camara.")
    parser.add_argument("--out", type=str, default="comparacion_placas.xlsx",
                        help="Archivo Excel de salida.")
    parser.add_argument("--distancia", type=float, default=DISTANCIA_MAXIMA,
                        help="Diferencia maxima tolerada entre dos lecturas.")
    parser.add_argument("--incluir-sin-match", action="store_true",
                        help="Incluir tambien los pasos que no aparecen en la otra camara.")
    return parser.parse_args()


def _confianza(clasificacion, dentro_del_tiempo):
    """Resume en una palabra que tan fiable es la correspondencia."""
    if clasificacion == COINCIDENCIA_EXACTA:
        return "alta" if dentro_del_tiempo else "media"
    if clasificacion == COINCIDENCIA_LETRA:
        return "media" if dentro_del_tiempo else "baja"
    return "baja"


def _advertencia(clasificacion, dentro_del_tiempo, minutos):
    """Explica en palabras que hay que mirar antes de usar la fila."""
    avisos = []
    if clasificacion == COINCIDENCIA_LETRA:
        avisos.append("los numeros coinciden pero una letra difiere")
    elif clasificacion == COINCIDENCIA_NUMERO:
        avisos.append("cambia un numero: podrian ser dos vehiculos distintos")
    elif clasificacion == COINCIDENCIA_MIXTA:
        avisos.append("difieren letras y numeros")

    if not dentro_del_tiempo:
        if abs(minutos) < MINUTOS_ESPERADO_MIN:
            avisos.append("demasiado rapido para el recorrido")
        else:
            avisos.append("fuera del tiempo de recorrido, puede ser otro paso")

    return "; ".join(avisos)


def comparar(pasos_lastre, pasos_anpr, distancia_maxima):
    """Para cada paso del lastre, busca su mejor correspondencia en la otra camara."""
    filas = []
    for a in pasos_lastre:
        mejor = None
        for b in pasos_anpr:
            d = distancia_placa(a.placa, b.placa)
            if d > distancia_maxima:
                continue
            minutos = (b.momento - a.momento).total_seconds() / 60.0
            dentro = MINUTOS_ESPERADO_MIN <= abs(minutos) <= MINUTOS_ESPERADO_MAX
            # Se prefiere la lectura mas parecida y, a igualdad, la que cae
            # dentro del tiempo esperado y mas cerca del promedio.
            criterio = (d, not dentro, abs(minutos))
            if mejor is None or criterio < mejor[0]:
                mejor = (criterio, b, minutos, dentro)

        if mejor is None:
            filas.append({
                "_clave_lastre": (a.placa, a.fecha_hora), "_clave_otra": None,
                "_imagen_otra": "",
                "placa_lastre": a.placa, "placa_otra": "", "difieren": "sin correspondencia",
                "confianza": "", "hora_lastre": a.fecha_hora, "hora_otra": "",
                "minutos": "", "dentro": "", "tipo": a.tipo, "estado": a.origen,
                "advertencia": "no aparece en la otra camara",
            })
            continue

        _, b, minutos, dentro = mejor
        clas = clasificar_coincidencia(a.placa, b.placa)
        filas.append({
            "_clave_lastre": (a.placa, a.fecha_hora),
            "_clave_otra": (b.placa, b.momento.strftime("%Y%m%d%H%M%S")),
            "_imagen_otra": b.imagen,
            "placa_lastre": a.placa, "placa_otra": b.placa, "difieren": clas,
            "confianza": _confianza(clas, dentro),
            "hora_lastre": a.fecha_hora, "hora_otra": b.fecha_hora,
            "minutos": round(abs(minutos), 1),
            "dentro": "si" if dentro else "no",
            # El tipo de la otra camara viene de su propio detector, que
            # distingue camion de automovil. El del lastre solo deduce del
            # formato de placa, asi que nunca reconoce un camion.
            "tipo": b.tipo or a.tipo, "estado": a.origen,
            "advertencia": _advertencia(clas, dentro, minutos),
        })

    return filas


def escribir(destino, filas, resumen, fotos_lastre=None, fotos_anpr=None, ruta_zip=None):
    """Escribe la comparacion completa y su resumen."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Comparacion"

    relleno = PatternFill("solid", fgColor=COLOR_ENCABEZADO)
    for j, (titulo, ancho) in enumerate(COLUMNAS, start=1):
        c = hoja.cell(row=1, column=j, value=titulo)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = relleno
        c.alignment = Alignment(horizontal="center")
        hoja.column_dimensions[get_column_letter(j)].width = ancho
    hoja.freeze_panes = "A2"

    claves = ["placa_lastre", "placa_otra", "difieren", "confianza", "hora_lastre",
              "hora_otra", "minutos", "dentro", "tipo", "estado", "advertencia"]

    fotos_lastre = fotos_lastre or {}
    fotos_anpr = fotos_anpr or {}
    archivo_zip = zipfile.ZipFile(ruta_zip) if ruta_zip and Path(ruta_zip).suffix.lower() == ".zip" else None

    columna_foto_a = len(COLUMNAS) - 1
    columna_foto_b = len(COLUMNAS)

    for i, fila in enumerate(filas, start=2):
        color = COLORES.get(fila["difieren"], COLOR_OTRO)
        relleno = PatternFill("solid", fgColor=color)
        for j, clave in enumerate(claves, start=1):
            c = hoja.cell(row=i, column=j, value=fila[clave])
            c.fill = relleno
            c.alignment = Alignment(horizontal="center" if clave != "advertencia" else "left")

        hoja.row_dimensions[i].height = ALTO_FILA
        _insertar(hoja, fotos_lastre.get(fila["_clave_lastre"]), i, columna_foto_a)

        datos_otra = None
        ruta_suelta = fila.get("_imagen_otra")
        if ruta_suelta and Path(ruta_suelta).is_file():
            datos_otra = Path(ruta_suelta).read_bytes()
        elif archivo_zip and fila["_clave_otra"]:
            nombre = fotos_anpr.get(fila["_clave_otra"])
            if nombre:
                datos_otra = archivo_zip.read(nombre)
        _insertar(hoja, datos_otra, i, columna_foto_b)

    if archivo_zip:
        archivo_zip.close()

    h = libro.create_sheet("Resumen")
    h.column_dimensions["A"].width = 46
    h.column_dimensions["B"].width = 20
    h.cell(row=1, column=1, value="Comparacion de placas entre camaras").font = Font(bold=True, size=14)
    for i, (k, v) in enumerate(resumen.items(), start=3):
        h.cell(row=i, column=1, value=k).font = Font(bold=True)
        h.cell(row=i, column=2, value=v)

    libro.save(destino)
    return destino


def main():
    args = parse_args()

    capturas, ignorados = _cruzar.leer_anpr(args.anpr, args.imagenes)
    pasos_lastre, sin_hora = _cruzar.leer_lastre(args.lastre)
    pasos_anpr = consolidar_capturas(capturas, ventana_segundos=180)

    filas = comparar(pasos_lastre, pasos_anpr, args.distancia)

    con = [f for f in filas if f["placa_otra"]]
    sin_correspondencia = len(filas) - len(con)

    # El listado util es el de los que emparejaron; los demas solo estorban
    if not args.incluir_sin_match:
        filas = con
    exactas = [f for f in con if f["difieren"] == COINCIDENCIA_EXACTA]
    dentro = [f for f in con if f["dentro"] == "si"]
    revisar = [f for f in con if requiere_revision(f["difieren"])]

    resumen = {
        "Pasos comparados de la via de lastre": len(filas),
        "Descartados por falta de hora": sin_hora,
        "Pasos de la otra camara": len(pasos_anpr),
        "Con correspondencia de placa": len(con),
        "  lectura identica": len(exactas),
        "  lectura que difiere (revisar)": len(revisar),
        "  dentro del tiempo esperado": len(dentro),
        "  fuera del tiempo esperado": len(con) - len(dentro),
        "Sin correspondencia (no listados)": sin_correspondencia,
        "Camiones identificados": sum(1 for f in con if f["tipo"] == "truck"),
        "Buses identificados": sum(1 for f in con if f["tipo"] == "bus"),
        "Automoviles identificados": sum(1 for f in con if f["tipo"] == "car"),
        "Tiempo esperado de recorrido": f"{MINUTOS_ESPERADO_MIN:.0f} a {MINUTOS_ESPERADO_MAX:.0f} minutos",
        "Generado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


    print("Extrayendo las fotos de ambas camaras...", flush=True)
    fotos_lastre = imagenes_del_excel(args.lastre)
    fotos_anpr = imagenes_del_zip(args.anpr)

    destino = escribir(args.out, filas, resumen,
                       fotos_lastre=fotos_lastre, fotos_anpr=fotos_anpr, ruta_zip=args.anpr)

    print("=" * 70)
    print("COMPARACION DE PLACAS")
    print("=" * 70)
    for k, v in resumen.items():
        print(f"  {k:40s} {v}")
    print("-" * 70)
    print(f"  Excel: {destino}")
    print("=" * 70)


if __name__ == "__main__":
    main()
