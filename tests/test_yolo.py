"""Pruebas unitarias para el adaptador YOLO26 (lastre.yolo)."""

from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
import pytest

from lastre.yolo import (
    CajaEsquinas,
    COCO_CLASSES,
    DeteccionCruda,
    YOLO26Detector,
    YOLODeteccionError,
    calcular_hash_archivo,
    resolver_ruta_modelo_yolo,
)


def test_resolver_ruta_modelo_existente(tmp_path):
    """Verifica que una ruta existente se resuelva directamente."""
    dummy = tmp_path / "modelo_prueba.onnx"
    dummy.write_text("test")
    res = resolver_ruta_modelo_yolo(dummy)
    assert res == dummy.resolve()


def test_resolver_ruta_modelo_inexistente_lanza_error():
    """Verifica que un modelo no encontrado lance YOLODeteccionError explicativo."""
    with pytest.raises(YOLODeteccionError, match="No se encontró el archivo del modelo YOLO"):
        resolver_ruta_modelo_yolo("modelo_que_no_existe_12345")


def test_calcular_hash_archivo(tmp_path):
    """Verifica el cálculo correcto de SHA256 sobre un archivo."""
    archivo = tmp_path / "archivo.bin"
    archivo.write_bytes(b"antigravity-yolo26")
    import hashlib
    esperado = hashlib.sha256(b"antigravity-yolo26").hexdigest()
    assert calcular_hash_archivo(archivo) == esperado


def test_preprocesamiento_letterbox_dimensiones_y_normalizacion():
    """Verifica letterbox a 640x640 con padding 114 y normalización [0, 1]."""
    detector = YOLO26Detector(modelo="yolo26n", session=MagicMock())

    # Imagen simulada 1920x1080 (alto=1080, ancho=1920)
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    img[:, :] = [50, 100, 150]  # BGR

    tensor, escala, pad_w, pad_h = detector.preprocesar(img)

    assert tensor.shape == (1, 3, 640, 640)
    assert tensor.dtype == np.float32
    assert pad_w == 0
    # Escala: 640 / 1920 = 0.3333...
    # Altura redimensionada: 1080 * (640/1920) = 360
    # Padding vertical: (640 - 360) // 2 = 140
    assert pad_h == 140
    assert escala == pytest.approx(640.0 / 1920.0, rel=1e-3)

    # Verificar que el borde acolchado tenga el valor 114 / 255.0
    val_pad = 114.0 / 255.0
    assert tensor[0, 0, 0, 0] == pytest.approx(val_pad, abs=1e-3)

    # Verificar conversión BGR a RGB en el área central
    # BGR [50, 100, 150] -> RGB [150, 100, 50]
    assert tensor[0, 0, 200, 200] == pytest.approx(150.0 / 255.0, abs=1e-3)
    assert tensor[0, 1, 200, 200] == pytest.approx(100.0 / 255.0, abs=1e-3)
    assert tensor[0, 2, 200, 200] == pytest.approx(50.0 / 255.0, abs=1e-3)


def test_preprocesamiento_errores_tipo_y_forma():
    """Verifica validación de entradas inválidas."""
    detector = YOLO26Detector(modelo="yolo26n", session=MagicMock())

    with pytest.raises(YOLODeteccionError, match="numpy.ndarray"):
        detector.preprocesar("no_es_array")

    with pytest.raises(YOLODeteccionError, match="forma"):
        detector.preprocesar(np.zeros((640, 640), dtype=np.uint8))

    with pytest.raises(YOLODeteccionError, match="vacío"):
        detector.preprocesar(np.zeros((0, 0, 3), dtype=np.uint8))


def test_predict_desescala_coordenadas_al_espacio_original():
    """Verifica que las coordenadas de salida se transformen inversamente al tamaño original."""
    mock_session = MagicMock()
    detector = YOLO26Detector(modelo="yolo26n", session=mock_session)

    # Simular una imagen original de 1000x2000 (H=1000, W=2000)
    img = np.zeros((1000, 2000, 3), dtype=np.uint8)

    # Para 2000x1000: escala = 640/2000 = 0.32
    # nw = 640, nh = 320, pad_w = 0, pad_h = 160
    # Simulamos una detección en el espacio letterbox 640x640:
    # x1=160, y1=240, x2=320, y2=400, conf=0.88, cls_id=2 (car)
    mock_out = np.array([[[160.0, 240.0, 320.0, 400.0, 0.88, 2.0]]], dtype=np.float32)
    mock_session.run.return_value = [mock_out]

    dets = detector.predict(img)

    assert len(dets) == 1
    d = dets[0]
    assert d.label == "car"
    assert d.confidence == pytest.approx(0.88, abs=1e-3)

    # Inversión:
    # x1 = (160 - 0) / 0.32 = 500
    # y1 = (240 - 160) / 0.32 = 80 / 0.32 = 250
    # x2 = (320 - 0) / 0.32 = 1000
    # y2 = (400 - 160) / 0.32 = 240 / 0.32 = 750
    assert d.bounding_box.x1 == 500
    assert d.bounding_box.y1 == 250
    assert d.bounding_box.x2 == 1000
    assert d.bounding_box.y2 == 750


def test_predict_lote_de_imagenes():
    """Verifica que predict soporte listas de imágenes devolviendo listas de listas."""
    mock_session = MagicMock()
    detector = YOLO26Detector(modelo="yolo26n", session=mock_session)

    mock_out = np.array([[[10.0, 10.0, 50.0, 50.0, 0.9, 3.0]]], dtype=np.float32)
    mock_session.run.return_value = [mock_out]

    img1 = np.zeros((100, 100, 3), dtype=np.uint8)
    img2 = np.zeros((200, 200, 3), dtype=np.uint8)

    dets = detector.predict([img1, img2])
    assert len(dets) == 2
    assert isinstance(dets[0], list)
    assert isinstance(dets[1], list)
    assert dets[0][0].label == "motorcycle"


def test_rechaza_salida_onnx_sin_posprocesar():
    sesion = MagicMock()
    sesion.run.return_value = [np.zeros((1, 84, 8400), dtype=np.float32)]
    detector = YOLO26Detector(session=sesion)
    with pytest.raises(YOLODeteccionError, match="incompatible"):
        detector.predict(np.zeros((100, 100, 3), dtype=np.uint8))


def test_descarta_predicciones_no_finitas():
    sesion = MagicMock()
    sesion.run.return_value = [np.array([[[1, 1, 20, 20, .9, np.nan]]])]
    assert YOLO26Detector(session=sesion).predict(np.zeros((100, 100, 3), dtype=np.uint8)) == []
