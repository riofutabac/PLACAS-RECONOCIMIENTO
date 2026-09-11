"""Script para generar la imagen de verificación con la delimitación de la zona superpuesta.

Uso:
    python scripts/verificar_zona.py <video> --frame <numero_cuadro> [--config <ruta_config>] [--output <ruta_salida>]

Ejemplo:
    python scripts/verificar_zona.py "Camara Placas 2_20260909105651-20260909163038(60).mp4" --frame 2697
"""

import argparse
from pathlib import Path
import sys

# Asegurar que la raíz del proyecto esté en sys.path para importar lastre
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from lastre.config import cargar_configuracion, ConfiguracionError
from lastre.video import leer_cuadro_especifico, VideoLecturaError
from lastre.zona import superponer_zona


def parse_args():
    parser = argparse.ArgumentParser(
        description="Superpone la zona de análisis y la banda de reloj excluida sobre un cuadro del video.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "video",
        type=str,
        help="Ruta al archivo de video de entrada.",
    )
    parser.add_argument(
        "--frame",
        "-f",
        type=int,
        required=True,
        help="Número de cuadro a extraer (1-indexed).",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default="config/zona.json",
        help="Ruta al archivo de configuración JSON de la zona.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Ruta donde se guardará la imagen resultante (por defecto out/verificacion_zona_f{frame}.jpg).",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # 1. Cargar configuración de la zona
    try:
        config = cargar_configuracion(args.config)
    except ConfiguracionError as err:
        print(f"Error de configuración: {err}", file=sys.stderr)
        sys.exit(1)

    # 2. Determinar ruta de salida
    if args.output:
        ruta_salida = Path(args.output)
    else:
        ruta_salida = Path("out") / f"verificacion_zona_f{args.frame}.jpg"
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)

    # 3. Leer secuencialmente hasta el cuadro indicado
    print(f"Decodificando video de manera secuencial hasta el cuadro {args.frame}...")
    try:
        cuadro = leer_cuadro_especifico(args.video, args.frame)
    except VideoLecturaError as err:
        print(f"Error al leer video: {err}", file=sys.stderr)
        sys.exit(1)

    # 4. Superponer la zona delimitada y la exclusión del reloj
    visualizacion = superponer_zona(cuadro, config)

    # 5. Agregar rótulos explicativos en la imagen
    # Rótulo de la banda del reloj excluida
    alto_reloj = config.banda_reloj.alto
    cv2.putText(
        visualizacion,
        f"Banda de reloj excluida (0 a {alto_reloj}px)",
        (30, max(35, alto_reloj // 2 + 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.1,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    # Rótulo de la zona de análisis (vía de lastre)
    cv2.putText(
        visualizacion,
        "ZONA DE ANALISIS (VIA DE LASTRE)",
        (30, alto_reloj + 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (0, 255, 0),
        3,
        cv2.LINE_AA,
    )

    # Rótulo de la carretera principal excluida
    cv2.putText(
        visualizacion,
        "Carretera principal (excluida)",
        (config.dimensiones.ancho - 750, config.dimensiones.alto - 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.1,
        (0, 200, 255),
        2,
        cv2.LINE_AA,
    )

    # Información de cuadro y resolución en la esquina inferior izquierda
    info_cuadro = f"Cuadro: {args.frame} | Resolucion: {config.dimensiones.ancho}x{config.dimensiones.alto}"
    cv2.putText(
        visualizacion,
        info_cuadro,
        (30, config.dimensiones.alto - 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    # 6. Guardar imagen resultante
    ok = cv2.imwrite(str(ruta_salida), visualizacion, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        print(f"Error: No se pudo escribir la imagen en '{ruta_salida}'", file=sys.stderr)
        sys.exit(1)

    print(f"Evidencia visual generada con éxito:")
    print(f"  Ruta: {ruta_salida}")
    print(f"  Cuadro: {args.frame}")
    print(f"  Dimensiones: {visualizacion.shape[1]}x{visualizacion.shape[0]}")


if __name__ == "__main__":
    main()
