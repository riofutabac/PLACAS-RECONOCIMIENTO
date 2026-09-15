# Deduplicación de cajas idénticas — 15 de septiembre de 2026

## Alcance

`DetectorVehiculos.detectar` conserva una detección por caja exactamente igual,
con la mayor confianza y su clase. En empate conserva la primera. Aplica los
filtros de clase, confianza y zona antes de deduplicar. No suprime cajas distintas
por IoU, no cambia umbrales, frecuencia, OCR ni asociación del seguidor.

La clase ganadora queda en `DeteccionVehiculo`. Transportarla hasta el tipo del
Excel sigue pendiente: el formato de placa todavía determina ese tipo.

## Evidencia TDD

Rama: `codex/base-rapida-paso1`.

| Comportamiento | Prueba en tests/test_vehiculos.py | RED | GREEN |
|---|---|---|---|
| Una caja, mayor confianza y clase; ambos órdenes y misma/distinta clase | test_caja_identica_conserva_mayor_confianza_y_clase | 4 fallos: dos detecciones | 4 pasan |
| Empate determinista | test_caja_identica_empate_conserva_primera | Dos detecciones | Pasa |
| Cajas distintas, aunque casi idénticas, se conservan | test_cajas_casi_identicas_se_conservan | Pasa desde el inicio | Pasa |
| Duplicación no crea otra pista durante 30 cuadros | test_caja_duplicada_no_siembra_segunda_trayectoria | Dos trayectorias | Una trayectoria |

- RED: `.venv312/bin/pytest tests/test_vehiculos.py -q`: **6 fallan, 18 pasan**.
  Checkpoint `bb75d4a`.
- GREEN: **24 pasan** en ese archivo; suite completa `.venv312/bin/pytest -q`:
  **295 pasan**, 10.80 s. Checkpoint `a04d886`.
- Se adaptó la prueba de aceptación de todas las clases para usar cajas distintas.
  Su primer ajuste usaba anchos consecutivos, pero el helper divide por dos y
  producía pares iguales; se corrigió a anchos pares diferentes.
- Cobertura: `.venv312/bin/python -m coverage run --branch --source=lastre.vehiculos -m pytest tests/test_vehiculos.py -q`
  y `coverage report -m`: **92 %**, 90 sentencias, 6 no cubiertas, 30 ramas,
  2 parciales. Faltan carga real del modelo y descarte de área nula en esta
  medición aislada. El video usa el modelo real por separado.
- `git diff --check`: correcto.

Los checkpoints contienen solamente el detector y sus pruebas. El resto de
cambios de la revisión anterior continúa sin incluirse en esos commits.

## Ejecución real del video 61

Comando: `.venv312/bin/python scripts/procesar_lote.py validacion/review_20260914/entrada61 --out-dir validacion/deduplicacion_cajas_20260915/informe61 --acelerador cpu`.
Salida 0, sin errores. Se ejecutó fuera del sandbox para permitir la decodificación
de OpenCV, con parámetros por defecto y sin reutilizar checkpoints.

**Confirmado: cuatro registros pasan a tres.** Desaparece RR773, la fila
espuria de la misma furgoneta. Los tres registros conservados tienen imágenes
byte-idénticas a sus equivalentes anteriores, comprobadas con SHA-256.

| Vehículo | Antes | Después |
|---|---|---|
| Furgoneta escolar | RR773 y BAC2573 en dos filas | Una fila BAC2573, sale |
| Moto | MZS872, pendiente | MZS872, pendiente; mismos campos salvo ID/ruta |
| Camión | PAB6741, validado | PAB6741, validado; mismos campos salvo ID/ruta |

**El error PAC2573 → BAC2573 persiste.** Confianza 0.949, seis apoyos, consenso
0.186 → 0.158. No mejora el OCR por reunir las observaciones; continúa pendiente.
`lecturas` cuenta apoyos a la placa ganadora, no todas las lecturas OCR; el
consenso usa votos ponderados por confianza. El tipo del Excel sigue pendiente.

Excel verificado con openpyxl: hoja Placas con cuatro filas (cabecera + tres
vehículos), tres imágenes incrustadas y tres archivos de evidencia existentes.
Los tres registros tienen hora y sentido sale; uno validado y dos pendientes.

Se decodificaron 8230 cuadros; el metadato declara 8231, como en la corrida previa.
Tiempo medido antes de exportar Excel: **464.8 s** (anterior: 423.2 s). Detección
321.0 s, decodificación 115.0 s, OCR 16.4 s/189 llamadas (antes 192), guardado
4.0 s/235 llamadas. No se demuestra aceleración con este arreglo; la diferencia
de tiempo entre dos corridas no es un experimento pareado de rendimiento.

Artefactos: `validacion/deduplicacion_cajas_20260915/comparacion61.json`,
`resultado_ejecucion.txt`, `coverage.json`, `coverage.data`, `manifest.json`
y `informe61/`. La salida anterior se conserva en
`validacion/review_20260914/informe61`.

Conclusión acotada: se elimina este duplicado sin perder ninguno de los otros
registros previamente observados. No se ha anotado exhaustivamente el video,
no se ha repetido el video 60 con este cambio y no se demuestra recall global.
El diagnóstico anterior que atribuía este caso al seguidor queda corregido.

Tras GREEN se retiraron dos imports sin uso detectados por pyflakes. Las 24
pruebas del detector vuelven a pasar; pyflakes queda limpio. La ejecución real
usó el mismo comportamiento, anterior solamente a esa limpieza de imports.

## Ampliación: cajas degeneradas

Se añadió una prueba parametrizada con cinco casos: ancho cero, alto cero,
punto y esquinas invertidas en cada eje. Comprueba que se descartan antes de
consultar la zona y que una detección válida del mismo cuadro se conserva.
La zona se sustituye por un doble que acepta todo: así otro filtro no puede
ocultar la ausencia de la guarda de área.

Las **29 pruebas del detector pasan**; cobertura de sentencias y ramas combinada
**93 %**, 5 sentencias sin cubrir, 1 rama parcial, correspondientes a la carga
del modelo (líneas 98–107). Datos en
`validacion/deduplicacion_cajas_20260915/coverage-degeneradas.data`.
Es cobertura adicional de comportamiento existente: no hubo cambio de producción
ni una fase RED nueva. No se repitieron videos por este cambio exclusivo de pruebas.
