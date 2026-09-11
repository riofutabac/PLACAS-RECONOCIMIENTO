"""Pruebas unitarias para el módulo lastre.registro."""

import pytest

from lastre.registro import (
    SENTIDO_ENTRA,
    SENTIDO_INDETERMINADO,
    SENTIDO_SALE,
    RegistroError,
    clasificar_sentido,
    registrar_vehiculos,
)
from lastre.trayectoria import Posicion, Trayectoria

OBSERVACIONES_MINIMAS = 10
DESPLAZAMIENTO_MINIMO = 150


def _trayectoria(id_t, xs, cuadro_inicio=100, areas=None):
    """Construye una trayectoria que recorre las coordenadas x indicadas."""
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


def test_vehiculo_que_avanza_a_la_derecha_sale():
    """En esta cámara la carretera queda a la derecha, así que ir a la derecha es salir."""
    trayectoria = _trayectoria(1, [1369, 1800, 2352])

    assert clasificar_sentido(trayectoria, DESPLAZAMIENTO_MINIMO) == SENTIDO_SALE


def test_vehiculo_que_avanza_a_la_izquierda_entra():
    """El movimiento hacia el lastre corresponde a un ingreso."""
    trayectoria = _trayectoria(2, [2061, 1600, 1240])

    assert clasificar_sentido(trayectoria, DESPLAZAMIENTO_MINIMO) == SENTIDO_ENTRA


def test_vehiculo_casi_quieto_queda_indeterminado():
    """Un desplazamiento menor al mínimo no permite afirmar el sentido."""
    trayectoria = _trayectoria(3, [1400, 1410, 1420])

    assert clasificar_sentido(trayectoria, DESPLAZAMIENTO_MINIMO) == SENTIDO_INDETERMINADO


def test_descarta_trayectorias_demasiado_cortas():
    """Los destellos de una o dos observaciones son ruido, no vehículos."""
    ruido = _trayectoria(9, [1460, 1461])
    real = _trayectoria(1, list(range(1300, 1300 + 20 * 60, 60)))

    registros = registrar_vehiculos([ruido, real], OBSERVACIONES_MINIMAS, DESPLAZAMIENTO_MINIMO)

    assert len(registros) == 1
    assert registros[0].trayectoria_id == 1


def test_registra_ambos_sentidos_sin_descartar_ninguno():
    """El registro conserva entradas y salidas por igual."""
    sale = _trayectoria(1, list(range(1300, 1300 + 15 * 70, 70)))
    entra = _trayectoria(2, list(range(2100, 2100 - 15 * 70, -70)))

    registros = registrar_vehiculos([sale, entra], OBSERVACIONES_MINIMAS, DESPLAZAMIENTO_MINIMO)

    assert len(registros) == 2
    assert {r.sentido for r in registros} == {SENTIDO_SALE, SENTIDO_ENTRA}


def test_elige_el_cuadro_donde_el_vehiculo_se_ve_mas_grande():
    """El cuadro más cercano a la cámara es el mejor para leer la placa."""
    areas = [100] * 9 + [5000] + [200] * 5
    trayectoria = _trayectoria(1, list(range(1300, 1300 + 15 * 70, 70)), areas=areas)

    registro = registrar_vehiculos([trayectoria], OBSERVACIONES_MINIMAS, DESPLAZAMIENTO_MINIMO)[0]

    assert registro.cuadro_representativo == 109


def test_registros_ordenados_por_aparicion():
    """Los vehículos se entregan en el orden en que aparecen en el video."""
    tardio = _trayectoria(1, list(range(1300, 1300 + 15 * 70, 70)), cuadro_inicio=5000)
    temprano = _trayectoria(2, list(range(1300, 1300 + 15 * 70, 70)), cuadro_inicio=100)

    registros = registrar_vehiculos([tardio, temprano], OBSERVACIONES_MINIMAS, DESPLAZAMIENTO_MINIMO)

    assert [r.cuadro_inicio for r in registros] == [100, 5000]


def test_sentido_claro_se_distingue_del_ambiguo():
    """El registro indica si su sentido es confiable."""
    quieto = _trayectoria(1, [1400] * 15)

    registro = registrar_vehiculos([quieto], OBSERVACIONES_MINIMAS, DESPLAZAMIENTO_MINIMO)[0]

    assert not registro.sentido_es_claro


def test_parametros_invalidos():
    """Los parámetros fuera de rango se rechazan de forma explícita."""
    with pytest.raises(RegistroError, match="observaciones_minimas"):
        registrar_vehiculos([], 0, DESPLAZAMIENTO_MINIMO)

    with pytest.raises(RegistroError, match="desplazamiento_minimo"):
        clasificar_sentido(_trayectoria(1, [100, 200]), -5)


def test_sin_trayectorias_no_hay_registros():
    """Un video sin vehículos produce un registro vacío, no un error."""
    assert registrar_vehiculos([], OBSERVACIONES_MINIMAS, DESPLAZAMIENTO_MINIMO) == ()


def test_fusiona_la_continuacion_del_mismo_vehiculo():
    """Un vehículo que el seguimiento pierde y recupera no se cuenta dos veces."""
    primera = _trayectoria(1, list(range(2000, 2000 - 15 * 70, -70)), cuadro_inicio=100)
    # Reaparece 40 cuadros después, cerca de donde se perdió
    reaparece = _trayectoria(2, list(range(1000, 1000 + 14 * 20, 20)), cuadro_inicio=154)

    registros = registrar_vehiculos(
        [primera, reaparece], OBSERVACIONES_MINIMAS, DESPLAZAMIENTO_MINIMO
    )

    assert len(registros) == 1
    assert registros[0].sentido == SENTIDO_ENTRA


def test_no_fusiona_vehiculos_distantes_en_el_tiempo():
    """Dos vehículos separados por minutos son registros distintos."""
    uno = _trayectoria(1, list(range(1300, 1300 + 15 * 70, 70)), cuadro_inicio=100)
    otro = _trayectoria(2, list(range(1300, 1300 + 15 * 70, 70)), cuadro_inicio=5000)

    registros = registrar_vehiculos([uno, otro], OBSERVACIONES_MINIMAS, DESPLAZAMIENTO_MINIMO)

    assert len(registros) == 2


def test_no_fusiona_vehiculos_distantes_en_el_espacio():
    """Dos vehículos simultáneos en extremos opuestos no son el mismo."""
    izquierda = _trayectoria(1, list(range(500, 500 + 15 * 20, 20)), cuadro_inicio=100)
    derecha = _trayectoria(2, list(range(2500, 2500 + 15 * 20, 20)), cuadro_inicio=120)

    registros = registrar_vehiculos([izquierda, derecha], OBSERVACIONES_MINIMAS, DESPLAZAMIENTO_MINIMO)

    assert len(registros) == 2


def test_parametros_de_fusion_invalidos():
    """Los parámetros de fusión fuera de rango se rechazan."""
    from lastre.registro import fusionar_continuaciones

    with pytest.raises(RegistroError, match="ventana_cuadros"):
        fusionar_continuaciones([], -1, 400)

    with pytest.raises(RegistroError, match="distancia_maxima"):
        fusionar_continuaciones([], 60, -1)
