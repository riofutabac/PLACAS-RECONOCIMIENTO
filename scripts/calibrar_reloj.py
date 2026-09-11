"""Genera las plantillas de dígitos del reloj que la cámara imprime.

La tipografía y la posición de la marca son constantes, de modo que basta
calibrar una vez con un cuadro cuya hora se conoce. A partir de ahí la marca
de cualquier cuadro se lee por comparación, sin depender de ningún modelo.

Uso:
    python scripts/calibrar_reloj.py <video> --frame 738 --marca "09/09/2026 16:17:47"
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from lastre.reloj import recortar_franja_reloj, segmentar_digitos
from lastre.video import leer_cuadro_especifico, VideoLecturaError

DIRECTORIO_PLANTILLAS = Path("config/reloj")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Calibra la lectura del reloj impreso por la camara.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("video", type=str, help="Video de referencia.")
    parser.add_argument("--frame", type=int, required=True, help="Cuadro a usar.")
    parser.add_argument("--marca", type=str, required=True,
                        help='Hora exacta visible en ese cuadro, "DD/MM/AAAA HH:MM:SS".')
    parser.add_argument("--salida", type=str, default=str(DIRECTORIO_PLANTILLAS),
                        help="Carpeta donde se guardan las plantillas.")
    return parser.parse_args()


def main():
    args = parse_args()

    digitos = "".join(c for c in args.marca if c.isdigit())
    if len(digitos) != 14:
        print(f"La marca debe contener 14 digitos, se recibieron {len(digitos)}: '{args.marca}'",
              file=sys.stderr)
        sys.exit(1)

    try:
        cuadro = leer_cuadro_especifico(args.video, args.frame)
    except VideoLecturaError as err:
        print(f"Error al leer el video: {err}", file=sys.stderr)
        sys.exit(1)

    recortes = segmentar_digitos(recortar_franja_reloj(cuadro))
    if len(recortes) != 14:
        print(f"Se aislaron {len(recortes)} digitos en lugar de 14. "
              "Revise que el cuadro muestre la marca completa.", file=sys.stderr)
        sys.exit(1)

    destino = Path(args.salida)
    destino.mkdir(parents=True, exist_ok=True)

    # Un mismo digito puede aparecer varias veces; se promedian sus apariciones
    acumulado = {}
    for caracter, recorte in zip(digitos, recortes):
        acumulado.setdefault(caracter, []).append(recorte.astype(np.float32))

    for caracter, muestras in sorted(acumulado.items()):
        promedio = np.mean(muestras, axis=0).astype(np.uint8)
        cv2.imwrite(str(destino / f"{caracter}.png"), promedio)

    faltantes = sorted(set("0123456789") - set(acumulado))
    print(f"Plantillas generadas en {destino}: {sorted(acumulado)}")
    if faltantes:
        print(f"Faltan los digitos {faltantes}. Calibre con otro cuadro que los contenga "
              "para completar el juego.")
    else:
        print("Juego completo de 0 a 9.")


if __name__ == "__main__":
    main()
