"""Fusión de registros que corresponden a un mismo vehículo.

Cuando el seguimiento pierde un vehículo durante varios segundos, la fusión
por cercanía espacial ya no alcanza. Una placa validada permite unir fragmentos
compatibles, pero nunca observaciones simultáneas ni lecturas pendientes.
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
    lecturas: int = 0
    trayectoria_id: Optional[int] = None
    cuadro_inicio: Optional[int] = None
    cuadro_fin: Optional[int] = None

    @property
    def fue_duplicado(self) -> bool:
        """Indica si el registro resultó de fusionar varias apariciones."""
        return self.registros_fusionados > 1


def _son_compatibles(a: dict, b: dict) -> bool:
    """Descarta contradicciones de confianza, dirección y coexistencia."""
    if a.get("estado") != "validado" or b.get("estado") != "validado":
        return False
    sentidos = {a.get("sentido"), b.get("sentido")}
    if "entra" in sentidos and "sale" in sentidos:
        return False
    limites = (a.get("cuadro_inicio"), a.get("cuadro_fin"),
               b.get("cuadro_inicio"), b.get("cuadro_fin"))
    if all(limite is not None for limite in limites):
        inicio_a, fin_a, inicio_b, fin_b = limites
        if max(inicio_a, inicio_b) <= min(fin_a, fin_b):
            return False
    return True


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
                if not all(_son_compatibles(registro, miembro) for miembro in grupo):
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
        tiene_intervalos = all(
            r.get("cuadro_inicio") is not None and r.get("cuadro_fin") is not None
            for r in grupo
        )
        finales.append(
            RegistroFinal(
                placa=mejor.get("placa"),
                cuadro=grupo[0]["cuadro"],
                sentido=mejor["sentido"],
                confianza=mejor.get("confianza", 0.0),
                estado=mejor["estado"],
                imagen=mejor.get("imagen", ""),
                registros_fusionados=len(grupo),
                lecturas=mejor.get("lecturas", 0),
                trayectoria_id=grupo[0].get("trayectoria_id"),
                cuadro_inicio=min(r["cuadro_inicio"] for r in grupo) if tiene_intervalos else None,
                cuadro_fin=max(r["cuadro_fin"] for r in grupo) if tiene_intervalos else None,
            )
        )

    return tuple(finales)
