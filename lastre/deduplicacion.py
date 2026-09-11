"""Fusión de registros que corresponden a un mismo vehículo.

Cuando el seguimiento pierde un vehículo durante varios segundos, la fusión
por cercanía espacial ya no alcanza. La placa, en cambio, es identidad: dos
registros con la misma placa en un intervalo corto son el mismo vehículo.
"""

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple


class DeduplicacionError(ValueError):
    """Excepción lanzada cuando los parámetros de deduplicación son inválidos."""


@dataclass(frozen=True)
class RegistroFinal:
    """Registro listo para el listado, ya libre de duplicados."""
    placa: Optional[str]
    cuadro: int
    sentido: str
    confianza: float
    estado: str
    imagen: str
    registros_fusionados: int

    @property
    def fue_duplicado(self) -> bool:
        """Indica si el registro resultó de fusionar varias apariciones."""
        return self.registros_fusionados > 1


def deduplicar_por_placa(
    registros: Sequence[dict],
    ventana_cuadros: int,
) -> Tuple[RegistroFinal, ...]:
    """Fusiona los registros que comparten placa dentro de una ventana de tiempo.

    Los registros sin placa nunca se fusionan entre sí: sin identidad no hay
    forma de afirmar que sean el mismo vehículo, y perder uno es peor que
    dejar un duplicado.
    """
    if ventana_cuadros < 0:
        raise DeduplicacionError(
            f"ventana_cuadros debe ser >= 0, se recibió: {ventana_cuadros}"
        )

    ordenados = sorted(registros, key=lambda r: r["cuadro"])
    grupos: list[list[dict]] = []

    for registro in ordenados:
        placa = registro.get("placa")
        destino = None

        if placa:
            for grupo in grupos:
                if grupo[-1].get("placa") != placa:
                    continue
                if registro["cuadro"] - grupo[-1]["cuadro"] <= ventana_cuadros:
                    destino = grupo
                    break

        if destino is None:
            grupos.append([registro])
        else:
            destino.append(registro)

    finales = []
    for grupo in grupos:
        # Se conserva la aparición de mayor confianza como representativa
        mejor = max(grupo, key=lambda r: r.get("confianza", 0.0))
        finales.append(
            RegistroFinal(
                placa=mejor.get("placa"),
                cuadro=grupo[0]["cuadro"],
                sentido=mejor["sentido"],
                confianza=mejor.get("confianza", 0.0),
                estado=mejor["estado"],
                imagen=mejor.get("imagen", ""),
                registros_fusionados=len(grupo),
            )
        )

    return tuple(finales)
