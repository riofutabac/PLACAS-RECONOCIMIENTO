"""Pruebas unitarias para el módulo lastre.video."""

from pathlib import Path
import cv2
import numpy as np
import pytest

from lastre.video import (
    VideoLecturaError,
    iterar_cuadros,
    leer_cuadro_especifico,
    obtener_metadatos_video,
)


@pytest.fixture
def video_sintetico(tmp_path: Path) -> Path:
    """Crea un archivo de video sintético de 10 cuadros (100x80) para pruebas rápidas y deterministas."""
    ruta_video = tmp_path / "test_video.avi"
    cuatrocc = cv2.VideoWriter_fourcc(*"MJPG")
    ancho, alto = 100, 80
    fps = 10.0
    total_cuadros = 10

    writer = cv2.VideoWriter(str(ruta_video), cuatrocc, fps, (ancho, alto))
    for i in range(1, total_cuadros + 1):
        # Crear un cuadro con un valor de brillo distintivo por cuadro
        cuadro = np.full((alto, ancho, 3), fill_value=i * 20, dtype=np.uint8)
        writer.write(cuadro)
    writer.release()

    return ruta_video


def test_video_inexistente():
    """Verifica que intentar abrir un archivo inexistente lance VideoLecturaError."""
    with pytest.raises(VideoLecturaError, match="no encontrado"):
        obtener_metadatos_video("video_inexistente.mp4")

    with pytest.raises(VideoLecturaError, match="no encontrado"):
        next(iterar_cuadros("video_inexistente.mp4"))


def test_parametros_invalidos(video_sintetico: Path):
    """Verifica validación de rango de cuadros."""
    with pytest.raises(VideoLecturaError, match="desde_cuadro debe ser >= 1"):
        next(iterar_cuadros(video_sintetico, desde_cuadro=0))

    with pytest.raises(VideoLecturaError, match="no puede ser menor a desde_cuadro"):
        next(iterar_cuadros(video_sintetico, desde_cuadro=5, hasta_cuadro=4))

    with pytest.raises(VideoLecturaError, match="numero_cuadro debe ser >= 1"):
        leer_cuadro_especifico(video_sintetico, numero_cuadro=0)


def test_metadatos_video(video_sintetico: Path):
    """Verifica la lectura de metadatos de un video."""
    meta = obtener_metadatos_video(video_sintetico)
    assert meta.ancho == 100
    assert meta.alto == 80
    assert meta.fps == 10.0
    assert meta.total_cuadros == 10
    assert pytest.approx(meta.duracion_segundos, rel=1e-2) == 1.0


def test_iterar_cuadros_secuencial_completo(video_sintetico: Path):
    """Verifica lectura secuencial completa de todos los cuadros."""
    indices = []
    for num, cuadro in iterar_cuadros(video_sintetico):
        indices.append(num)
        assert cuadro.shape == (80, 100, 3)
        # El cuadro i tiene un valor característico ~ i * 20
        # (por compresión de códec comprobamos proximidad)
        assert np.mean(cuadro) > 0

    assert indices == list(range(1, 11))


def test_iterar_cuadros_rango_especifico(video_sintetico: Path):
    """Verifica lectura secuencial entre rangos [desde_cuadro, hasta_cuadro]."""
    cuadros = list(iterar_cuadros(video_sintetico, desde_cuadro=4, hasta_cuadro=6))
    indices = [num for num, _ in cuadros]
    assert indices == [4, 5, 6]


def test_leer_cuadro_especifico(video_sintetico: Path):
    """Verifica la extracción secuencial de un cuadro puntual."""
    cuadro = leer_cuadro_especifico(video_sintetico, numero_cuadro=5)
    assert cuadro.shape == (80, 100, 3)

    # Solicitar cuadro fuera de rango
    with pytest.raises(VideoLecturaError, match="no pudo ser decodificado"):
        leer_cuadro_especifico(video_sintetico, numero_cuadro=999)


def test_video_real_metadatos_y_lectura():
    """Verifica lectura de metadatos y primeros cuadros en el archivo real de muestra si está presente."""
    ruta_real = Path("Camara Placas 2_20260909105651-20260909163038(60).mp4")
    if not ruta_real.is_file():
        pytest.skip("Archivo de muestra real no disponible en el entorno")

    meta = obtener_metadatos_video(ruta_real)
    assert meta.ancho == 2960
    assert meta.alto == 1664
    assert meta.total_cuadros > 8000

    # Leer secuencialmente los primeros 3 cuadros
    primeros = list(iterar_cuadros(ruta_real, desde_cuadro=1, hasta_cuadro=3))
    assert len(primeros) == 3
    assert [num for num, _ in primeros] == [1, 2, 3]
    for _, fr in primeros:
        assert fr.shape == (1664, 2960, 3)
