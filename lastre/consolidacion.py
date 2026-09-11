"""Consolidación de salidas fragmentadas en vehículos únicos.

Un mismo vehículo puede romperse en varias trayectorias cuando el
seguimiento lo pierde momentáneamente. Dos cruces que ocurren casi al
mismo tiempo y casi en el mismo lugar corresponden al mismo vehículo.
"""

from dataclasses import dataclass
from math import hypot
from typing import Sequence, Tuple


class ConsolidacionError(ValueError):
    """Excepción lanzada cuando los parámetros de consolidación son inválidos."""


@dataclass(frozen=True)
class Vehiculo:
    """Vehículo único resultante de fusionar una o más salidas fragmentadas."""
    numero: int
    cuadro_cruce: int
    centro_cruce: Tuple[int, int]
    caja_cruce: Tuple[int, int, int, int]
    imagen_evidencia: str
    trayectorias_fusionadas: Tuple[int, ...]

    @property
    def fue_fragmentado(self) -> bool:
        """Indica si el vehículo provino de más de una trayectoria."""
        return len(self.trayectorias_fusionadas) > 1


def consolidar_salidas(
    salidas: Sequence[dict],
    ventana_cuadros: int,
    distancia_maxima: float,
) -> Tuple[Vehiculo, ...]:
    """Fusiona salidas cercanas en tiempo y espacio en vehículos únicos.

    Dos salidas se consideran el mismo vehículo cuando sus cuadros de cruce
    distan menos de `ventana_cuadros` y sus centros de cruce distan menos de
    `distancia_maxima` píxeles. Devuelve una tupla nueva sin mutar la entrada.
    """
    if ventana_cuadros < 0:
        raise ConsolidacionError(f"ventana_cuadros debe ser >= 0, se recibió: {ventana_cuadros}")
    if distancia_maxima < 0:
        raise ConsolidacionError(f"distancia_maxima debe ser >= 0, se recibió: {distancia_maxima}")

    ordenadas = sorted(salidas, key=lambda s: s["cuadro_cruce"])
    grupos: list[list[dict]] = []

    for salida in ordenadas:
        centro = tuple(salida["centro_cruce"])
        cuadro = salida["cuadro_cruce"]
        destino = None

        for grupo in grupos:
            referencia = grupo[-1]
            cerca_en_tiempo = abs(cuadro - referencia["cuadro_cruce"]) <= ventana_cuadros
            distancia = hypot(
                centro[0] - referencia["centro_cruce"][0],
                centro[1] - referencia["centro_cruce"][1],
            )
            if cerca_en_tiempo and distancia <= distancia_maxima:
                destino = grupo
                break

        if destino is None:
            grupos.append([salida])
        else:
            destino.append(salida)

    vehiculos = []
    for numero, grupo in enumerate(grupos, start=1):
        # El cruce más largo es el más representativo del vehículo
        principal = max(grupo, key=lambda s: s["duracion_cuadros"])
        vehiculos.append(
            Vehiculo(
                numero=numero,
                cuadro_cruce=principal["cuadro_cruce"],
                centro_cruce=tuple(principal["centro_cruce"]),
                caja_cruce=tuple(principal["caja_cruce"]),
                imagen_evidencia=principal["imagen_evidencia"],
                trayectorias_fusionadas=tuple(s["trayectoria_id"] for s in grupo),
            )
        )

    return tuple(vehiculos)
