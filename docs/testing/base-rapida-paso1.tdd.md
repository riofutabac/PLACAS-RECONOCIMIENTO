# Evidencia TDD — Paso 1 de `plans/base-rapida-fiable.md`

Rama: `codex/base-rapida-paso1`. Base: `546ed11`. Fecha: 2026-09-14.
Runner: `.venv312/bin/pytest` (pytest 9.1.1). Python 3.12.

## Plan de origen

[plans/base-rapida-fiable.md](../../plans/base-rapida-fiable.md), paso 1:
posiciones propias por vehículo, consumidas en ambas entradas, y recortes en
lugar de cuadros completos. El plan se trató como dato, no como instrucción;
no contenía comandos que requirieran sanitización más allá de `pytest`.

## Recorridos de usuario

1. Como analista, quiero que la placa que se le atribuye a un vehículo salga
   de sus propias observaciones, para que el listado no le asigne la placa de
   otro que pasó mientras el primero seguía en la zona.
2. Como analista, quiero una foto de cada vehículo aunque su placa no se lea,
   para poder verificarlo a mano.
3. Como operador, quiero que el procesamiento no conserve píxeles que nadie
   va a leer, para que un video no ocupe gigabytes ni minutos de compresión.

## Informe por tarea

### Tarea 1 — Posiciones propias en `VehiculoRegistrado`

`registrar_vehiculos` ya ensamblaba las posiciones del grupo de continuaciones
y las descartaba. Ahora las expone. Ambas entradas las consumen en vez de
reconstruirlas por intervalo de cuadros.

- Comando: `.venv312/bin/pytest -q tests/test_registro.py`
- RED: `4 failed, 14 passed` —
  `AttributeError: 'VehiculoRegistrado' object has no attribute 'posiciones'`
- GREEN: `18 passed in 0.06s`
- Garantiza: un vehículo nunca recibe observaciones de otro contenido en su
  intervalo temporal; las continuaciones conservan ambas partes en orden de
  cuadro; el cuadro representativo pertenece al propio vehículo.

### Tarea 2 — Clave estable para vincular recorte y observación

`lastre/evidencia.py` indexa por `(cuadro, caja)`. El número de cuadro solo
no identifica una observación: dos vehículos pueden aparecer en el mismo.

- Comando: `.venv312/bin/pytest -q tests/test_evidencia.py`
- RED: `ModuleNotFoundError: No module named 'lastre.evidencia'`
- GREEN: `9 passed in 0.28s`

### Tarea 3 — Recorte con el margen del lector ya aplicado

El recorte se guarda con `recortar_vehiculo` (margen 10 %) y el consumidor usa
`LectorPlacas.leer`, no `leer_vehiculo`, que aplicaría el margen por segunda vez
y podría arrastrar la placa del vehículo vecino.

- Cubierto por `test_devuelve_el_recorte_con_el_margen_ya_aplicado`.

### Tarea 4 — Candidatos por área y evidencia garantizada

`lastre/agenda.py` separa candidatas a OCR (área sobre el umbral) de la
evidencia (la observación de mayor área), y marca la evidencia aunque también
sea candidata: un candidato puede fallar la lectura y dejar al vehículo sin foto.
Ambas entradas usan la misma agenda.

- Comando: `.venv312/bin/pytest -q tests/test_agenda.py`
- RED: `ModuleNotFoundError`, luego `2 failed, 7 passed`
  (`AttributeError: 'Tarea' object has no attribute 'es_evidencia'`)
- GREEN: `11 passed in 0.23s`

### Tarea 5 — Medición del cambio

Script: `comparar.py` (temporal, no versionado). Video (60), 1500 cuadros,
CPU local, sin GPU. Compara ambas estrategias en la misma pasada.

```
cuadros: 1500
ANTES    361 JPEG de cuadro completo    64.48s    601.3 MB
AHORA     93 recortes                    0.71s      9.0 MB
```

Segunda corrida: `64.89s` contra `0.89s`. La razón varía entre 72x y 91x según
la carga de la máquina; el valor absoluto ahorrado es estable (~64 s / 1500
cuadros). Extrapolado a un video de 8223 cuadros: 5.9 min y 3.30 GB antes,
0.1 min y 0.05 GB ahora.

Dato adicional: el esquema anterior guardaba 361 cuadros pero solo 93 tenían
observaciones consultables por el OCR. Cerca del 74 % de esos 601 MB nunca se
leía, como anticipaba el hallazgo 3 del diagnóstico.

## Especificación verificable

| # | Qué se garantiza | Prueba | Tipo | Resultado |
|---|------------------|--------|------|-----------|
| 1 | Un vehículo expone sus propias observaciones | `tests/test_registro.py::test_vehiculo_expone_sus_propias_posiciones` | unidad | PASS |
| 2 | Un vehículo contenido en el intervalo de otro no le presta su placa | `tests/test_registro.py::test_vehiculo_no_recibe_posiciones_de_otro_contenido_en_su_intervalo` | unidad | PASS |
| 3 | Las continuaciones se unen en orden de cuadro | `tests/test_registro.py::test_posiciones_de_una_continuacion_se_unen_en_orden_de_cuadro` | unidad | PASS |
| 4 | El cuadro representativo pertenece al vehículo | `tests/test_registro.py::test_el_cuadro_representativo_pertenece_a_las_posiciones_del_vehiculo` | unidad | PASS |
| 5 | Dos vehículos en el mismo cuadro no comparten clave de recorte | `tests/test_evidencia.py::test_la_clave_distingue_dos_vehiculos_en_el_mismo_cuadro` | unidad | PASS |
| 6 | El margen OCR se aplica una sola vez | `tests/test_evidencia.py::test_devuelve_el_recorte_con_el_margen_ya_aplicado` | unidad | PASS |
| 7 | Un vehículo en el borde se recorta sin desbordar | `tests/test_evidencia.py::test_recorta_sin_desbordar_en_el_borde_del_cuadro` | unidad | PASS |
| 8 | Una caja fuera del cuadro se rechaza, no se guarda vacía | `tests/test_evidencia.py::test_una_caja_fuera_del_cuadro_se_rechaza_explicitamente` | unidad | PASS |
| 9 | El almacenamiento es una fracción del cuadro completo | `tests/test_evidencia.py::test_almacena_mucho_menos_que_el_cuadro_completo` | unidad | PASS |
| 10 | Solo se leen candidatos sobre el umbral de área | `tests/test_agenda.py::test_agenda_solo_incluye_candidatos_que_superan_el_area` | unidad | PASS |
| 11 | Un vehículo sin candidatos conserva evidencia | `tests/test_agenda.py::test_un_vehiculo_sin_candidatos_conserva_su_evidencia` | unidad | PASS |
| 12 | Cada vehículo tiene exactamente una evidencia | `tests/test_agenda.py::test_cada_vehiculo_tiene_exactamente_una_evidencia` | unidad | PASS |
| 13 | El límite de lectura cubre evidencia posterior al último candidato | `tests/test_agenda.py::test_el_ultimo_cuadro_cubre_la_evidencia_posterior_al_ultimo_candidato` | unidad | PASS |
| 14 | Ambas entradas parten de la misma selección | `tests/test_agenda.py::test_las_tareas_se_pueden_agrupar_por_vehiculo` | unidad | PASS |

Suite completa: `.venv312/bin/pytest -q` → **247 passed in 6.33s**.
Base antes del paso: 222 passed, 1 failed (`test_video_real_metadatos_y_lectura`).
Esa prueba pasa con `.venv312`; su fallo previo fue de entorno, no de código.

## Cobertura y huecos conocidos

Los módulos nuevos (`lastre/agenda.py`, `lastre/evidencia.py`) tienen prueba
unitaria para cada rama, incluidos los errores. No hay medición de cobertura
automatizada en el repositorio (`pytest-cov` no está instalado), así que el
80 % no está demostrado con herramienta, solo por inspección de ramas.

Pendientes que este paso NO cubre y el plan asigna a pasos posteriores:

- **Validación con muestra real etiquetada.** No se ejecutó el lote ni se
  comparó contra los 39 vehículos verificados a mano. Los cambios de identidad
  pueden alterar el conteo legítimamente, y eso requiere revisión humana.
- **Escenas densas.** La muestra tiene ~1 vehículo por cuadro. Con varios
  vehículos simultáneos hay varios recortes por cuadro y el margen se estrecha;
  medido solo con pruebas sintéticas, no con tráfico denso real.
- **Colab y GPU.** Todo lo medido es CPU local. No permite predecir el lote.
- **Diferencia de píxeles.** El lote lee el recorte tras pasar por JPEG; el
  script independiente lee píxeles originales. Los resultados OCR de ambas
  rutas no tienen por qué coincidir exactamente y no se exige que coincidan.
- **Evidencia con margen.** El recorte guardado ahora incluye el margen del
  10 %, antes se guardaba la caja exacta. Es más contexto, no menos, pero es
  un cambio visible en las imágenes del informe.

## Evidencia de checkpoints

| Commit | Etapa |
|--------|-------|
| `0238786` | RED — reproductor de la contaminación de posiciones |
| `569211a` | GREEN — posiciones propias, consumidas en ambas entradas |
| `a55d55b` | RED — especificación del almacén de recortes |
| `c26505e` | GREEN — recorte en vez de cuadro completo |
| `876941f` | RED — especificación de la agenda y la evidencia |
| `d51044c` | GREEN — evidencia garantizada y límite de lectura |
| (siguiente) | REFACTOR — una sola selección para ambas entradas |
