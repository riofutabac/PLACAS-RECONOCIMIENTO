"""Wiring de configuración y checkpoint ante fallos de evidencia."""

from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import ANY, Mock

import pytest

from lastre.evidencia import EvidenciaError
from scripts import procesar_lote as lote


def test_flags_movimiento_llegan_a_los_constructores(monkeypatch, tmp_path):
    movimiento = Mock(return_value=object())
    vehiculos = Mock(return_value=object())
    hibrido = Mock(return_value=object())
    monkeypatch.setattr(lote, "DetectorMovimiento", movimiento)
    monkeypatch.setattr(lote, "DetectorVehiculos", vehiculos)
    monkeypatch.setattr(lote, "DetectorHibrido", hibrido)
    monkeypatch.setattr(lote, "obtener_metadatos_video", lambda p: NS(fps=25))
    monkeypatch.setattr(lote, "iterar_cuadros", lambda p: iter(()))
    config = NS(seguimiento=NS(distancia_maxima=100, tolerancia_oclusion=2))
    args = NS(escala_movimiento=0.125, paso_movimiento=7, paso=5,
              observaciones_minimas=2)

    assert lote.procesar_video(Path("v.mp4"), config, None, None,
                               args, tmp_path, ()) == []
    movimiento.assert_called_once_with(config, factor_escala=0.125)
    hibrido.assert_called_once_with(movimiento.return_value, vehiculos.return_value,
                                    paso=5, paso_movimiento=7, medidor=ANY)


@pytest.mark.parametrize("error", [EvidenciaError("JPEG fallido"), OSError("disco lleno")])
def test_error_de_evidencia_no_guarda_checkpoint(monkeypatch, tmp_path, error, capsys):
    video = tmp_path / "video.mp4"
    video.touch()
    args = NS(carpeta=str(tmp_path), out_dir=str(tmp_path / "salida"),
              config="unused", acelerador="cpu", limite=None, reiniciar=False,
              solo_informe=False)
    avance = Mock()
    avance.videos_hechos = ()
    avance.ruta = tmp_path / "avance.json"
    avance.cuadros_hechos.return_value = 0
    avance.esta_hecho.return_value = False
    avance.todas_las_filas.return_value = []
    entregar = Mock()
    monkeypatch.setattr(lote, "parse_args", lambda: args)
    monkeypatch.setattr(lote, "cargar_configuracion", lambda p: None)
    monkeypatch.setattr(lote, "elegir_proveedores", lambda a: ("CPUExecutionProvider",))
    monkeypatch.setattr(lote, "listar_videos", lambda *a: [video])
    monkeypatch.setattr(lote, "obtener_metadatos_video", lambda p: NS(total_cuadros=10))
    monkeypatch.setattr(lote, "Checkpoint", lambda p: avance)
    monkeypatch.setattr(lote, "cargar_plantillas", lambda: None)
    monkeypatch.setattr(lote, "LectorPlacas", lambda **k: object())
    monkeypatch.setattr(lote, "procesar_video", Mock(side_effect=error))
    monkeypatch.setattr(lote, "_entregar", entregar)

    lote.main()

    avance.guardar_video.assert_not_called()
    entregar.assert_called_once()
    assert entregar.call_args.args[5] == [(video.name, str(error))]
    assert str(error) in capsys.readouterr().err
