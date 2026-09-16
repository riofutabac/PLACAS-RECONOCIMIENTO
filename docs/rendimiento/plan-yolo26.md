# Experimento: YOLO26n frente a RF-DETR Nano

Fecha: 2026-09-16. Rama: `codex/experimento-yolo26`.
Base de código: `726f87c`, con reutilización persistente de modelos en Colab.
Estado: plan preparado; integración y mediciones pendientes.

## Objetivo y decisión

Evaluar YOLO26n como reemplazo del detector de vehículos. RF-DETR Nano 384 COCO es la referencia actual. Si Nano pierde eventos o lecturas correctas, evaluar YOLO26s. La hipótesis es menor latencia; no existe todavía una medición de estos candidatos en este equipo.

No se cambia el detector de placas YOLO v9 Tiny 384 ni el OCR Global Plates MobileViT v2. Mantener zona, MOG2, paso=3, paso_movimiento=1, escala=0.25, seguimiento y mínimos de observaciones durante la comparación principal.

## 1. Congelar referencia

- Preservar commit base, configuración, versiones, proveedor, hilos y huellas de videos/pesos. Guardar manifiesto de cada corrida y diff si el código no está limpio.
- Usar videos 60 y 61 para integración y regresión; sus conteos esperados son cinco y tres. La placa PAC2573 es un error OCR conocido y no puede convertirse en referencia correcta como BAC2573.
- Añadir clips anotados independientes con motos, vehículos pequeños, solapamientos y ausencia de tráfico antes de aprobar uso general. Identificar fuente de cada placa manual; no copiar predicciones como verdad.
- Volver a ejecutar la referencia en la misma sesión que el candidato. El benchmark histórico bc0859f/cb876a8 no sustituye esta comparación.

## 2. Integrar un detector seleccionable

- Añadir selector explícito RF-DETR Nano / YOLO26n / YOLO26s en CLI, Colab y manifiesto del checkpoint. Incluir tamaño, umbral, modo de salida y hash de pesos: variantes distintas no comparten resultados reanudados.
- Adaptar YOLO al contrato existente de detecciones: caja en coordenadas originales, clase, confianza, área y centro. Conservar filtrado por zona y clases de vehículos.
- Usar ONNX Runtime FP32 para la comparación inicial CPU de ambos modelos. Exportación y descargas fuera del tiempo de procesamiento; inicialización de sesiones incluida y medida aparte.
- Fijar versión del exportador y comprobar salida ONNX real. Documentar cabeza de detección y posprocesamiento; no asumir que toda exportación YOLO26 elimina NMS.
- RF-DETR usa 384; candidato inicial YOLO26n usa 640 según la configuración documentada. Es una comparación de configuraciones operativas, no de arquitecturas a resolución igual. Cambios de resolución son experimentos separados.
- Probar color BGR/RGB, normalización, letterbox, inversión de coordenadas, clases COCO, cajas vacías/degeneradas y proveedor realmente activo. Verificar CPU primero, CUDA después.

## 3. Verificación breve y puerta de precisión

- Ejecutar clips de tráfico antes del benchmark largo y revisar evidencia por evento: automóvil, moto, cisterna y furgoneta.
- Misma confianza inicial que la referencia. Las confianzas de modelos diferentes no están calibradas igual; cualquier ajuste posterior se hace en un conjunto de desarrollo y se congela antes de evaluar reserva.
- Comparar omisiones, falsos positivos, duplicados, dirección, hora, correspondencia de recortes y placas correctas recuperadas. No exigir igualdad exacta de cajas entre modelos diferentes.
- Si YOLO26n pierde cualquier evento conocido o lectura correcta, detener su promoción y probar YOLO26s con el mismo protocolo. No reducir observaciones mínimas para compensar.

## 4. Benchmark completo controlado

- Tres rondas RF-DETR/YOLO alternadas (A-B, B-A, A-B) en procesos aislados con salidas nuevas. Guardar stdout/stderr y no permitir que código 0 o existencia de Excel sustituyan la auditoría de contenido.
- Medir tiempo total desde carga hasta Excel, etapas, inferencias, cuadros efectivamente entregados, metadatos por separado y pico RSS por proceso. Comparar resultados completos por vehículo, no solamente conteos.
- Guardar resultados por corrida y resumen regenerable. Mantener corridas lentas; sin telemetría no atribuir variación a temperatura. Separar latencia de modelo y rendimiento completo.
- CPU es el primer entorno. CUDA necesita nuevas pruebas y no hereda conclusiones de CPU. No incluir INT8/FP16 u otros motores en esta primera comparación.

## 5. Criterios para aceptar el reemplazo

- Menor tiempo medio completo; reportar dispersión y todas las rondas. Si la diferencia resulta pequeña frente a la variación, repetir antes de decidir.
- Cero nuevas omisiones o duplicaciones de eventos anotados y cero pérdidas de placas correctas en el conjunto evaluado. No aumentar falsos validados.
- Evidencias correctas, memoria acotada y reanudación sin mezcla entre modelos.
- Si cumple solo en 60/61, declarar candidato prometedor, no validación general. Promover el valor por defecto después de evaluar clips independientes.
- Si ninguno cumple, conservar RF-DETR. Los adaptadores y mediciones quedan disponibles para nuevos experimentos.

## Entregables

1. Selector y adaptador con pruebas.
2. Manifiestos y resultados separados por candidato.
3. Tabla de velocidad, memoria, eventos y OCR, con evidencia de diferencias.
4. Decisión documentada: aceptar Nano, evaluar Small o mantener referencia.

Referencia oficial de modelos/exportación: https://docs.ultralytics.com/models/yolo26/
Las velocidades publicadas no se extrapolan a nuestro hardware ni al pipeline completo.
