"""Pruebas de la lectura adelantada de cuadros.

Decodificar cuesta casi tanto como detectar, y hoy se hace por turnos: el
procesador espera al disco y el disco espera al procesador. Adelantar la
lectura en un hilo solapa ambas etapas sin descartar ni reordenar cuadros.
"""

import time
from threading import Event

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
    """El productor avanza mientras el consumidor aún procesa el primer cuadro."""
    segunda_lectura = Event()

    def origen():
        yield (0, "primero")
        segunda_lectura.set()
        yield (1, "segundo")

    flujo = cuadros_adelantados(origen(), capacidad=2)
    assert next(flujo) == (0, "primero")

    # No pedimos el segundo elemento: que ya se haya leído demuestra que no
    # trabaja en serie con el consumidor. El margen es solo para planificar
    # el hilo, no una afirmación frágil de rendimiento absoluto.
    assert segunda_lectura.wait(timeout=1)
    flujo.close()


def test_mide_solo_el_trabajo_del_productor():
    medidas = []

    def origen():
        time.sleep(0.02)
        yield (1, "a")

    assert list(cuadros_adelantados(origen(), al_leer=medidas.append)) == [(1, "a")]
    assert len(medidas) == 1
    assert medidas[0] >= 0.02
