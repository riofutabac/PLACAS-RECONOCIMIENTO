"""Agenda de observaciones que hay que visitar en el video.

Recorrer el video es secuencial y caro, así que conviene saber de antemano
qué observaciones se van a mirar en cada cuadro. Son de dos clases:

- candidatas a OCR: las suficientemente grandes para que el lector distinga
  los caracteres. Leer las demás es trabajo perdido.
- evidencia: la observación donde el vehículo se ve más grande. Se visita
  aunque no sea candidata, porque un vehículo sin placa legible sigue
  necesitando una foto con la que el analista pueda verificarlo a mano.
"""

from dataclasses import dataclass
from typing import Dict, Sequence, Tuple


class AgendaError(ValueError):
    """Excepción lanzada cuando los parámetros de la agenda son inválidos."""


@dataclass(frozen=True)
class Tarea:
    """Una observación que debe recortarse cuando el video llegue a su cuadro."""
    indice: int
    cuadro: int
    caja: Tuple[int, int, int, int]
    es_candidato: bool
    # La observacion donde el vehiculo se ve mas grande. Su recorte se guarda
    # siempre, sin esperar a que el OCR prospere: un candidato puede fallar la
    # lectura y el vehiculo quedarse sin ninguna foto.
    es_evidencia: bool = False


Agenda = Dict[int, Tuple[Tarea, ...]]


def construir_agenda(vehiculos: Sequence, area_minima: int) -> Agenda:
    """Agrupa por cuadro las observaciones que hay que recortar.

    Cada vehículo aporta sus candidatas a OCR y, si ninguna lo es, su
    observación representativa como evidencia.
    """
    if area_minima < 0:
        raise AgendaError(f"area_minima debe ser >= 0, se recibió: {area_minima}")

    agenda: Dict[int, list] = {}

    for indice, vehiculo in enumerate(vehiculos):
        candidatos = tuple(
            p for p in vehiculo.posiciones if p.area >= area_minima
        )
        representativo = vehiculo.cuadro_representativo

        for posicion in candidatos:
            agenda.setdefault(posicion.cuadro, []).append(
                Tarea(
                    indice,
                    posicion.cuadro,
                    posicion.caja,
                    es_candidato=True,
                    es_evidencia=(posicion.cuadro == representativo
                                  and posicion.caja == vehiculo.caja_representativa),
                )
            )

        # La representativa ya está agendada cuando es candidata: visitarla de
        # nuevo duplicaría el recorte y la lectura.
        if candidatos:
            continue

        agenda.setdefault(representativo, []).append(
            Tarea(
                indice,
                representativo,
                vehiculo.caja_representativa,
                es_candidato=False,
                es_evidencia=True,
            )
        )

    return {cuadro: tuple(tareas) for cuadro, tareas in sorted(agenda.items())}


def ultimo_cuadro_necesario(agenda: Agenda) -> int:
    """Último cuadro que hay que leer del video.

    Cortar en el último candidato OCR dejaría sin foto a los vehículos cuya
    evidencia aparece después.
    """
    return max(agenda) if agenda else 0


def tareas_por_vehiculo(agenda: Agenda) -> Dict[int, Tuple[Tarea, ...]]:
    """Reagrupa la agenda por vehículo, en orden de cuadro.

    El lote recorre vehículos y el script independiente recorre cuadros, pero
    ambos deben partir de la misma selección de observaciones.
    """
    por_vehiculo: Dict[int, list] = {}
    for cuadro in sorted(agenda):
        for tarea in agenda[cuadro]:
            por_vehiculo.setdefault(tarea.indice, []).append(tarea)
    return {indice: tuple(tareas) for indice, tareas in por_vehiculo.items()}
