"""Pruebas del flujo Colab sin Google Drive, descargas ni GPU."""
import ast
import base64
import hashlib
import io
import json
import sys
from pathlib import Path
import zipfile

import pytest

from colab.ejecucion import listar_videos, preparar_salida, procesar


def test_rutas_con_espacios_mayusculas_y_reanudacion(tmp_path):
    entrada = tmp_path / 'Cam PL'
    entrada.mkdir()
    videos = [entrada / 'video 1.MP4', entrada / 'video 2.mp4']
    for p in videos:
        p.write_bytes(b'video')
    assert listar_videos(entrada) == videos
    salida = preparar_salida(tmp_path / 'informes', videos, 'v1', 'gpu')
    comandos = []

    def runner(cmd, repo, log):
        comandos.append(cmd)
        if '--solo-informe' in cmd:
            enlaces = list(Path(cmd[5]).iterdir())
            assert all(p.is_symlink() and p.resolve().parent == entrada for p in enlaces)
            assert len(enlaces) == len(json.loads((salida / 'avance.json').read_text())['videos'])
            return
        temporal = Path(cmd[5])
        copia = next(temporal.iterdir())
        assert copia.read_bytes() == b'video'
        assert temporal != entrada
        archivo = salida / 'avance.json'
        avance = json.loads(archivo.read_text()) if archivo.exists() else {'videos': {}}
        avance['videos'][copia.name] = {'filas': [], 'cuadros': 1}
        archivo.write_text(json.dumps(avance))

    procesar(videos, salida, 'python', tmp_path, limite=1, local=tmp_path, runner=runner)
    procesar(videos, salida, 'python', tmp_path, local=tmp_path, runner=runner)
    assert len([c for c in comandos if '--solo-informe' not in c]) == 2
    assert all(p.exists() for p in videos)
    assert not list(tmp_path.glob('lastre-video-*'))
    assert len(json.loads((salida / 'avance.json').read_text())['videos']) == 2


def test_no_mezcla_versiones_o_videos_modificados(tmp_path):
    video = tmp_path / 'v.mp4'
    video.write_bytes(b'a')
    a = preparar_salida(tmp_path, [video], 'v1', 'gpu')
    assert a == preparar_salida(tmp_path, [video], 'v1', 'gpu')
    b = preparar_salida(tmp_path, [video], 'v2', 'gpu')
    video.write_bytes(b'otro contenido')
    c = preparar_salida(tmp_path, [video], 'v1', 'gpu')
    assert len({a, b, c}) == 3


def test_no_declara_exito_sin_checkpoint(tmp_path):
    video = tmp_path / 'v.mp4'
    video.write_bytes(b'a')
    salida = preparar_salida(tmp_path, [video], 'v1', 'gpu')
    with pytest.raises(RuntimeError, match='No se completó'):
        procesar([video], salida, 'python', tmp_path, local=tmp_path, runner=lambda *a: None)
    assert video.exists()
    assert not list(tmp_path.glob('lastre-video-*'))


def test_el_notebook_no_incrusta_el_codigo_como_blob():
    """Un base64 de cien kilobytes en una celda no se puede leer ni revisar.

    Era un parche para que el cuaderno no dependiera de elegir la rama en
    Colab. Clonar con --branch resuelve lo mismo y deja la celda legible.
    """
    raiz = Path(__file__).resolve().parents[1]
    notebook = json.loads((raiz / 'colab/placas_lastre.ipynb').read_text())

    for celda in notebook['cells']:
        fuente = ''.join(celda['source'])
        assert 'PAQUETE' not in fuente
        assert len(fuente) < 4000, f'celda de {len(fuente)} caracteres: ilegible'


def test_el_primer_paso_clona_el_repositorio():
    """El codigo debe venir del repositorio, no de dentro del cuaderno."""
    raiz = Path(__file__).resolve().parents[1]
    notebook = json.loads((raiz / 'colab/placas_lastre.ipynb').read_text())
    primera = ''.join(
        [c for c in notebook['cells'] if c['cell_type'] == 'code'][0]['source'])

    assert 'PLACAS-RECONOCIMIENTO' in primera
    assert 'clone' in primera
    assert 'RAMA' in primera


def test_el_primer_paso_define_lo_que_usan_los_demas():
    """Los pasos 2 a 6 leen REPO, PYTHON y VERSION: el paso 1 debe definirlos."""
    raiz = Path(__file__).resolve().parents[1]
    notebook = json.loads((raiz / 'colab/placas_lastre.ipynb').read_text())
    primera = ''.join(
        [c for c in notebook['cells'] if c['cell_type'] == 'code'][0]['source'])
    arbol = ast.parse(primera)

    asignados = {
        nodo.targets[0].id
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Assign) and isinstance(nodo.targets[0], ast.Name)
    }

    assert {'REPO', 'PYTHON', 'VERSION'} <= asignados


def test_el_notebook_generado_coincide_con_el_generador():
    """Regenerar no debe producir un cuaderno distinto del versionado."""
    import subprocess
    raiz = Path(__file__).resolve().parents[1]
    antes = (raiz / 'colab/placas_lastre.ipynb').read_text()

    subprocess.run([sys.executable, str(raiz / 'colab/generar_notebook.py')],
                   check=True, capture_output=True, cwd=raiz)

    assert (raiz / 'colab/placas_lastre.ipynb').read_text() == antes
