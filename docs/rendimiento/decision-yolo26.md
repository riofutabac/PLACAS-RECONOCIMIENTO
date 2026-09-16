# Decisión Técnica: Evaluación de YOLO26 (Nano / Small) frente a RF-DETR Nano 384

Fecha: 2026-09-16  
Rama: `codex/experimento-yolo26`  
Protocolo aplicado: [`docs/rendimiento/plan-yolo26.md`](file:///Users/desarrollopashq/Documents/GitHub/PlacasVideos/docs/rendimiento/plan-yolo26.md)  
Resultados y auditoría: [`validacion/experimento_yolo26/resultados_comparacion.json`](file:///Users/desarrollopashq/Documents/GitHub/PlacasVideos/validacion/experimento_yolo26/resultados_comparacion.json)

---

## 1. Veredicto y Decisión Ejecutiva

**Decisión: MANTENER RF-DETR Nano 384 como detector de vehículos predeterminado y RECHAZAR el reemplazo por YOLO26n / YOLO26s para producción.**

### Justificación según los criterios del plan:
1. **Regla de aceptación:** *"Cero nuevas omisiones o duplicaciones de eventos anotados y cero pérdidas de placas correctas en el conjunto evaluado. No aumentar falsos validados."*
2. **Fallo crítico de YOLO26n:** 
   - **Omisión completa de vehículo real:** En el Video 61, omite por completo la motocicleta `MZS872` (frame 5108). Debido a pérdidas de detección intermitentes en cuadros consecutivos, la pista no alcanza el umbral de 10 observaciones mínimas y se descarta.
   - **Falso positivo de tráfico:** Registra un autobús de la carretera principal (frame 2059, placa `IC138`) como vehículo circulando en la vía monitoreada.
3. **Fallo de YOLO26s:**
   - Si bien recupera la trayectoria de la motocicleta, la geometría de la caja delimitadora recorta la imagen de forma distinta a RF-DETR, impidiendo que el OCR detecte la placa (lectura vacía `""`, perdiendo `MZS872`).
   - También incorpora el falso positivo del autobús de la carretera principal (frame 2047, placa `IOE333`).
   - Su mayor costo computacional en CPU anula la ventaja de velocidad.
4. **Beneficio temporal real insuficiente frente a la pérdida de calidad:**
   - Aunque la inferencia aislada del modelo de vehículos se redujo de 521.8 s a 237.4 s en el lote, el tiempo total del pipeline completo solo bajó de **904.2 s a 848.4 s (-6.2% de ahorro real)**, debido a que decodificación y filtro de movimiento absorbieron el cuello de botella.
   - Un ahorro del 6.2% no justifica bajo ningún concepto perder vehículos reales ni lecturas correctas de placas.

---

## 2. Métricas Comparativas de Rendimiento (CPU)

Medición sobre el conjunto de evaluación completo (Videos 60 y 61, 16,454 cuadros analizados en procesos aislados bajo macOS con `/usr/bin/time -l`):

| Métrica | RF-DETR Nano 384 (Referencia) | YOLO26n (Candidato Nano) | Variación |
| :--- | :---: | :---: | :---: |
| **Tiempo Total Pipeline** | **904.21 s** | **848.37 s** | **-55.84 s (-6.18%)** |
| **Tiempo Inferencia Vehículos** | 521.8 s (57.9%) | 237.4 s (28.1%) | -284.4 s (-54.5%) |
| **Latencia media / inferencia** | 627.9 ms | 285.6 ms | 2.2x más rápido en pipeline |
| **Decodificación de video** | 290.1 s | 433.4 s | Mayor contención |
| **Filtro de movimiento (MOG2)** | 253.0 s | 411.4 s | Mayor contención |
| **Lector de placas (ALPR + OCR)** | 41.9 s | 49.2 s | Similar |
| **Pico de Memoria RSS** | **593.93 MB** | **542.01 MB** | **-51.92 MB (-8.74%)** |
| **Cuadros analizados** | 16,454 | 16,454 | Idénticos |
| **Vehículos totales reportados** | 8 (5 en V60, 3 en V61) | 8 (5 en V60, 3 en V61) | **Diferentes identidades** |

---

## 3. Auditoría de Vehículos y Precisión por Evento

### Video 60 (5 vehículos esperados)
| # | Evento / Descripción | Placa Esperada | RF-DETR Nano 384 | YOLO26n | Estado Auditoría |
|---|---|---|---|---|---|
| 1 | Automóvil (Chevrolet Aveo gris) | `PCM2497` | `PCM2497` (conf 0.941) | `PCM7497` (conf 0.927) | Ambos detectan el evento |
| 2 | Camión cisterna de agua | `PCG3981` | `PCG3981` (conf 0.964) | `PCG3981` (conf 0.971) | Ambos detectan y leen |
| 3 | Camioneta gris | `TAA2204` | `TAA2204` (conf 0.950, val) | `TAA2204` (conf 0.953) | Ambos detectan y validan |
| 4 | Furgoneta | `JJ4306` | `JJ4306` (conf 0.675) | `JUO1168` (conf 0.772) | Ambos detectan el evento |
| 5 | Camioneta / Moto | `VE9715` | `VE9715` (conf 0.722) | `GB9795` (conf 0.711) | Ambos detectan el evento |

### Video 61 (3 vehículos esperados)
| # | Evento / Descripción | Placa Esperada | RF-DETR Nano 384 | YOLO26n | Estado Auditoría |
|---|---|---|---|---|---|
| 1 | Furgoneta escolar JAC blanca | `BAC2573` (real `PAC2573`) | `BAC2573` (conf 0.949) | `BAC2573` (conf 0.947) | Ambos detectan y leen |
| 2 | **Motocicleta (frame 5108)** | `MZS872` | **`MZS872` (conf 0.629)** | **NO DETECTADO (OMISIÓN)** | **FALLO CRÍTICO YOLO26n** |
| 3 | Camioneta roja | `PAB6741` | `PAB6741` (conf 0.972, val) | `PAB6741` (conf 0.955, val) | Ambos detectan y validan |
| - | Autobús carretera principal | *Ninguno (fuera de vía)* | *Ignorado correctamente* | **`IC138` (falso positivo)** | **FALLO YOLO26n** |

---

## 4. Entregables Implementados y Conservados

A pesar de que el modelo predeterminado continúa siendo RF-DETR Nano 384, todo el trabajo de ingeniería quedó integrado y verificado con 356 pruebas unitarias exitosas:

1. **Módulo Adaptador (`lastre/yolo.py`):**
   - Ejecución pura sobre ONNX Runtime FP32 compatible con NumPy 2.x.
   - Preprocesamiento letterbox a 640×640 con padding 114 y posprocesamiento con proyección exacta de coordenadas y filtrado de cajas degeneradas.
   - Extracción de metadatos ONNX y hash criptográfico SHA-256 de los pesos.
2. **Selector en Línea de Comandos y Lote (`scripts/procesar_lote.py`):**
   - Nuevo parámetro `--modelo-vehiculos {rf-detr-nano-384-coco, yolo26n, yolo26s}`.
   - Permite alternar fácilmente el detector para futuros experimentos.
3. **Aislamiento en Checkpoints (`lastre/checkpoint.py`):**
   - Registro del manifiesto de ejecución (`modelo_vehiculos`, `peso_hash`, tamaño de entrada) en `avance.json`.
   - Prevención automática de reanudaciones cruzadas entre modelos incompatibles.
4. **Herramienta de Auditoría y Benchmark (`scripts/comparar_detectores.py`):**
   - Script automatizado para mediciones reproducibles de tiempo, memoria RSS y auditoría evento por evento contra `referencia_base.json`.
