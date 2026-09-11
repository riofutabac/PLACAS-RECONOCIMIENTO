"""Pruebas unitarias para el módulo lastre.lectura."""

import pytest

from lastre.lectura import (
    ESTADO_PENDIENTE,
    ESTADO_SIN_PLACA,
    ESTADO_VALIDADO,
    Lectura,
    LecturaError,
    consolidar_lecturas,
)

UMBRAL = 0.75
MINIMO = 3


def _lecturas(*pares):
    """Construye lecturas a partir de pares (texto, confianza)."""
    return [Lectura(cuadro=i, texto=t, confianza=c, imagen_recorte=f"r{i}.jpg")
            for i, (t, c) in enumerate(pares, start=1)]


def test_gana_la_placa_mas_votada():
    """El texto con mayor confianza acumulada gana la votación."""
    lecturas = _lecturas(("TAA2204", 0.9), ("TAA2204", 0.88), ("TAA2205", 0.6))

    resultado = consolidar_lecturas(lecturas, UMBRAL, MINIMO)

    assert resultado.placa == "TAA2204"
    assert resultado.lecturas_coincidentes == 2
    assert resultado.total_lecturas == 3


def test_lecturas_confundidas_se_corrigen_y_suman():
    """Las variantes por confusión de caracteres votan por la misma placa."""
    lecturas = _lecturas(("TAA22O4", 0.9), ("TAA2204", 0.85), ("TAA22O4", 0.8))

    resultado = consolidar_lecturas(lecturas, UMBRAL, MINIMO)

    assert resultado.placa == "TAA2204"
    assert resultado.lecturas_coincidentes == 3
    assert resultado.estado == ESTADO_VALIDADO


def test_confianza_alta_y_apoyo_suficiente_valida():
    """Superar umbral y mínimo de coincidencias deja el registro validado."""
    lecturas = _lecturas(("PBA1234", 0.9), ("PBA1234", 0.85), ("PBA1234", 0.8))

    resultado = consolidar_lecturas(lecturas, UMBRAL, MINIMO)

    assert resultado.estado == ESTADO_VALIDADO
    assert not resultado.requiere_revision
    assert resultado.confianza == pytest.approx(0.85)


def test_confianza_baja_queda_pendiente():
    """Por debajo del umbral el registro queda pendiente de revisión."""
    lecturas = _lecturas(("PBA1234", 0.5), ("PBA1234", 0.4), ("PBA1234", 0.45))

    resultado = consolidar_lecturas(lecturas, UMBRAL, MINIMO)

    assert resultado.estado == ESTADO_PENDIENTE
    assert resultado.requiere_revision


def test_apoyo_insuficiente_queda_pendiente():
    """Una sola lectura de alta confianza no basta para validar."""
    lecturas = _lecturas(("PBA1234", 0.99))

    resultado = consolidar_lecturas(lecturas, UMBRAL, MINIMO)

    assert resultado.estado == ESTADO_PENDIENTE
    assert resultado.lecturas_coincidentes == 1


def test_sin_lecturas_es_sin_placa_identificable():
    """Un vehículo sin ninguna lectura queda marcado como sin placa."""
    resultado = consolidar_lecturas([], UMBRAL, MINIMO)

    assert resultado.placa is None
    assert resultado.confianza == 0.0
    assert resultado.estado == ESTADO_SIN_PLACA


def test_lecturas_irrecuperables_equivalen_a_sin_placa():
    """Si ninguna lectura alcanza formato válido el vehículo queda sin placa."""
    resultado = consolidar_lecturas(_lecturas(("XX", 0.9), ("???", 0.8)), UMBRAL, MINIMO)

    assert resultado.placa is None
    assert resultado.estado == ESTADO_SIN_PLACA


def test_conserva_el_recorte_de_mayor_confianza():
    """La imagen de respaldo es la de la lectura más confiable."""
    lecturas = _lecturas(("TAA2204", 0.6), ("TAA2204", 0.95), ("TAA2204", 0.7))

    resultado = consolidar_lecturas(lecturas, UMBRAL, MINIMO)

    assert resultado.imagen_recorte == "r2.jpg"


def test_marca_si_la_placa_provino_solo_de_correcciones():
    """Si toda lectura ganadora fue corregida, el resultado lo indica."""
    solo_corregidas = consolidar_lecturas(_lecturas(("TAA22O4", 0.9), ("TAA22O4", 0.9)), UMBRAL, MINIMO)
    assert solo_corregidas.fue_corregida

    alguna_limpia = consolidar_lecturas(_lecturas(("TAA22O4", 0.9), ("TAA2204", 0.9)), UMBRAL, MINIMO)
    assert not alguna_limpia.fue_corregida


def test_parametros_invalidos():
    """Los parámetros fuera de rango se rechazan de forma explícita."""
    with pytest.raises(LecturaError, match="umbral_confianza"):
        consolidar_lecturas([], 1.5, MINIMO)

    with pytest.raises(LecturaError, match="minimo_coincidencias"):
        consolidar_lecturas([], UMBRAL, 0)


def test_un_caracter_dudoso_impide_validar():
    """Una placa con una sola letra insegura queda pendiente pese al buen promedio.

    Reproduce el caso real de PCW-2497 leída como PCM2497: seis caracteres
    casi perfectos y uno equivocado promedian por encima del umbral.
    """
    lecturas = [
        Lectura(cuadro=i, texto="PCM2497", confianza=0.94, confianza_minima=0.41)
        for i in range(3)
    ]

    resultado = consolidar_lecturas(lecturas, UMBRAL, MINIMO)

    assert resultado.placa == "PCM2497"
    assert resultado.estado == ESTADO_PENDIENTE
    assert resultado.requiere_revision
    assert resultado.confianza_minima == pytest.approx(0.41)


def test_todos_los_caracteres_seguros_permite_validar():
    """Sin caracteres dudosos la placa se valida normalmente."""
    lecturas = [
        Lectura(cuadro=i, texto="TAA2204", confianza=0.95, confianza_minima=0.90)
        for i in range(3)
    ]

    resultado = consolidar_lecturas(lecturas, UMBRAL, MINIMO)

    assert resultado.estado == ESTADO_VALIDADO


def test_sin_confianza_por_caracter_se_usa_la_global():
    """Si el motor no informa por carácter, la confianza global decide."""
    lecturas = [Lectura(cuadro=i, texto="TAA2204", confianza=0.95) for i in range(3)]

    resultado = consolidar_lecturas(lecturas, UMBRAL, MINIMO)

    assert resultado.estado == ESTADO_VALIDADO


def test_una_lectura_nitida_basta_para_validar():
    """Un cuadro nítido valida la placa aunque otros cuadros salgan borrosos."""
    lecturas = [
        Lectura(cuadro=1, texto="TAA2204", confianza=0.95, confianza_minima=0.30),
        Lectura(cuadro=2, texto="TAA2204", confianza=0.96, confianza_minima=0.92),
        Lectura(cuadro=3, texto="TAA2204", confianza=0.94, confianza_minima=0.45),
    ]

    resultado = consolidar_lecturas(lecturas, UMBRAL, MINIMO)

    assert resultado.estado == ESTADO_VALIDADO
    assert resultado.confianza_minima == pytest.approx(0.92)


def test_si_ninguna_lectura_es_nitida_queda_pendiente():
    """Sin un solo cuadro confiable la placa no se valida."""
    lecturas = [
        Lectura(cuadro=i, texto="PCM2497", confianza=0.94, confianza_minima=c)
        for i, c in enumerate((0.50, 0.16, 0.49))
    ]

    resultado = consolidar_lecturas(lecturas, UMBRAL, MINIMO)

    assert resultado.estado == ESTADO_PENDIENTE
