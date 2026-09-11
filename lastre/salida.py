"""Módulo de clasificación de trayectorias y detección de eventos de salida."""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple
import numpy as np

from lastre.config import ZonaConfig
from lastre.trayectoria import Trayectoria


class SalidaError(ValueError):
    """Excepción lanzada ante inconsistencias en la evaluación de salidas."""
    pass


CATEGORIA_SALIDA = "salida"
CATEGORIA_ENTRADA = "entrada"
CATEGORIA_PERMANENCIA = "permanencia"
CATEGORIA_RUIDO = "ruido"


@dataclass(frozen=True)
class ResultadoClasificacion:
    """Resultado inmutable de la clasificación de una trayectoria vehicular."""
    trayectoria_id: int
    categoria: str
    es_salida: bool
    cuadro_cruce: Optional[int]
    caja_cruce: Optional[Tuple[int, int, int, int]]
    centro_cruce: Optional[Tuple[int, int]]
    razon: str


def _orientacion(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
) -> float:
    """Producto vectorial 2D que indica de qué lado del vector p1->p2 se encuentra p3.

    > 0: a la izquierda del vector.
    < 0: a la derecha del vector.
    = 0: colineal.
    """
    return (p2[0] - p1[0]) * (p3[1] - p1[1]) - (p2[1] - p1[1]) * (p3[0] - p1[0])


def _segmentos_se_cruzan(
    a: Tuple[float, float],
    b: Tuple[float, float],
    c: Tuple[float, float],
    d: Tuple[float, float],
) -> bool:
    """Determina si el segmento AB se cruza geométricamente con el segmento CD."""
    o1 = _orientacion(a, b, c)
    o2 = _orientacion(a, b, d)
    o3 = _orientacion(c, d, a)
    o4 = _orientacion(c, d, b)

    # Cruce estricto o sobre el segmento
    if ((o1 > 0 and o2 < 0) or (o1 < 0 and o2 > 0)) and ((o3 > 0 and o4 < 0) or (o3 < 0 and o4 > 0)):
        return True

    return False


def clasificar_trayectoria(
    trayectoria: Trayectoria,
    config: ZonaConfig,
    desplazamiento_minimo: float = 30.0,
) -> ResultadoClasificacion:
    """Evalúa una trayectoria y determina si corresponde a una salida válida hacia la carretera.

    Criterios:
    1. Si total_observaciones < config.seguimiento.minimo_cuadros -> RUIDO.
    2. Si desplazamiento_neto < desplazamiento_minimo -> RUIDO (ej. vehículo estacionado o vibración).
    3. Si cruza el segmento de salida desde la zona interior hacia el exterior -> SALIDA.
    4. Si cruza en sentido inverso (desde exterior hacia interior) -> ENTRADA.
    5. Si se desplaza dentro de la zona sin cruzar el segmento -> PERMANENCIA.
    """
    tid = trayectoria.id

    # 1. Filtro de duración mínima (descarte de ruido)
    min_cuadros = config.seguimiento.minimo_cuadros
    if trayectoria.total_observaciones < min_cuadros:
        return ResultadoClasificacion(
            trayectoria_id=tid,
            categoria=CATEGORIA_RUIDO,
            es_salida=False,
            cuadro_cruce=None,
            caja_cruce=None,
            centro_cruce=None,
            razon=f"Duración insuficiente ({trayectoria.total_observaciones} < {min_cuadros} cuadros)",
        )

    # 2. Filtro de desplazamiento neto mínimo
    if trayectoria.desplazamiento_neto < desplazamiento_minimo:
        return ResultadoClasificacion(
            trayectoria_id=tid,
            categoria=CATEGORIA_RUIDO,
            es_salida=False,
            cuadro_cruce=None,
            caja_cruce=None,
            centro_cruce=None,
            razon=f"Desplazamiento neto despreciable ({trayectoria.desplazamiento_neto:.1f} < {desplazamiento_minimo} px)",
        )

    # Puntos del segmento de salida
    seg_a = (
        float(config.segmento_salida.punto_inicio.x),
        float(config.segmento_salida.punto_inicio.y),
    )
    seg_b = (
        float(config.segmento_salida.punto_fin.x),
        float(config.segmento_salida.punto_fin.y),
    )

    # Determinar qué lado de la línea divisoria es el interior del polígono
    vertices = config.poligono.como_lista
    centroide_x = float(sum(v[0] for v in vertices) / len(vertices))
    centroide_y = float(sum(v[1] for v in vertices) / len(vertices))
    orientacion_interior = _orientacion(seg_a, seg_b, (centroide_x, centroide_y))

    if abs(orientacion_interior) < 1e-5:
        raise SalidaError("El segmento de salida pasa por el centroide del polígono y es ambiguo")

    signo_interior = 1.0 if orientacion_interior > 0 else -1.0

    # 3. Analizar pares consecutivos de posiciones para detectar el evento de cruce
    posiciones = trayectoria.posiciones
    cruce_salida_idx: Optional[int] = None
    cruce_entrada_idx: Optional[int] = None

    for i in range(len(posiciones) - 1):
        p1 = (float(posiciones[i].centro[0]), float(posiciones[i].centro[1]))
        p2 = (float(posiciones[i + 1].centro[0]), float(posiciones[i + 1].centro[1]))

        if _segmentos_se_cruzan(seg_a, seg_b, p1, p2):
            o_p1 = _orientacion(seg_a, seg_b, p1)
            o_p2 = _orientacion(seg_a, seg_b, p2)

            # De interior hacia exterior -> Salida
            if (o_p1 * signo_interior >= 0) and (o_p2 * signo_interior < 0):
                cruce_salida_idx = i + 1
            # De exterior hacia interior -> Entrada
            elif (o_p1 * signo_interior <= 0) and (o_p2 * signo_interior > 0):
                cruce_entrada_idx = i + 1

    # También verificar si la última posición terminó al exterior habiendo iniciado al interior
    # y aproximándose al segmento de salida
    if cruce_salida_idx is not None:
        pos_cruce = posiciones[cruce_salida_idx]
        return ResultadoClasificacion(
            trayectoria_id=tid,
            categoria=CATEGORIA_SALIDA,
            es_salida=True,
            cuadro_cruce=pos_cruce.cuadro,
            caja_cruce=pos_cruce.caja,
            centro_cruce=pos_cruce.centro,
            razon="Cruce confirmado del segmento de salida hacia la carretera principal",
        )

    if cruce_entrada_idx is not None:
        pos_cruce = posiciones[cruce_entrada_idx]
        return ResultadoClasificacion(
            trayectoria_id=tid,
            categoria=CATEGORIA_ENTRADA,
            es_salida=False,
            cuadro_cruce=pos_cruce.cuadro,
            caja_cruce=pos_cruce.caja,
            centro_cruce=pos_cruce.centro,
            razon="Cruce en sentido contrario (ingreso desde la carretera hacia el lastre)",
        )

    # Si no cruzó la línea
    return ResultadoClasificacion(
        trayectoria_id=tid,
        categoria=CATEGORIA_PERMANENCIA,
        es_salida=False,
        cuadro_cruce=None,
        caja_cruce=None,
        centro_cruce=None,
        razon="El vehículo permaneció en la vía sin cruzar el segmento de salida",
    )


def clasificar_trayectorias(
    trayectorias: Sequence[Trayectoria],
    config: ZonaConfig,
    desplazamiento_minimo: float = 30.0,
) -> Tuple[ResultadoClasificacion, ...]:
    """Clasifica un conjunto de trayectorias devolviendo una tupla inmutable de resultados."""
    return tuple(
        clasificar_trayectoria(t, config, desplazamiento_minimo=desplazamiento_minimo)
        for t in trayectorias
    )
