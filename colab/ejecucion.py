"""Orquestación de Colab: disco local para video, Drive para resultados."""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

EXTENSIONES = {'.mp4', '.avi', '.mov', '.mkv', '.m4v'}
LANZADOR = (
    "import sys,runpy; import onnxruntime as ort; "
    "ort.preload_dlls(directory=''); "
    "sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name='__main__')"
)


def listar_videos(carpeta):
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        raise ValueError(f'No existe la carpeta: {carpeta}. Revisa la ruta de Drive.')
    videos = sorted(p for p in carpeta.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONES)
    if not videos:
        raise ValueError(f'No hay videos compatibles en {carpeta}. No se buscan subcarpetas.')
    return videos


def preparar_salida(base, videos, version, acelerador):
    identidad = {
        'codigo': version, 'acelerador': acelerador,
        'videos': [{'ruta': str(p.resolve()), 'bytes': p.stat().st_size,
                    'modificado': p.stat().st_mtime_ns} for p in videos],
        'parametros': {'paso': 3, 'paso_movimiento': 1, 'escala_movimiento': .25,
                       'observaciones_minimas': 10},
    }
    serializado = json.dumps(identidad, sort_keys=True, ensure_ascii=False)
    firma = hashlib.sha256(serializado.encode()).hexdigest()[:16]
    salida = Path(base) / f'lote_{firma}'
    salida.mkdir(parents=True, exist_ok=True)
    manifiesto = salida / 'ejecucion.json'
    if manifiesto.exists():
        if json.loads(manifiesto.read_text()) != identidad:
            raise ValueError('La identidad de la ejecución no coincide. Usa otra carpeta de salida.')
    elif (salida / 'avance.json').exists():
        raise ValueError('Hay avance sin manifiesto. Usa otra carpeta de salida.')
    else:
        manifiesto.write_text(serializado, encoding='utf-8')
    return salida


def leer_avance(salida):
    archivo = Path(salida) / 'avance.json'
    if not archivo.exists():
        return {}
    return json.loads(archivo.read_text(encoding='utf-8'))['videos']


def ejecutar(comando, repo, log):
    """Transmite salida y conserva el diagnóstico; un error detiene el notebook."""
    with Path(log).open('a', encoding='utf-8') as registro:
        with subprocess.Popen(comando, cwd=repo, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, bufsize=1) as proceso:
            try:
                for linea in proceso.stdout:
                    print(linea, end='', flush=True)
                    registro.write(linea)
                    registro.flush()
                codigo = proceso.wait()
            except BaseException:
                proceso.terminate()
                try:
                    proceso.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proceso.kill()
                    proceso.wait()
                raise
    if codigo:
        raise RuntimeError(f'El proceso terminó con código {codigo}. Revisa {log}.')


def procesar(videos, salida, python, repo, limite=None, local='/content', runner=ejecutar):
    """Prueba el primer video o continúa todo; verifica el checkpoint de cada uno."""
    seleccion = videos if limite is None else videos[:limite]
    for indice, video in enumerate(seleccion, 1):
        if video.name in leer_avance(salida):
            print(f'[{indice}/{len(seleccion)}] Ya terminado: {video.name}', flush=True)
            continue
        if shutil.disk_usage(local).free < video.stat().st_size + 1024**3:
            raise RuntimeError('Falta espacio local para copiar el siguiente video (más 1 GB de margen).')
        print(f'[{indice}/{len(seleccion)}] Copiando desde Drive: {video.name}', flush=True)
        with tempfile.TemporaryDirectory(prefix='lastre-video-', dir=local) as temporal:
            destino = Path(temporal) / video.name
            shutil.copy2(video, destino)
            if destino.stat().st_size != video.stat().st_size:
                raise OSError(f'La copia quedó incompleta: {video.name}')
            comando = [str(python), '-u', '-c', LANZADOR,
                       str(Path(repo) / 'scripts/procesar_lote.py'), temporal,
                       '--out-dir', str(salida), '--acelerador', 'gpu',
                       '--paso', '3', '--paso-movimiento', '1',
                       '--escala-movimiento', '0.25', '--observaciones-minimas', '10']
            runner(comando, repo, Path(salida) / 'procesamiento.log')
            # El script puede informar fallos por video y aun así salir con 0.
            if video.name not in leer_avance(salida):
                raise RuntimeError(f'No se completó {video.name}. Revisa procesamiento.log y reintenta esta celda.')
    # El resumen debe contar solo los videos terminados, igual que sus filas.
    # Los enlaces permiten leer metadatos sin volver a copiar todo el lote.
    hechos = leer_avance(salida)
    if hechos:
        with tempfile.TemporaryDirectory(prefix='lastre-informe-', dir=local) as temporal:
            for video in videos:
                if video.name in hechos:
                    (Path(temporal) / video.name).symlink_to(video.resolve())
            comando = [str(python), '-u', '-c', LANZADOR,
                       str(Path(repo) / 'scripts/procesar_lote.py'), temporal,
                       '--out-dir', str(salida), '--solo-informe', '--acelerador', 'gpu']
            runner(comando, repo, Path(salida) / 'procesamiento.log')
    print(f'Terminados: {len(leer_avance(salida))}/{len(videos)}. Resultados: {salida}', flush=True)
