# Resultados de diagnóstico ejecutado — 2026-09-16

## Hilos: doce corridas, tres rondas alternadas

| ONNX/OpenCV solicitados | Media total | Desviación muestral |
|---|---:|---:|
| auto/auto | 12.122 s | 0.237 s |
| 2/2 | 11.878 s | 0.310 s |
| 2/1 | 12.620 s | 0.235 s |
| 3/1 | 13.031 s | 0.455 s |

Todas procesaron 60 cuadros y 13 inferencias, con lectura adelantada. El total incluye decodificar cuadros anteriores. OpenCV reportó cuatro hilos en todas, incluso tras solicitar uno o dos en una comprobación separada. Su backend paralelo informa GCD. No se certifica configuración efectiva 2/2, ausencia de throttling ni una mejora integral del 2%. Mantener defaults hasta una prueba representativa.

Artefactos: `validacion/experimento_yolo26/hilos_corregidos.json` y `.log`.

## Moto: diagnóstico de los cuadros 5080–5139

RF-DETR detectó en 52 cuadros y YOLO26n en 26. Son inferencias en todos los cuadros, con seguidor reiniciado; no reproduce movimiento ni agenda paso=3 del video completo.

El primer diagnóstico de márgenes usó recortes sin compresión. Ninguna lectura cruda fue MZS872. Se detectó que faltaba reproducir JPEG calidad 92 del almacén; se corrigió el script y se repitió el cuadro 5108:

| Modelo | Margen .10 | Margen .15 | Margen .20 |
|---|---|---|---|
| RF-DETR | M25872 (.629) | M25132 (.701) | vacío |
| YOLO26n | vacío | vacío | M25182 (.692) |

La corrección de formato 2→Z y 5→S explica M25872→MZS872. No es evidencia independiente de exactitud. En la evidencia original se aprecia una motocicleta y no se distingue una placa legible. Revisar la anotación manual antes de tratar MZS872 como verdad. No promover margen .20 como recuperación de placa correcta.

Artefactos: `diagnostico_5080_5140.json` (sin JPEG) y `diagnostico_5108_5109.json` (con JPEG 92), dentro de `validacion/experimento_yolo26/`.

## Autobús: cuadros 2030–2089

RF-DETR: 56 cuadros con detección y una pista de 56 observaciones. YOLO: 58 cuadros, dos pistas de 47 y 36 observaciones. Se encontraron 25 pares casi idénticos.

Reproducción del seguidor sobre detecciones YOLO guardadas: supresión experimental por IoU > .98, ordenada por confianza, elimina 25 cajas y produce una pista de 58 observaciones. El registro del segmento pasa de dos a uno. No prueba que la pista restante pertenezca a la vía correcta, ni seguridad ante tráfico superpuesto, ni el efecto sobre el lote completo.

Artefacto: `diagnostico_2030_2090.json`. El ensayo de supresión es offline; no está activado en producción. Mantener fuera el NMS general .65 y el mínimo de ocho observaciones hasta medir falsos positivos.

## Decisión

Conservar RF-DETR por defecto. Próximo candidato acotado: supresión de cajas casi idénticas de YOLO, comprobando trayectorias completas y vehículos superpuestos. Confirmar primero las placas manuales y medir el lote con el ajuste aislado. No hay una nueva aceleración de producción demostrada en esta sesión.
