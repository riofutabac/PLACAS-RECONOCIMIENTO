"""Pruebas unitarias para el módulo lastre.formato_ecuador."""

import pytest

from lastre.formato_ecuador import (
    FormatoError,
    TIPO_AUTOMOVIL,
    TIPO_MOTOCICLETA,
    corregir,
    es_valida,
    normalizar,
    tipo_de_placa,
    validar_o_corregir,
)


def test_normaliza_separadores_y_minusculas():
    """El guion, los espacios y las minúsculas no forman parte de la placa."""
    assert normalizar("taa-2204") == "TAA2204"
    assert normalizar(" P B A 1 2 3 ") == "PBA123"
    assert normalizar("TAA·2204") == "TAA2204"


def test_normalizar_rechaza_no_cadena():
    """Una entrada que no es texto se rechaza de forma explícita."""
    with pytest.raises(FormatoError, match="debe ser una cadena"):
        normalizar(2204)


def test_reconoce_placa_de_automovil():
    """Tres letras y tres o cuatro dígitos es formato de automóvil."""
    assert tipo_de_placa("TAA-2204") == TIPO_AUTOMOVIL
    assert tipo_de_placa("PBA123") == TIPO_AUTOMOVIL
    assert es_valida("TAA2204")


def test_reconoce_placa_de_motocicleta():
    """Dos letras y tres o cuatro dígitos es formato de motocicleta."""
    assert tipo_de_placa("TA123") == TIPO_MOTOCICLETA
    assert tipo_de_placa("PB1234") == TIPO_MOTOCICLETA


def test_rechaza_formatos_imposibles():
    """Textos que no encajan en ningún formato se rechazan."""
    for invalido in ("", "A1", "ABCD1234", "12345", "ABC", "ABCDE123456"):
        assert tipo_de_placa(invalido) is None
        assert not es_valida(invalido)


def test_corrige_digito_en_posicion_de_letra():
    """Un 0 leído donde va letra se corrige a O."""
    assert corregir("TAA22O4") == "TAA2204"
    assert corregir("0BA1234") == "OBA1234"


def test_corrige_letra_en_posicion_de_digito():
    """Una O, B, I o S leída donde va dígito se corrige al dígito."""
    assert corregir("TAA22O4") == "TAA2204"
    assert corregir("PBAI23") == "PBA123"
    assert corregir("PBAS23") == "PBA523"
    assert corregir("PBAB23") == "PBA823"


def test_no_inventa_caracteres_faltantes():
    """Una lectura incompleta no se completa con caracteres inventados."""
    assert corregir("TAA22") is None
    assert corregir("TA") is None


def test_placa_ya_valida_no_se_altera():
    """Una placa correcta se devuelve intacta y marcada como no corregida."""
    placa, corregida = validar_o_corregir("TAA-2204")
    assert placa == "TAA2204"
    assert corregida is False


def test_placa_corregida_se_marca():
    """Una placa obtenida por corrección se marca como tal."""
    placa, corregida = validar_o_corregir("TAA22O4")
    assert placa == "TAA2204"
    assert corregida is True


def test_placa_irrecuperable_devuelve_none():
    """Si no se alcanza un formato válido el resultado es None."""
    placa, corregida = validar_o_corregir("XX")
    assert placa is None
    assert corregida is False
