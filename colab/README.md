# Usar el notebook de Colab

Abre **[placas_lastre.ipynb](placas_lastre.ipynb)** en Google Colab mediante
**Archivo → Subir cuaderno**. Activa GPU antes de empezar.

## Qué ejecutar

1. **Preparar:** instala el programa en un entorno separado. Espera «PREPARACIÓN LISTA». No requiere reiniciar.
2. **Carpetas:** conecta Drive. Cambia solamente `CARPETA_VIDEOS` y `CARPETA_INFORMES` si hace falta.
3. **GPU:** comprueba las sesiones reales de detección y OCR. Si falla, no continúa en CPU.
4. **Zona:** revisa la imagen de la cámara.
5. **Procesar:** marca `ZONA_CORRECTA = True`. Deja `MODO = 'prueba'` para procesar el primer video.
6. **Resultado:** muestra las primeras filas y descarga el Excel.

Cuando revises la prueba, cambia `MODO = 'lote'` en el paso 5 y ejecuta ese paso
otra vez. Luego ejecuta el 6 para descargar el resultado actualizado.

## Reanudar

Si la sesión sigue activa, ejecuta el paso 5. Si Colab perdió el entorno,
ejecuta primero los pasos 1–4 y después el 5 con `MODO = 'lote'`.
El video interrumpido se repite; los terminados se omiten. No uses dos sesiones
simultáneas sobre la misma carpeta de resultados.

## Resultados y velocidad

Los videos se copian uno por uno al disco local antes del análisis. Drive
conserva Excel, recortes, avance y registros de diagnóstico. No hace falta
copiar el lote completo ni reservar espacio para todos los videos juntos.

La subcarpeta `lote_<identificador>` separa versiones del código y conjuntos
de videos, usando rutas, tamaños y fechas de modificación. No es un hash del
contenido de los videos: si sustituyes archivos preservando todos esos datos,
usa otra carpeta de informes. Los checkpoints antiguos no se importan.

El último Excel reúne los resultados acumulados. El resumen se regenera con
los videos terminados; el cronometraje de esa regeneración no representa
el tiempo de inferencia. Los tiempos de cada ejecución quedan en
`procesamiento.log`. Los modelos se vuelven a cargar por video: este flujo
prioriza reanudación y claridad, sin afirmar rendimiento óptimo del lote.

## Instalación

Se usa un entorno virtual exclusivo y ONNX Runtime GPU 1.22.0 con las
bibliotecas CUDA/cuDNN declaradas por ese paquete. Cada proceso precarga esas
bibliotecas antes de cargar los modelos. No se modifica el Python del notebook
ni se necesita reiniciarlo para sustituir una librería ya importada.

La compatibilidad no se deduce solamente de `nvidia-smi`: el paso 3 verifica
las sesiones de los modelos. Véase la [documentación oficial de ONNX Runtime](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html).

## Mantenimiento y validación

El notebook contiene una copia de `lastre`, `scripts`, `config`, los requisitos
y el ayudante `colab/ejecucion.py`. Así se puede subir directamente a Colab sin
publicar primero cambios en GitHub. No incluye videos, resultados ni credenciales.

Después de cambiar esos archivos, regenerar:

```bash
.venv312/bin/python colab/generar_notebook.py
.venv312/bin/pytest tests/test_colab.py -q
```

Las pruebas locales comprueban sintaxis de todas las celdas, integridad y
actualidad del paquete, separación de ejecuciones, rutas con espacios,
extensiones en mayúsculas, reanudación, limpieza de copias temporales y
fallo sin checkpoint. No sustituyen ejecutar instalación, montaje de Drive
y modelos CUDA en un entorno real de Colab.
