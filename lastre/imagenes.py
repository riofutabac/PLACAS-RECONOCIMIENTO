"""Escritura de imágenes con fallos visibles para el consumidor."""

import cv2


def guardar_imagen(ruta, recorte, calidad=95):
    """Guarda un JPEG o lanza OSError; nunca devuelve una ruta ficticia."""
    try:
        guardado = cv2.imwrite(str(ruta), recorte, [cv2.IMWRITE_JPEG_QUALITY, calidad])
    except cv2.error as exc:
        raise OSError(f"No se pudo guardar la imagen '{ruta}': {exc}") from exc
    if not guardado:
        raise OSError(f"No se pudo guardar la imagen '{ruta}'")
