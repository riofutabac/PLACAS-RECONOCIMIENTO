# Plan: Placas leídas y consolidadas

**Source PRD**: `.claude/prds/placas-via-lastre.prd.md`
**Selected Milestone**: 3 — Placas leídas y consolidadas
**Complexity**: Large

## Summary
Para cada vehículo confirmado como salida, buscar la placa a lo largo de toda su trayectoria, no en un cuadro fijo, y consolidar las múltiples lecturas en un único resultado con nivel de confianza. La evidencia del hito 2 obliga a esto: los vehículos cruzan de costado en el tramo cercano y algunos circulan sin placa frontal, así que la única oportunidad de lectura aparece en unos pocos cuadros del recorrido.

## Patterns to Mirror
| Category | Source | Pattern |
|---|---|---|
| Naming | `lastre/consolidacion.py:36` | Verbo en infinitivo y español, `consolidar_salidas`, `detectar` |
| Errors | `lastre/consolidacion.py:12` | Excepción propia por módulo, mensaje con el valor recibido |
| Config | `lastre/config.py` | Toda constante ajustable vive en `config/zona.json` y se valida al cargar |
| Inmutabilidad | `lastre/consolidacion.py:19` | Dataclasses `frozen=True`, funciones que devuelven tuplas nuevas |
| Tests | `tests/test_consolidacion.py:9` | Constructor auxiliar de datos mínimos, casos límite explícitos, prueba de no mutación |

## Files to Change
| File | Action | Why |
|---|---|---|
| `config/zona.json` | UPDATE | Umbral de confianza, mínimo de lecturas y parámetros del lector |
| `requirements.txt` | UPDATE | Añadir el motor de reconocimiento de placas |
| `lastre/config.py` | UPDATE | Validar la sección nueva |
| `lastre/placa.py` | CREATE | Localizar y leer la placa en un recorte de vehículo |
| `lastre/formato_ecuador.py` | CREATE | Validar y corregir el formato de placa ecuatoriano |
| `lastre/lectura.py` | CREATE | Consolidar las lecturas de una trayectoria en un único resultado |
| `scripts/leer_placas.py` | CREATE | Recorrer las salidas y producir el resultado por vehículo |
| `tests/test_placa.py` | CREATE | Probar el lector sobre recortes conocidos |
| `tests/test_formato_ecuador.py` | CREATE | Probar validación y corrección de caracteres confundibles |
| `tests/test_lectura.py` | CREATE | Probar la consolidación por votación y el umbral de confianza |

## Decisiones que propongo
**Reprocesar el video una sola vez.** El hito 2 ya guarda el recuadro del vehículo en cada cuadro de su trayectoria. El lector recorre el video en secuencia una vez, y en los cuadros que pertenecen a una salida recorta el vehículo y busca la placa. Evita decodificar el video una vez por vehículo.

**Consolidar por votación ponderada.** Cada lectura aporta su texto y su confianza. Gana el texto más votado, ponderando por confianza. El resultado final lleva la confianza promedio de las lecturas ganadoras y el número de lecturas que lo sustentan.

**Corregir solo lo que el formato permite.** Las confusiones conocidas, O con 0, B con 8, I con 1, S con 5, se corrigen únicamente cuando la posición del carácter exige letra o dígito según el formato ecuatoriano. Nunca se inventa un carácter que ninguna lectura vio.

## Tasks

### Task 1: Formato de placa ecuatoriano
- **Action**: Crear `lastre/formato_ecuador.py` con la validación del formato vigente y la corrección posicional de caracteres confundibles. Incluir el formato de motocicleta, que difiere del de automóvil.
- **Mirror**: `lastre/consolidacion.py:12`, excepción propia.
- **Validate**: `.venv/bin/pytest tests/test_formato_ecuador.py`

### Task 2: Lector de placa sobre un recorte
- **Action**: Añadir el motor de reconocimiento a `requirements.txt` y crear `lastre/placa.py`, que reciba un recorte de vehículo y devuelva las candidatas con su texto, confianza y recuadro. Sin lógica de consolidación.
- **Mirror**: `lastre/deteccion.py`, clase con configuración inyectada que no muta el cuadro.
- **Validate**: `.venv/bin/pytest tests/test_placa.py`

### Task 3: Consolidación de lecturas por vehículo
- **Action**: Crear `lastre/lectura.py` que reciba todas las lecturas de una trayectoria y devuelva un resultado único: placa, confianza, número de lecturas y estado. El estado es validado con confianza de 75 % o superior, pendiente de revisión por debajo, y sin placa identificable cuando no hubo ninguna lectura.
- **Mirror**: `lastre/consolidacion.py:36`, agrupar y elegir representante.
- **Validate**: `.venv/bin/pytest tests/test_lectura.py`

### Task 4: Script de lectura sobre las salidas
- **Action**: Crear `scripts/leer_placas.py` que lea el archivo de trayectorias del hito 2, recorra el video una vez, acumule lecturas por vehículo y escriba el resultado con la ruta del recorte de placa de cada uno.
- **Mirror**: `scripts/contar_salidas.py`, mismos argumentos, progreso y resumen final.
- **Validate**: Correr sobre la primera muestra y comparar contra la lectura manual de las imágenes.

## Validation
```bash
.venv/bin/pytest -q
.venv/bin/python scripts/leer_placas.py "Camara Placas 2_20260909105651-20260909163038(60).mp4"
```

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Ningún cuadro de la trayectoria muestra la placa | Alta | Ya decidido: el registro queda como sin placa identificable, con su imagen |
| El motor de reconocimiento no está ajustado al formato local | Alta | La corrección posicional y la validación de formato actúan después de la lectura |
| Una lectura errónea de alta confianza gana la votación | Media | Exigir un mínimo de lecturas coincidentes además del umbral de confianza |
| El recorte del vehículo incluye dos vehículos superpuestos | Media | Marcar el caso para revisión, según ya decidiste |
| El costo de procesamiento se dispara al leer cada cuadro | Media | Leer solo en los cuadros donde el vehículo supera un tamaño mínimo en pantalla |

## Acceptance
- [ ] Cada vehículo de salida tiene exactamente un resultado de placa
- [ ] Las placas entregadas como validadas cumplen el formato ecuatoriano
- [ ] Todo resultado tiene su recorte de placa o, si no la hubo, la imagen del vehículo
- [ ] Los tres vehículos reales de la muestra se contrastan contra la lectura manual
- [ ] `.venv/bin/pytest -q` pasa

---
*Milestone 3 de 5. No se escribe código hasta recibir confirmación.*
