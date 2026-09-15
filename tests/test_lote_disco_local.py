"""Pruebas para la reutilización de modelos y copia local (Colab) en scripts.procesar_lote."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from scripts.procesar_lote import main


def crear_video_ficticio(ruta: Path):
    """Crea un archivo binario ficticio simulando un video."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"video_data_ficticia" * 100)


def test_lista_videos_y_disco_local_ciclo_completo(tmp_path, monkeypatch):
    """Verifica que --lista-videos y --disco-local copien video por video,

    reutilicen los modelos cargados y eliminen la copia local tras cada video.
    """
    drive_dir = tmp_path / "drive_videos"
    drive_dir.mkdir()
    v1 = drive_dir / "Camara Placas 2_20260909105651-20260909163038(60).mp4"
    v2 = drive_dir / "Camara Placas 2_20260909105651-20260909163038(61).mp4"
    crear_video_ficticio(v1)
    crear_video_ficticio(v2)

    salida = tmp_path / "salida_drive"
    salida.mkdir()
    disco_local = tmp_path / "content_local"
    disco_local.mkdir()

    lista_archivo = tmp_path / "lista.txt"
    lista_archivo.write_text(f"{v1.resolve()}\n{v2.resolve()}\n", encoding="utf-8")

    # Mocks para evitar inferencia ONNX real y OpenCV pesado en pruebas unitarias
    mock_meta = MagicMock()
    mock_meta.total_cuadros = 100
    mock_meta.fps = 25.0

    instancias_detector = []

    def mock_crear_detector(*args, **kwargs):
        inst = MagicMock()
        inst.sesion = MagicMock()
        instancias_detector.append(inst)
        return inst

    copias_locales_vistas = []

    def mock_procesar_video(ruta, config, lector, progreso, args, dir_recortes, proveedores,
                           plantillas_reloj=None, medidor=None, detector_vehiculos=None):
        # Verificar que la ruta procesada esté dentro de disco_local y no en drive_dir
        assert disco_local in ruta.parents
        assert ruta.name in (v1.name, v2.name)
        assert ruta.is_file()
        copias_locales_vistas.append(ruta.name)
        # Devolver fila ficticia
        return [{
            "trayectoria_id": 1,
            "placa": "ABC1234",
            "hora_paso": "2026-09-09 16:17:46",
            "tiempo_video": "00:30",
            "video": ruta.name,
            "tipo_vehiculo": "automovil",
            "sentido": "sale",
            "confianza": 0.95,
            "consenso": 0.9,
            "lecturas": 5,
            "estado": "validado",
            "imagen": "",
        }]

    monkeypatch.setattr("scripts.procesar_lote.obtener_metadatos_video", lambda r: mock_meta)
    monkeypatch.setattr("scripts.procesar_lote.DetectorVehiculos", mock_crear_detector)
    monkeypatch.setattr("scripts.procesar_lote.LectorPlacas", lambda *a, **kw: MagicMock(sesiones={}))
    monkeypatch.setattr("scripts.procesar_lote.verificar_sesiones", lambda *a, **kw: (True, ["sesion ok"]))
    monkeypatch.setattr("scripts.procesar_lote.procesar_video", mock_procesar_video)
    monkeypatch.setattr("scripts.procesar_lote.cargar_plantillas", lambda *a: None)
    monkeypatch.setattr("scripts.procesar_lote._entregar", lambda *a, **kw: None)

    test_args = [
        "procesar_lote.py",
        str(drive_dir),
        "--lista-videos", str(lista_archivo),
        "--disco-local", str(disco_local),
        "--out-dir", str(salida),
        "--config", "config/zona.json",
        "--acelerador", "cpu",
    ]
    monkeypatch.setattr("sys.argv", test_args)

    main()

    # 1. Verificar que DetectorVehiculos se instanció UNA SOLA VEZ para todo el lote
    assert len(instancias_detector) == 1

    # 2. Verificar que ambos videos se procesaron desde disco local
    assert copias_locales_vistas == [v1.name, v2.name]

    # 3. Verificar que las copias locales temporales fueron eliminadas
    assert list(disco_local.glob("lastre-video-*")) == []

    # 4. Verificar que el avance se guardó con el nombre canónico de cada video
    avance_path = salida / "avance.json"
    assert avance_path.is_file()
    datos_avance = json.loads(avance_path.read_text(encoding="utf-8"))
    assert v1.name in datos_avance["videos"]
    assert v2.name in datos_avance["videos"]


def test_reanudacion_omite_videos_ya_hechos(tmp_path, monkeypatch):
    """Verifica que si un video ya está en avance.json, no se copie ni reprocese."""
    drive_dir = tmp_path / "drive_videos"
    drive_dir.mkdir()
    v1 = drive_dir / "video1.mp4"
    v2 = drive_dir / "video2.mp4"
    crear_video_ficticio(v1)
    crear_video_ficticio(v2)

    salida = tmp_path / "salida_drive"
    salida.mkdir()
    disco_local = tmp_path / "content_local"
    disco_local.mkdir()

    # v1 ya está en avance.json
    avance_inicial = {
        "version": 1,
        "videos": {
            v1.name: {"filas": [], "cuadros": 100}
        }
    }
    (salida / "avance.json").write_text(json.dumps(avance_inicial), encoding="utf-8")

    mock_meta = MagicMock()
    mock_meta.total_cuadros = 100
    mock_meta.fps = 25.0

    copias_locales_vistas = []

    def mock_procesar_video(ruta, *args, **kwargs):
        copias_locales_vistas.append(ruta.name)
        return []

    monkeypatch.setattr("scripts.procesar_lote.obtener_metadatos_video", lambda r: mock_meta)
    monkeypatch.setattr("scripts.procesar_lote.DetectorVehiculos", lambda *a, **kw: MagicMock(sesion=MagicMock()))
    monkeypatch.setattr("scripts.procesar_lote.LectorPlacas", lambda *a, **kw: MagicMock(sesiones={}))
    monkeypatch.setattr("scripts.procesar_lote.verificar_sesiones", lambda *a, **kw: (True, ["sesion ok"]))
    monkeypatch.setattr("scripts.procesar_lote.procesar_video", mock_procesar_video)
    monkeypatch.setattr("scripts.procesar_lote.cargar_plantillas", lambda *a: None)
    monkeypatch.setattr("scripts.procesar_lote._entregar", lambda *a, **kw: None)

    test_args = [
        "procesar_lote.py",
        str(drive_dir),
        "--disco-local", str(disco_local),
        "--out-dir", str(salida),
        "--config", "config/zona.json",
        "--acelerador", "cpu",
    ]
    monkeypatch.setattr("sys.argv", test_args)

    main()

    # Únicamente v2 debió ser copiado y procesado
    assert copias_locales_vistas == [v2.name]
    assert list(disco_local.glob("lastre-video-*")) == []
