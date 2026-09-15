# Colab: análisis de velocidad y preservación de precisión

Fecha: 15 de septiembre de 2026. Basado en la salida real de Colab compartida
por el usuario y en la inspección del código vigente. No se ha ejecutado una
nueva medición CUDA desde el entorno local. El usuario verificó manualmente
que el video (1), de unos 35 segundos, no contiene vehículos.

## Diagnóstico medido

| Etapa | Tiempo | Fracción del cuerpo medido |
|---|---:|---:|
| Detector híbrido completo | 16.4 s | 47.9 % |
| Entrega/decodificación de cuadros | 16.0 s | 46.7 % |
| Intentos de lectura del reloj | 0.8 s | 2.3 % |
| Sin atribuir | 1.1 s | 3.1 % |
| Total instrumentado | 34.3 s | 100 % |

El proceso informa aproximadamente 36 s, sin incluir la copia previa de Drive.
La regeneración posterior del Excel no es otra inferencia y su tiempo de 0 s
no sustituye el tiempo de procesamiento. Instalación, comprobación inicial de
modelos, lectura de zona y copia tampoco están en esos 36 s.

Se entregaron 923 cuadros; el contenedor declara 924. La etiqueta de 924
cuadros analizados usa metadatos, no cuadros realmente entregados. Hay que
registrar ambos valores. La discrepancia de uno no prueba por sí sola que
haya un cuadro utilizable perdido.

Los tres modelos reportan CUDA en sus sesiones. Eso no implica que toda
operación o todo nodo del grafo se ejecute en GPU. El aviso Memcpy es una
pista de transferencias, no una medida del tiempo perdido.

Cero vehículos registrados coincide con la revisión manual de este video.
No demuestra cero detecciones intermedias, cero falsas alarmas del filtro de
movimiento, precisión OCR ni recall positivo. No hubo llamadas a lectura de
placas en la salida compartida.

## Qué hace realmente el código

- `lastre/video.py:iterar_cuadros`: `VideoCapture` y `read()` secuenciales,
  entregando la imagen completa BGR. No solicita aceleración de decodificación.
  No hay evidencia de NVDEC en esta ejecución; activar CUDA para ONNX no la activa.
- `scripts/procesar_lote.py:procesar_video`: espera el siguiente cuadro y luego
  hace reloj, movimiento, posible inferencia, seguimiento y recortes. No solapa
  explícitamente lectura y procesamiento de cuadros (el backend puede tener
  sus propios hilos internos).
- `lastre/deteccion.py:DetectorMovimiento`: reduce el cuadro a 740×416, aplica
  MOG2 sobre toda esa imagen y solo después restringe el primer plano a la zona.
  Umbral, morfología, contornos, escalado y ordenación siguen en CPU.
- `lastre/vehiculos.py:DetectorHibrido`: por defecto llama movimiento en cada
  cuadro; llama RF-DETR una de cada tres ocasiones con movimiento. Las 923
  llamadas del informe son al híbrido, **no a RF-DETR**. No se puede atribuir
  los 16.4 s enteros al modelo ni al filtro.
- `DetectorHibrido.estadisticas` ya cuenta movimiento y confirmaciones, pero
  esos contadores no aparecen en el informe compartido. Falta separar tiempos.
- El lote ya usa `rf-detr-nano-384-coco`; recomendar cambiar de small a nano
  sería repetir una optimización que ya existe.
- `colab/ejecucion.py` copia cada video a disco local y crea un proceso por video.
  El proceso carga OCR, un detector para verificar sesiones y otro detector
  para analizar. Es costo fijo repetido, especialmente visible en clips cortos.
- El reloj se intenta hasta encontrar una marca. Aquí hubo 923 intentos: no
  obtuvo referencia durante el bucle. Como no hay vehículos, el resumen de
  cero registros sin hora no demuestra que el reloj funcione para este clip.

## Límites cuantitativos: por qué no basta un ajuste

Cálculos sobre los 34.3 s instrumentados, suponiendo las demás etapas constantes:

| Hipótesis ideal | Tiempo resultante | Aceleración del cuerpo |
|---|---:|---:|
| Decodificación gratis | 18.3 s | 1.87× |
| Híbrido gratis | 17.9 s | 1.92× |
| Ambas etapas cuestan la mitad | 18.1 s | 1.90× |
| Solapar lectura con todo el procesamiento, sin sobrecosto | aprox. 18.3 s | aprox. 1.87× |

El solapamiento ideal depende de recursos independientes; si ambas tareas
compiten por CPU/memoria, la ganancia será menor o puede no haberla.
Inicialización, copia y exportación quedan fuera de estos cálculos.
Para 3× tiempo real, 35 s deben procesarse en unos 11.7 s; para 5×, en 7 s.
Son metas de evaluación, no promesas. Ambas exigen mejorar más de una etapa.

## Orden de trabajo propuesto

### 1. Preparar una comparación breve, reproducible y diagnóstica

Usar el clip vacío (1), el 60 y el 61, más un conjunto adicional anotado que
no se use para elegir los parámetros. Registrar GPU, CPU/vCPU, RAM, versiones,
backend de video, códec, resolución y FPS reales. Mantener copia local.

Separar: copia de Drive, carga de cada modelo, decodificación/entrega BGR,
resize+MOG2+postproceso, inferencia real RF-DETR, reloj, OCR, escritura y Excel.
Mostrar los contadores ya disponibles del híbrido. Medir también el total de
pared y memoria máxima. Para variantes con hilos, no sumar tiempos solapados
como si fueran tiempo total. No confundir espera de cola con decodificación.

Repetir cada variante al menos tres veces en la misma sesión de Colab,
alternando orden. Separar primer arranque con descargas/caché fría de las
repeticiones calientes. Cada variante usa su propia salida y checkpoint;
una ejecución reanudada que omite videos no cuenta como medición.

### 2. Primer candidato de ejecución: lectura anticipada acotada

Un único productor posee VideoCapture y entrega cuadros en orden a una cola
de 2–4 elementos. Un único consumidor mantiene movimiento y seguimiento en
su orden original. No descartar cuadros cuando la cola se llena: esperar.

Ventaja: no cambia imágenes, muestreo, modelos ni criterios. Validar igualdad
de índices y bytes de cuadros, propagación de errores, cierre/interrupción,
conteo, agendas OCR y salidas. En CUDA comparar también variabilidad de la
misma versión consigo misma antes de exigir igualdad flotante entre corridas.

A 2960×1664×3 cada cuadro BGR ocupa 14.8 MB decimales. Una cola de cuatro
contiene unos 59.1 MB, además de productor/consumidor, buffers y caché OCR.
No usar una cola ilimitada ni cargar todo el video en RAM.

### 3. Segundo candidato: backend de decodificación

Comparar OpenCV actual, configuración de hilos del backend disponible y
NVDEC si la GPU/códec/compilación lo permiten. No instalar compilaciones
complejas a ciegas ni asumir que `pip install opencv` incorpora NVDEC.

Medir hasta obtener el BGR que consume el algoritmo: decodificar rápido en
GPU y descargar/convertir toda la imagen puede borrar la ganancia. Conservar
orden, cantidad de cuadros, PTS y correspondencia con evidencia y hora. No usar
saltos aleatorios para acelerar este códec sin demostrar sincronía.

La salida puede cambiar numéricamente por conversión de color/rango. Por eso
no basta comparar FPS: hay que repetir detección, placas y conteo con etiquetas.

Referencias primarias:
- https://docs.opencv.org/4.12.0/d4/d15/group__videoio__flags__base.html
- https://github.com/opencv/opencv/wiki/Video-IO-hardware-acceleration
- https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/ffmpeg-with-nvidia-gpu/index.html

### 4. Tercer candidato: restringir trabajo de movimiento

El rectángulo de la zona ocupa aproximadamente 47 % del cuadro. Se puede
experimentar aplicando MOG2 a esa región después del resize actual, conservando
margen para morfología, máscara, coordenadas y aprendizaje temporal.

Esto reduce trabajo de algunos pasos, no necesariamente 53 % del tiempo total
ni de todo el híbrido. Mantener el resize previo evita alterar su interpolación.
Recortar antes de reducir, cambiar resolución o retirar márgenes exige una
validación distinta. Comparar cada decisión de movimiento sobre la secuencia
completa, especialmente los bordes, sombras, motos y primeras observaciones.
No reducir la imagen disponible para OCR.

### 5. Quitar carga repetida y mejorar el ciclo de lote

Reutilizar sesiones de modelos en un trabajador persistente y reiniciar solo
MOG2/seguimiento entre videos. Verificar las mismas sesiones que procesan el
video, evitando instanciar RF-DETR dos veces. Conservar checkpoint por video,
liberar caché y comprobar memoria en lote largo. Medir carga por separado para
saber si la complejidad merece la pena en clips de varios minutos.

La lectura del reloj tiene un techo de ahorro pequeño en esta muestra (0.8 s).
Puede estudiarse una búsqueda temporal acotada o diferida, pero no eliminar
intentos sin comprobar las horas de los registros.

## Qué no cambiar todavía

No bajar observaciones_minimas ni aumentar pasos de muestreo como primera
solución. El video 60 contiene un duplicado casi idéntico confirmado que hoy
no genera un registro espurio gracias al filtrado de trayectorias cortas.
Hay también `minimo_cuadros=15` en seguimiento y `observaciones_minimas=10`
en registro; cualquier revisión debe tratar ambos y la fusión de continuaciones.

No añadir NMS general por IoU sobre dos videos, reducir resolución de OCR,
aceptar lecturas tempranas para ahorrar llamadas ni reemplazar B por P.
No extrapolar el costo del clip vacío a tráfico denso ni al lote de 63 videos.

## Criterios de aceptación

Separar velocidad, conteo y placas; no resumirlos en una sola “confianza”.

- Vacío: cero registros finales.
- Video 60: conservar los cinco eventos anotados; informar falsos positivos y
  omitidos por emparejamiento temporal/dirección, no solo igualar el total.
- Video 61: conservar los tres vehículos observados, sin duplicar la furgoneta.
- Placas: exactitud de placa completa contra verdad manual y proporción de
  vehículos legibles con lectura correcta. Separar legibles e ilegibles.
- PAC2573 sigue siendo un error conocido: conservar BAC2573 no significa buena
  precisión; una optimización de ejecución no debe esconderlo ni validarlo.
- Comprobar hora, dirección, evidencia propia y clase física por separado.
- Evaluar falsos “validados” y acierto por bandas de confianza/consenso. Un
  valor 0.95 no equivale a 95 % de probabilidad calibrada de placa correcta.
- En el conjunto de reserva no aceptar pérdidas de eventos conocidos ni
  nuevos falsos positivos para declarar una variante apta. Informar tamaño de
  muestra e incertidumbre; los tres clips no certifican precisión general.

## Decisión

La prioridad es una comparación con desglose interno y un prototipo de lectura
anticipada que no omita cuadros. Después, medir decodificador y región de
movimiento de forma aislada antes de combinarlos. No modificar los umbrales de
conteo ni prometer un factor de aceleración sin medir en la GPU de Colab.

## Implementación inicial — pendiente de medición en Colab

Se implementaron dos cambios que no modifican modelos, umbrales, resolución OCR ni el orden de cuadros.

1. MOG2 procesa el recuadro de la máscara de zona después del resize. Con la configuración actual pasa de 740×416 a 559×257 píxeles: 53.3 % menos de área modelada. Las coordenadas se reponen antes de regresar a la resolución original. La secuencia de regresión conserva exactamente las detecciones sintéticas de referencia.
2. La lectura de video corre en un productor con una cola de dos cuadros y el consumidor conserva el orden. La cola contiene como máximo unos 29.6 MB BGR, propaga errores y al cerrar el consumidor cierra la lectura. No descarta cuadros para mantenerse al día.

El informe separa `decodificar video`, `filtro de movimiento` y `modelo de vehiculos`, e informa cuadros vistos, cuadros con movimiento e inferencias reales. Cuando lectura y consumo se solapan, muestra `solapado entre etapas`: la suma de etapas no se debe confundir con tiempo de pared.

Pruebas: 335 pasan localmente. Cubren orden, límite, cierre, propagación de error y solapamiento de la cola; secuencia de MOG2; reparto de tiempos; integración de lote, agenda, recortes y checkpoint. Esto prueba contratos de software, no rendimiento CUDA ni precisión general.

La próxima corrida en Colab debe usar una salida nueva y procesar el video vacío (1), el 60 y el 61. Comparar contra las salidas guardadas: 0 registros, cinco eventos y tres vehículos. Anotar tiempo de pared, reparto interno, contador del detector, RSS y GPU. Solo entonces decidir backend de decodificación, reutilización de modelos o una región de movimiento más estrecha.

No modificar los umbrales de conteo ni prometer un factor de aceleración antes de medir en la GPU de Colab.

## Validación local CPU — 15 de septiembre de 2026

La corrida nueva, sin reutilizar checkpoints, procesó los videos 60 y 61 con CPU: 16,452 cuadros realmente entregados. Conservó cinco registros para el 60 y tres para el 61; el Excel contiene ocho filas de datos y ocho evidencias. El 61 conserva BAC2573 pendiente, MZS872 pendiente y PAB6741 validado. Esta mejora no corrige el OCR conocido ni duplica otra vez la furgoneta.

| Medición | Resultado |
|---|---:|
| Lote 60 + 61 | 1,051.5 s (17m33) |
| RF-DETR | 596.5 s, 831 inferencias, 56.7 % del tiempo de pared |
| Decodificación | 329.0 s |
| Filtro de movimiento | 299.0 s |
| Solapamiento lectura/proceso | 235.1 s |

El 60 hizo 1,562 comprobaciones de movimiento y 520 inferencias; el 61, 935 y 311 respectivamente. La lectura adelantada se evaluó frente a una variante secuencial en el 61: adelantada, aproximadamente 494 s dentro del lote; secuencial, 525.6 s (8m47). Ambas produjeron los mismos tres registros. Por eso se conserva la lectura adelantada también para CPU. La diferencia no es un benchmark con repeticiones suficientes para prometer un porcentaje universal, pero descarta el cambio secuencial como mejora en esta máquina.

El cuello de botella CPU es el modelo de vehículos. La próxima optimización debe reducir inferencias confirmadas manteniendo los eventos anotados; no debe alterar `observaciones_minimas` ni aceptar pérdida de recall para declarar una ganancia.
