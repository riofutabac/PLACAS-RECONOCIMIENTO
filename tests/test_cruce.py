"""Pruebas unitarias para el módulo lastre.cruce."""

from datetime import datetime, timedelta

import pytest

from lastre.cruce import (
    CruceError,
    Paso,
    consolidar_capturas,
    distancia_placa,
    emparejar,
)

BASE = datetime(2026, 9, 9, 11, 0, 0)


def _captura(placa, segundos, tipo="car"):
    return {"placa": placa, "momento": BASE + timedelta(seconds=segundos), "tipo": tipo}


def _paso(placa, minutos, origen="A"):
    return Paso(placa=placa, momento=BASE + timedelta(minutes=minutos), origen=origen)


def test_placas_identicas_distan_cero():
    """Dos lecturas iguales no tienen diferencia."""
    assert distancia_placa("PCX6575", "PCX6575") == 0.0


def test_confusiones_conocidas_cuestan_menos():
    """Los errores de lectura esperables penalizan la mitad.

    Casos reales observados en los datos: el 7 leido como T y la Y como V.
    """
    assert distancia_placa("PBN2792", "PBN2T92") == 0.5
    assert distancia_placa("PCY2297", "PCV2297") == 0.5
    assert distancia_placa("PCW2497", "PCM2497") == 0.5


def test_placas_distintas_quedan_lejos():
    """Dos vehiculos diferentes no deben confundirse nunca."""
    assert distancia_placa("PBN2792", "PDK8093") >= 4.0


def test_distancia_rechaza_nulos():
    """Una placa ausente se rechaza de forma explícita."""
    with pytest.raises(CruceError, match="nulas"):
        distancia_placa(None, "ABC1234")


def test_agrupa_capturas_repetidas_del_mismo_vehiculo():
    """Una camara fotografia decenas de veces al mismo vehiculo."""
    capturas = [_captura("PBN2792", s) for s in (0, 5, 12, 30, 60)]

    pasos = consolidar_capturas(capturas, ventana_segundos=180)

    assert len(pasos) == 1
    assert pasos[0].capturas == 5
    assert pasos[0].momento == BASE


def test_separa_dos_pasos_distantes_de_la_misma_placa():
    """El mismo vehiculo puede volver a pasar horas despues."""
    capturas = [_captura("PBN2792", 0), _captura("PBN2792", 7200)]

    assert len(consolidar_capturas(capturas, ventana_segundos=180)) == 2


def test_no_agrupa_placas_distintas():
    """Dos vehiculos simultaneos son dos pasos."""
    capturas = [_captura("PBN2792", 0), _captura("PDK8093", 5)]

    assert len(consolidar_capturas(capturas, ventana_segundos=180)) == 2


def test_empareja_por_placa_dentro_de_la_ventana():
    """Un vehiculo que entra debe aparecer en la otra camara poco despues."""
    a = [_paso("PCX6575", 0)]
    b = [_paso("PCX6575", 12, "B")]

    parejas, sin_a, sin_b = emparejar(a, b, minutos_min=5, minutos_max=25)

    assert len(parejas) == 1
    assert parejas[0].minutos == 12.0
    assert parejas[0].placa_coincide_exacta
    assert sin_a == () and sin_b == ()


def test_empareja_pese_a_un_error_de_lectura():
    """El proposito del cruce: reconocer al mismo vehiculo leido distinto."""
    a = [_paso("PBN2792", 0)]
    b = [_paso("PBN2T92", 12, "B")]

    parejas, _, _ = emparejar(a, b, minutos_min=5, minutos_max=25)

    assert len(parejas) == 1
    assert not parejas[0].placa_coincide_exacta


def test_no_empareja_fuera_de_la_ventana_de_tiempo():
    """Una coincidencia de placa a horas de distancia es otro paso distinto."""
    a = [_paso("PCX6575", 0)]
    b = [_paso("PCX6575", 120, "B")]

    parejas, sin_a, sin_b = emparejar(a, b, minutos_min=5, minutos_max=25)

    assert parejas == ()
    assert len(sin_a) == 1 and len(sin_b) == 1


def test_no_empareja_placas_demasiado_distintas():
    """Dos vehiculos distintos en la ventana no se emparejan entre si."""
    a = [_paso("PBN2792", 0)]
    b = [_paso("PDK8093", 12, "B")]

    parejas, sin_a, sin_b = emparejar(a, b)

    assert parejas == ()
    assert len(sin_a) == 1 and len(sin_b) == 1


def test_cada_paso_se_empareja_una_sola_vez():
    """Un vehiculo no puede salir dos veces por el mismo ingreso."""
    a = [_paso("PCX6575", 0)]
    b = [_paso("PCX6575", 10, "B"), _paso("PCX6575", 14, "B")]

    parejas, sin_a, sin_b = emparejar(a, b, minutos_min=5, minutos_max=25)

    assert len(parejas) == 1
    assert len(sin_b) == 1


def test_prefiere_la_placa_mas_parecida():
    """Ante dos candidatos, gana el de lectura identica."""
    a = [_paso("PBN2792", 0)]
    b = [_paso("PBN2T92", 10, "B"), _paso("PBN2792", 14, "B")]

    parejas, _, _ = emparejar(a, b, minutos_min=5, minutos_max=25)

    assert parejas[0].paso_b.placa == "PBN2792"


def test_reporta_los_que_no_completaron_el_recorrido():
    """Quien entra y no sale es el hallazgo que interesa al estudio."""
    a = [_paso("PCX6575", 0), _paso("ABC1234", 1)]
    b = [_paso("PCX6575", 12, "B")]

    parejas, sin_a, sin_b = emparejar(a, b, minutos_min=5, minutos_max=25)

    assert len(parejas) == 1
    assert [p.placa for p in sin_a] == ["ABC1234"]


def test_parametros_invalidos():
    """Los rangos incoherentes se rechazan de forma explícita."""
    with pytest.raises(CruceError, match="minutos_min"):
        emparejar([], [], minutos_min=30, minutos_max=10)

    with pytest.raises(CruceError, match="distancia_maxima"):
        emparejar([], [], distancia_maxima=-1)

    with pytest.raises(CruceError, match="ventana_segundos"):
        consolidar_capturas([], ventana_segundos=-1)
