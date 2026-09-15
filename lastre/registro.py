"""Registro de todos los vehículos que circulan por la vía de lastre.

La decisión automática de quién sale y quién entra fue la mayor fuente de
error del proceso. Registrar todo vehículo con su sentido, y dejar el filtro
final al analista, evita perder vehículos por una clasificación equivocada:
una columna de sentido errada se corrige mirando la foto, pero un vehículo
descartado se pierde para siempre.
"""

from dataclasses import dataclass
from math import hypot
from typing import Optional, Sequence, Tuple

from lastre.trayectoria import Posicion, Trayectoria


class RegistroError(ValueError):
    """Excepción lanzada cuando los parámetros de registro son inválidos."""


SENTIDO_SALE = "sale"
SENTIDO_ENTRA = "entra"
SENTIDO_INDETERMINADO = "indeterminado"


@dataclass(frozen=True)
class VehiculoRegistrado:
    """Un vehículo observado en la zona, con su sentido de circulación."""
    trayectoria_id: int
    cuadro_inicio: int
    cuadro_fin: int
    observaciones: int
    sentido: str
    desplazamiento_x: int
    caja_representativa: Tuple[int, int, int, int]
    cuadro_representativo: int
    # Las observaciones que componen este vehiculo, incluidas las de sus
    # continuaciones. Es la identidad del vehiculo: quien necesite sus recortes
    # debe leerlas de aqui y nunca reconstruirlas por intervalo de cuadros,
    # porque otro vehiculo puede pasar entero dentro de ese intervalo.
    posiciones: Tuple[Posicion, ...]

    @property
    def sentido_es_claro(self) -> bool:
        """Indica si el sentido pudo determinarse sin ambigüedad."""
        return self.sentido != SENTIDO_INDETERMINADO


def _cuadro_mas_grande(trayectoria: Trayectoria):
    """Devuelve la observación donde el vehículo se ve más grande.

    Es el cuadro más cercano a la cámara y por tanto el mejor candidato para
    leer la placa.
    """
    return max(trayectoria.posiciones, key=lambda p: p.area)


def clasificar_sentido(
    trayectoria: Trayectoria,
    desplazamiento_minimo: int,
) -> str:
    """Determina el sentido según el desplazamiento horizontal neto.

    En esta cámara la vía de lastre queda a la izquierda y la carretera a la
    derecha, de modo que avanzar hacia la derecha equivale a salir.
    """
    if desplazamiento_minimo < 0:
        raise RegistroError(
            f"desplazamiento_minimo debe ser >= 0, se recibió: {desplazamiento_minimo}"
        )

    dx = trayectoria.posiciones[-1].centro[0] - trayectoria.posiciones[0].centro[0]
    if dx >= desplazamiento_minimo:
        return SENTIDO_SALE
    if dx <= -desplazamiento_minimo:
        return SENTIDO_ENTRA
    return SENTIDO_INDETERMINADO


def fusionar_continuaciones(
    trayectorias: Sequence[Trayectoria],
    ventana_cuadros: int,
    distancia_maxima: float,
) -> Tuple[Tuple[Trayectoria, ...], ...]:
    """Agrupa las trayectorias que son continuación de un mismo vehículo.

    El seguimiento pierde un vehículo cuando se detiene, maniobra o queda
    ocluido, y al reaparecer abre una trayectoria nueva. Si esa nueva empieza
    poco después y cerca de donde terminó la anterior, se trata del mismo
    vehículo y no de uno adicional.
    """
    if ventana_cuadros < 0:
        raise RegistroError(f"ventana_cuadros debe ser >= 0, se recibió: {ventana_cuadros}")
    if distancia_maxima < 0:
        raise RegistroError(f"distancia_maxima debe ser >= 0, se recibió: {distancia_maxima}")

    ordenadas = sorted(trayectorias, key=lambda t: t.cuadro_inicio)
    grupos: list[list[Trayectoria]] = []

    for trayectoria in ordenadas:
        inicio = trayectoria.posiciones[0].centro
        destino = None

        for grupo in grupos:
            anterior = grupo[-1]
            hueco = trayectoria.cuadro_inicio - anterior.cuadro_fin
            if not 0 <= hueco <= ventana_cuadros:
                continue
            fin = anterior.posiciones[-1].centro
            distancia = hypot(inicio[0] - fin[0], inicio[1] - fin[1])
            if distancia <= distancia_maxima:
                destino = grupo
                break

        if destino is None:
            grupos.append([trayectoria])
        else:
            destino.append(trayectoria)

    return tuple(tuple(g) for g in grupos)


def registrar_vehiculos(
    trayectorias: Sequence[Trayectoria],
    observaciones_minimas: int,
    desplazamiento_minimo: int,
    ventana_cuadros: int = 60,
    distancia_continuacion: float = 400.0,
) -> Tuple[VehiculoRegistrado, ...]:
    """Convierte las trayectorias en registros de vehículo, descartando el ruido.

    Las trayectorias con menos de `observaciones_minimas` detecciones son
    destellos espurios: en la muestra verificada, los vehículos reales tuvieron
    entre 14 y 76 observaciones, y el ruido nunca pasó de 2.
    """
    if observaciones_minimas < 1:
        raise RegistroError(
            f"observaciones_minimas debe ser >= 1, se recibió: {observaciones_minimas}"
        )

    grupos = fusionar_continuaciones(trayectorias, ventana_cuadros, distancia_continuacion)

    registros = []
    for grupo in grupos:
        posiciones = tuple(p for t in grupo for p in t.posiciones)
        trayectoria = Trayectoria(
            id=grupo[0].id,
            cuadro_inicio=grupo[0].cuadro_inicio,
            cuadro_fin=grupo[-1].cuadro_fin,
            posiciones=posiciones,
        )
        if trayectoria.total_observaciones < observaciones_minimas:
            continue

        mejor = _cuadro_mas_grande(trayectoria)
        dx = trayectoria.posiciones[-1].centro[0] - trayectoria.posiciones[0].centro[0]

        registros.append(
            VehiculoRegistrado(
                trayectoria_id=trayectoria.id,
                cuadro_inicio=trayectoria.cuadro_inicio,
                cuadro_fin=trayectoria.cuadro_fin,
                observaciones=trayectoria.total_observaciones,
                sentido=clasificar_sentido(trayectoria, desplazamiento_minimo),
                desplazamiento_x=int(dx),
                caja_representativa=mejor.caja,
                cuadro_representativo=mejor.cuadro,
                posiciones=trayectoria.posiciones,
            )
        )

    return tuple(sorted(registros, key=lambda r: r.cuadro_inicio))
