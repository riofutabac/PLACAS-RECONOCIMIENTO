"""Almacén de recortes de vehículos para lectura de placas y evidencia.

Guardar el cuadro completo comprimido en cada cuadro con pistas activas
costaba unos 142 ms y acumulaba ~3.3 GB por video, y casi todo ese píxel
se descartaba: el lector solo mira la caja del vehículo. El recorte de esa
caja cuesta alrededor de 10 ms y es lo único que alguien vuelve a abrir.

El recorte se guarda con el margen del lector ya aplicado, de modo que quien
lo consuma use `LectorPlacas.leer` y no `leer_vehiculo`: aplicar el margen
por segunda vez agranda la ventana y puede arrastrar la placa del vecino.
"""

from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from lastre.placa import PlacaError, recortar_vehiculo
from lastre.trayectoria import Posicion

CALIDAD_JPEG = 92

Clave = Tuple[int, Tuple[int, int, int, int]]


class EvidenciaError(ValueError):
    """Excepción lanzada cuando un recorte no puede almacenarse."""


def clave_de(numero_cuadro: int, caja: Tuple[int, int, int, int]) -> Clave:
    """Identifica una observación sin ambigüedad.

    El número de cuadro no alcanza como clave: dos vehículos pueden aparecer
    en el mismo cuadro, y entonces uno sobrescribiría el recorte del otro.
    """
    return (numero_cuadro, tuple(caja))


class AlmacenRecortes:
    """Guarda en memoria el recorte comprimido de cada observación."""

    def __init__(self, calidad: int = CALIDAD_JPEG) -> None:
        """Prepara el almacén.

        - `calidad`: calidad JPEG del recorte, entre 1 y 100.
        """
        if not 1 <= calidad <= 100:
            raise EvidenciaError(
                f"calidad debe estar entre 1 y 100, se recibió: {calidad}"
            )

        self._calidad = calidad
        self._recortes: Dict[Clave, bytes] = {}
        self._permanentes: set[Clave] = set()
        self._mejores: Dict[int, Tuple[float, Clave]] = {}
        self._referencias: Dict[Clave, int] = {}

    def __len__(self) -> int:
        """Cantidad de observaciones almacenadas."""
        return len(self._recortes)

    @property
    def bytes_totales(self) -> int:
        """Memoria ocupada por los recortes, para poder vigilarla por video."""
        return sum(len(v) for v in self._recortes.values())

    def guardar(
        self,
        numero_cuadro: int,
        caja: Tuple[int, int, int, int],
        cuadro: np.ndarray,
    ) -> None:
        """Comprime y guarda el recorte de esta observación.

        Guardar dos veces la misma observación no duplica el almacenamiento.
        """
        self._comprimir(numero_cuadro, caja, cuadro)
        self._permanentes.add(clave_de(numero_cuadro, caja))

    def guardar_observacion(
        self, id_pista: int, posicion: Posicion, cuadro: np.ndarray,
        area_minima: int,
    ) -> None:
        """Conserva todos los candidatos OCR y la mejor evidencia por pista.

        Las continuaciones conservan representantes independientes: el registro
        final puede elegir la mejor de ellas después de fusionar las pistas.
        Los empates mantienen la primera, como registrar_vehiculos.
        """
        if area_minima < 0:
            raise EvidenciaError("area_minima debe ser >= 0")
        clave = clave_de(posicion.cuadro, posicion.caja)
        anterior = self._mejores.get(id_pista)
        es_mejor = anterior is None or posicion.area > anterior[0]
        es_candidato = posicion.area >= area_minima
        if not es_candidato and not es_mejor:
            return

        # No reemplazar evidencia válida si falla la nueva compresión.
        self._comprimir(posicion.cuadro, posicion.caja, cuadro)
        if es_candidato:
            self._permanentes.add(clave)
        if not es_mejor:
            return

        self._mejores[id_pista] = (posicion.area, clave)
        self._referencias[clave] = self._referencias.get(clave, 0) + 1
        if anterior is not None:
            vieja = anterior[1]
            self._referencias[vieja] -= 1
            if self._referencias[vieja] == 0:
                del self._referencias[vieja]
                if vieja not in self._permanentes:
                    del self._recortes[vieja]

    def _comprimir(
        self, numero_cuadro: int, caja: Tuple[int, int, int, int],
        cuadro: np.ndarray,
    ) -> None:
        clave = clave_de(numero_cuadro, caja)
        if clave in self._recortes:
            return

        try:
            recorte = recortar_vehiculo(cuadro, caja)
        except PlacaError as exc:
            raise EvidenciaError(
                f"No se pudo recortar la observación {clave}: {exc}"
            ) from exc

        try:
            ok, codificado = cv2.imencode(
                ".jpg", recorte, [cv2.IMWRITE_JPEG_QUALITY, self._calidad]
            )
        except cv2.error as exc:
            raise EvidenciaError(f"No se pudo comprimir el recorte {clave}: {exc}") from exc
        if not ok:
            raise EvidenciaError(f"No se pudo comprimir el recorte {clave}")

        self._recortes[clave] = codificado.tobytes()

    def obtener(
        self,
        numero_cuadro: int,
        caja: Tuple[int, int, int, int],
    ) -> Optional[np.ndarray]:
        """Devuelve el recorte de esta observación, o None si no se guardó."""
        codificado = self._recortes.get(clave_de(numero_cuadro, caja))
        if codificado is None:
            return None
        try:
            recorte = cv2.imdecode(np.frombuffer(codificado, np.uint8), cv2.IMREAD_COLOR)
        except cv2.error as exc:
            raise EvidenciaError(f"No se pudo decodificar el recorte {numero_cuadro}: {exc}") from exc
        if recorte is None:
            raise EvidenciaError(f"Recorte almacenado ilegible en cuadro {numero_cuadro}")
        return recorte
