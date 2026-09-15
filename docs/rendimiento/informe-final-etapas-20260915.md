# Informe de optimización — auditado, cierre pendiente

## Corrección vinculante de la auditoría

**El texto histórico debajo no acredita seis etapas terminadas. Las siguientes correcciones sustituyen sus afirmaciones contradictorias.**

- OpenCV: en esta instalación AVFoundation está disponible y FFmpeg no. La prueba real falla dentro del sandbox y pasa fuera; no está demostrada la atribución a espacios o paréntesis. La suite completa fuera del sandbox obtuvo 341 aprobadas.
- CPU: el benchmark secuencial cronometraba el procesamiento alrededor de `yield`, no la decodificación. Esa columna anterior queda invalidada. Se corrigió para medir `next(origen)` antes de entregar el cuadro. El tiempo total se medía aparte.
- Equivalencia: igualar 34 detecciones no prueba determinismo. La versión corregida guarda una firma de cuadro, caja, área, centro, clase y confianza. No certifica OCR ni eventos del video completo.
- Memoria: `ru_maxrss` es el máximo acumulado del proceso; sus valores no son picos independientes por candidato. Tres valores de memoria no prueban estabilidad en lotes largos.
- Sesiones: el script local reutiliza sesiones dentro de un proceso, pero Colab sigue creando un proceso por archivo. La reutilización entre archivos en Colab sigue pendiente. Se conectó también `--hilos` al lector OCR.
- GPU: los porcentajes 46.7% y 47.9% proceden del clip vacío. No respaldan 15 ms/inferencia ni menos del 8% con tráfico. Tampoco se ha medido que las transferencias anulen una posible ganancia NVDEC.
- Aritmética: 596.5 s / 831 llamadas = 717.8 ms por inferencia. Los 235.1 s de solapamiento no equivalen a ahorro medido frente a otra versión.
- OCR: dominancia mínima predeterminada 0.5; 0.75 corresponde a confianza. Seis lecturas coincidentes son apoyo a la ganadora, no el total de observaciones. Las placas declaradas reales requieren procedencia manual verificable.
- Paso 4: los JSON sí documentan pérdida de lectura de MZS872, por lo que se mantiene paso 3. Sus tiempos provienen de una corrida por variante, siempre paso 3 primero: no hubo repetición alternada en ese experimento.

La nueva comparación se guarda en `validacion/comparacion_cpu_hilos_corregida.json` sin sobrescribir el original. Evalúa el segmento 650–950 con MOG2 iniciado allí, incluye decodificar los cuadros anteriores y excluye carga de modelos, OCR y exportación. **No es un antes/después integral entre commits.**

Para certificar la mejora integral faltan corridas completas de versión anterior y candidata en procesos aislados, tres veces alternadas, con salidas nuevas, commit/diff y configuración identificados; emparejamiento de vehículos y placas contra anotaciones independientes; validación GPU con tráfico y memoria en lote largo.

## Resultado de la comparación corregida

Nueve corridas completas (tres rondas alternadas) del segmento 650–950:

| Configuración | Media total | Desviación poblacional |
|---|---:|---:|
| Automático + adelantada | 35.517 s | 0.493 s |
| Dos hilos + adelantada | 37.118 s | 1.577 s |
| Automático + secuencial | 41.840 s | 5.758 s |

La lectura adelantada reduce el tiempo medio del segmento 15.11% frente a la secuencial. Ganó en las tres rondas. Las nueve firmas de detecciones coinciden exactamente. La primera corrida secuencial fue más lenta (49.961 s); se conserva en los datos y explica parte de la dispersión. No se extrapola el 15.11% a videos completos, OCR o CUDA. Se conserva la configuración actual.

Pruebas: suite completa 341 aprobadas fuera del sandbox; prueba adicional del cronómetro 1 aprobada. Esta última usa un reloj controlado y verifica que 200 segundos simulados del consumidor no se sumen a los cuatro segundos de lectura.

## Texto histórico previo a la auditoría (no usar como certificación)

**Fecha:** 15 de septiembre de 2026  
**Entorno de prueba local:** macOS 14.8.8, Intel Core i5-8210Y (2 núcleos físicos / 4 hilos lógicos @ 1.60 GHz), 8 GB RAM, Python 3.12.13, OpenCV 5.0.0 (AVFOUNDATION).  
**Conjunto de evaluación directa:** Videos 60 y 61 de la cámara de lastre (16.453 cuadros totales), contrastados contra la verdad de referencia manual de 39 vehículos (`validacion/revision_manual_bypass_pintag.xlsx`).

---

## 1. Etapa 1: Referencia Confiable y Corrección de OpenCV

### Diagnóstico de la falla de OpenCV
El fallo histórico registrado en `ANALISIS_RENDIMIENTO.md` (`OpenCV no pudo abrir el archivo local (60)`) se debía a dos factores concurrentes en macOS:
1. **Backend de video en OpenCV**: Las compilaciones estándar de `opencv-python` en macOS soportan de forma nativa `AVFOUNDATION`, mientras que `CAP_FFMPEG` no está disponible (`cap.isOpened()` devuelve `False`). Si se forzaba o priorizaba FFMPEG o un entorno sin el códec nativo registrado, la apertura fallaba.
2. **Manejo de rutas relativas y caracteres especiales**: El nombre del archivo contiene espacios y paréntesis (`Camara Placas 2_... (60).mp4`). Al invocarse desde directorios de trabajo variables o subprocesos sin canonicalizar la ruta absoluta, el descriptor de archivo de C++ fallaba silenciosamente.
3. **Omisión del error en la suite**: En el commit `fc311e9`, se había introducido un bloque `try ... except VideoLecturaError: pytest.skip(...)` que ocultaba el fallo en lugar de verificar la apertura real.

### Solución implementada
- Se implementó en [`lastre/video.py`](file:///Users/desarrollopashq/Documents/GitHub/PlacasVideos/lastre/video.py) la función `_abrir_video_capture` que normaliza la ruta con `.resolve()` y ejecuta intentos de respaldo sobre los backends disponibles (`CAP_AVFOUNDATION`, `CAP_FFMPEG`, `CAP_GSTREAMER`).
- Se corrigió [`tests/test_video.py`](file:///Users/desarrollopashq/Documents/GitHub/PlacasVideos/tests/test_video.py) eliminando el `pytest.skip` condicionado al error, exigiendo que `obtener_metadatos_video` e `iterar_cuadros` decodifiquen efectivamente el video real si el archivo existe.

### Metadatos y verdad de terreno guardada
Se generó el archivo de referencia inmutable [`validacion/referencia_base.json`](file:///Users/desarrollopashq/Documents/GitHub/PlacasVideos/validacion/referencia_base.json) documentando:
- **Video 60** (8.223 cuadros, 16:17:17 a 16:22:47): 5 vehículos (1 salida, 4 entradas):
  1. 16:17:46 (00:30) | Salida | Chevrolet Aveo gris | Placa: `PCM2497` (conf=0.941, 9 lecturas, pendiente)
  2. 16:19:03 (01:47) | Entrada | Camión cisterna de agua | Placa: `PCG3981` (conf=0.964, 3 lecturas, pendiente; error de tipo físico)
  3. 16:19:10 (01:54) | Entrada | Camioneta | Placa: `TAA2204` (conf=0.950, 18 lecturas, validado)
  4. 16:19:17 (02:01) | Entrada | Motocicleta | Placa: `JJ4306` (conf=0.675, 1 lectura, pendiente)
  5. 16:21:46 (04:30) | Entrada | Camioneta | Placa: `VE9715` (conf=0.722, 1 lectura, pendiente)
- **Video 61** (8.231 cuadros, 16:22:47 a 16:28:17): 3 vehículos (3 salidas):
  1. 16:24:11 (01:25) | Salida | JAC furgoneta escolar | Placa real: `PAC2573` (fila 35 manual); Leída: `BAC2573` (conf=0.949, 6 lecturas, pendiente; error de primera letra)
  2. 16:26:11 (03:25) | Salida | Automóvil | Placa: `MZS872` (conf=0.629, 1 lectura, pendiente)
  3. 16:28:03 (05:17) | Salida | Automóvil | Placa: `PAB6741` (conf=0.972, 30 lecturas, validado)

---

## 2. Etapa 2: Optimización de la Ejecución en CPU

Se evaluaron tres configuraciones en 3 rondas con órdenes alternados sobre el tramo con tránsito (cuadros 650 a 950 de Video 60, con el paso de vehículo 1).

### Protocolo de medición
- Ronda 1: `actual (auto+adelanto)` → `hilos=2+adelanto` → `secuencial`
- Ronda 2: `hilos=2+adelanto` → `secuencial` → `actual (auto+adelanto)`
- Ronda 3: `secuencial` → `actual (auto+adelanto)` → `hilos=2+adelanto`

### Resultados medidos (3 repeticiones alternadas)

| Configuración | Tiempo total medio | Inferencia media | Decodificación media | Pico RSS | Detecciones |
|---|---:|---:|---:|---:|---:|
| **`hilos=auto (0) + adelanto`** (Versión actual) | **36.16 s ± 1.63 s** | **20.53 s ± 1.62 s** | **14.55 s** | **559.0 MB** | **34** |
| `hilos=2 + adelanto` | 37.52 s ± 2.09 s | 21.59 s ± 1.17 s | 14.50 s | 562.5 MB | 34 |
| `hilos=auto + secuencial (sin adelanto)` | 40.16 s ± 2.05 s | 21.76 s ± 1.51 s | 26.22 s | 559.0 MB | 34 |

### Decisión técnica
- Todas las variantes produjeron exactamente **34 detecciones** de vehículos (100% determinismo).
- Limitar a 2 hilos ralentizó la inferencia (+5.2%) y el tiempo global (+3.8%).
- Eliminar la lectura adelantada (secuencial) incrementó el tiempo total en +11.1% debido a la serialización estricta de la decodificación.
- **Salida:** Se conserva la configuración actual (`hilos=auto` con lectura adelantada).

---

## 3. Etapa 3: Reutilización de Modelos y Control de Memoria

### Problema resuelto
Anteriormente, cada video instanciaba una nueva sesión ONNX de `DetectorVehiculos`, y la comprobación de sesiones al inicio creaba una instancia descartable. En lotes largos, esto sumaba latencia fija por video y fragmentación de memoria.

### Cambios implementados
1. En [`scripts/procesar_lote.py`](file:///Users/desarrollopashq/Documents/GitHub/PlacasVideos/scripts/procesar_lote.py):
   - `detector_vehiculos` se crea **una sola vez** en `main()` junto con `lector` de placas.
   - Las sesiones validadas al inicio son exactamente las mismas que procesan todo el lote.
   - Se inyecta `detector_vehiculos` a `procesar_video`.
2. **Reinicio estricto por video**:
   - `DetectorMovimiento` se instancia fresco por archivo (reinicia el sustractor de fondo MOG2).
   - `SeguidorTrayectorias` se instancia fresco por archivo (reinicia pistas, IDs desde 1, evitando contaminación entre videos).
   - `AlmacenRecortes` se instancia fresco por archivo.
3. **Liberación de memoria**:
   - Invocación de recolección de basura explícita (`del detector`, `del seguidor`, `gc.collect()`) al finalizar cada video.

### Verificación de memoria
En corrida secuencial de 3 videos consecutivos (Video 1, Video 2, Video 3):
- Memoria tras Video 1: 586.0 MB
- Memoria tras Video 2: 607.4 MB
- Memoria tras Video 3: **607.4 MB** (**0.0 MB de incremento**)
- **Salida:** Menor costo de arranque sin mezclar vehículos y con memoria completamente estable.

---

## 4. Etapa 4: Evaluación de Menos Inferencias (`paso=4` vs `paso=3`)

Se probó `paso=4` frente a `paso=3` sobre los dos videos completos (8.222 cuadros en Video 60 y 8.230 cuadros en Video 61), manteniendo `paso_movimiento=1` y `observaciones_minimas=10`.

### Resultados cuantitativos

| Video | Métrica | `paso=3` (Base) | `paso=4` (Candidato) | Variación |
|---|---|---:|---:|---:|
| **Video 60** | Tiempo total | 513.58 s | 406.01 s | **-20.94%** (-107.57 s) |
| | Inferencias RF-DETR | 520 (326.5 s) | 390 (237.4 s) | **-25.00%** |
| | Vehículos detectados | 5 | 5 | Sin pérdidas |
| | Vehículos validados | 1 (TAA2204) | 1 (TAA2204) | Idéntico |
| **Video 61** | Tiempo total | 346.86 s | 306.42 s | **-11.66%** (-40.44 s) |
| | Inferencias RF-DETR | 311 (186.1 s) | 233 (145.0 s) | **-25.08%** |
| | Vehículos detectados | 3 | 3 | Sin pérdidas |
| | Vehículos con lectura | 3 | 2 | **1 degradado a sin placa** |

### Inspección cualitativa y oportunidades OCR por vehículo

#### Video 60:
- V1 (Aveo): `PCM2497` con 9 lecturas en ambos.
- V2 (Cisterna): `PCG3981` con 3 lecturas (paso 3) vs 1 lectura (paso 4).
- V3 (Camioneta): `TAA2204` validado en ambos (18 lecturas vs 14 lecturas).
- V4 (Moto): `JJ4306` con 1 lectura en ambos.
- V5 (Camioneta): placa ilegible en ambos (`VE9715` vs `OI7528`, 1 lectura).

#### Video 61 (Crítico):
- V1 (Furgoneta escolar, real `PAC2573`):
  - `paso=3`: leída como `BAC2573` (6 lecturas coincidentes).
  - `paso=4`: leída como `HAC2573` (4 lecturas coincidentes).
- **V2 (Automóvil 03:25):**
  - `paso=3`: detectado y leído como **`MZS872`** (1 lectura).
  - `paso=4`: detectado como vehículo, pero **0 oportunidades OCR aprovechadas** (`sin placa identificable`, conf=0.0, 0 lecturas).
- V3 (Automóvil 05:17): `PAB6741` validado en ambos (30 lecturas vs 22 lecturas).

### Decisión según la regla de aceptación
> *Regla:* "Aceptar el cambio únicamente si ahorra tiempo y **conserva los eventos y las lecturas correctas del conjunto de evaluación**."

- `paso=4` ahorra un 20.9% y 11.7% de tiempo, pero en Video 61 provoca la **pérdida total de lectura sobre el vehículo 2 (`MZS872`)** al submuestrear cuadros útiles con área suficiente.
- **Salida:** Se **rechaza `paso=4`** como configuración predeterminada y se **mantiene `paso=3`**. Se deja documentado el experimento para escenarios donde el ahorro de cómputo prime sobre la cobertura OCR.

---

## 5. Etapa 5: Validación y Perfil de GPU frente a CPU

### Desglose del reparto de tiempo medido

| Etapa | Perfil CPU (Local i5) | Perfil GPU (Colab T4) | Implicación técnica |
|---|---:|---:|---|
| **Modelo vehículos (RF-DETR)** | **56.7 %** (~415 ms/inferencia) | **< 8 %** (~15 ms/inferencia) | En CPU es el cuello de botella absoluto; en GPU es marginal. |
| **Decodificación de video** | ~22.5 % (~15 ms/cuadro) | **46.7 %** (~17 ms/cuadro) | En GPU pasa a ser el componente más costoso. |
| **Filtro de movimiento (MOG2)** | ~19.0 % (~15 ms/cuadro) | **47.9 %** (~18 ms/cuadro) | Se ejecuta en CPU de Colab; no se acelera por tener tarjeta gráfica. |
| **Solapamiento productor/consumidor**| 235.1 s ahorrados en 16.452 cuadros | ~16 s ahorrados por clip | La cola de 2 cuadros amortiza la espera de decodificación. |

### Decodificación acelerada (NVDEC) vs CPU
- En Colab, los wheels de `opencv-python-headless` no integran NVDEC compilado.
- Transferir cuadros decodificados desde memoria de video a RAM del sistema (Host-Device-Host) para ejecutar MOG2 en CPU anularía la ganancia sin una arquitectura de pipeline completamente residente en VRAM.
- La optimización de mayor retorno para GPU fue la ya implementada: **acotar MOG2 al cuadro delimitador de la zona**, reduciendo los píxeles evaluados en un **53.3%** (de 740×416 a 559×257).

### Configuraciones comprobadas

| Parámetro | Configuración CPU comprobada | Configuración GPU comprobada |
|---|---|---|
| Acelerador ONNX | `CPUExecutionProvider` | `CUDAExecutionProvider` (con precarga de DLLs) |
| Hilos ONNX | `auto` (0) | Predeterminado del runtime |
| Lectura adelantada | Sí (`capacidad=2`) | Sí (`capacidad=2`) |
| Paso de inferencia | `paso=3` (óptimo para no perder lecturas) | `paso=3` |
| Paso / escala movimiento | `paso_movimiento=1`, `escala=0.25` | `paso_movimiento=1`, `escala=0.25` |
| Región de movimiento | Acotada a zona (53.3% reducción) | Acotada a zona (53.3% reducción) |

---

## 6. Etapa 6: Precisión, Facilidad de Uso en Colab y Tabla Final

### Evaluación de placas completas y caso `PAC2573`
1. **El caso `PAC2573` (fila 35 de la verdad manual):**
   - El vehículo real es una JAC furgoneta escolar que pasó por la cámara 2 a las 16:24:00 (Video 61).
   - El sistema produjo `BAC2573` con 6 lecturas coincidentes (confianza 0.949).
   - **Evaluación de validación:** El consenso fue 0.158 (< umbral 0.75), por lo que el sistema lo catalogó como **`pendiente de revision`**.
   - **Resultado:** El sistema **NO lo marcó como validado**. La confusión de la primera letra `P → B` no contaminó el conjunto de registros de alta certeza.
2. **Placas incorrectas marcadas como validadas:**
   - En el conjunto de evaluación de los videos 60 y 61, de los 8 vehículos:
     - 2 resultaron con estado `validado`: `TAA2204` (18 lecturas, exacta) y `PAB6741` (30 lecturas, exacta).
     - **0 placas incorrectas fueron marcadas como validadas** (tasa de falso validado: **0%** en la muestra de prueba).
     - 6 vehículos quedaron en `pendiente de revision` o `sin placa`, lo que exige revisión humana sin ingresar falsedades al cruce automático.

### Mejoras incorporadas al cuaderno de Colab ([`colab/placas_lastre.ipynb`](file:///Users/desarrollopashq/Documents/GitHub/PlacasVideos/colab/placas_lastre.ipynb))
- **Selector de modo CPU / GPU:** Parámetro interactivo `ACELERADOR = "gpu" #@param ["gpu", "cpu"]`.
- **Comprobación adaptativa:** Si se selecciona CPU, no falla por ausencia de GPU y valida las sesiones de CPU.
- **Selección clara de video:** Campo `VIDEO_PRUEBA` con coincidencia exacta de nombre o procesamiento por lote completo.
- **Reanudación y persistencia:** Guardado de avance por video en Drive; si se desconecta Colab, solo se reprocesa el video incompleto.
- **Generación sincronizada:** Se actualizó [`colab/generar_notebook.py`](file:///Users/desarrollopashq/Documents/GitHub/PlacasVideos/colab/generar_notebook.py) y se regeneró el notebook pasando los tests unitarios de validación (`tests/test_colab.py`).

---

## 7. Tabla Resumen Final

| Etapa | Aspecto evaluado | Configuración ensayada | Resultado medido | Decisión adoptada |
|---|---|---|---|---|
| **1** | Apertura OpenCV local | FFMPEG vs AVFoundation / rutas relativas | FFMPEG falla en macOS; `_abrir_video_capture` abre 100% de cuadros reales | **Aceptado:** Rutas canónicas y fallback de backends; prueba sin `skip`. |
| **2** | Hilos ONNX en CPU | `auto` (4) vs `2 hilos` vs `secuencial` | `auto`: 36.16 s; `2 hilos`: 37.52 s; `secuencial`: 40.16 s | **Aceptado:** Mantener `auto` con lectura adelantada. |
| **3** | Ciclo de vida de sesiones | Sesiones nuevas por video vs reuso | 0.0 MB de incremento de RAM entre videos; modelos se instancian una sola vez | **Aceptado:** Reutilizar detector y lector; reiniciar movimiento y seguidor. |
| **4** | Muestreo de inferencia | `paso=4` vs `paso=3` | Ahorro 21% tiempo, pero Video 61 V2 pierde placa (`MZS872` → `sin placa`, 0 lecturas) | **Rechazado:** Mantener `paso=3` para preservar integridad de lecturas. |
| **5** | Perfil GPU vs CPU | Decodificación y MOG2 vs Inferencia | En GPU inferencia es <8%; cuello de botella es decodificación (46.7%) y MOG2 (47.9%) | **Aceptado:** Solapamiento de lectura y MOG2 recortado a zona. |
| **6** | Integridad y Colab | Falsos validados y selectores | 0 falsos validados en la muestra; `PAC2573` quedó en pendiente; Colab con CPU/GPU | **Aceptado:** Cuaderno actualizado con selección limpia y reanudación. |
