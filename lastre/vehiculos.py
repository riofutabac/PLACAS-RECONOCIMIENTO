"""Detección de vehículos por reconocimiento de objetos, acotada a la zona.

Sustituye a la detección por movimiento, que confundía las sombras de la
carretera principal con vehículos y fragmentaba un mismo vehículo en varias
trayectorias. Un modelo de objetos reconoce el vehículo en sí, de modo que
una sombra nunca produce una detección.
"""

from dataclasses import dataclass
from typing import Tuple

import numpy as np

from lastre.config import ZonaConfig
from lastre.deteccion import Deteccion
from lastre.zona import caja_en_zona


class VehiculoDeteccionError(RuntimeError):
    """Excepción lanzada cuando la detección de vehículos falla."""


# Clases del catálogo COCO que corresponden a vehículos de interés
CLASES_VEHICULO = frozenset({"car", "motorcycle", "bus", "truck"})

# Las motocicletas se registran aparte porque su placa usa otro formato
CLASE_MOTOCICLETA = "motorcycle"

TIPO_AUTOMOVIL = "automovil"
TIPO_MOTOCICLETA = "motocicleta"


@dataclass(frozen=True)
class DeteccionVehiculo:
    """Vehículo reconocido en un cuadro, con su clase y confianza."""
    caja: Tuple[int, int, int, int]
    area: int
    centro: Tuple[int, int]
    clase: str
    confianza: float

    @property
    def tipo(self) -> str:
        """Tipo de vehículo en los términos del informe final."""
        return TIPO_MOTOCICLETA if self.clase == CLASE_MOTOCICLETA else TIPO_AUTOMOVIL

    @property
    def como_deteccion(self) -> Deteccion:
        """Vista compatible con el seguimiento, que solo usa caja, área y centro."""
        return Deteccion(caja=self.caja, area=self.area, centro=self.centro)


def _a_deteccion(x1: int, y1: int, x2: int, y2: int, clase: str, confianza: float) -> DeteccionVehiculo:
    """Convierte una caja en coordenadas de esquinas al formato interno."""
    ancho = max(0, x2 - x1)
    alto = max(0, y2 - y1)
    return DeteccionVehiculo(
        caja=(x1, y1, ancho, alto),
        area=ancho * alto,
        centro=(x1 + ancho // 2, y1 + alto // 2),
        clase=clase,
        confianza=float(confianza),
    )


class DetectorVehiculos:
    """Reconoce vehículos en el cuadro y descarta los que están fuera de la zona."""

    def __init__(
        self,
        config: ZonaConfig,
        modelo: str = "rf-detr-small-512-coco",
        confianza_minima: float = 0.5,
        criterio_zona: str = "base",
        proveedores=None,
        detector=None,
    ) -> None:
        """Prepara el detector.

        - `criterio_zona` 'base' usa el punto de contacto del vehículo con el
          suelo, que es lo que determina por qué vía circula. Un vehículo alto
          de la carretera principal puede invadir la zona con su carrocería,
          pero nunca con sus ruedas.
        - `detector` permite inyectar un doble en las pruebas.
        """
        if not 0.0 <= confianza_minima <= 1.0:
            raise VehiculoDeteccionError(
                f"confianza_minima debe estar entre 0 y 1, se recibió: {confianza_minima}"
            )

        self._config = config
        self._confianza_minima = confianza_minima
        self._criterio_zona = criterio_zona

        if detector is not None:
            self._detector = detector
        else:
            try:
                from open_image_models import create_detector
            except ImportError as exc:  # pragma: no cover - depende del entorno
                raise VehiculoDeteccionError(
                    "open_image_models no está instalado; se requiere para detectar vehículos"
                ) from exc
            if proveedores:
                self._detector = create_detector(modelo, providers=list(proveedores))
            else:
                self._detector = create_detector(modelo)

    def detectar(self, cuadro: np.ndarray) -> Tuple[DeteccionVehiculo, ...]:
        """Devuelve los vehículos reconocidos que circulan dentro de la zona.

        No modifica el cuadro recibido.
        """
        if not isinstance(cuadro, np.ndarray):
            raise VehiculoDeteccionError(
                f"El cuadro debe ser un numpy.ndarray, se recibió: {type(cuadro).__name__}"
            )

        try:
            crudas = self._detector.predict(cuadro)
        except Exception as exc:  # pragma: no cover - depende del modelo
            raise VehiculoDeteccionError(f"El modelo de detección falló: {exc}") from exc

        vehiculos = {}
        for cruda in crudas:
            if cruda.label not in CLASES_VEHICULO:
                continue
            if cruda.confidence < self._confianza_minima:
                continue

            caja = cruda.bounding_box
            deteccion = _a_deteccion(caja.x1, caja.y1, caja.x2, caja.y2, cruda.label, cruda.confidence)
            if deteccion.area <= 0:
                continue
            if not caja_en_zona(deteccion.caja, self._config, criterio=self._criterio_zona):
                continue

            # RF-DETR puede emitir la misma caja con varias etiquetas COCO.
            # Deduplicar antes del seguimiento evita sembrar pistas paralelas.
            # Cajas distintas se conservan; en empate gana la primera etiqueta.
            anterior = vehiculos.get(deteccion.caja)
            if anterior is None or deteccion.confianza > anterior.confianza:
                vehiculos[deteccion.caja] = deteccion

        return tuple(vehiculos.values())


class DetectorHibrido:
    """Combina un filtro barato de movimiento con la confirmación por modelo.

    La mayoría de los cuadros no contiene ningún vehículo, y correr el modelo
    de objetos en todos ellos es desperdicio. El movimiento indica en qué
    cuadros vale la pena mirar; el modelo decide si lo que se movió es un
    vehículo o solo una sombra.
    """

    def __init__(
        self,
        detector_movimiento,
        detector_vehiculos: DetectorVehiculos,
        paso: int = 3,
        paso_movimiento: int = 1,
    ) -> None:
        """Prepara el detector combinado.

        - `paso` limita la confirmación a uno de cada N cuadros con movimiento,
          porque un vehículo permanece visible durante decenas de cuadros.
        - `paso_movimiento` saltea cuadros también en el filtro barato, que
          resultó ser la etapa más costosa. A 25 cuadros por segundo, mirar uno
          de cada dos deja ocho centésimas entre miradas, tiempo en que ningún
          vehículo alcanza a cruzar la zona.
        """
        if paso < 1:
            raise VehiculoDeteccionError(f"paso debe ser >= 1, se recibió: {paso}")
        if paso_movimiento < 1:
            raise VehiculoDeteccionError(
                f"paso_movimiento debe ser >= 1, se recibió: {paso_movimiento}")

        self._movimiento = detector_movimiento
        self._vehiculos = detector_vehiculos
        self._paso = paso
        self._paso_movimiento = paso_movimiento
        self._cuadros_vistos = 0
        self._cuadros_con_movimiento = 0
        self._cuadros_confirmados = 0

    @property
    def estadisticas(self) -> dict:
        """Cuántos cuadros activaron el filtro y en cuántos corrió el modelo."""
        return {
            "cuadros_vistos": self._cuadros_vistos,
            "cuadros_con_movimiento": self._cuadros_con_movimiento,
            "cuadros_confirmados": self._cuadros_confirmados,
        }

    def detectar(self, cuadro: np.ndarray) -> Tuple[DeteccionVehiculo, ...]:
        """Devuelve los vehículos confirmados, o vacío si no hay nada que mirar."""
        self._cuadros_vistos += 1
        if self._cuadros_vistos % self._paso_movimiento:
            return ()

        if not self._movimiento.detectar(cuadro):
            return ()

        self._cuadros_con_movimiento += 1
        if self._cuadros_con_movimiento % self._paso:
            return ()

        self._cuadros_confirmados += 1
        return self._vehiculos.detectar(cuadro)
