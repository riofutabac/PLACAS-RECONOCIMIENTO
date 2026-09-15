"""Pruebas unitarias para el módulo lastre.medicion."""

import time

import pytest

from lastre.medicion import Medidor, MedicionError


def test_acumula_el_tiempo_de_una_etapa():
    """El tiempo de cada bloque se suma a su etapa."""
    medidor = Medidor()

    with medidor.fase("decodificar"):
        time.sleep(0.02)

    assert medidor.etapas["decodificar"].segundos >= 0.02
    assert medidor.etapas["decodificar"].llamadas == 1


def test_suma_varias_ejecuciones_de_la_misma_etapa():
    """Una etapa que corre muchas veces acumula su costo total."""
    medidor = Medidor()

    for _ in range(3):
        with medidor.fase("modelo"):
            time.sleep(0.01)

    assert medidor.etapas["modelo"].llamadas == 3
    assert medidor.etapas["modelo"].segundos >= 0.03


def test_calcula_el_costo_medio_por_llamada():
    """Saber cuanto cuesta una sola ejecucion orienta la optimizacion."""
    medidor = Medidor()
    medidor.anotar("modelo", 1.0)
    medidor.anotar("modelo", 1.0)

    assert medidor.etapas["modelo"].milisegundos_por_llamada == pytest.approx(1000.0)


def test_etapa_sin_llamadas_no_divide_por_cero():
    """Una etapa recien creada informa costo cero, no un error."""
    from lastre.medicion import Etapa

    assert Etapa("vacia").milisegundos_por_llamada == 0.0


def test_ordena_las_etapas_por_costo():
    """El informe debe mostrar primero lo que mas tiempo consume."""
    medidor = Medidor()
    medidor.anotar("barata", 0.1)
    medidor.anotar("cara", 5.0)
    medidor.anotar("media", 1.0)

    assert [f[0] for f in medidor.reparto()] == ["cara", "media", "barata"]


def test_el_tiempo_sin_atribuir_queda_a_la_vista():
    """Lo que no se midio debe verse, o la optimizacion apunta al lugar equivocado."""
    medidor = Medidor()
    time.sleep(0.05)
    medidor.anotar("algo", 0.001)

    informe = medidor.informe()

    assert "sin atribuir" in informe
    assert medidor.total > medidor.medido


def test_una_excepcion_no_pierde_la_medicion():
    """El tiempo se anota aunque el bloque falle."""
    medidor = Medidor()

    with pytest.raises(ValueError):
        with medidor.fase("riesgosa"):
            raise ValueError("fallo")

    assert medidor.etapas["riesgosa"].llamadas == 1


def test_entradas_invalidas():
    """Una etapa sin nombre o un tiempo negativo se rechazan."""
    medidor = Medidor()

    with pytest.raises(MedicionError, match="nombre"):
        with medidor.fase(""):
            pass

    with pytest.raises(MedicionError, match="negativo"):
        medidor.anotar("algo", -1.0)


def test_informe_incluye_todas_las_etapas():
    """El informe lista cada etapa medida con su porcentaje."""
    medidor = Medidor()
    medidor.anotar("decodificar", 2.0)
    medidor.anotar("modelo", 1.0)

    informe = medidor.informe()

    assert "decodificar" in informe and "modelo" in informe
    assert "TOTAL" in informe


def test_informe_declara_etapas_solapadas():
    medidor = Medidor()
    medidor.anotar("leer", 2.0)
    medidor.anotar("procesar", 2.0)
    medidor.inicio -= 3.0

    assert "solapado entre etapas" in medidor.informe()
