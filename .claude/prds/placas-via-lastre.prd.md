# Registro de placas en la vía de lastre del peaje

## Problem
Junto al peaje existe una vía alterna de lastre que algunos vehículos usan para evadir la estación de cobro. Se instaló una cámara para registrarlos, pero su campo de visión cubre también la carretera principal, por lo que la grabación mezcla vehículos del objeto de análisis con tránsito irrelevante. Revisar a mano las ~700.000 imágenes de la grabación (6 h 30 min a 30 fps) tomaría decenas de horas y acumularía errores por fatiga, así que hoy la evasión no se cuantifica ni se documenta.

## Evidence
- Existen dos archivos de muestra en la raíz del proyecto, tramos distintos de una grabación mayor. Son representativos de la realidad, no el corpus completo a procesar; el resto está en la nube. La cámara permaneció fija durante toda la grabación, por lo que una sola delimitación sirve para todos los archivos.
- Cada archivo mide 2960x1664 a 24,9 cuadros por segundo y dura 5,5 minutos.
- Los cuadros llevan la fecha y hora grabadas en la propia imagen, en la esquina superior derecha, con formato `DD/MM/AAAA HH:MM:SS`.
- La vía de lastre quedó delimitada como un polígono cerrado de 12 vértices ajustado a la superficie real, no como un semiplano. Un semiplano incluía el cielo y el tramo lejano de la carretera principal.
- Prueba sobre la primera muestra: 11 eventos de movimiento en la zona del lastre en 5,5 minutos, equivalente a unos 780 vehículos en 6 h 30 min.
- Legibilidad confirmada: la placa TAA-2204 se lee con claridad al recortar y ampliar un vehículo cercano. La resolución de 2960x1664 alcanza.
- Riesgo confirmado en campo: un vehículo de la muestra circula sin placa frontal, y en el tramo cercano los vehículos cruzan de costado.
- Supuesto — la magnitud de la evasión no está medida. Necesita validación mediante el propio conteo que produzca este proceso, contrastado contra una muestra verificada manualmente.

## Users
- **Primary**: Analista interno de la concesionaria que realiza un estudio puntual para dimensionar cuántos vehículos evaden el peaje por la vía de lastre y sustentar una decisión de control.
- **Not for**: Uso probatorio, sancionatorio o de notificación a propietarios. Tampoco operación en vivo ni monitoreo continuo.

## Hypothesis
Creemos que **un proceso automatizado de detección, seguimiento y lectura de placas restringido a la zona de la vía de lastre** permitirá **obtener el listado de vehículos que salieron por esa vía sin revisión manual exhaustiva** para el **analista interno**.
Sabremos que acertamos cuando **al menos el 95 % de las placas entregadas como validadas coincidan con una muestra verificada manualmente, y ningún vehículo que salió por el lastre quede ausente del listado.**

## Success Metrics
| Metric | Target | How measured |
|---|---|---|
| Exactitud de placa (registros validados) | ≥ 95 % de coincidencia exacta | Comparación contra muestra verificada manualmente |
| Vehículos de salida no detectados | 0 en la muestra | Conteo manual de la muestra vs. listado generado |
| Falsos registros de la vía principal | TBD — umbral a definir tras la primera corrida | Revisión de las imágenes de respaldo de la muestra |
| Esfuerzo de revisión manual restante | TBD — se fija al conocer el volumen de pendientes | Conteo de registros en estado pendiente |
| Cobertura de imagen de respaldo | 100 % de los registros tienen al menos una imagen | Verificación de que cada fila referencia un archivo existente |
| Vehículos sin placa identificable | TBD — se mide en la primera corrida completa | Proporción de registros marcados como sin placa sobre el total |

## Scope
**MVP** — Procesar la grabación existente y producir un archivo CSV o Excel con un registro por vehículo que salió por la vía de lastre. Cada registro incluye: placa identificada, nombre o identificador único del registro, fecha y hora real de paso, posición en el video, tipo de vehículo (automóvil o motocicleta), nivel de confianza, ruta de la imagen de donde se extrajo la placa, y estado. Un registro queda **validado** con confianza de 75 % o superior y **pendiente de revisión** por debajo de ese umbral. Cuando el vehículo no expone ninguna placa legible en todo su recorrido, el registro se marca como **sin placa identificable**, con placa vacía y confianza cero. Todo vehículo detectado genera una fila y al menos una imagen de respaldo, sin excepción, de modo que el conteo de vehículos siempre queda completo aunque la placa no se obtenga. El proceso delimita la zona de análisis, sigue cada vehículo individualmente, descarta los que no salen, consolida las múltiples lecturas de un mismo vehículo en un solo resultado y valida el formato de placa ecuatoriano.

**Out of scope**
- Interfaz de revisión manual — el CSV con las imágenes de respaldo basta para el estudio puntual.
- Procesamiento en vivo o de cámara en tiempo real — solo grabaciones existentes.
- Cruce con bases vehiculares o identificación de propietarios — fuera del uso interno declarado.
- Reposicionamiento de la cámara — la grabación ya existe y no se puede repetir.

## Delivery Milestones
<!-- Business outcomes, not engineering tasks. /plan turns each into a plan. -->
<!-- Status: pending | in-progress | complete -->

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | Zona de análisis delimitada | El proceso solo considera vehículos dentro del polígono cerrado de la vía de lastre, con evidencia visual de la delimitación | complete | `.claude/plans/placas-via-lastre.plan.md` |
| 2 | Conteo de salidas confiable | Se obtiene el número de vehículos que salieron por el lastre, sin duplicados y sin contar el tránsito principal | in-progress | `.claude/plans/placas-via-lastre-h2.plan.md` |
| 3 | Placas leídas y consolidadas | Cada vehículo de salida tiene una placa única consolidada, validada contra el formato ecuatoriano, con su imagen de respaldo | in-progress | `.claude/plans/placas-via-lastre-h3.plan.md` |
| 4 | Precisión medida | Se conoce la exactitud real del proceso contra una muestra verificada manualmente | pending | — |
| 5 | Entrega final | El analista recibe el archivo con todos los campos y las imágenes asociadas | pending | — |

## Open Questions
- [ ] La línea divisoria está definida, pero falta confirmar por dónde pasa la línea de conteo que decide que un vehículo "salió".
- [ ] ¿Cuál es el listado completo de archivos a procesar y cuánto suman en horas?
- [ ] ¿Qué tamaño debe tener la muestra verificada manualmente para que la medición de precisión sea creíble?
- [ ] Cuando varios vehículos pasan simultáneamente por la zona, ¿se acepta algún criterio de resolución o todos esos casos van a revisión manual?

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| La placa no es legible a simple vista en la zona del lastre | Alta | Crítico — la meta de 95 % sería inalcanzable | Validar legibilidad en una muestra antes de comprometer la meta; renegociar el umbral si la imagen no da |
| Vehículos de la vía principal aparecen superpuestos sobre el área del lastre | Alta | Alto — falsos registros | Exigir trayectoria completa dentro de la zona, no solo presencia puntual |
| Varios vehículos simultáneos en la zona confunden la asociación placa-vehículo | Media | Alto — placas cruzadas entre registros | Marcar esos tramos como pendientes de revisión con su imagen de respaldo |
| Confusión de caracteres similares (O/0, B/8, I/1, S/5) | Alta | Medio — placas incorrectas dadas por válidas | Consolidar múltiples lecturas por vehículo y validar contra el formato ecuatoriano |
| El reloj grabado en la imagen se lee mal o está desajustado | Baja | Medio — horas incorrectas en el listado | Leer el reloj del cuadro y contrastarlo contra el nombre de archivo, que también codifica el rango |
| Vehículos sin placa frontal o que cruzan solo de costado | Alta | Medio — el vehículo se cuenta pero no se identifica | Intentar la lectura en todo el recorrido, frontal y trasera, quedarse con la mejor y, si ninguna sirve, marcar el registro como sin placa identificable |
| El reloj grabado en la imagen dispara falsos eventos de movimiento | Confirmada | Bajo — ruido en la detección | Excluir la franja superior del cuadro de la zona de análisis |
| El salto por número de cuadro es inexacto en este códec | Confirmada | Medio — tiempos y muestreo incorrectos | Decodificar en secuencia; costo aproximado de 3 min de proceso por cada 5,5 min de video |
| Variaciones de iluminación y contraluz a lo largo del día | Alta | Medio — precisión desigual por franja horaria | Medir la precisión por franja horaria, no solo el promedio global |

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
