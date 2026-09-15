import cv2
import numpy as np
import pytest

from lastre.imagenes import guardar_imagen


def test_guarda_imagen_legible(tmp_path):
    ruta = tmp_path / "evidencia.jpg"
    guardar_imagen(ruta, np.full((20, 30, 3), 120, dtype=np.uint8))
    assert cv2.imread(str(ruta)).shape == (20, 30, 3)


def test_escritura_false_es_error_visible(monkeypatch, tmp_path):
    monkeypatch.setattr(cv2, "imwrite", lambda *a: False)
    with pytest.raises(OSError, match="evidencia.jpg"):
        guardar_imagen(tmp_path / "evidencia.jpg", np.zeros((2, 2, 3), np.uint8))


def test_error_opencv_se_traduce_con_causa(monkeypatch, tmp_path):
    def fallar(*args):
        raise cv2.error("fallo del codec")
    monkeypatch.setattr(cv2, "imwrite", fallar)
    with pytest.raises(OSError, match="evidencia.jpg") as error:
        guardar_imagen(tmp_path / "evidencia.jpg", np.zeros((2, 2, 3), np.uint8))
    assert isinstance(error.value.__cause__, cv2.error)
