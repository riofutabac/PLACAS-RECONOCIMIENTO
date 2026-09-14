"""Pruebas unitarias para el módulo lastre.vehiculos."""

from dataclasses import dataclass

import numpy as np
import pytest

from lastre.config import cargar_configuracion
from lastre.vehiculos import (
    CLASES_VEHICULO,
    TIPO_AUTOMOVIL,
    TIPO_MOTOCICLETA,
    DetectorVehiculos,
    VehiculoDeteccionError,
)

# Punto claramente dentro de la zona y punto claramente en la carretera
DENTRO = (1400, 1400)
FUERA = (2800, 1000)


@dataclass
class _Caja:
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass
class _Cruda:
    label: str
    confidence: float
    bounding_box: _Caja


class _DetectorFalso:
    """Doble de prueba que devuelve detecciones fijas."""

    def __init__(self, detecciones):
        self._detecciones = detecciones

    def predict(self, cuadro):
        return self._detecciones


def _caja_centrada_en(punto, ancho=200, alto=160):
    """Construye una caja cuyo punto de contacto con el suelo es `punto`."""
    x, y = punto
    return _Caja(x - ancho // 2, y - alto, x + ancho // 2, y)


@pytest.fixture
def config_zona():
    """Configuración real del proyecto, para probar contra la zona vigente."""
    return cargar_configuracion("config/zona.json")


@pytest.fixture
def cuadro():
    return np.zeros((1664, 2960, 3), dtype=np.uint8)


def _detector(config, detecciones, **kwargs):
    return DetectorVehiculos(config, detector=_DetectorFalso(detecciones), **kwargs)


def test_detecta_vehiculo_dentro_de_la_zona(config_zona, cuadro):
    """Un automóvil dentro del lastre se reporta."""
    crudas = [_Cruda("car", 0.9, _caja_centrada_en(DENTRO))]

    resultado = _detector(config_zona, crudas).detectar(cuadro)

    assert len(resultado) == 1
    assert resultado[0].clase == "car"
    assert resultado[0].tipo == TIPO_AUTOMOVIL


def test_descarta_vehiculo_de_la_carretera_principal(config_zona, cuadro):
    """Un vehículo cuyo contacto con el suelo cae fuera de la zona se descarta."""
    crudas = [_Cruda("car", 0.95, _caja_centrada_en(FUERA))]

    assert _detector(config_zona, crudas).detectar(cuadro) == ()


def test_descarta_objetos_que_no_son_vehiculos(config_zona, cuadro):
    """Personas, animales y demás clases no cuentan como vehículos."""
    crudas = [
        _Cruda("person", 0.99, _caja_centrada_en(DENTRO)),
        _Cruda("dog", 0.99, _caja_centrada_en(DENTRO)),
    ]

    assert _detector(config_zona, crudas).detectar(cuadro) == ()


def test_descarta_detecciones_de_baja_confianza(config_zona, cuadro):
    """Por debajo del umbral la detección no se acepta."""
    crudas = [_Cruda("truck", 0.3, _caja_centrada_en(DENTRO))]

    assert _detector(config_zona, crudas, confianza_minima=0.5).detectar(cuadro) == ()


def test_motocicleta_se_marca_con_su_tipo(config_zona, cuadro):
    """La motocicleta se distingue porque su placa usa otro formato."""
    crudas = [_Cruda("motorcycle", 0.8, _caja_centrada_en(DENTRO))]

    resultado = _detector(config_zona, crudas).detectar(cuadro)

    assert resultado[0].tipo == TIPO_MOTOCICLETA


def test_todas_las_clases_de_vehiculo_se_aceptan(config_zona, cuadro):
    """Automóvil, motocicleta, bus y camión son vehículos de interés."""
    crudas = [_Cruda(c, 0.9, _caja_centrada_en(DENTRO)) for c in sorted(CLASES_VEHICULO)]

    resultado = _detector(config_zona, crudas).detectar(cuadro)

    assert len(resultado) == len(CLASES_VEHICULO)


def test_vista_compatible_con_el_seguimiento(config_zona, cuadro):
    """La detección expone caja, área y centro para el seguimiento existente."""
    crudas = [_Cruda("car", 0.9, _caja_centrada_en(DENTRO, ancho=200, alto=160))]

    vehiculo = _detector(config_zona, crudas).detectar(cuadro)[0]
    vista = vehiculo.como_deteccion

    assert vista.caja == vehiculo.caja
    assert vista.area == 200 * 160
    assert vista.centro == vehiculo.centro


def test_no_muta_el_cuadro(config_zona, cuadro):
    """El detector no altera el arreglo del cuadro recibido."""
    copia = cuadro.copy()
    crudas = [_Cruda("car", 0.9, _caja_centrada_en(DENTRO))]

    _detector(config_zona, crudas).detectar(cuadro)

    assert np.array_equal(cuadro, copia)


def test_entradas_invalidas(config_zona):
    """Los parámetros y entradas inválidas se rechazan de forma explícita."""
    with pytest.raises(VehiculoDeteccionError, match="confianza_minima"):
        _detector(config_zona, [], confianza_minima=1.5)

    with pytest.raises(VehiculoDeteccionError, match="numpy.ndarray"):
        _detector(config_zona, []).detectar("no es un cuadro")


class _MovimientoFalso:
    """Doble que responde si hay movimiento según una secuencia dada."""

    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = 0

    def detectar(self, cuadro):
        r = self._respuestas[self.llamadas % len(self._respuestas)]
        self.llamadas += 1
        return (object(),) if r else ()


def _hibrido(config, hay_movimiento, crudas, paso=3):
    from lastre.vehiculos import DetectorHibrido
    return DetectorHibrido(
        _MovimientoFalso(hay_movimiento),
        _detector(config, crudas),
        paso=paso,
    )


def test_hibrido_ignora_cuadros_sin_movimiento(config_zona, cuadro):
    """Sin movimiento el modelo costoso no llega a ejecutarse."""
    detector = _hibrido(config_zona, [False], [_Cruda("car", 0.9, _caja_centrada_en(DENTRO))], paso=1)

    assert detector.detectar(cuadro) == ()
    assert detector.estadisticas["cuadros_confirmados"] == 0


def test_hibrido_confirma_vehiculo_cuando_hay_movimiento(config_zona, cuadro):
    """Con movimiento y un vehículo presente, la detección se reporta."""
    detector = _hibrido(config_zona, [True], [_Cruda("car", 0.9, _caja_centrada_en(DENTRO))], paso=1)

    assert len(detector.detectar(cuadro)) == 1
    assert detector.estadisticas["cuadros_confirmados"] == 1


def test_hibrido_descarta_movimiento_sin_vehiculo(config_zona, cuadro):
    """Una sombra en movimiento no produce ninguna detección."""
    detector = _hibrido(config_zona, [True], [], paso=1)

    assert detector.detectar(cuadro) == ()
    assert detector.estadisticas["cuadros_con_movimiento"] == 1


def test_hibrido_respeta_el_paso(config_zona, cuadro):
    """Con paso 3 el modelo corre en uno de cada tres cuadros con movimiento."""
    crudas = [_Cruda("car", 0.9, _caja_centrada_en(DENTRO))]
    detector = _hibrido(config_zona, [True], crudas, paso=3)

    resultados = [detector.detectar(cuadro) for _ in range(6)]

    assert sum(1 for r in resultados if r) == 2
    assert detector.estadisticas["cuadros_confirmados"] == 2


def test_hibrido_rechaza_paso_invalido(config_zona):
    """Un paso menor que uno se rechaza de forma explícita."""
    from lastre.vehiculos import DetectorHibrido
    with pytest.raises(VehiculoDeteccionError, match="paso"):
        DetectorHibrido(_MovimientoFalso([True]), _detector(config_zona, []), paso=0)


def test_hibrido_saltea_cuadros_en_el_filtro_de_movimiento(config_zona, cuadro):
    """El filtro de movimiento resulto ser la etapa mas cara del proceso.

    Con paso_movimiento 2 solo se examina la mitad de los cuadros, lo que a 25
    por segundo deja ocho centesimas entre miradas: ningun vehiculo cruza la
    zona en ese lapso.
    """
    movimiento = _MovimientoFalso([True])
    from lastre.vehiculos import DetectorHibrido
    detector = DetectorHibrido(
        movimiento, _detector(config_zona, [_Cruda("car", 0.9, _caja_centrada_en(DENTRO))]),
        paso=1, paso_movimiento=2,
    )

    for _ in range(6):
        detector.detectar(cuadro)

    assert movimiento.llamadas == 3
    assert detector.estadisticas["cuadros_vistos"] == 6


def test_paso_movimiento_uno_examina_todos_los_cuadros(config_zona, cuadro):
    """Por defecto no se saltea nada, para no perder vehiculos rapidos."""
    movimiento = _MovimientoFalso([True])
    from lastre.vehiculos import DetectorHibrido
    detector = DetectorHibrido(movimiento, _detector(config_zona, []), paso=1)

    for _ in range(4):
        detector.detectar(cuadro)

    assert movimiento.llamadas == 4


def test_paso_movimiento_invalido(config_zona):
    """Un paso menor que uno se rechaza de forma explícita."""
    from lastre.vehiculos import DetectorHibrido
    with pytest.raises(VehiculoDeteccionError, match="paso_movimiento"):
        DetectorHibrido(_MovimientoFalso([True]), _detector(config_zona, []), paso_movimiento=0)
