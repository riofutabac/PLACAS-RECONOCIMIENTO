# Plan: Conteo de salidas confiable

**Source PRD**: `.claude/prds/placas-via-lastre.prd.md`
**Selected Milestone**: 2 — Conteo de salidas confiable
**Complexity**: Medium

## Summary
Detectar cada vehículo que circula dentro del polígono de la vía de lastre, seguirlo a lo largo de los cuadros como una sola entidad y decidir si salió hacia la carretera principal. El entregable es el número de salidas del tramo de muestra, sin duplicados y sin tránsito de la vía principal, más un archivo de trayectorias que el hito 3 usará para buscar la placa. Todavía no se lee ninguna placa.

## Patterns to Mirror
| Category | Source | Pattern |
|---|---|---|
| Naming | `lastre/video.py:39` | Funciones como verbo en infinitivo y español, `obtener_metadatos_video`, `iterar_cuadros` |
| Errors | `lastre/video.py:23` | Excepción propia por módulo que hereda de un error estándar, mensaje con el valor recibido |
| Config | `lastre/config.py:74` | Validación total en el límite, dataclasses `frozen=True`, fallo temprano con `ConfiguracionError` |
| Inmutabilidad | `lastre/zona.py:11` | Las funciones devuelven arreglos nuevos y nunca mutan la entrada |
| Tests | `tests/test_video.py:17` | `pytest` con fixture que fabrica un video sintético en `tmp_path`, sin depender de las muestras reales |

## Files to Change
| File | Action | Why |
|---|---|---|
| `config/zona.json` | UPDATE | Añadir el segmento de salida y los umbrales de detección y seguimiento |
| `lastre/config.py` | UPDATE | Validar las secciones nuevas con el mismo rigor que el polígono |
| `lastre/deteccion.py` | CREATE | Detectar regiones en movimiento dentro de la máscara, cuadro a cuadro |
| `lastre/seguimiento.py` | CREATE | Asociar detecciones entre cuadros en trayectorias con identificador único |
| `lastre/salida.py` | CREATE | Decidir si una trayectoria constituye una salida y en qué cuadro ocurre |
| `lastre/trayectoria.py` | CREATE | Estructura inmutable de trayectoria y su serialización a JSON |
| `scripts/contar_salidas.py` | CREATE | Recorrer un video y emitir el conteo y el archivo de trayectorias |
| `tests/test_deteccion.py` | CREATE | Probar detección sobre cuadros sintéticos con la máscara real |
| `tests/test_seguimiento.py` | CREATE | Probar asociación, continuidad ante oclusión y separación de dos móviles |
| `tests/test_salida.py` | CREATE | Probar el criterio de salida, entrada y permanencia sin salida |

## Decisión de diseño pendiente de tu confirmación
El PRD deja abierto por dónde pasa la línea que marca la salida. Propongo definirla como el **borde derecho del polígono**, el tramo que va del vértice `(1924, 858)` al vértice `(2442, 1554)`, que es justo donde el lastre se encuentra con la carretera. Una trayectoria cuenta como salida cuando su último punto cruza ese borde hacia la derecha después de haber estado dentro de la zona al menos un mínimo de cuadros. El segmento queda en la configuración, así que se corrige sin tocar código si la evidencia visual muestra que quedó mal ubicado.

## Tasks

### Task 1: Configuración de detección, seguimiento y salida
- **Action**: Añadir a `config/zona.json` el segmento de salida, el área mínima de detección, la distancia máxima de asociación entre cuadros, los cuadros de tolerancia ante oclusión y el mínimo de cuadros para considerar válida una trayectoria. Extender `validar_configuracion` con las mismas comprobaciones de tipo y rango.
- **Mirror**: `lastre/config.py:74`, validación total en el límite.
- **Validate**: `.venv/bin/pytest tests/test_config.py`

### Task 2: Detección de movimiento acotada a la zona
- **Action**: Crear `lastre/deteccion.py` con un detector que aplique sustracción de fondo, restrinja el resultado a la máscara del polígono y devuelva las cajas delimitadoras que superen el área mínima. El detector no muta los cuadros recibidos.
- **Mirror**: `lastre/zona.py:11`, devolver estructuras nuevas.
- **Validate**: `.venv/bin/pytest tests/test_deteccion.py`

### Task 3: Seguimiento de vehículos entre cuadros
- **Action**: Crear `lastre/trayectoria.py` con la estructura inmutable de trayectoria, y `lastre/seguimiento.py` que asocie cada detección a la trayectoria más cercana dentro de la distancia máxima, abra una nueva cuando no haya candidata y cierre las que superen la tolerancia de oclusión. Cada trayectoria lleva identificador, cuadro inicial, cuadro final y la lista de posiciones.
- **Mirror**: `lastre/config.py:14`, dataclasses `frozen=True`.
- **Validate**: `.venv/bin/pytest tests/test_seguimiento.py`

### Task 4: Criterio de salida y descarte de duplicados
- **Action**: Crear `lastre/salida.py` que clasifique cada trayectoria como salida, entrada o permanencia, según el cruce del segmento de salida y el sentido del desplazamiento. Descartar trayectorias más cortas que el mínimo de cuadros, que corresponden a ruido.
- **Mirror**: `lastre/video.py:23`, excepción propia para entradas inválidas.
- **Validate**: `.venv/bin/pytest tests/test_salida.py`

### Task 5: Script de conteo y evidencia
- **Action**: Crear `scripts/contar_salidas.py` que recorra un video en secuencia, imprima el conteo por categoría y escriba un JSON con las trayectorias, incluyendo para cada salida el cuadro de cruce y el recuadro del vehículo. Guardar además una imagen por salida para inspección.
- **Mirror**: `scripts/verificar_zona.py`, mismo estilo de argumentos y de mensajes de salida.
- **Validate**: Correr sobre la primera muestra y contrastar el conteo contra la revisión manual de las imágenes generadas.

## Validation
```bash
.venv/bin/pytest -q
.venv/bin/python scripts/contar_salidas.py "Camara Placas 2_20260909105651-20260909163038(60).mp4"
```

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| El segmento de salida queda mal ubicado y cuenta de más o de menos | Media | Vive en la configuración; las imágenes por salida permiten corregirlo sin reprocesar el código |
| Un vehículo se fragmenta en dos trayectorias y se cuenta dos veces | Media | Tolerancia a oclusión configurable; contrastar el conteo contra la revisión manual de la muestra |
| Dos vehículos simultáneos se fusionan en una sola trayectoria | Media | Registrar el caso y marcarlo para revisión, según ya decidiste para las placas |
| Las sombras largas de la tarde se detectan como vehículos | Alta | Desactivar la detección de sombras del sustractor y exigir el área mínima |
| El camión blanco estacionado en el borde inferior genera detecciones | Media | Exigir el mínimo de cuadros y desplazamiento real, no solo presencia |

## Acceptance
- [ ] El conteo de salidas del tramo de muestra coincide con la revisión manual de las imágenes generadas
- [ ] Ningún vehículo de la carretera principal aparece entre las salidas
- [ ] Ningún vehículo aparece dos veces
- [ ] El archivo de trayectorias queda listo para que el hito 3 busque la placa
- [ ] `.venv/bin/pytest -q` pasa

---
*Milestone 2 de 5. No se escribe código hasta recibir confirmación.*
