"""Lectura de placas sobre el recorte de un vehículo.

El modelo de reconocimiento no encuentra la placa en el cuadro completo,
porque la reescala a unos cientos de píxeles y la placa queda de unos treinta.
Sobre el recorte del vehículo, en cambio, la lee con alta confianza.
"""

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

import numpy as np


class PlacaError(RuntimeError):
    """Excepción lanzada cuando la lectura de placa falla."""


# Margen añadido alrededor de la caja del vehículo. La placa suele quedar
# en el borde inferior y un recorte ajustado puede cortarla.
MARGEN_RECORTE = 0.10


@dataclass(frozen=True)
class LecturaPlaca:
    """Texto leído en un recorte, con su confianza y su recuadro."""
    texto: str
    confianza: float
    caja_placa: Tuple[int, int, int, int]
    confianza_por_caracter: Tuple[float, ...] = ()

    @property
    def confianza_minima(self) -> float:
        """Confianza del carácter menos seguro de la lectura.

        Es más informativa que el promedio: una placa con un solo carácter
        dudoso puede promediar alto y estar mal, como ocurre al confundir
        una W con una M.
        """
        if not self.confianza_por_caracter:
            return self.confianza
        return min(self.confianza_por_caracter)


def recortar_vehiculo(
    cuadro: np.ndarray,
    caja: Tuple[int, int, int, int],
    margen: float = MARGEN_RECORTE,
) -> np.ndarray:
    """Extrae el recorte del vehículo con un margen alrededor.

    Devuelve un arreglo nuevo y nunca modifica el cuadro recibido.
    """
    if not isinstance(cuadro, np.ndarray):
        raise PlacaError(f"El cuadro debe ser un numpy.ndarray, se recibió: {type(cuadro).__name__}")
    if margen < 0:
        raise PlacaError(f"El margen debe ser >= 0, se recibió: {margen}")

    alto_img, ancho_img = cuadro.shape[:2]
    x, y, ancho, alto = caja
    if ancho <= 0 or alto <= 0:
        raise PlacaError(f"La caja debe tener ancho y alto positivos, se recibió: {caja}")

    dx = int(ancho * margen)
    dy = int(alto * margen)
    x1 = max(0, x - dx)
    y1 = max(0, y - dy)
    x2 = min(ancho_img, x + ancho + dx)
    y2 = min(alto_img, y + alto + dy)

    if x1 >= x2 or y1 >= y2:
        raise PlacaError(f"La caja {caja} no intersecta el cuadro de {ancho_img}x{alto_img}")

    return cuadro[y1:y2, x1:x2].copy()


def _confianzas(valor) -> Tuple[float, ...]:
    """Normaliza la confianza entregada por el motor a una tupla por carácter."""
    if isinstance(valor, (list, tuple)):
        return tuple(float(v) for v in valor)
    return (float(valor),)


def _confianza_media(valor) -> float:
    """El motor entrega la confianza por carácter; el resultado es su promedio."""
    por_caracter = _confianzas(valor)
    return sum(por_caracter) / len(por_caracter) if por_caracter else 0.0


class LectorPlacas:
    """Lee las placas presentes en un recorte de vehículo."""

    def __init__(
        self,
        detector_modelo: str = "yolo-v9-t-384-license-plate-end2end",
        ocr_modelo: str = "global-plates-mobile-vit-v2-model",
        proveedores=None,
        alpr=None,
        hilos: Optional[int] = None,
    ) -> None:
        """Prepara el lector. `alpr` permite inyectar un doble en las pruebas."""
        if alpr is not None:
            self._alpr = alpr
            return
        try:
            from fast_alpr import ALPR
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise PlacaError(
                "fast_alpr no está instalado; se requiere para leer placas"
            ) from exc
        from lastre.aceleracion import configurar_opciones_sesion
        sess_options = configurar_opciones_sesion(hilos)
        kwargs = {
            "detector_model": detector_modelo,
            "ocr_model": ocr_modelo,
        }
        if sess_options is not None:
            kwargs["detector_sess_options"] = sess_options
            kwargs["ocr_sess_options"] = sess_options
        if proveedores:
            kwargs["detector_providers"] = list(proveedores)
            kwargs["ocr_providers"] = list(proveedores)

        self._alpr = ALPR(**kwargs)

    @property
    def sesiones(self) -> dict:
        """Modelos internos con sesión ONNX propia, para verificar el acelerador.

        El lector carga dos: el detector de placas y el OCR. Que uno consiga la
        tarjeta no dice nada del otro, así que el lote debe verlos por separado.
        Si la librería cambia de forma, se informa menos pero no se rompe.
        """
        detector = getattr(getattr(self._alpr, "detector", None), "detector", None)
        ocr = getattr(getattr(self._alpr, "ocr", None), "ocr_model", None)
        encontrados = {"detector de placas": detector, "ocr": ocr}
        return {k: v for k, v in encontrados.items() if v is not None}

    def leer(self, recorte: np.ndarray) -> Tuple[LecturaPlaca, ...]:
        """Devuelve todas las placas legibles del recorte, sin modificarlo."""
        if not isinstance(recorte, np.ndarray):
            raise PlacaError(f"El recorte debe ser un numpy.ndarray, se recibió: {type(recorte).__name__}")
        if recorte.size == 0:
            return ()

        try:
            resultados = self._alpr.predict(recorte)
        except Exception as exc:  # pragma: no cover - depende del modelo
            raise PlacaError(f"El motor de lectura falló: {exc}") from exc

        lecturas = []
        for resultado in resultados:
            if resultado.ocr is None or not resultado.ocr.text:
                continue
            caja = resultado.detection.bounding_box
            lecturas.append(
                LecturaPlaca(
                    texto=resultado.ocr.text,
                    confianza=_confianza_media(resultado.ocr.confidence),
                    caja_placa=(caja.x1, caja.y1, caja.x2 - caja.x1, caja.y2 - caja.y1),
                    confianza_por_caracter=_confianzas(resultado.ocr.confidence),
                )
            )

        return tuple(lecturas)

    def leer_vehiculo(
        self,
        cuadro: np.ndarray,
        caja_vehiculo: Tuple[int, int, int, int],
    ) -> Tuple[LecturaPlaca, ...]:
        """Recorta el vehículo del cuadro y lee las placas que contenga."""
        return self.leer(recortar_vehiculo(cuadro, caja_vehiculo))
