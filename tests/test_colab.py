"""Pruebas del flujo Colab sin Google Drive, descargas ni GPU."""
import ast
import base64
import hashlib
import io
import json
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


def test_notebook_compila_y_contiene_codigo_actual():
    raiz = Path(__file__).resolve().parents[1]
    notebook = json.loads((raiz / 'colab/placas_lastre.ipynb').read_text())
    valores = {}
    for celda in notebook['cells']:
        if celda['cell_type'] != 'code':
            continue
        arbol = ast.parse(''.join(celda['source']))
        for nodo in arbol.body:
            if isinstance(nodo, ast.Assign) and isinstance(nodo.targets[0], ast.Name):
                if nodo.targets[0].id in {'VERSION', 'PAQUETE'}:
                    valores[nodo.targets[0].id] = ast.literal_eval(nodo.value)
    paquete = base64.b64decode(valores['PAQUETE'])
    assert hashlib.sha256(paquete).hexdigest() == valores['VERSION']
    with zipfile.ZipFile(io.BytesIO(paquete)) as z:
        assert 'config/reloj/0.png' in z.namelist()
        for nombre in z.namelist():
            assert z.read(nombre) == (raiz / nombre).read_bytes()
