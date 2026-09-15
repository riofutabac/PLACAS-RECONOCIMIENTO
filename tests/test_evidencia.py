"""Pruebas unitarias para el módulo lastre.evidencia."""

import numpy as np
import pytest

from lastre.evidencia import AlmacenRecortes, EvidenciaError, clave_de
from lastre.trayectoria import Posicion


def _cuadro(ancho=400, alto=300):
    """Cuadro sintético con textura, para que el JPEG no sea degenerado."""
    generador = np.random.default_rng(7)
    return generador.integers(0, 255, (alto, ancho, 3), dtype=np.uint8)


def _posicion(cuadro=10, caja=(100, 80, 60, 40)):
    x, y, ancho, alto = caja
    return Posicion(
        cuadro=cuadro,
        centro=(x + ancho // 2, y + alto // 2),
        caja=caja,
        area=ancho * alto,
    )


def test_la_clave_distingue_dos_vehiculos_en_el_mismo_cuadro():
    """El número de cuadro no identifica una observación: puede haber varios."""
    izquierda = _posicion(cuadro=10, caja=(100, 80, 60, 40))
    derecha = _posicion(cuadro=10, caja=(300, 80, 60, 40))

    assert clave_de(izquierda) != clave_de(derecha)


def test_la_clave_es_estable_para_la_misma_observacion():
    """Guardar y consultar deben coincidir sin depender del orden de llamada."""
    assert clave_de(_posicion()) == clave_de(_posicion())


def test_devuelve_el_recorte_con_el_margen_ya_aplicado():
    """El recorte guardado es el que el lector debe leer, sin volver a recortar.

    Aplicar el margen dos veces agrandaría la ventana y podría arrastrar la
    placa de un vehículo vecino.
    """
    imagen = _cuadro()
    posicion = _posicion(caja=(100, 80, 60, 40))
    almacen = AlmacenRecortes()

    almacen.guardar(posicion, imagen)
    recorte = almacen.obtener(posicion)

    # margen del 10 %: 6 px en x y 4 px en y a cada lado
    assert recorte.shape[:2] == (40 + 4 * 2, 60 + 6 * 2)


def test_una_observacion_no_guardada_no_devuelve_recorte():
    """Consultar algo ausente no puede inventar una imagen."""
    assert AlmacenRecortes().obtener(_posicion()) is None


def test_recorta_sin_desbordar_en_el_borde_del_cuadro():
    """Un vehículo pegado al borde se recorta hasta donde llega la imagen."""
    imagen = _cuadro(ancho=400, alto=300)
    posicion = _posicion(caja=(370, 280, 30, 20))
    almacen = AlmacenRecortes()

    almacen.guardar(posicion, imagen)
    recorte = almacen.obtener(posicion)

    alto, ancho = recorte.shape[:2]
    assert 0 < ancho <= 400 and 0 < alto <= 300


def test_guardar_la_misma_observacion_dos_veces_no_duplica_almacenamiento():
    """El mismo vehículo puede recorrer la misma ruta dos veces por error."""
    imagen = _cuadro()
    posicion = _posicion()
    almacen = AlmacenRecortes()

    almacen.guardar(posicion, imagen)
    bytes_uno = almacen.bytes_totales
    almacen.guardar(posicion, imagen)

    assert len(almacen) == 1
    assert almacen.bytes_totales == bytes_uno


def test_almacena_mucho_menos_que_el_cuadro_completo():
    """Es la razón de ser del módulo: no conservar píxeles que nadie lee."""
    imagen = _cuadro(ancho=2960, alto=1664)
    posicion = _posicion(caja=(1000, 700, 300, 200))
    almacen = AlmacenRecortes()

    almacen.guardar(posicion, imagen)

    assert almacen.bytes_totales < imagen.nbytes // 20


def test_una_caja_fuera_del_cuadro_se_rechaza_explicitamente():
    """Nunca guardar silenciosamente una evidencia vacía."""
    almacen = AlmacenRecortes()

    with pytest.raises(EvidenciaError):
        almacen.guardar(_posicion(caja=(5000, 5000, 60, 40)), _cuadro())


def test_la_calidad_invalida_se_rechaza_al_construir():
    """Un parámetro fuera de rango debe fallar de entrada, no por video."""
    with pytest.raises(EvidenciaError):
        AlmacenRecortes(calidad=0)
