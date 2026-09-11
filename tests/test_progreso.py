"""Pruebas unitarias para el módulo lastre.progreso."""

import time

import pytest

from lastre.progreso import Progreso, ProgresoError


def test_porcentaje_refleja_los_cuadros_procesados():
    """El avance se mide sobre el total de cuadros del lote."""
    progreso = Progreso(total_cuadros=1000, videos_totales=2)

    progreso.avanzar(250)

    assert progreso.porcentaje == pytest.approx(25.0)


def test_avance_parcial_de_un_video_cuenta():
    """Un video a medias también es trabajo hecho, no espera al final."""
    progreso = Progreso(total_cuadros=8000, videos_totales=2)

    progreso.avanzar(2000)

    assert 0 < progreso.porcentaje < 50
    assert progreso.videos_hechos == 0


def test_porcentaje_nunca_supera_cien():
    """Un conteo de cuadros mayor al previsto no rompe la escala."""
    progreso = Progreso(total_cuadros=100, videos_totales=1)

    progreso.avanzar(500)

    assert progreso.porcentaje == 100.0


def test_lote_vacio_esta_terminado():
    """Sin cuadros que procesar el lote está completo."""
    assert Progreso(total_cuadros=0).porcentaje == 100.0


def test_cuenta_videos_completados():
    """El avance informa cuántos videos se terminaron."""
    progreso = Progreso(total_cuadros=1000, videos_totales=3)

    progreso.terminar_video()
    progreso.terminar_video()

    assert progreso.videos_hechos == 2


def test_no_cuenta_mas_videos_de_los_previstos():
    """El contador de videos no excede el total del lote."""
    progreso = Progreso(total_cuadros=100, videos_totales=1)

    progreso.terminar_video()
    progreso.terminar_video()

    assert progreso.videos_hechos == 1


def test_sin_avance_no_hay_estimacion():
    """El tiempo restante no se inventa antes de tener datos."""
    assert Progreso(total_cuadros=1000, videos_totales=1).restante_estimado is None


def test_estima_el_tiempo_restante_con_el_ritmo_observado():
    """Con la mitad hecha, falta aproximadamente lo ya transcurrido."""
    progreso = Progreso(total_cuadros=1000, videos_totales=1)
    time.sleep(0.05)
    progreso.avanzar(500)

    restante = progreso.restante_estimado

    assert restante is not None
    assert restante == pytest.approx(progreso.transcurrido, rel=0.5)


def test_linea_muestra_porcentaje_y_avance_de_videos():
    """La línea de consola informa porcentaje y videos completados."""
    progreso = Progreso(total_cuadros=1000, videos_totales=4)
    progreso.avanzar(500)
    progreso.terminar_video()

    linea = progreso.linea("procesando muestra.mp4")

    assert "50.0%" in linea
    assert "1/4" in linea
    assert "procesando muestra.mp4" in linea


def test_parametros_invalidos():
    """Los valores negativos se rechazan de forma explícita."""
    with pytest.raises(ProgresoError, match="total_cuadros"):
        Progreso(total_cuadros=-1)

    with pytest.raises(ProgresoError, match="cuadros"):
        Progreso(total_cuadros=100).avanzar(-5)
