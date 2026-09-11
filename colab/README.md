# Ejecutar el proceso en Google Colab

## 1. Preparar los videos

**Si los videos son tuyos:** súbelos a una carpeta de tu Google Drive.

**Si te los comparten por enlace:** pide que compartan la *carpeta*, ábrela en
Drive y usa "Organizar > Añadir acceso directo" para colocarla en tu unidad.
Así se monta como si fuera tuya. Evita descargar por enlace con `gdown`: con
decenas de gigabytes se topa con los límites de cuota de Google y falla a
mitad de camino.

## 2. Activar la GPU

En Colab: `Entorno de ejecución > Cambiar tipo de entorno de ejecución > GPU`.

Sin GPU el proceso es más lento que en un portátil, porque Colab asigna pocos
núcleos de procesador. La GPU es lo que justifica usar Colab.

## 3. Celdas a ejecutar

### Montar el Drive

```python
from google.colab import drive
drive.mount('/content/drive')
```

### Instalar dependencias

```python
!pip install -q opencv-python-headless numpy openpyxl pillow
!pip install -q fast-alpr open-image-models
!pip uninstall -y -q onnxruntime
!pip install -q onnxruntime-gpu
```

`onnxruntime` y `onnxruntime-gpu` no pueden convivir: hay que desinstalar el
primero o la GPU nunca se usará.

### Traer el código

```python
!git clone <url-del-repositorio> /content/lastre
%cd /content/lastre
```

Si no está en un repositorio, sube la carpeta del proyecto a Drive y cópiala:

```python
!cp -r "/content/drive/MyDrive/lastre" /content/lastre
%cd /content/lastre
```

### Comprobar que la GPU se reconoce

```python
import onnxruntime
print(onnxruntime.get_available_providers())
```

Debe aparecer `CUDAExecutionProvider`. Si no aparece, revisa el paso 2.

### Ajustar la zona de análisis

`config/zona.json` contiene el polígono de la vía de lastre. Está calibrado
para esta cámara en su posición actual. Si la cámara se movió, hay que
regenerar la evidencia visual y corregir los vértices:

```python
!python scripts/verificar_zona.py "/content/drive/MyDrive/videos/uno.mp4" --frame 2697
```

### Probar con pocos videos primero

```python
!python scripts/procesar_lote.py \
    "/content/drive/MyDrive/videos" \
    --out-dir "/content/drive/MyDrive/informe_lastre" \
    --acelerador gpu \
    --limite 3
```

Mide cuánto tarda. Multiplica por el número real de videos antes de lanzar
todo el lote.

### Procesar el lote completo

```python
!python scripts/procesar_lote.py \
    "/content/drive/MyDrive/videos" \
    --out-dir "/content/drive/MyDrive/informe_lastre" \
    --acelerador gpu
```

Agrega `--solo-salidas` si únicamente interesan los vehículos que salen.

## 4. Si Colab se desconecta

No se pierde nada. El avance se guarda en `informe_lastre/avance.json` cada
vez que termina un video. Vuelve a ejecutar exactamente el mismo comando: los
videos ya procesados se omiten y el trabajo continúa donde quedó.

Para rehacer todo desde cero, agrega `--reiniciar`.

Para regenerar solo el Excel con lo ya procesado, sin analizar más video:

```python
!python scripts/procesar_lote.py "/content/drive/MyDrive/videos" \
    --out-dir "/content/drive/MyDrive/informe_lastre" --solo-informe
```

## 5. Resultado

En la carpeta de salida quedan:

- `placas_lastre.xlsx` con una fila por vehículo y su foto incrustada, más una
  hoja de resumen con los totales del lote.
- `recortes/` con las imágenes sueltas por si hace falta ampliarlas.
- `avance.json` con el estado del procesamiento.

## Advertencias

La salida debe apuntar a Drive. El disco local de Colab se borra al
desconectar y con él se irían el Excel y las imágenes.

Colab libre corta las sesiones por inactividad. Mantén la pestaña abierta, o
usa Colab Pro para sesiones largas. La reanudación cubre el resto.
