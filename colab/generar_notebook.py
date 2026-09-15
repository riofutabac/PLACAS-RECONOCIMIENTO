"""Genera el notebook autónomo con una copia exacta del código de ejecución."""
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def generar():
    cells = []
    def md(s):
        cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(True)})
    def code(s):
        cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[], 'source':s.splitlines(True)})
    md('''# Placas: ejecutar sin pelear con Colab

**Primera vez:** activa GPU en **Entorno de ejecución → Cambiar tipo de entorno de ejecución**.
Después ejecuta los pasos **1 a 6**, de arriba hacia abajo. La primera corrida procesa **un video**.
Para continuar todos, cambia `MODO` a `lote` en el paso 5 y ejecuta de nuevo ese paso.

El paso 1 descarga el código del repositorio. Si quieres probar otra rama, cámbiala allí.
Los modelos se descargan durante la preparación. La instalación usa un entorno separado y **no requiere reiniciar**.
Si aparece un error rojo, detente en esa celda; el mensaje indica qué revisar.
''')
    md('## 1. Preparar el programa y las dependencias\nPuede tardar varios minutos la primera vez. Espera a ver **PREPARACIÓN LISTA**.')
    code('''import shutil, subprocess, sys
from pathlib import Path

def correr(cmd, **kw):
    \'\'\'Ejecuta y, si falla, muestra el error real del comando.

    subprocess con check=True solo deja un CalledProcessError sin motivo.
    \'\'\'
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        raise RuntimeError('Fallo: ' + ' '.join(str(c) for c in cmd))
    return r

RAMA = 'codex/base-rapida-paso1' #@param {type:"string"}
URL = 'https://github.com/riofutabac/PLACAS-RECONOCIMIENTO.git'

if not Path('/content').exists():
    raise RuntimeError('Abre este notebook en Google Colab.')
if not ((3, 12) <= sys.version_info[:2] <= (3, 13)):
    raise RuntimeError('Esta instalacion requiere Python 3.12 o 3.13. Cambia la version del entorno de Colab.')
try:
    subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'], check=True)
except (FileNotFoundError, subprocess.CalledProcessError) as exc:
    raise RuntimeError('Activa GPU en Entorno de ejecucion -> Cambiar tipo de entorno y vuelve a ejecutar.') from exc

REPO = Path('/content/lastre')
if (REPO / '.git').exists():
    correr(['git', '-C', str(REPO), 'fetch', '--quiet', 'origin', RAMA])
    correr(['git', '-C', str(REPO), 'reset', '--hard', '--quiet', 'FETCH_HEAD'])
else:
    correr(['git', 'clone', '--quiet', '--branch', RAMA, URL, str(REPO)])

# El commit identifica el codigo medido: los resultados de versiones distintas
# no se mezclan en la misma carpeta de Drive.
VERSION = correr(['git', '-C', str(REPO), 'rev-parse', 'HEAD']).stdout.strip()

# Entorno aparte: evita que las versiones que Colab trae preinstaladas choquen
# con las del proyecto, y asi no hace falta reiniciar el entorno.
PYTHON = REPO / '.venv/bin/python'

def entorno_sirve():
    \'\'\'Un entorno a medias tiene bin/python pero no pip: hay que probarlo.\'\'\'
    if not PYTHON.exists():
        return False
    return subprocess.run([str(PYTHON), '-m', 'pip', '--version'],
                          capture_output=True).returncode == 0

if not entorno_sirve():
    # El Python de Colab no trae ensurepip, asi que `python -m venv` falla y
    # deja un .venv inservible. virtualenv no depende de ensurepip.
    shutil.rmtree(REPO / '.venv', ignore_errors=True)
    correr([sys.executable, '-m', 'pip', 'install', '-q', 'virtualenv'])
    correr([sys.executable, '-m', 'virtualenv', '-q', str(REPO / '.venv')])

marca = REPO / '.instalado'
if marca.exists() and marca.read_text() != VERSION:
    marca.unlink()
if not marca.exists():
    requisitos = []
    for linea in (REPO / 'requirements.txt').read_text().splitlines():
        linea = linea.strip()
        if not linea or linea.startswith('#') or linea.startswith(('onnxruntime', 'pytest')):
            continue
        requisitos.append(linea.replace('opencv-python==', 'opencv-python-headless=='))
    correr([str(PYTHON), '-m', 'pip', 'install', *requisitos])
    correr([str(PYTHON), '-m', 'pip', 'uninstall', '-y', 'onnxruntime', 'onnxruntime-gpu'])
    correr([str(PYTHON), '-m', 'pip', 'install', 'onnxruntime-gpu[cuda,cudnn]==1.22.0'])
    correr([str(PYTHON), '-c', 'import cv2, numpy, fast_alpr, open_image_models, onnxruntime'])
    marca.write_text(VERSION)
print('PREPARACION LISTA. Sigue al paso 2. Codigo:', VERSION[:12])
''')
    md('## 2. Conectar Drive y elegir tus carpetas\nSolo cambia estas dos rutas si tus carpetas tienen otro nombre. El programa crea una subcarpeta para esta versión y estos videos; tus informes anteriores permanecen disponibles.')
    code('''from google.colab import drive
from importlib.util import spec_from_file_location, module_from_spec

drive.mount('/content/drive')
CARPETA_VIDEOS = '/content/drive/MyDrive/Cam PL' #@param {type:"string"}
CARPETA_INFORMES = '/content/drive/MyDrive/informe_lastre' #@param {type:"string"}

spec = spec_from_file_location('flujo_colab', REPO / 'colab/ejecucion.py')
flujo = module_from_spec(spec)
spec.loader.exec_module(flujo)
# Basta con que este dentro de Drive: MyDrive, una unidad compartida o un
# acceso directo. Lo que se evita es escribir en el disco efimero de Colab,
# que se pierde al cerrar la sesion.
for ruta in (CARPETA_VIDEOS, CARPETA_INFORMES):
    if not Path(ruta).resolve().is_relative_to(Path('/content/drive').resolve()):
        raise ValueError('Usa carpetas dentro de /content/drive. Revisa la ruta con: !ls /content/drive')
if not Path(CARPETA_VIDEOS).exists():
    raise ValueError('No existe ' + CARPETA_VIDEOS + '. Mira que hay con: !ls \'' + str(Path(CARPETA_VIDEOS).parent) + '\'')
VIDEOS = flujo.listar_videos(CARPETA_VIDEOS)
SALIDA = flujo.preparar_salida(CARPETA_INFORMES, VIDEOS, VERSION, 'gpu')
print('Videos encontrados:', len(VIDEOS))
print('Ya terminados en esta ejecución:', len(flujo.leer_avance(SALIDA)))
print('Resultados:', SALIDA)
for video in VIDEOS[:5]:
    print(' •', video.name)
''')
    md('## 3. Comprobar los modelos y la GPU\nEsta comprobación carga los modelos reales. Si alguno queda en CPU, se detiene antes del lote. Espera a ver **GPU LISTA**.')
    code('''GPU_LISTA = False
comprobacion = """
import onnxruntime as ort
ort.preload_dlls(directory='')
from lastre.config import cargar_configuracion
from lastre.placa import LectorPlacas
from lastre.vehiculos import DetectorVehiculos
from lastre.aceleracion import verificar_sesiones
proveedores = ('CUDAExecutionProvider', 'CPUExecutionProvider')
lector = LectorPlacas(proveedores=proveedores)
modelos = dict(lector.sesiones)
modelos['vehiculos'] = DetectorVehiculos(cargar_configuracion('config/zona.json'), modelo='rf-detr-nano-384-coco', proveedores=proveedores).sesion
ok, informes = verificar_sesiones(modelos, 'gpu')
print('ONNX Runtime:', ort.__version__)
for informe in informes: print(informe)
if not ok: raise RuntimeError('Algún modelo no usa GPU. Revisa el error de CUDA anterior; no inicies el lote.')
"""
flujo.ejecutar([str(PYTHON), '-u', '-c', comprobacion], REPO, SALIDA / 'diagnostico_gpu.log')
GPU_LISTA = True
print('GPU LISTA. Sigue al paso 4.')
''')
    md('## 4. Ver la zona de la cámara\nEl verde debe cubrir el lastre y excluir la carretera principal. Si la cámara cambió de posición, no continúes: hay que recalibrar la zona. Esta imagen queda guardada en tu carpeta de resultados.')
    code('''from IPython.display import Image, display

imagen_zona = SALIDA / 'verificacion_zona.jpg'
flujo.ejecutar([str(PYTHON), '-u', '-c', flujo.LANZADOR,
    str(REPO / 'scripts/verificar_zona.py'), str(VIDEOS[0]),
    '--output', str(imagen_zona)], REPO, SALIDA / 'zona.log')
display(Image(filename=str(imagen_zona), width=950))
''')
    md('''## 5. Procesar o continuar

Primero deja `MODO = 'prueba'`: procesa solamente el primer video. Revisa el Excel en el paso 6.
Después cambia a `'lote'` y ejecuta esta misma celda: omite los videos terminados.
Marca `ZONA_CORRECTA = True` después de revisar la imagen del paso 4.

Se copia **un video a la vez** al disco local y se libera esa copia al terminar.
Los resultados y el avance se escriben en Drive. Si Colab pierde el entorno,
ejecuta los pasos 1–4 y después este paso con `MODO = 'lote'`.
Se repite únicamente el video que no alcanzó a terminar. No ejecutes dos sesiones sobre la misma salida.
''')
    code('''MODO = 'prueba' #@param ["prueba", "lote"]
ZONA_CORRECTA = False #@param {type:"boolean"}

if not globals().get('GPU_LISTA', False):
    raise RuntimeError('Ejecuta primero el paso 3: comprobar GPU.')
if not ZONA_CORRECTA:
    raise RuntimeError('Revisa la imagen del paso 4 y marca ZONA_CORRECTA = True.')
if MODO not in ('prueba', 'lote'):
    raise ValueError("MODO debe ser 'prueba' o 'lote'.")
flujo.procesar(VIDEOS, SALIDA, PYTHON, REPO, limite=1 if MODO == 'prueba' else None)
''')
    md('## 6. Ver y descargar el Excel\nEl Excel incluye los resultados acumulados. Las placas pendientes necesitan revisión; una confianza alta por sí sola no garantiza que la placa sea correcta.')
    code('''from IPython.display import HTML, display
from google.colab import files
import html

avance = flujo.leer_avance(SALIDA)
filas = [fila for datos in avance.values() for fila in datos['filas']]
print(f'Videos terminados: {len(avance)}/{len(VIDEOS)} | Vehículos registrados: {len(filas)}')
print('Carpeta en Drive:', SALIDA)
columnas = ['placa', 'hora_paso', 'sentido', 'estado', 'consenso']
tabla = '<tr>' + ''.join('<th>' + c + '</th>' for c in columnas) + '</tr>'
for fila in filas[:20]:
    tabla += '<tr>' + ''.join('<td>' + html.escape(str(fila.get(c, ''))) + '</td>' for c in columnas) + '</tr>'
display(HTML('<table>' + tabla + '</table>'))
excel = SALIDA / 'placas_lastre.xlsx'
if excel.exists():
    files.download(str(excel))
else:
    print('Todavía no hay Excel. Termina la prueba del paso 5.')
''')
    md('''### Si aparece un error

- **No hay GPU:** cambia el tipo de entorno a GPU y vuelve al paso 1.
- **No encuentra videos:** corrige la ruta del paso 2. Las extensiones en mayúsculas también se aceptan.
- **Error de CUDA o de un modelo:** revisa `diagnostico_gpu.log` en la carpeta de resultados. No continúa silenciosamente en CPU.
- **Se cortó mientras procesaba:** repite el paso 5; si se perdió la sesión, ejecuta antes 1–4.
- **Cambiaste videos o código:** se crea otra salida para no mezclar mediciones ni checkpoints.

Los modelos requieren Internet la primera vez. La GPU no elimina los costos de decodificar video, leer Drive ni generar imágenes.
La instalación fija ONNX Runtime 1.22.0 y carga sus bibliotecas CUDA/cuDNN; no presupone que todas las versiones posteriores requieran CUDA 13.
[Documentación oficial de CUDA y carga de bibliotecas](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html).
''')
    notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'colab':{'name':'placas_lastre.ipynb'},'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'cells':cells}
    titulos = iter(['Preparar programa', 'Carpetas de Drive', 'Comprobar GPU',
                    'Ver zona', 'Procesar o continuar', 'Ver y descargar Excel'])
    for i,c in enumerate(cells):
        c['id']=f'lastre-{i:02d}'
        if c['cell_type'] == 'code':
            c['source'].insert(0, '#@title ' + next(titulos) + '\n')
            c['metadata']['cellView'] = 'form'
    (ROOT/'colab/placas_lastre.ipynb').write_text(json.dumps(notebook, ensure_ascii=False, indent=1)+'\n')
    print('Notebook generado sin codigo incrustado')

if __name__ == '__main__':
    generar()
