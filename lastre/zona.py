"""Módulo de delimitación geométrica y máscaras para la vía de lastre."""

from typing import Optional, Tuple
import cv2
import numpy as np

from lastre.config import ZonaConfig


def construir_mascara_zona(config: ZonaConfig) -> np.ndarray:
    """Construye la máscara binaria uint8 (alto, ancho) de la zona de análisis.

    Los píxeles pertenecientes a la vía de lastre tienen valor 255.
    Los píxeles fuera de la vía o dentro de la banda superior del reloj tienen valor 0.
    Devuelve un nuevo arreglo sin modificar ningún objeto recibido.
    """
    alto = config.dimensiones.alto
    ancho = config.dimensiones.ancho

    # Contorno cerrado ajustado a la superficie de la vía de lastre
    vertices = np.array(config.poligono.como_lista, dtype=np.int32)

    mascara = np.zeros((alto, ancho), dtype=np.uint8)
    cv2.fillPoly(mascara, [vertices], 255)

    # Excluir la banda horizontal del reloj (franja superior)
    alto_reloj = config.banda_reloj.alto
    if alto_reloj > 0:
        mascara[0:alto_reloj, :] = 0

    return mascara


def punto_en_zona(punto: Tuple[int, int], config: ZonaConfig) -> bool:
    """Evalúa si un punto (x, y) cae dentro de la zona de análisis de la vía de lastre.

    La banda superior del reloj y los píxeles fuera de los límites del cuadro
    quedan explícitamente excluidos.
    """
    x, y = punto
    ancho = config.dimensiones.ancho
    alto = config.dimensiones.alto

    # 1. Comprobación de límites del cuadro
    if x < 0 or x >= ancho or y < 0 or y >= alto:
        return False

    # 2. Exclusión de la banda superior del reloj
    if y < config.banda_reloj.alto:
        return False

    # 3. Comprobación de pertenencia al polígono de la vía de lastre
    contorno = np.array(config.poligono.como_lista, dtype=np.int32)
    return cv2.pointPolygonTest(contorno, (float(x), float(y)), False) >= 0


def caja_en_zona(
    caja: Tuple[int, int, int, int],
    config: ZonaConfig,
    criterio: str = "centro",
    mascara: Optional[np.ndarray] = None,
) -> bool:
    """Evalúa si una caja delimitadora (x, y, w, h) se encuentra dentro de la zona.

    Criterios disponibles:
    - 'centro': El punto medio de la caja (x + w//2, y + h//2) está en la zona.
    - 'base': El punto inferior medio (x + w//2, y + h) está en la zona (contacto rueda/vía).
    - 'cualquiera': Al menos una esquina (o píxeles si se provee máscara) cae en la zona.
    - 'completa': Las 4 esquinas caen dentro de la zona.

    Si se proporciona una máscara precomputada, se utiliza para acelerar la comprobación
    sin recalcular la geometría. Devuelve un booleano sin mutar ninguna entrada.
    """
    x, y, w, h = caja
    if w <= 0 or h <= 0:
        return False

    alto = config.dimensiones.alto
    ancho = config.dimensiones.ancho

    if mascara is not None:
        # Recorte seguro de la caja contra las dimensiones de la imagen
        x1 = max(0, min(x, ancho - 1))
        y1 = max(0, min(y, alto - 1))
        x2 = max(0, min(x + w, ancho))
        y2 = max(0, min(y + h, alto))

        if x1 >= x2 or y1 >= y2:
            return False

        if criterio == "centro":
            cx = max(0, min(x + w // 2, ancho - 1))
            cy = max(0, min(y + h // 2, alto - 1))
            return bool(mascara[cy, cx] > 0)
        elif criterio == "base":
            cx = max(0, min(x + w // 2, ancho - 1))
            by = max(0, min(y + h, alto - 1))
            return bool(mascara[by, cx] > 0)
        elif criterio == "cualquiera":
            return bool(np.any(mascara[y1:y2, x1:x2] > 0))
        elif criterio == "completa":
            esquinas = [
                (x1, y1),
                (max(0, min(x + w - 1, ancho - 1)), y1),
                (x1, max(0, min(y + h - 1, alto - 1))),
                (max(0, min(x + w - 1, ancho - 1)), max(0, min(y + h - 1, alto - 1))),
            ]
            return all(mascara[ey, ex] > 0 for ex, ey in esquinas)
        else:
            raise ValueError(f"Criterio desconocido: '{criterio}'")

    # Evaluación geométrica directa sin máscara precomputada
    if criterio == "centro":
        return punto_en_zona((x + w // 2, y + h // 2), config)
    elif criterio == "base":
        return punto_en_zona((x + w // 2, y + h), config)
    elif criterio == "cualquiera":
        esquinas = [
            (x, y),
            (x + w, y),
            (x, y + h),
            (x + w, y + h),
        ]
        return any(punto_en_zona(p, config) for p in esquinas)
    elif criterio == "completa":
        esquinas = [
            (x, y),
            (x + w, y),
            (x, y + h),
            (x + w, y + h),
        ]
        return all(punto_en_zona(p, config) for p in esquinas)
    else:
        raise ValueError(f"Criterio desconocido: '{criterio}'")


def superponer_zona(
    imagen: np.ndarray,
    config: ZonaConfig,
    alfa_zona: float = 0.35,
    color_zona: Tuple[int, int, int] = (0, 200, 0),
    color_reloj: Tuple[int, int, int] = (0, 0, 200),
    color_linea: Tuple[int, int, int] = (0, 255, 255),
    grosor_linea: int = 3,
) -> np.ndarray:
    """Superpone la zona de análisis y la banda de reloj excluida sobre una imagen.

    Retorna una copia nueva de la imagen sin alterar el arreglo original.
    - Zona de lastre: verde semitransparente.
    - Banda del reloj excluida: roja semitransparente.
    - Línea divisoria: trazo amarillo visible.
    """
    salida = imagen.copy()
    alto, ancho = salida.shape[:2]

    # Capa de color para la mezcla
    capa_color = salida.copy()

    # 1. Pintar zona del lastre
    mascara = construir_mascara_zona(config)
    capa_color[mascara > 0] = color_zona

    # 2. Pintar banda del reloj excluida
    alto_reloj = config.banda_reloj.alto
    if alto_reloj > 0:
        capa_color[0:alto_reloj, :] = color_reloj

    # Mezclar con transparencia
    cv2.addWeighted(capa_color, alfa_zona, salida, 1.0 - alfa_zona, 0, salida)

    # 3. Dibujar el contorno nítido del polígono
    contorno = np.array(config.poligono.como_lista, dtype=np.int32)
    cv2.polylines(salida, [contorno], True, color_linea, grosor_linea, cv2.LINE_AA)

    # 4. Dibujar línea límite de la banda del reloj
    if alto_reloj > 0:
        cv2.line(salida, (0, alto_reloj), (ancho, alto_reloj), (0, 0, 255), 2, cv2.LINE_AA)

    return salida
