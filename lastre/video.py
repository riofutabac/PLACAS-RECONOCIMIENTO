"""Módulo de lectura y decodificación secuencial de video.

ADVERTENCIA TÉCNICA - PROHIBICIÓN DE SALTO POR ÍNDICE (SEEK):
En este códec y contenedor de video (grabaciones de cámara de seguridad H.264 / MP4
con estructuras GOP largas y compresión inter-frame basada en cuadros I/P/B sin tabla
de índices temporales deterministas en contenedor), el uso de:
    `cap.set(cv2.CAP_PROP_POS_FRAMES, n)`
produce inexactitud severa. OpenCV salta hacia el cuadro clave (I-frame) anterior más
cercano sin reconstruir la predicción temporal, lo que genera deriva en el conteo de
cuadros, cuadros duplicados o imágenes desincronizadas.

Para asegurar resultados reproducibles y deterministas, TODA lectura en este proyecto
se realiza de manera estrictamente secuencial mediante llamadas continuas a `cap.read()`.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Optional, Tuple, Union
import cv2
import numpy as np


class VideoLecturaError(RuntimeError):
    """Excepción lanzada cuando ocurre un error al abrir o decodificar un archivo de video."""
    pass


@dataclass(frozen=True)
class MetadatosVideo:
    """Información técnica inmutable de un archivo de video."""
    ruta: Path
    ancho: int
    alto: int
    fps: float
    total_cuadros: int
    duracion_segundos: float


def obtener_metadatos_video(ruta: Union[str, Path]) -> MetadatosVideo:
    """Extrae las propiedades técnicas y dimensiones de un archivo de video.

    Lanza VideoLecturaError si el archivo no existe o no puede abrirse.
    """
    ruta_path = Path(ruta)
    if not ruta_path.is_file():
        raise VideoLecturaError(f"Archivo de video no encontrado: '{ruta}'")

    cap = cv2.VideoCapture(str(ruta_path))
    if not cap.isOpened():
        raise VideoLecturaError(f"No fue posible abrir el video con OpenCV: '{ruta}'")

    try:
        ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        alto = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        total_cuadros = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duracion = (total_cuadros / fps) if fps > 0 else 0.0

        if ancho <= 0 or alto <= 0:
            raise VideoLecturaError(f"Dimensiones de video inválidas ({ancho}x{alto}) en '{ruta}'")

        return MetadatosVideo(
            ruta=ruta_path,
            ancho=ancho,
            alto=alto,
            fps=fps,
            total_cuadros=total_cuadros,
            duracion_segundos=duracion,
        )
    finally:
        cap.release()


def iterar_cuadros(
    ruta: Union[str, Path],
    desde_cuadro: int = 1,
    hasta_cuadro: Optional[int] = None,
) -> Generator[Tuple[int, np.ndarray], None, None]:
    """Generador que entrega los cuadros del video de manera estrictamente secuencial.

    Entrega tuplas (numero_cuadro, cuadro_bgr), donde numero_cuadro está indexado
    a partir de 1 (1-indexed).

    Parámetros:
    - ruta: Ruta al archivo de video.
    - desde_cuadro: Número de cuadro inicial (>= 1). Los cuadros anteriores se decodifican
      y descartan secuencialmente para mantener la sincronía del códec.
    - hasta_cuadro: Número de cuadro final opcional (inclusive).

    Garantiza la liberación del descriptor de video al terminar o interrumpirse.
    """
    if desde_cuadro < 1:
        raise VideoLecturaError(f"desde_cuadro debe ser >= 1, se recibió: {desde_cuadro}")
    if hasta_cuadro is not None and hasta_cuadro < desde_cuadro:
        raise VideoLecturaError(
            f"hasta_cuadro ({hasta_cuadro}) no puede ser menor a desde_cuadro ({desde_cuadro})"
        )

    ruta_path = Path(ruta)
    if not ruta_path.is_file():
        raise VideoLecturaError(f"Archivo de video no encontrado: '{ruta}'")

    cap = cv2.VideoCapture(str(ruta_path))
    if not cap.isOpened():
        raise VideoLecturaError(f"No fue posible abrir el video: '{ruta}'")

    numero_cuadro = 0
    try:
        while True:
            ok, cuadro = cap.read()
            if not ok:
                break
            numero_cuadro += 1

            if numero_cuadro < desde_cuadro:
                continue

            if hasta_cuadro is not None and numero_cuadro > hasta_cuadro:
                break

            yield numero_cuadro, cuadro
    finally:
        cap.release()


def leer_cuadro_especifico(ruta: Union[str, Path], numero_cuadro: int) -> np.ndarray:
    """Decodifica secuencialmente el video hasta obtener el cuadro exacto solicitado.

    Lanza VideoLecturaError si el cuadro no se encuentra o el archivo falla.
    """
    if numero_cuadro < 1:
        raise VideoLecturaError(f"numero_cuadro debe ser >= 1, se recibió: {numero_cuadro}")

    for num, cuadro in iterar_cuadros(ruta, desde_cuadro=numero_cuadro, hasta_cuadro=numero_cuadro):
        if num == numero_cuadro:
            return cuadro

    raise VideoLecturaError(
        f"El cuadro {numero_cuadro} no pudo ser decodificado (el video terminó antes o el cuadro no existe)"
    )
