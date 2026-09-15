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

    assert clave_de(izquierda.cuadro, izquierda.caja) != clave_de(derecha.cuadro, derecha.caja)


def test_la_clave_es_estable_para_la_misma_observacion():
    """Guardar y consultar deben coincidir sin depender del orden de llamada."""
    assert clave_de(_posicion().cuadro, _posicion().caja) == clave_de(_posicion().cuadro, _posicion().caja)


def test_devuelve_el_recorte_con_el_margen_ya_aplicado():
    """El recorte guardado es el que el lector debe leer, sin volver a recortar.

    Aplicar el margen dos veces agrandaría la ventana y podría arrastrar la
    placa de un vehículo vecino.
    """
    imagen = _cuadro()
    posicion = _posicion(caja=(100, 80, 60, 40))
    almacen = AlmacenRecortes()

    almacen.guardar(posicion.cuadro, posicion.caja, imagen)
    recorte = almacen.obtener(posicion.cuadro, posicion.caja)

    # margen del 10 %: 6 px en x y 4 px en y a cada lado
    assert recorte.shape[:2] == (40 + 4 * 2, 60 + 6 * 2)


def test_una_observacion_no_guardada_no_devuelve_recorte():
    """Consultar algo ausente no puede inventar una imagen."""
    assert AlmacenRecortes().obtener(_posicion().cuadro, _posicion().caja) is None


def test_recorta_sin_desbordar_en_el_borde_del_cuadro():
    """Un vehículo pegado al borde se recorta hasta donde llega la imagen."""
    imagen = _cuadro(ancho=400, alto=300)
    posicion = _posicion(caja=(370, 280, 30, 20))
    almacen = AlmacenRecortes()

    almacen.guardar(posicion.cuadro, posicion.caja, imagen)
    recorte = almacen.obtener(posicion.cuadro, posicion.caja)

    alto, ancho = recorte.shape[:2]
    assert 0 < ancho <= 400 and 0 < alto <= 300


def test_guardar_la_misma_observacion_dos_veces_no_duplica_almacenamiento():
    """El mismo vehículo puede recorrer la misma ruta dos veces por error."""
    imagen = _cuadro()
    posicion = _posicion()
    almacen = AlmacenRecortes()

    almacen.guardar(posicion.cuadro, posicion.caja, imagen)
    bytes_uno = almacen.bytes_totales
    almacen.guardar(posicion.cuadro, posicion.caja, imagen)

    assert len(almacen) == 1
    assert almacen.bytes_totales == bytes_uno


def test_almacena_mucho_menos_que_el_cuadro_completo():
    """Es la razón de ser del módulo: no conservar píxeles que nadie lee."""
    imagen = _cuadro(ancho=2960, alto=1664)
    posicion = _posicion(caja=(1000, 700, 300, 200))
    almacen = AlmacenRecortes()

    almacen.guardar(posicion.cuadro, posicion.caja, imagen)

    assert almacen.bytes_totales < imagen.nbytes // 20


def test_una_caja_fuera_del_cuadro_se_rechaza_explicitamente():
    """Nunca guardar silenciosamente una evidencia vacía."""
    almacen = AlmacenRecortes()

    with pytest.raises(EvidenciaError):
        almacen.guardar(10, (5000, 5000, 60, 40), _cuadro())


def test_la_calidad_invalida_se_rechaza_al_construir():
    """Un parámetro fuera de rango debe fallar de entrada, no por video."""
    with pytest.raises(EvidenciaError):
        AlmacenRecortes(calidad=0)


def test_filtro_temprano_no_comprime_pequenas_que_no_mejoran(monkeypatch):
    import cv2
    llamadas = []
    original = cv2.imencode
    def contar(*args, **kwargs):
        llamadas.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(cv2, "imencode", contar)
    almacen = AlmacenRecortes()
    imagen = _cuadro()
    almacen.guardar_observacion(1, _posicion(cuadro=1), imagen, 5000)
    memoria = almacen.bytes_totales
    for numero in range(2, 102):
        almacen.guardar_observacion(1, _posicion(cuadro=numero), imagen, 5000)
    assert len(llamadas) == 1
    assert len(almacen) == 1
    assert almacen.bytes_totales == memoria


def test_conserva_umbral_inclusivo_y_todos_los_candidatos():
    almacen = AlmacenRecortes()
    imagen = _cuadro()
    posiciones = [_posicion(cuadro=n, caja=(20, 20, ancho, 40))
                  for n, ancho in enumerate((40, 60, 80, 60), 1)]
    for posicion in posiciones:
        almacen.guardar_observacion(1, posicion, imagen, 2400)
    assert almacen.obtener(posiciones[0].cuadro, posiciones[0].caja) is None
    for posicion in posiciones[1:]:
        assert almacen.obtener(posicion.cuadro, posicion.caja) is not None
    assert len(almacen) == 3


def test_reemplaza_solo_evidencia_pequena_y_conserva_otras_pistas():
    almacen = AlmacenRecortes()
    imagen = _cuadro()
    vieja = _posicion(cuadro=1)
    mejor = _posicion(cuadro=2, caja=(100, 80, 80, 40))
    for pista in (1, 2):
        almacen.guardar_observacion(pista, vieja, imagen, 5000)
    almacen.guardar_observacion(1, mejor, imagen, 5000)
    assert almacen.obtener(vieja.cuadro, vieja.caja) is not None
    almacen.guardar_observacion(2, mejor, imagen, 5000)
    assert almacen.obtener(vieja.cuadro, vieja.caja) is None
    assert len(almacen) == 1


def test_evidencia_de_continuaciones_resuelve_representante_final():
    from lastre.registro import registrar_vehiculos
    from lastre.trayectoria import Trayectoria
    almacen = AlmacenRecortes()
    imagen = _cuadro()
    primera = _posicion(cuadro=1)
    ultima = _posicion(cuadro=3, caja=(100, 80, 80, 40))
    trayectorias = []
    for pista, posicion in enumerate((primera, ultima), 1):
        almacen.guardar_observacion(pista, posicion, imagen, 5000)
        trayectorias.append(Trayectoria(pista, posicion.cuadro,
                                       posicion.cuadro, (posicion,)))
    vehiculos = registrar_vehiculos(trayectorias, 1, 1)
    assert len(vehiculos) == 1
    assert vehiculos[0].cuadro_representativo == ultima.cuadro
    assert almacen.obtener(vehiculos[0].cuadro_representativo,
                            vehiculos[0].caja_representativa) is not None


def test_error_de_nueva_evidencia_no_borra_la_anterior():
    almacen = AlmacenRecortes()
    primera = _posicion(cuadro=1)
    almacen.guardar_observacion(1, primera, _cuadro(), 5000)
    with pytest.raises(EvidenciaError):
        almacen.guardar_observacion(
            1, _posicion(cuadro=2, caja=(5000, 5000, 80, 40)), _cuadro(), 5000)
    assert almacen.obtener(primera.cuadro, primera.caja) is not None


def test_rechaza_umbral_negativo():
    with pytest.raises(EvidenciaError):
        AlmacenRecortes().guardar_observacion(1, _posicion(), _cuadro(), -1)


def test_calidad_predeterminada_conserva_92(monkeypatch):
    import cv2
    original = cv2.imencode
    parametros = []
    def contar(extension, imagen, params):
        parametros.extend(params)
        return original(extension, imagen, params)
    monkeypatch.setattr(cv2, "imencode", contar)
    AlmacenRecortes().guardar(1, _posicion().caja, _cuadro())
    assert parametros == [cv2.IMWRITE_JPEG_QUALITY, 92]
def test_error_opencv_compresion_es_error_de_evidencia(monkeypatch):
    import cv2
    import numpy as np
    import pytest
    from lastre.evidencia import AlmacenRecortes, EvidenciaError

    def fallar(*args, **kwargs):
        raise cv2.error("compresor fallido")

    monkeypatch.setattr(cv2, "imencode", fallar)
    with pytest.raises(EvidenciaError, match="comprimir"):
        AlmacenRecortes().guardar(1, (0, 0, 20, 20), np.zeros((30, 30, 3), np.uint8))
