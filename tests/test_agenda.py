"""Pruebas unitarias para el módulo lastre.agenda."""

import pytest

from lastre.agenda import AgendaError, construir_agenda, ultimo_cuadro_necesario
from lastre.registro import registrar_vehiculos
from lastre.trayectoria import Posicion, Trayectoria

AREA_MINIMA = 40000
OBSERVACIONES_MINIMAS = 10
DESPLAZAMIENTO_MINIMO = 150


def _trayectoria(id_t, xs, cuadro_inicio=100, areas=None):
    areas = areas or [1000] * len(xs)
    posiciones = tuple(
        Posicion(
            cuadro=cuadro_inicio + i,
            centro=(x, 1200),
            caja=(x - 50, 1150, 100, 100),
            area=areas[i],
        )
        for i, x in enumerate(xs)
    )
    return Trayectoria(
        id=id_t,
        cuadro_inicio=cuadro_inicio,
        cuadro_fin=cuadro_inicio + len(xs) - 1,
        posiciones=posiciones,
    )


def _vehiculos(*trayectorias):
    return registrar_vehiculos(
        list(trayectorias), OBSERVACIONES_MINIMAS, DESPLAZAMIENTO_MINIMO
    )


def test_agenda_solo_incluye_candidatos_que_superan_el_area():
    """Leer una placa que el lector descartaría es trabajo perdido."""
    xs = list(range(1300, 1300 + 20 * 60, 60))
    areas = [1000] * 18 + [90000, 95000]
    vehiculos = _vehiculos(_trayectoria(1, xs, areas=areas))

    agenda = construir_agenda(vehiculos, AREA_MINIMA)

    candidatos = [t for tareas in agenda.values() for t in tareas if t.es_candidato]
    assert len(candidatos) == 2


def test_un_vehiculo_sin_candidatos_conserva_su_evidencia():
    """Un vehículo sin placa legible sigue necesitando una foto.

    Es el invariante del plan: sin esta tarea el informe deja la celda vacía
    y el analista no puede verificar nada a mano.
    """
    xs = list(range(1300, 1300 + 20 * 60, 60))
    vehiculos = _vehiculos(_trayectoria(1, xs, areas=[1000] * 20))

    agenda = construir_agenda(vehiculos, AREA_MINIMA)

    tareas = [t for tareas in agenda.values() for t in tareas]
    assert len(tareas) == 1
    assert tareas[0].es_candidato is False
    assert tareas[0].cuadro == vehiculos[0].cuadro_representativo


def test_dos_vehiculos_en_el_mismo_cuadro_conservan_ambas_tareas():
    """El cuadro no identifica una observación: no puede perderse ninguna."""
    grandes = [90000] * 20
    uno = _trayectoria(1, list(range(1300, 1300 + 20 * 60, 60)), areas=grandes)
    otro = _trayectoria(2, list(range(400, 400 + 20 * 60, 60)), areas=grandes)
    vehiculos = _vehiculos(uno, otro)

    agenda = construir_agenda(vehiculos, AREA_MINIMA)

    assert len(agenda[100]) == 2
    assert {t.indice for t in agenda[100]} == {0, 1}


def test_la_agenda_no_repite_la_evidencia_si_ya_es_candidata():
    """Si el cuadro representativo ya se lee, no hay que visitarlo dos veces."""
    xs = list(range(1300, 1300 + 20 * 60, 60))
    vehiculos = _vehiculos(_trayectoria(1, xs, areas=[90000] * 20))

    agenda = construir_agenda(vehiculos, AREA_MINIMA)
    representativo = vehiculos[0].cuadro_representativo

    del_cuadro = agenda[representativo]
    assert len(del_cuadro) == 1


def test_el_ultimo_cuadro_cubre_la_evidencia_posterior_al_ultimo_candidato():
    """Cortar la lectura en el último candidato dejaría sin foto al vehículo.

    Aquí el cuadro más grande es el final, después del último área legible.
    """
    xs = list(range(1300, 1300 + 20 * 60, 60))
    areas = [90000] * 2 + [1000] * 17 + [500000]
    vehiculos = _vehiculos(_trayectoria(1, xs, areas=areas))

    agenda = construir_agenda(vehiculos, AREA_MINIMA)

    assert ultimo_cuadro_necesario(agenda) == vehiculos[0].cuadro_representativo
    assert ultimo_cuadro_necesario(agenda) == 119


def test_agenda_vacia_no_tiene_ultimo_cuadro():
    """Sin vehículos no hay nada que leer y el script no debe abrir el video."""
    assert construir_agenda((), AREA_MINIMA) == {}
    assert ultimo_cuadro_necesario({}) == 0


def test_area_minima_negativa_se_rechaza():
    """Un umbral inválido debe fallar de entrada."""
    with pytest.raises(AgendaError):
        construir_agenda((), -1)


def test_la_observacion_representativa_queda_marcada_como_evidencia():
    """Un candidato puede fallar el OCR y el vehículo quedarse sin foto.

    Marcar la representativa como evidencia, aunque también sea candidata,
    permite guardar su recorte sin depender de que la lectura prospere.
    """
    xs = list(range(1300, 1300 + 20 * 60, 60))
    vehiculos = _vehiculos(_trayectoria(1, xs, areas=[90000] * 20))

    agenda = construir_agenda(vehiculos, AREA_MINIMA)
    representativo = vehiculos[0].cuadro_representativo

    evidencias = [t for tareas in agenda.values() for t in tareas if t.es_evidencia]
    assert len(evidencias) == 1
    assert evidencias[0].cuadro == representativo
    assert evidencias[0].es_candidato is True


def test_cada_vehiculo_tiene_exactamente_una_evidencia():
    """Ni un vehículo sin foto ni dos fotos compitiendo por la misma celda."""
    grandes = [90000] * 20
    uno = _trayectoria(1, list(range(1300, 1300 + 20 * 60, 60)), areas=grandes)
    otro = _trayectoria(2, list(range(400, 400 + 20 * 60, 60)), areas=[1000] * 20)
    vehiculos = _vehiculos(uno, otro)

    agenda = construir_agenda(vehiculos, AREA_MINIMA)

    evidencias = [t for tareas in agenda.values() for t in tareas if t.es_evidencia]
    assert sorted(t.indice for t in evidencias) == [0, 1]
