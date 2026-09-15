"""Pruebas unitarias para el módulo lastre.placa."""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pytest

from lastre.placa import LectorPlacas, PlacaError, recortar_vehiculo


@dataclass
class _Caja:
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass
class _Ocr:
    text: str
    confidence: object


@dataclass
class _Deteccion:
    bounding_box: _Caja


@dataclass
class _Resultado:
    ocr: Optional[_Ocr]
    detection: _Deteccion


class _AlprFalso:
    """Doble de prueba que devuelve resultados fijos."""

    def __init__(self, resultados):
        self._resultados = resultados
        self.recortes_recibidos = []

    def predict(self, imagen):
        self.recortes_recibidos.append(imagen.shape)
        return self._resultados


@pytest.fixture
def cuadro():
    return np.full((1664, 2960, 3), 128, dtype=np.uint8)


def _resultado(texto, confianza):
    return _Resultado(ocr=_Ocr(texto, confianza), detection=_Deteccion(_Caja(10, 20, 110, 50)))


def test_recorte_incluye_margen(cuadro):
    """El recorte agrega margen porque la placa suele quedar en el borde."""
    recorte = recortar_vehiculo(cuadro, (1000, 800, 400, 300), margen=0.10)

    assert recorte.shape[1] == 400 + 2 * 40
    assert recorte.shape[0] == 300 + 2 * 30


def test_recorte_se_ajusta_a_los_bordes_del_cuadro(cuadro):
    """Una caja pegada al borde no se sale de la imagen."""
    recorte = recortar_vehiculo(cuadro, (0, 0, 200, 200))

    assert recorte.shape[0] > 0 and recorte.shape[1] > 0


def test_recorte_no_modifica_el_cuadro(cuadro):
    """El recorte es una copia independiente."""
    copia = cuadro.copy()
    recorte = recortar_vehiculo(cuadro, (1000, 800, 400, 300))
    recorte[:] = 0

    assert np.array_equal(cuadro, copia)


def test_recorte_rechaza_entradas_invalidas(cuadro):
    """Cajas y márgenes inválidos se rechazan de forma explícita."""
    with pytest.raises(PlacaError, match="ancho y alto positivos"):
        recortar_vehiculo(cuadro, (100, 100, 0, 50))

    with pytest.raises(PlacaError, match="margen"):
        recortar_vehiculo(cuadro, (100, 100, 50, 50), margen=-1)

    with pytest.raises(PlacaError, match="numpy.ndarray"):
        recortar_vehiculo("no es un cuadro", (0, 0, 10, 10))


def test_lee_placa_del_recorte(cuadro):
    """Una placa reconocida se devuelve con su texto y confianza."""
    lector = LectorPlacas(alpr=_AlprFalso([_resultado("TAA2204", 0.97)]))

    lecturas = lector.leer_vehiculo(cuadro, (1000, 800, 400, 300))

    assert len(lecturas) == 1
    assert lecturas[0].texto == "TAA2204"
    assert lecturas[0].confianza == pytest.approx(0.97)


def test_promedia_la_confianza_por_caracter(cuadro):
    """El motor entrega confianza por carácter; se reporta el promedio."""
    lector = LectorPlacas(alpr=_AlprFalso([_resultado("TAA2204", [1.0, 0.8, 0.9, 0.9, 0.9, 0.9, 0.8])]))

    lecturas = lector.leer_vehiculo(cuadro, (1000, 800, 400, 300))

    assert lecturas[0].confianza == pytest.approx(0.8857, abs=1e-3)


def test_descarta_detecciones_sin_texto(cuadro):
    """Una placa detectada pero ilegible no produce lectura."""
    sin_ocr = _Resultado(ocr=None, detection=_Deteccion(_Caja(0, 0, 10, 10)))
    vacia = _resultado("", 0.9)
    lector = LectorPlacas(alpr=_AlprFalso([sin_ocr, vacia]))

    assert lector.leer_vehiculo(cuadro, (1000, 800, 400, 300)) == ()


def test_recorte_vacio_no_produce_lecturas():
    """Un recorte sin píxeles se resuelve sin invocar al motor."""
    lector = LectorPlacas(alpr=_AlprFalso([_resultado("TAA2204", 0.9)]))

    assert lector.leer(np.zeros((0, 0, 3), dtype=np.uint8)) == ()


def test_el_motor_recibe_el_recorte_no_el_cuadro_completo(cuadro):
    """El modelo debe recibir el recorte; en el cuadro completo no ve la placa."""
    falso = _AlprFalso([_resultado("TAA2204", 0.9)])
    LectorPlacas(alpr=falso).leer_vehiculo(cuadro, (1000, 800, 400, 300))

    alto, ancho = falso.recortes_recibidos[0][:2]
    assert ancho < cuadro.shape[1] and alto < cuadro.shape[0]


def test_lector_rechaza_entrada_invalida():
    """Una entrada que no es imagen se rechaza de forma explícita."""
    lector = LectorPlacas(alpr=_AlprFalso([]))

    with pytest.raises(PlacaError, match="numpy.ndarray"):
        lector.leer("no es una imagen")


def test_lector_placas_acepta_hilos():
    """LectorPlacas debe aceptar el parámetro hilos para configurar CPU."""
    lector = LectorPlacas(alpr=_AlprFalso([]), hilos=2)
    assert lector is not None


# --- Sesiones ONNX expuestas para verificar el acelerador -------------------

class _SesionOnnxFalsa:
    def __init__(self, proveedores):
        self._proveedores = proveedores

    def get_providers(self):
        return list(self._proveedores)


class _SubmodeloOnnxFalso:
    def __init__(self, proveedores):
        self.model = _SesionOnnxFalsa(proveedores)


class _AlprConSesionesFalso:
    """Reproduce la forma real de fast_alpr: dos submodelos con sesión propia."""

    def __init__(self):
        self.detector = type("D", (), {})()
        self.detector.detector = _SubmodeloOnnxFalso(("CUDAExecutionProvider",))
        self.ocr = type("O", (), {})()
        self.ocr.ocr_model = _SubmodeloOnnxFalso(("CPUExecutionProvider",))


def test_el_lector_expone_las_sesiones_de_sus_dos_modelos():
    """El lector carga detector de placas y OCR, cada uno con su sesión.

    Que uno consiga la tarjeta no dice nada del otro, así que el lote necesita
    verlos por separado para saber dónde se está ejecutando de verdad.
    """
    lector = LectorPlacas(alpr=_AlprConSesionesFalso())

    sesiones = lector.sesiones

    assert set(sesiones) == {"detector de placas", "ocr"}


def test_las_sesiones_del_lector_reportan_proveedores_distintos():
    """Una caída silenciosa de un solo modelo debe poder distinguirse."""
    from lastre.aceleracion import proveedores_activos

    sesiones = LectorPlacas(alpr=_AlprConSesionesFalso()).sesiones

    assert proveedores_activos(sesiones["detector de placas"]) == ("CUDAExecutionProvider",)
    assert proveedores_activos(sesiones["ocr"]) == ("CPUExecutionProvider",)


def test_un_alpr_sin_la_forma_esperada_no_rompe_el_lote():
    """Si la librería cambia de forma, se informa menos, pero no se cae."""
    lector = LectorPlacas(alpr=object())

    assert lector.sesiones == {}
