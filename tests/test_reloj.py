"""Pruebas unitarias para el módulo lastre.reloj."""

from datetime import datetime

import numpy as np
import pytest

from lastre.reloj import (
    MarcaTemporal,
    RelojError,
    es_coherente,
    interpretar,
    rango_de_nombre,
    recortar_franja_reloj,
)


def test_interpreta_la_marca_de_la_camara():
    """La cámara imprime la marca como DD/MM/AAAA HH:MM:SS."""
    assert interpretar("09/09/2026 16:17:47") == datetime(2026, 9, 9, 16, 17, 47)


def test_tolera_espacios_dentro_de_la_hora():
    """El reconocimiento suele separar los dos puntos de la hora."""
    assert interpretar("Network Camera 09/09/2026 16: 17: 47") == datetime(2026, 9, 9, 16, 17, 47)


def test_texto_sin_marca_devuelve_none():
    """Sin marca reconocible no se inventa una fecha."""
    for texto in ("", "Network Camera", "16:17", None, 12345):
        assert interpretar(texto) is None


def test_fecha_imposible_se_descarta():
    """Un dígito mal leído puede producir una fecha que no existe."""
    assert interpretar("32/13/2026 25:99:99") is None


def test_extrapola_la_hora_de_otro_cuadro():
    """Con una marca de referencia se fecha cualquier cuadro del video."""
    marca = MarcaTemporal(cuadro=100, momento=datetime(2026, 9, 9, 16, 17, 47))

    # 25 cuadros despues a 25 fps es exactamente un segundo
    assert marca.en_cuadro(125, 25.0) == datetime(2026, 9, 9, 16, 17, 48)
    # Tambien hacia atras
    assert marca.en_cuadro(75, 25.0) == datetime(2026, 9, 9, 16, 17, 46)


def test_extrapolar_con_fps_invalido_falla():
    """Una tasa de cuadros no positiva se rechaza de forma explícita."""
    marca = MarcaTemporal(cuadro=1, momento=datetime(2026, 9, 9, 16, 0, 0))

    with pytest.raises(RelojError, match="fps"):
        marca.en_cuadro(100, 0)


def test_recorta_la_franja_superior_derecha():
    """La marca vive en la banda superior, hacia la derecha del cuadro."""
    cuadro = np.zeros((1664, 2960, 3), dtype=np.uint8)

    franja = recortar_franja_reloj(cuadro)

    assert franja.shape[0] < cuadro.shape[0] * 0.1
    assert franja.shape[1] < cuadro.shape[1] * 0.5


def test_el_recorte_no_modifica_el_cuadro():
    """El recorte es una copia independiente."""
    cuadro = np.zeros((100, 200, 3), dtype=np.uint8)
    copia = cuadro.copy()

    recortar_franja_reloj(cuadro)[:] = 255

    assert np.array_equal(cuadro, copia)


def test_valida_la_coherencia_con_la_fecha_esperada():
    """Una lectura desplazada por años se detecta como incoherente."""
    esperada = datetime(2026, 9, 9, 16, 0, 0)

    assert es_coherente(datetime(2026, 9, 9, 16, 17, 47), esperada)
    assert not es_coherente(datetime(2020, 9, 9, 16, 17, 47), esperada)


def test_extrae_el_rango_del_nombre_de_archivo():
    """El nombre codifica el rango de toda la grabación, no de un fragmento."""
    nombre = "Camara Placas 2_20260909105651-20260909163038(60).mp4"

    inicio, fin = rango_de_nombre(nombre)

    assert inicio == datetime(2026, 9, 9, 10, 56, 51)
    assert fin == datetime(2026, 9, 9, 16, 30, 38)


def test_nombre_sin_fechas_devuelve_none():
    """Un nombre sin el patrón esperado no produce un rango inventado."""
    assert rango_de_nombre("video.mp4") is None
    assert rango_de_nombre("") is None


def test_el_rango_del_nombre_no_fecha_un_fragmento():
    """Documenta el error corregido: el fragmento 60 no empieza a las 10:56.

    El reloj del cuadro marcaba 16:17 mientras el nombre sugeria 10:56, mas
    de cinco horas de diferencia en cada registro del informe.
    """
    inicio, fin = rango_de_nombre("Camara Placas 2_20260909105651-20260909163038(60).mp4")
    real = interpretar("09/09/2026 16:17:47")

    assert inicio < real < fin
    assert (real - inicio).total_seconds() > 5 * 3600
