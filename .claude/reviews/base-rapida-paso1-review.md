# Code review: `codex/base-rapida-paso1` → `main`

**Fecha**: 2026-09-14 · **Modo**: local (no hay `gh` instalado)
**Alcance**: 9 archivos, +798 / −61 · **Decisión**: APROBAR con comentarios

## Resumen

El paso 1 del plan corrige la contaminación de identidad en ambas entradas y
reemplaza el almacenamiento de cuadros completos por recortes. Sin hallazgos
CRÍTICOS ni ALTOS. Los tres hallazgos MEDIOS detectados durante la revisión
se corrigieron en `6ab7075`; el resto son preexistentes y quedan fuera del
alcance de este paso.

## Hallazgos

### CRÍTICO
Ninguno. No hay credenciales, entrada sin validar, rutas construidas con datos
externos ni dependencias nuevas. Los módulos nuevos validan sus parámetros y
lanzan excepción propia (`AgendaError`, `EvidenciaError`).

### ALTO
Ninguno.

### MEDIO — corregidos en esta rama

1. **`scripts/leer_placas.py`: recorte recalculado hasta tres veces.**
   Se llamaba `recortar_vehiculo` para la evidencia, otra vez dentro de
   `leer_vehiculo` y una más por cada placa encontrada. Corregido: un recorte
   por observación y `lector.leer`, igual que el lote.
2. **Ambos scripts: el mismo archivo se escribía una vez por placa encontrada.**
   Un recorte con dos placas producía dos `imwrite` idénticos. Corregido con
   una sola escritura por observación.
3. **`scripts/leer_placas.py`: contador de progreso incoherente.**
   `analizados` cuenta solo candidatos OCR pero se comparaba contra el total de
   tareas, evidencia incluida, así que nunca alcanzaba el total anunciado.
   Corregido separando `total_candidatos`.

### MEDIO — preexistentes, fuera de alcance

4. **Funciones largas.** `procesar_video()` pasa de 143 a 167 líneas y
   `leer_placas.main()` de 152 a 175. Ya excedían el límite de 50 antes de
   este cambio; partirlas es refactor de scripts, no del paso 1.
5. **`scripts/leer_placas.py`: `por_cuadro_crudo` indexa por cuadro.**
   Dos vehículos con el mismo cuadro representativo se pisarían al construir
   las filas finales. Preexistente y no agravado aquí, pero es el mismo error
   de indexar por cuadro que este paso corrigió en otro sitio.
6. **Imports sin uso** (preexistentes): `typing.Optional` en
   `lastre/registro.py:12` y `rango_de_nombre` en `scripts/procesar_lote.py:37`.

### BAJO

7. `lastre/evidencia.py` mantiene todos los recortes de un video en memoria.
   Medido en 0.05 GB por video contra 3.30 GB antes, así que no es un problema
   hoy; en escenas densas conviene vigilar `bytes_totales`.

## Validación

| Comprobación | Resultado |
|---|---|
| Sintaxis (`ast.parse`) | Pass |
| Lint (`pyflakes`, módulos nuevos) | Pass — 0 avisos |
| Pruebas (`.venv312/bin/pytest -q`) | Pass — 247 passed in 2.98s |
| Secretos / debug en módulos nuevos | Pass — ninguno |
| Build | N/A (no hay paso de build) |

## Verificación por categoría

- **Corrección**: las nuevas rutas tienen prueba por rama, incluidos bordes de
  imagen, caja fuera del cuadro y dos vehículos en el mismo cuadro. La clave
  `(cuadro, caja)` elimina la colisión que tenía indexar solo por cuadro.
- **Seguridad**: sin superficie nueva. Los nombres de archivo se componen de
  enteros y del `stem` de una ruta ya validada por el script.
- **Rendimiento**: mejora medida en la etapa de almacenamiento (64.5 s → 0.71 s
  y 601 MB → 9 MB sobre 1500 cuadros). No se ha medido el lote completo.
- **Completitud**: 14 garantías con prueba, documentadas en
  `docs/testing/base-rapida-paso1.tdd.md` junto con los huecos conocidos.
- **Mantenibilidad**: los dos módulos nuevos rondan las 100 líneas y explican
  en el docstring por qué existen. Ambas entradas comparten una sola regla de
  selección, que antes estaba duplicada y podía divergir.

## Archivos revisados

| Archivo | Cambio |
|---|---|
| `lastre/agenda.py` | Añadido |
| `lastre/evidencia.py` | Añadido |
| `lastre/registro.py` | Modificado |
| `scripts/procesar_lote.py` | Modificado |
| `scripts/leer_placas.py` | Modificado |
| `tests/test_agenda.py` | Añadido |
| `tests/test_evidencia.py` | Añadido |
| `tests/test_registro.py` | Modificado |
| `docs/testing/base-rapida-paso1.tdd.md` | Añadido |

## Condición de salida pendiente

El plan no considera el paso aprobado por tener pruebas unitarias: exige
comparar la misma muestra real antes y después, contra las etiquetas de los
39 vehículos verificados a mano. Esa validación **no** se ha ejecutado.
