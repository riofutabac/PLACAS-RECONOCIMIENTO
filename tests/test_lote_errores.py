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
              solo_informe=False, paso=3, paso_movimiento=1, escala_movimiento=.25,
              observaciones_minimas=10, umbral=.75, minimo_lecturas=2)
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
    monkeypatch.setattr(lote, "Checkpoint", lambda p, **kwargs: avance)
    monkeypatch.setattr(lote, "cargar_plantillas", lambda: None)
    monkeypatch.setattr(lote, "LectorPlacas", lambda **k: object())
    monkeypatch.setattr(lote, "procesar_video", Mock(side_effect=error))
    monkeypatch.setattr(lote, "_entregar", entregar)

    lote.main()

    avance.guardar_video.assert_not_called()
    entregar.assert_called_once()
    assert entregar.call_args.args[5] == [(video.name, str(error))]
    assert str(error) in capsys.readouterr().err


def test_reutilizacion_de_sesiones_y_reinicio_de_seguimiento_entre_videos(monkeypatch, tmp_path):
    """Verifica que detector y lector se reutilicen entre videos y el seguimiento se reinicie."""
    video1 = tmp_path / "v1.mp4"
    video2 = tmp_path / "v2.mp4"
    video1.touch()
    video2.touch()

    args = NS(
        carpeta=str(tmp_path),
        out_dir=str(tmp_path / "salida"),
        config="unused",
        acelerador="cpu",
        limite=None,
        reiniciar=False,
        solo_informe=False,
        hilos=None,
        paso=3,
        paso_movimiento=1,
        escala_movimiento=0.25,
        observaciones_minimas=10,
        umbral=.75,
        minimo_lecturas=2,
    )

    mock_detector_instancia = Mock(name="detector_vehiculos_instancia", sesion=object())
    mock_detector_clase = Mock(return_value=mock_detector_instancia)

    mock_lector_instancia = Mock(name="lector_placas_instancia", sesiones={"ocr": object()})
    mock_lector_clase = Mock(return_value=mock_lector_instancia)

    movimientos_creados = []
    seguidores_creados = []

    def fake_procesar_video(ruta, config, lector, progreso, args, dir_recortes,
                           proveedores, plantillas_reloj, medidor, detector_vehiculos=None):
        # Verificar que recibe las instancias reutilizadas
        assert lector is mock_lector_instancia
        assert detector_vehiculos is mock_detector_instancia
        # Simular instanciación de movimiento y seguidor como hace procesar_video real
        mov = lote.DetectorMovimiento(config, factor_escala=args.escala_movimiento)
        seg = lote.SeguidorTrayectorias(config)
        movimientos_creados.append(mov)
        seguidores_creados.append(seg)
        return [{"video": ruta.name, "placa": "ABC1234", "estado": "validado"}]

    avance = Mock()
    avance.videos_hechos = ()
    avance.ruta = tmp_path / "avance.json"
    avance.cuadros_hechos.return_value = 0
    avance.esta_hecho.return_value = False
    avance.todas_las_filas.return_value = []

    monkeypatch.setattr(lote, "parse_args", lambda: args)
    monkeypatch.setattr(lote, "cargar_configuracion", lambda p: NS())
    monkeypatch.setattr(lote, "elegir_proveedores", lambda a: ("CPUExecutionProvider",))
    monkeypatch.setattr(lote, "listar_videos", lambda *a: [video1, video2])
    monkeypatch.setattr(lote, "obtener_metadatos_video", lambda p: NS(total_cuadros=100))
    monkeypatch.setattr(lote, "Checkpoint", lambda p, **kwargs: avance)
    monkeypatch.setattr(lote, "cargar_plantillas", lambda: None)
    monkeypatch.setattr(lote, "LectorPlacas", mock_lector_clase)
    monkeypatch.setattr(lote, "DetectorVehiculos", mock_detector_clase)
    monkeypatch.setattr(lote, "DetectorMovimiento", Mock(side_effect=lambda *a, **k: Mock()))
    monkeypatch.setattr(lote, "SeguidorTrayectorias", Mock(side_effect=lambda *a, **k: Mock()))
    monkeypatch.setattr(lote, "verificar_sesiones", lambda m, a: (True, ("ok",)))
    monkeypatch.setattr(lote, "procesar_video", fake_procesar_video)
    monkeypatch.setattr(lote, "_entregar", Mock())

    lote.main()

    # Los modelos deben construirse UNA SOLA VEZ para todo el lote
    mock_detector_clase.assert_called_once()
    mock_lector_clase.assert_called_once()

    # Movimiento y seguidor deben construirse de nuevo para CADA video (2 veces)
    assert len(movimientos_creados) == 2
    assert movimientos_creados[0] is not movimientos_creados[1]
    assert len(seguidores_creados) == 2
    assert seguidores_creados[0] is not seguidores_creados[1]

    # Checkpoint debe guardarse por video individual
    assert avance.guardar_video.call_count == 2
    assert avance.guardar_video.call_args_list[0].args[0] == video1.name
    assert avance.guardar_video.call_args_list[1].args[0] == video2.name
