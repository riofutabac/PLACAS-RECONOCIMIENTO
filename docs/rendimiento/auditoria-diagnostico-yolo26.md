# Auditoría de los ajustes propuestos para YOLO26

Fecha: 2026-09-16. Estado: correcciones de implementación y diagnóstico; candidato no promovido.

## Hallazgos

- El diagnóstico de OCR recortaba directamente la caja, sin margen. Producción usa `recortar_vehiculo` con margen 0.10. Se corrigió el diagnóstico para usar la misma función. Las conclusiones previas sobre el margen necesitan una nueva comparación explícita.
- Una salida M25182 no demuestra recuperación correcta de MZS872. Debe contrastarse con lectura manual. Aumentar margen también puede incorporar placas ajenas.
- El diagnóstico ejecuta el modelo en todos los cuadros del segmento, con seguimiento nuevo y sin el filtro híbrido. No reproduce los contadores globales de movimiento/paso=3 del video completo. No demuestra por sí solo por qué producción acumuló ocho observaciones.
- El ensayo de hilos procesaba 60 cuadros, no 400, sin lectura adelantada, una vez por configuración e incluyendo la decodificación de unos 700 cuadros previos. No medía temperatura ni prueba estrangulamiento térmico. Se corrigieron descripción, restauración de hilos globales, lectura adelantada, rondas alternadas y persistencia JSON. Falta ejecutar el protocolo corregido.
- NMS agnóstico IoU=0.65 puede suprimir vehículos distintos superpuestos. Eliminar la segunda caja de un autobús tampoco garantiza excluir su caja principal de la zona. No se activa globalmente sin comprobar ambos casos.
- Bajar observaciones mínimas a ocho debilita la protección contra pistas espurias ya observadas. Confianza 0.40 y margen 0.20 siguen siendo candidatos, no valores aceptados.

## Cambios realizados

- Checkpoints comparan todos los campos esperados y rechazan hashes/campos ausentes; el manifiesto incluye muestreo y criterios OCR/registro.
- Se eliminó la captura de TypeError que podía reabrir un checkpoint sin validación. Los dobles de pruebas ahora aceptan el contrato real.
- El adaptador YOLO rechaza salidas incompatibles con Nx6 y descarta valores no finitos y clases no enteras. Valida la imagen antes de acceder a sus dimensiones.
- Las pruebas cubren salida ONNX cruda incompatible y campos de checkpoint ausentes o distintos.

## Próximo experimento

Repetir diagnóstico con recortes idénticos a producción y guardar detecciones crudas, decisiones de zona/confianza, cuadros realmente confirmados por el híbrido, pistas y lecturas. Comparar cada ajuste de margen, confianza o supresión de forma aislada, incluyendo escenas con vehículos superpuestos y tráfico fuera de zona. Mantener la referencia actual hasta demostrar conservación de eventos y placas correctas.
