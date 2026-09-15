"""Módulo de detección de movimiento acotado a la zona de análisis."""

from dataclasses import dataclass
from typing import Tuple
import cv2
import numpy as np

from lastre.config import ZonaConfig
from lastre.zona import construir_mascara_zona


# MOG2 marca el primer plano con 255 y las sombras con 127
VALOR_PRIMER_PLANO = 255


def _recuadro_de(mascara: np.ndarray, ancho: int, alto: int) -> Tuple[int, int, int, int]:
    """Devuelve (x_ini, y_ini, x_fin, y_fin) del area util de la mascara.

    Una mascara vacia no tiene recuadro: se conserva el cuadro entero para no
    romper la detección con un recorte de tamaño cero.
    """
    columnas = np.flatnonzero(mascara.any(axis=0))
    filas = np.flatnonzero(mascara.any(axis=1))
    if columnas.size == 0 or filas.size == 0:
        return (0, 0, ancho, alto)
    return (int(columnas[0]), int(filas[0]), int(columnas[-1]) + 1, int(filas[-1]) + 1)


class DeteccionError(RuntimeError):
    """Excepción lanzada cuando ocurre un error durante el proceso de detección."""
    pass


@dataclass(frozen=True)
class Deteccion:
    """Representa un objeto móvil detectado en un cuadro individual."""
    caja: Tuple[int, int, int, int]  # (x, y, ancho, alto) en coordenadas originales
    area: int                        # Área en píxeles (escala original)
    centro: Tuple[int, int]          # (x_centro, y_centro)


class DetectorMovimiento:
    """Detector de movimiento basado en sustracción de fondo (MOG2) acotado a la zona."""

    def __init__(
        self,
        config: ZonaConfig,
        historial: int = 300,
        umbral_varianza: float = 40.0,
        factor_escala: float = 1.0,
    ) -> None:
        """Inicializa el detector con la configuración de la zona y parámetros MOG2.

        Parámetros:
        - config: Configuración inmutable de la zona.
        - historial: Número de cuadros para modelar el fondo (por defecto 300).
        - umbral_varianza: Umbral Mahalanobis para clasificar primer plano (por defecto 40.0).
        - factor_escala: Factor de reducción espacial para acelerar el procesamiento (ej. 0.25).
          Las detecciones se reescalan siempre a las coordenadas originales del video.
        """
        if factor_escala <= 0.0 or factor_escala > 1.0:
            raise DeteccionError(f"factor_escala debe estar en el rango (0.0, 1.0], recibido: {factor_escala}")

        self._config = config
        self._historial = historial
        self._umbral_varianza = umbral_varianza
        self._factor_escala = factor_escala

        # Construcción de la máscara binaria completa
        self._mascara_completa = construir_mascara_zona(config)

        # Preparar dimensiones de procesamiento
        ancho_orig = config.dimensiones.ancho
        alto_orig = config.dimensiones.alto
        self._ancho_proc = max(1, int(ancho_orig * factor_escala))
        self._alto_proc = max(1, int(alto_orig * factor_escala))

        if self._factor_escala < 1.0:
            mascara_escalada = cv2.resize(
                self._mascara_completa,
                (self._ancho_proc, self._alto_proc),
                interpolation=cv2.INTER_NEAREST,
            )
        else:
            mascara_escalada = self._mascara_completa.copy()

        # MOG2 modela cada pixel por separado, asi que los de fuera de la zona
        # nunca influyen en los de dentro: recortar al recuadro que contiene
        # el poligono da exactamente las mismas detecciones y ahorra modelar
        # mas de la mitad del cuadro que la mascara descartaba despues.
        self._recorte = _recuadro_de(mascara_escalada, self._ancho_proc, self._alto_proc)
        x_ini, y_ini, x_fin, y_fin = self._recorte
        self._mascara_proc = mascara_escalada[y_ini:y_fin, x_ini:x_fin]

        # Elementos estructurantes para limpieza morfológica
        self._kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        self._kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

        # Sustractor de fondo MOG2 con detección de sombras desactivada
        # (mitiga falsos positivos causados por sombras vespertinas sobre el asfalto)
        self._sustractor = cv2.createBackgroundSubtractorMOG2(
            history=historial,
            varThreshold=umbral_varianza,
            detectShadows=True,
        )

    @property
    def dimensiones_procesadas(self) -> Tuple[int, int]:
        """(ancho, alto) que MOG2 modela realmente, ya recortado a la zona."""
        x_ini, y_ini, x_fin, y_fin = self._recorte
        return (x_fin - x_ini, y_fin - y_ini)

    def reiniciar(self) -> None:
        """Reinicia el modelo de fondo del sustractor."""
        self._sustractor = cv2.createBackgroundSubtractorMOG2(
            history=self._historial,
            varThreshold=self._umbral_varianza,
            detectShadows=True,
        )

    def detectar(self, cuadro: np.ndarray) -> Tuple[Deteccion, ...]:
        """Detecta objetos en movimiento dentro de la zona para el cuadro proporcionado.

        Retorna una tupla de detecciones en coordenadas de la resolución original.
        No modifica el arreglo del cuadro recibido.
        """
        if not isinstance(cuadro, np.ndarray):
            raise DeteccionError(f"El cuadro debe ser un numpy.ndarray, se recibió: {type(cuadro).__name__}")

        alto_in, ancho_in = cuadro.shape[:2]
        if alto_in != self._config.dimensiones.alto or ancho_in != self._config.dimensiones.ancho:
            raise DeteccionError(
                f"Dimensiones del cuadro ({ancho_in}x{alto_in}) no coinciden con la configuración "
                f"({self._config.dimensiones.ancho}x{self._config.dimensiones.alto})"
            )

        # 1. Escalar si es requerido para velocidad de procesamiento
        if self._factor_escala < 1.0:
            cuadro_proc = cv2.resize(
                cuadro,
                (self._ancho_proc, self._alto_proc),
                interpolation=cv2.INTER_LINEAR,
            )
        else:
            cuadro_proc = cuadro

        x_ini, y_ini, x_fin, y_fin = self._recorte
        cuadro_proc = cuadro_proc[y_ini:y_fin, x_ini:x_fin]

        # 2. Aplicar sustracción de fondo
        fg = self._sustractor.apply(cuadro_proc)

        # 3. Descartar las sombras. MOG2 las marca con el valor 127, y las sombras
        #    de los vehículos de la carretera principal caen dentro del polígono.
        _, fg = cv2.threshold(fg, VALOR_PRIMER_PLANO - 1, 255, cv2.THRESH_BINARY)

        # 4. Restringir la detección estrictamente a la máscara de la zona
        fg_zona = cv2.bitwise_and(fg, self._mascara_proc)

        # 5. Operaciones morfológicas para eliminar ruido y consolidar siluetas
        fg_limpio = cv2.morphologyEx(fg_zona, cv2.MORPH_OPEN, self._kernel_open)
        fg_limpio = cv2.morphologyEx(fg_limpio, cv2.MORPH_CLOSE, self._kernel_close)

        # 6. Encontrar contornos externos
        contornos, _ = cv2.findContours(fg_limpio, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        inv_escala = 1.0 / self._factor_escala
        factor_area = inv_escala * inv_escala
        area_minima = self._config.deteccion.area_minima

        detecciones = []
        for c in contornos:
            area_contorno = cv2.contourArea(c) * factor_area
            if area_contorno < area_minima:
                continue

            x, y, w, h = cv2.boundingRect(c)
            # Los contornos vienen en coordenadas del recorte: primero se
            # devuelven al cuadro reducido completo y luego al original.
            x += x_ini
            y += y_ini
            orig_x = int(round(x * inv_escala))
            orig_y = int(round(y * inv_escala))
            orig_w = int(round(w * inv_escala))
            orig_h = int(round(h * inv_escala))

            # Asegurar límites válidos
            orig_x = max(0, min(orig_x, self._config.dimensiones.ancho - 1))
            orig_y = max(0, min(orig_y, self._config.dimensiones.alto - 1))
            orig_w = min(orig_w, self._config.dimensiones.ancho - orig_x)
            orig_h = min(orig_h, self._config.dimensiones.alto - orig_y)

            if orig_w <= 0 or orig_h <= 0:
                continue

            cx = orig_x + orig_w // 2
            cy = orig_y + orig_h // 2

            detecciones.append(
                Deteccion(
                    caja=(orig_x, orig_y, orig_w, orig_h),
                    area=int(round(area_contorno)),
                    centro=(cx, cy),
                )
            )

        # Ordenar detecciones por área descendente
        detecciones.sort(key=lambda d: d.area, reverse=True)
        return tuple(detecciones)
