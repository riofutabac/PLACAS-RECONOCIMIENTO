"""Pruebas de la depuracion de filas previa al informe.

Se aplica tambien sobre registros ya guardados, de modo que regenerar el
informe corrige datos antiguos sin reprocesar ningun video.
"""

import importlib.util
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parent.parent / "scripts" / "procesar_lote.py"
_spec = importlib.util.spec_from_file_location("procesar_lote", RUTA)
procesar_lote = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(procesar_lote)

depurar = procesar_lote._depurar_filas


def _fila(placa, tiempo, video="a.mp4"):
    return {"placa": placa, "video": video, "tiempo_video": tiempo, "tipo_vehiculo": ""}


def test_fusiona_repeticiones_cercanas_del_mismo_vehiculo():
    """Reproduce el caso real de PCX6575 registrada tres veces en 28 segundos."""
    filas = [_fila("PCX6575", "00:04"), _fila("PCX6575", "00:28"), _fila("PCX6575", "00:31")]

    assert len(depurar(filas)) == 1


def test_conserva_un_segundo_paso_lejano_en_el_tiempo():
    """El mismo vehiculo puede volver a pasar mas tarde; eso no es duplicado."""
    filas = [_fila("PCX6575", "00:04"), _fila("PCX6575", "04:00")]

    assert len(depurar(filas)) == 2


def test_no_fusiona_entre_videos_distintos():
    """Una placa repetida en otro video es otro paso, no una repeticion."""
    filas = [_fila("PCX6575", "00:04", "a.mp4"), _fila("PCX6575", "00:06", "b.mp4")]

    assert len(depurar(filas)) == 2


def test_nunca_descarta_registros_sin_placa():
    """Sin identidad no se puede afirmar que sean el mismo vehiculo."""
    filas = [_fila("", "01:10"), _fila("", "01:12"), _fila(None, "01:14")]

    assert len(depurar(filas)) == 3


def test_completa_el_tipo_segun_el_formato_de_placa():
    """Dos letras es motocicleta y tres es automovil, sin mirar el video."""
    resultado = depurar([_fila("PCX6575", "00:04"), _fila("AB123", "01:00")])

    tipos = {f["placa"]: f["tipo_vehiculo"] for f in resultado}
    assert tipos["PCX6575"] == "automovil"
    assert tipos["AB123"] == "motocicleta"


def test_respeta_un_tipo_ya_asignado():
    """Si el tipo venia informado no se sobrescribe."""
    fila = _fila("PCX6575", "00:04")
    fila["tipo_vehiculo"] = "camion"

    assert depurar([fila])[0]["tipo_vehiculo"] == "camion"


def test_tipo_vacio_cuando_no_hay_placa():
    """Sin placa no se puede deducir el tipo."""
    assert depurar([_fila("", "00:04")])[0]["tipo_vehiculo"] == ""


def test_no_muta_las_filas_recibidas():
    """La depuracion devuelve copias y deja intacta la entrada."""
    filas = [_fila("PCX6575", "00:04")]
    copia = [dict(f) for f in filas]

    depurar(filas)

    assert filas == copia


def test_tiempo_ilegible_no_rompe_la_depuracion():
    """Un tiempo mal formado no debe impedir la entrega del informe."""
    filas = [_fila("PCX6575", "sin dato"), _fila("PCX6575", "00:04")]

    assert len(depurar(filas)) == 2


def test_lista_vacia():
    """Un lote sin filas produce una salida vacia, no un error."""
    assert depurar([]) == []
