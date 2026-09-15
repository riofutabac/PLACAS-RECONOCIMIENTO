# Plan ECC: base rápida y fiable para PlacasVideos

Fecha: 2026-09-14. Actualización: 2026-09-15. Estado: implementación parcial
revisada; ver [evidencia de revisión](../docs/testing/revision-ecc-20260914.md).
Paso 1 implementado y corregido, con validación real parcial; no se ha cerrado
la evaluación de los 39 vehículos. Flags y deduplicación del Paso 2 corregidos.
Pasos 3–5 aún pendientes como objetivos completos.
Base inspeccionada: commit `546ed11`. Método: ecc:blueprint.

## Objetivo y evidencia

Reducir tiempo y memoria del procesamiento conservando vehículos e identidad.
Preparar después una evaluación de captura con cámara sencilla. No prometer
aceleración de Colab ni precisión general sin validarlas.

El usuario aporta una medición de 1500 cuadros del video (60), CPU local:
71.8 ms/cuadro detección, 34.1 JPEG, 15.8 decodificación y 0.04 seguimiento.
MOG2: 15.5 ms/cuadro. Inferencia: 111 llamadas a 526 ms. JPEG: 24 % de
cuadros a 142 ms; recorte: 10 ms. Memoria reportada: ~3.3 GB/video.
Estos números son evidencia aportada, no una medición reproducida por este
plan. No se encontró su script/registro entre los archivos descubiertos.
Los 1500 cuadros equivalen a unos 60 segundos a 25 FPS, no al lote completo.

La aritmética es consistente: 111×526/1500 = 38.9 ms/cuadro de inferencia.
Sumados a MOG2 son 54.4 ms; quedan ~17.4 ms/cuadro dentro de detección para
otras operaciones y diferencias de medición, todavía sin desglose.
La suma del bucle es ~121.74 ms/cuadro (~8.2 FPS). No incluye necesariamente
OCR posterior, escritura de recortes finales, carga de modelos ni Excel.

JPEG de recorte cuesta ~14 veces menos por llamada en esa prueba; no implica
14 veces menos tiempo total. Incluso eliminar el 28 % de JPEG dejaría un
máximo teórico de ~1.39× para ese bucle local, manteniendo todo lo demás.
En escenas con varios vehículos hay varios recortes por cuadro: medirlos.
En Colab JPEG podría tener más peso al acelerar inferencia, pero aún es una
hipótesis. CoreML ausente de la selección no invalida mediciones CPU locales;
limita su extrapolación a otro proveedor/hardware. Tenerlo disponible tampoco
demuestra que sea más rápido para estos modelos.

El fallo previo de apertura local no prueba un defecto del video o del código.
El usuario reporta apertura correcta con .venv312. Registrar backend y entorno
si reaparece; no usar el intento fallido como benchmark.

## Invariantes

- Lectura secuencial, sin saltos por índice. No cambiar modelo, confianza,
  frecuencia ni escala predeterminados en la primera optimización.
- Cada lectura mantiene vínculo inequívoco con su observación y vehículo.
- Conservar el margen OCR de 10 %, recortar en resolución original y respetar
  límites. Coordenadas globales y locales deben distinguirse explícitamente.
- Un vehículo sin placa sigue teniendo registro y evidencia.
- No reutilizar checkpoints de otra variante en comparaciones. Usar salidas
  aisladas y registrar revisión, configuración, modelos y entorno.
- Comparar vehículos reales, no exigir que el total viejo sea idéntico:
  corregir fusiones puede aumentar correctamente el conteo.

## Paso 1 — Posiciones propias y recortes en vez de cuadros completos

Contexto: `registrar_vehiculos` ya concatena posiciones por grupo, pero
`VehiculoRegistrado` las descarta. El lote las reconstruye por intervalo y
mezcla vehículos. Guarda JPEG completo incluso en cuadros sin observaciones.
La misma contención temporal existe en `scripts/leer_placas.py` al construir
su mapa por cuadro: corregir ambas entradas en el mismo paso.
Archivos: lastre/registro.py, scripts/procesar_lote.py, scripts/leer_placas.py,
tests/test_registro.py, tests/test_placa.py y nuevas pruebas de integración de
ambos scripts. lastre/placa.py aporta las funciones existentes de recorte/lectura;
solo modificar su contrato si la implementación demuestra que es necesario.

Tareas:
1. Devolver la tupla de posiciones calculada en VehiculoRegistrado y consumirla
   directamente en ambos scripts. No introducir una segunda reconstrucción
   por IDs/intervalos. La carga de trayectorias del script independiente sigue
   usando su formato existente; el nuevo campo se construye en el registro.
   Esto corrige la contaminación posterior, no certifica la asociación del
   seguidor ni la fusión previa de continuaciones: evaluarlas por separado.
2. Vincular recortes a observaciones mediante una clave estable explícita;
   no indexar solo por número de cuadro porque puede haber varios vehículos.
   Decidir el contrato mínimo con el seguidor; no usar coordenadas ambiguas
   como identidad persistente de un vehículo.
3. Recortar con el margen existente al recibir detección y almacenar el JPEG
   del recorte, no el cuadro completo. Usar `lector.leer` sobre el recorte ya
   preparado: no aplicar otra vez la caja global ni duplicar el margen.
4. Conservar inicialmente las mismas oportunidades OCR y calidad JPEG.
   En el lote, guardar candidatos OCR solo si `area >= AREA_MINIMA_PARA_LEER`;
   usar exactamente el mismo umbral al capturar y al consumir. No guardar
   JPEG OCR de posiciones que el lector descartaría de todas formas.
   Mantener por separado la evidencia representativa de cada trayectoria,
   incluso bajo el umbral; actualizarla cuando mejore el área y resolver la
   representante final al fusionar continuaciones. Reutilizar un recorte OCR
   existente cuando coincida, evitando doble almacenamiento/codificación.
   El script independiente conoce las posiciones antes de leer: añadir el
   cuadro representativo a su agenda aunque no haya candidatos OCR y extender
   el límite de lectura hasta la última evidencia necesaria. No introducirle
   una caché JPEG para OCR: hoy lee directamente del cuadro original.
   No añadir top-K/parada temprana en este cambio.
5. Medir tiempo JPEG, decodificación de recortes, bytes almacenados y memoria
   máxima durante esta corrección, sin construir antes un sistema de telemetría.

Verificación: `.venv312/bin/pytest -q tests/test_registro.py tests/test_placa.py`
y pruebas nuevas de integración de ambas entradas: A contiene temporalmente a B;
continuaciones; dos vehículos en el mismo cuadro; recorte en bordes; ausencia
de placa. Verificar que OCR recibe solo las posiciones propias y que las
imágenes se resuelven sin colisiones.
Probar áreas por debajo, iguales y superiores al umbral; vehículo sin ningún
candidato OCR; evidencia posterior al último candidato OCR; continuaciones
cuya mejor evidencia esté en otro fragmento. Ambos scripts deben seleccionar
las mismas posiciones propias para las mismas trayectorias y parámetros.
No exigir OCR idéntico entre rutas: el independiente usa píxeles originales
y el lote usa JPEG. Verificar cada ruta contra su propia base y las etiquetas.
Comparar la misma muestra real antes/después. Comprimir antes o después de
recortar puede cambiar píxeles JPEG y resultados OCR: no asumir equivalencia.
Salida: menor coste JPEG/memoria, evidencia íntegra, sin pérdida de vehículos
ni aumento de placas incorrectamente aceptadas en la muestra etiquetada.
Registrar explícitamente cantidad de JPEG, coste acumulado, coste por cuadro,
recortes por cuadro y memoria máxima, incluyendo evidencia representativa.
La cantidad de llamadas puede aumentar: tres recortes de ~10 ms serían ~30 ms
frente a un JPEG completo de ~142 ms, sin que esos valores sean universales.
Comparar escenas de baja y alta densidad; no aprobar rendimiento con el coste
unitario de un recorte ni con la muestra de ~un vehículo por cuadro solamente.
Si no hay muestra real densa, registrar esa validación pendiente y cubrir
colisiones/identidad con pruebas sintéticas, sin llamarlas benchmark real.
Rollback: revertir este cambio aislado, preservando resultados comparativos.
Dependencias: ninguna. Ejecución: modelo predeterminado con revisión cuidadosa.

## Paso 2 — Conectar flags y corregir deduplicación insegura

Contexto: el lote ignora escala/paso de movimiento. La primera deduplicación
fusiona placas pendientes, antes de la protección de `_depurar_filas`.
Archivos: scripts/procesar_lote.py, lastre/deduplicacion.py, pruebas de lote.

Tareas: pasar ambos argumentos al detector, validar rangos, mantener defaults
0.25 y 1. Agregar prueba de integración que confirme propagación efectiva.
Impedir fusión sustentada solo en placa pendiente; comprobar coexistencia e
identidad antes de fusionar aun si la placa fue validada. Dos vehículos
simultáneos pueden compartir una lectura errónea de alta confianza.
No ajustar frecuencias todavía. Mantener separables ambos cambios en commits.

Verificación: `.venv312/bin/pytest -q tests/test_vehiculos.py tests/test_deduplicacion.py tests/test_depuracion_filas.py`
más integración de flags y dos vehículos con igual OCR. Salida: defaults
equivalentes, parámetros efectivos, ningún vehículo borrado por placa dudosa.
Rollback: revertir commit específico. Depende de paso 1 por archivos/contratos.
Ejecución: modelo predeterminado.

## Paso 3 — Comparación reproducible en Colab y control del entorno

Contexto: la medición CPU local no explica por sí sola seis horas del lote.
El cuaderno verifica un detector distinto de las sesiones usadas por el script.
Archivos: medición, aceleración, lote, cuaderno y script de benchmark nuevo.

Tareas: registrar por video decodificación, MOG2, inferencia de vehículos,
JPEG, OCR, escrituras, carga de modelos, checkpoint, Excel y tiempo total.
Registrar llamadas, cuadros, bytes, pico de memoria y proveedores efectivos
de detector de vehículos, detector de placas y OCR. Separar calentamiento de
ejecución, sin excluirlo del total operativo. Reutilizar detector de vehículos
entre videos; reiniciar estado de movimiento y seguimiento por video.

Comparar baseline, paso 1 y paso 2 sobre idénticos videos/entorno, salidas
separadas. Repetir muestra al menos tres veces y reportar dispersión. Incluir
escena vacía, tráfico, vehículos juntos y reloj fallido; ejecutar lote completo
solo después de la regresión. Comparar Drive con copia local incluyendo copia
y publicación de evidencias/checkpoint; conservar persistencia por video.
CoreML es experimento opcional de Mac, separado de la corrección CUDA/Colab.

Verificación: `.venv312/bin/pytest -q tests/test_aceleracion.py tests/test_medicion.py tests/test_checkpoint.py`
y benchmark documentado con comando, revisión y resultados exportados.
Salida: explicación cuantificada del tiempo total, errores de sesiones visibles,
resultados repetibles. Rollback: restaurar configuración/proveedor previo.
Depende de 2; se pueden preparar anotaciones de muestra en paralelo sin código.
Ejecución: modelo predeterminado.

## Paso 4 — Reducir frecuencia y OCR con protección de precisión

Contexto: los flags ya funcionan y hay una base medida. El seguidor hoy
confunde cuadros no evaluados con ausencia de detección. La confianza OCR
se apoya en lecturas temporalmente correlacionadas.
Archivos: detector híbrido, seguimiento, selección OCR, lectura y reloj.

Tareas: distinguir no evaluado/ausencia; expresar tolerancias en tiempo y
revisar mínimo de observaciones antes de experimentar con paso/escala.
Evaluar un cambio a la vez, incluyendo motos y detenciones. Después probar
selección de candidatos por calidad/diversidad y más OCR cuando discrepen.
No asumir que consenso alto implica exactitud. Espaciar reintentos de reloj
y corroborar varias marcas; mantener sin hora cuando la evidencia falle.

Verificación: `.venv312/bin/pytest -q` y regresión etiquetada con conteo,
identidad, placa exacta, precisión de autoaceptados, cobertura, hora y sentido.
Salida: mejora temporal demostrada sin regresión observada en esas métricas;
reportar incertidumbre y casos individuales. Rollback: parámetros anteriores
y desactivar selección adaptativa. Depende de 3. Ejecución: revisión de mayor
capacidad para decisiones de identidad/confianza; implementación predeterminada.

## Paso 5 — Validar base para cámara sencilla

Contexto: los 39 vehículos conocidos sirven de regresión, no certifican
precisión general. No hay datos de cámara candidata ni condiciones nocturnas.
Archivos: protocolo de validación, configuración y resultados; cambios de
algoritmo solo si la evidencia los justifica.

Tareas: definir hardware y tiempo objetivo con el usuario; medir tiempo de
proceso/duración, latencia y memoria. Etiquetar exhaustivamente segmentos para
medir falsos positivos; separar ajuste y evaluación, desglosar camiones/motos.
Conservar tipo de vehículo desde detección; no inferir camión por formato de
placa. Probar captura real de cámara candidata: tamaño de placa, movimiento,
ángulo, día/noche y compresión. Separar conteo de identificación. Considerar
timestamps de captura para operación en vivo, sin depender del reloj impreso.

Verificación: protocolo ejecutado sobre datos no usados para ajustar reglas,
con errores y cobertura publicados. Salida: rango de condiciones soportadas
y límites medidos, no promesa de funcionar con cualquier cámara.
Rollback: conservar configuración de cámara/base previamente validada.
Depende de 4 para certificación final; recopilación de datos puede adelantarse.
Ejecución: modelo predeterminado, revisión de mayor capacidad para evaluación.

## Coordinación y actualización

Orden de implementación: 1 → 2 → 3 → 4 → 5. Evitar agentes editando lote
simultáneamente. Preparación de datos puede ir en paralelo con 1–3.
Git disponible; `origin` está configurado para fetch y push a
`https://github.com/riofutabac/PLACAS-RECONOCIMIENTO.git`. gh está ausente.
Lo que no está configurado es la referencia simbólica local `origin/HEAD`;
eso no significa que falte el remoto ni impide por sí solo hacer push.
Plan para cambios locales/commits revisables; no se crean ni publican PRs aquí.
Ramas futuras: `codex/base-rapida-<paso>`. No tocar cambios ajenos existentes.
Tras cada paso registrar revisión, comandos, resultados, decisión y pendientes.
Si evidencia contradice el orden, modificar este plan conservando motivo/fecha;
no marcar completado por tener tests unitarios sin validación real.

Revisión adversarial ECC completada por subagente: incorporados margen OCR,
coordenadas, colisiones entre recortes, diferencias JPEG, alcance limitado de
la corrección de posiciones y límites de extrapolación CPU/Colab. Sin objeciones
críticas pendientes al diseño; mediciones reales siguen siendo criterios de
salida de la implementación, no resultados obtenidos por este plan.

Refinamiento 2026-09-14 a partir de segunda revisión del usuario: incorporada
la entrada leer_placas.py, aclarado origin frente a origin/HEAD y concretados
el filtro temprano por área, la evidencia independiente y la aceptación bajo
distintas densidades. Orden 1 → 2 → 3 → 4 → 5 conservado. Primer cambio de
implementación: posiciones propias en ambas entradas, seguido de caché de
recortes del lote y evidencia en ambas rutas; verificar estos cambios antes
de ajustar frecuencias o introducir selección OCR.
