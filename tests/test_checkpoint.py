"""Pruebas unitarias para el módulo lastre.checkpoint."""

import json

import pytest

from lastre.checkpoint import Checkpoint, CheckpointError


def _filas(placa):
    return [{"placa": placa, "sentido": "sale", "estado": "validado"}]


def test_marca_un_video_como_procesado(tmp_path):
    """Tras guardar un video, el avance lo reconoce como hecho."""
    avance = Checkpoint(tmp_path)

    avance.guardar_video("v1.mp4", _filas("PCW2497"), cuadros=8222)

    assert avance.esta_hecho("v1.mp4")
    assert not avance.esta_hecho("v2.mp4")


def test_el_avance_sobrevive_a_una_sesion_nueva(tmp_path):
    """Reabrir el lote recupera lo ya procesado, que es el punto de reanudar."""
    Checkpoint(tmp_path).guardar_video("v1.mp4", _filas("PCW2497"), cuadros=8222)

    reanudado = Checkpoint(tmp_path)

    assert reanudado.esta_hecho("v1.mp4")
    assert reanudado.filas_de("v1.mp4")[0]["placa"] == "PCW2497"
    assert reanudado.cuadros_hechos() == 8222


def test_acumula_las_filas_de_todos_los_videos(tmp_path):
    """El informe final se arma con lo guardado de cada video."""
    avance = Checkpoint(tmp_path)
    avance.guardar_video("v1.mp4", _filas("PCW2497"))
    avance.guardar_video("v2.mp4", _filas("TAA2204"))

    placas = [f["placa"] for f in avance.todas_las_filas()]

    assert sorted(placas) == ["PCW2497", "TAA2204"]


def test_un_archivo_corrupto_no_impide_arrancar(tmp_path):
    """Un corte a mitad de escritura no debe bloquear la siguiente corrida."""
    (tmp_path / "avance.json").write_text("{ esto no es json", encoding="utf-8")

    avance = Checkpoint(tmp_path)

    assert avance.videos_hechos == ()


def test_la_escritura_es_atomica(tmp_path):
    """El archivo final siempre queda como JSON completo y legible."""
    avance = Checkpoint(tmp_path)
    avance.guardar_video("v1.mp4", _filas("PCW2497"))

    datos = json.loads((tmp_path / "avance.json").read_text(encoding="utf-8"))

    assert "v1.mp4" in datos["videos"]
    assert not (tmp_path / "avance.tmp").exists()


def test_reprocesar_un_video_reemplaza_su_resultado(tmp_path):
    """Volver a procesar un video no duplica sus filas."""
    avance = Checkpoint(tmp_path)
    avance.guardar_video("v1.mp4", _filas("PCW2497"))
    avance.guardar_video("v1.mp4", _filas("TAA2204"))

    assert len(avance.todas_las_filas()) == 1
    assert avance.todas_las_filas()[0]["placa"] == "TAA2204"


def test_olvidar_permite_volver_a_procesar(tmp_path):
    """Se puede descartar un video para repetirlo en la siguiente corrida."""
    avance = Checkpoint(tmp_path)
    avance.guardar_video("v1.mp4", _filas("PCW2497"))

    avance.olvidar("v1.mp4")

    assert not avance.esta_hecho("v1.mp4")
    assert Checkpoint(tmp_path).videos_hechos == ()


def test_nombre_vacio_se_rechaza(tmp_path):
    """Un video sin nombre no puede registrarse."""
    with pytest.raises(CheckpointError, match="nombre"):
        Checkpoint(tmp_path).guardar_video("", [])


def test_guarda_y_recupera_manifiesto(tmp_path):
    """El checkpoint debe persistir el manifiesto de la corrida."""
    manifiesto = {"modelo_vehiculos": "yolo26n", "peso_hash": "abc123hash"}
    avance = Checkpoint(tmp_path, manifiesto=manifiesto)
    avance.guardar_video("v1.mp4", _filas("PCW2497"))

    reanudado = Checkpoint(tmp_path, manifiesto=manifiesto)
    assert reanudado.manifiesto == manifiesto
    assert reanudado.esta_hecho("v1.mp4")


def test_rechaza_manifiesto_incompatible(tmp_path):
    """Reanudar con un modelo o pesos distintos debe lanzar CheckpointError."""
    manifiesto1 = {"modelo_vehiculos": "rf-detr-nano-384-coco", "peso_hash": "hash_a"}
    avance = Checkpoint(tmp_path, manifiesto=manifiesto1)
    avance.guardar_video("v1.mp4", _filas("PCW2497"))

    manifiesto2 = {"modelo_vehiculos": "yolo26n", "peso_hash": "hash_b"}
    with pytest.raises(CheckpointError, match="Conflicto en checkpoint"):
        Checkpoint(tmp_path, manifiesto=manifiesto2)


def test_rechaza_checkpoint_sin_identidad_cuando_se_espera_modelo(tmp_path):
    """Un checkpoint previo sin manifiesto no debe aceptarse para una corrida con modelo."""
    avance_sin_id = Checkpoint(tmp_path)
    avance_sin_id.guardar_video("v1.mp4", _filas("PCW2497"))

    manifiesto_yolo = {"modelo_vehiculos": "yolo26n"}
    with pytest.raises(CheckpointError, match="no tiene manifiesto de identidad"):
        Checkpoint(tmp_path, manifiesto=manifiesto_yolo)


@pytest.mark.parametrize("cambio", [{"peso_hash": "nuevo"}, {"paso": 4}, {"tamano_entrada": [320, 320]}])
def test_rechaza_campos_ausentes_o_modificados(tmp_path, cambio):
    base = {"modelo_vehiculos": "yolo26n", "paso": 3}
    Checkpoint(tmp_path, manifiesto=base).guardar_video("v.mp4", [])
    with pytest.raises(CheckpointError):
        Checkpoint(tmp_path, manifiesto={**base, **cambio})
