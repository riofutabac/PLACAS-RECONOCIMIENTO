"""Pruebas unitarias para el módulo lastre.consolidacion."""

import pytest

from lastre.consolidacion import ConsolidacionError, consolidar_salidas


def _salida(id_tray, cuadro, centro, duracion=50):
    """Construye una salida mínima con la forma que emite el conteo."""
    return {
        "trayectoria_id": id_tray,
        "cuadro_cruce": cuadro,
        "centro_cruce": list(centro),
        "caja_cruce": [centro[0] - 50, centro[1] - 50, 100, 100],
        "duracion_cuadros": duracion,
        "imagen_evidencia": f"salidas/s{id_tray}.jpg",
    }


def test_fragmentos_del_mismo_vehiculo_se_fusionan():
    """Tres cruces casi simultáneos y contiguos son un solo vehículo."""
    salidas = [
        _salida(1, 2571, (1400, 1200), duracion=40),
        _salida(2, 2599, (1450, 1210), duracion=90),
        _salida(3, 2628, (1480, 1205), duracion=30),
    ]

    vehiculos = consolidar_salidas(salidas, ventana_cuadros=60, distancia_maxima=300)

    assert len(vehiculos) == 1
    assert vehiculos[0].fue_fragmentado
    assert vehiculos[0].trayectorias_fusionadas == (1, 2, 3)
    # Se conserva el cruce de mayor duración como representativo
    assert vehiculos[0].cuadro_cruce == 2599


def test_vehiculos_separados_en_el_tiempo_no_se_fusionan():
    """Cruces distantes en el tiempo son vehículos distintos."""
    salidas = [
        _salida(1, 700, (1400, 1200)),
        _salida(2, 5000, (1400, 1200)),
    ]

    vehiculos = consolidar_salidas(salidas, ventana_cuadros=60, distancia_maxima=300)

    assert len(vehiculos) == 2
    assert all(not v.fue_fragmentado for v in vehiculos)


def test_vehiculos_separados_en_el_espacio_no_se_fusionan():
    """Cruces simultáneos pero lejanos son vehículos distintos."""
    salidas = [
        _salida(1, 700, (700, 1200)),
        _salida(2, 710, (2000, 1200)),
    ]

    vehiculos = consolidar_salidas(salidas, ventana_cuadros=60, distancia_maxima=300)

    assert len(vehiculos) == 2


def test_numeracion_es_consecutiva_y_ordenada():
    """Los vehículos se numeran desde 1 en orden de aparición."""
    salidas = [_salida(3, 5000, (1400, 1200)), _salida(1, 700, (1400, 1200))]

    vehiculos = consolidar_salidas(salidas, ventana_cuadros=60, distancia_maxima=300)

    assert [v.numero for v in vehiculos] == [1, 2]
    assert vehiculos[0].cuadro_cruce == 700


def test_lista_vacia_no_produce_vehiculos():
    """Sin salidas no hay vehículos que consolidar."""
    assert consolidar_salidas([], ventana_cuadros=60, distancia_maxima=300) == ()


def test_parametros_invalidos():
    """Los parámetros negativos se rechazan de forma explícita."""
    with pytest.raises(ConsolidacionError, match="ventana_cuadros"):
        consolidar_salidas([], ventana_cuadros=-1, distancia_maxima=300)

    with pytest.raises(ConsolidacionError, match="distancia_maxima"):
        consolidar_salidas([], ventana_cuadros=60, distancia_maxima=-5)


def test_no_muta_la_entrada():
    """La consolidación no altera la lista ni los diccionarios recibidos."""
    salidas = [_salida(1, 700, (1400, 1200)), _salida(2, 720, (1420, 1210))]
    copia = [dict(s) for s in salidas]

    consolidar_salidas(salidas, ventana_cuadros=60, distancia_maxima=300)

    assert salidas == copia
