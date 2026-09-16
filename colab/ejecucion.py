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


def procesar(videos, salida, python, repo, limite=None, local='/content', runner=ejecutar, acelerador='gpu', paso=3, modelo_vehiculos=None):
    """Procesa videos en Colab reutilizando los modelos en un único proceso, copiando archivo por archivo a disco local."""
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    seleccion = videos if limite is None else videos[:limite]

    # Identificar videos que faltan por procesar
    hechos = leer_avance(salida)
    pendientes = [v for v in seleccion if v.name not in hechos]

    if not pendientes:
        print(f'Todos los videos seleccionados ({len(seleccion)}) ya están procesados en {salida}.', flush=True)
    else:
        print(f'Procesando {len(pendientes)} videos pendientes (de {len(seleccion)} seleccionados) '
              f'en un único proceso con modelos precargados...', flush=True)

        archivo_lista = salida / 'lista_videos_ejecucion.txt'
        archivo_lista.write_text('\n'.join(str(v.resolve()) for v in pendientes), encoding='utf-8')
        carpeta_base = seleccion[0].parent if seleccion else salida

        comando = [
            str(python), '-u', '-c', LANZADOR,
            str(Path(repo) / 'scripts/procesar_lote.py'), str(carpeta_base),
            '--lista-videos', str(archivo_lista),
            '--disco-local', str(local),
            '--out-dir', str(salida),
            '--acelerador', acelerador,
            '--paso', str(paso),
            '--paso-movimiento', '1',
            '--escala-movimiento', '0.25',
            '--observaciones-minimas', '10'
        ]
        if modelo_vehiculos:
            comando.extend(['--modelo-vehiculos', str(modelo_vehiculos)])

        runner(comando, repo, salida / 'procesamiento.log')

        # Verificar que los videos pendientes se hayan completado en el checkpoint
        hechos_ahora = leer_avance(salida)
        for v in pendientes:
            if v.name not in hechos_ahora:
                raise RuntimeError(f'No se completó {v.name}. Revisa procesamiento.log y reintenta esta celda.')

    print(f'Terminados: {len(leer_avance(salida))}/{len(videos)}. Resultados: {salida}', flush=True)

