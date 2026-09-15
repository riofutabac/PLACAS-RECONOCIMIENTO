"""Pruebas de la lectura adelantada de cuadros.

Decodificar cuesta casi tanto como detectar, y hoy se hace por turnos: el
procesador espera al disco y el disco espera al procesador. Adelantar la
lectura en un hilo solapa ambas etapas sin descartar ni reordenar cuadros.
"""

import time

import pytest

from lastre.adelanto import AdelantoError, cuadros_adelantados


def test_entrega_los_mismos_cuadros_y_en_el_mismo_orden():
    origen = iter([(1, "a"), (2, "b"), (3, "c")])

    assert list(cuadros_adelantados(origen)) == [(1, "a"), (2, "b"), (3, "c")]


def test_propaga_el_error_del_origen():
    """Un video corrupto debe fallar igual que sin adelanto, no quedarse mudo."""
    def origen():
        yield (1, "a")
        raise OSError("video truncado")

    obtenidos = []
    with pytest.raises(OSError, match="video truncado"):
        for cuadro in cuadros_adelantados(origen()):
            obtenidos.append(cuadro)

    assert obtenidos == [(1, "a")]


def test_rechaza_capacidad_invalida():
    with pytest.raises(AdelantoError):
        next(cuadros_adelantados(iter([]), capacidad=0))


def test_la_capacidad_limita_cuanto_se_adelanta():
    """Sin limite, un video entero cabria en memoria antes de procesarse."""
    leidos = []

    def origen():
        for numero in range(100):
            leidos.append(numero)
            yield (numero, "x")

    flujo = cuadros_adelantados(origen(), capacidad=3)
    next(flujo)
    time.sleep(0.2)

    assert len(leidos) <= 3 + 2
    flujo.close()


def test_solapa_la_lectura_con_el_consumo():
    """La garantia que justifica el cambio: leer y procesar a la vez."""
    def origen():
        for numero in range(6):
            time.sleep(0.02)
            yield (numero, "x")

    arranque = time.perf_counter()
    for _ in cuadros_adelantados(origen(), capacidad=2):
        time.sleep(0.02)
    transcurrido = time.perf_counter() - arranque

    # En serie serian 6*(0.02+0.02)=0.24 s; solapadas, poco mas de 0.12 s.
    assert transcurrido < 0.20
