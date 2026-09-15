# Revisión ECC posterior a la implementación

Fechas de ejecución: 2026-09-14 y 2026-09-15. Implementación recibida: `6b7c6ba`, comparada con
`546ed11`. Correcciones de esta revisión: cambios locales, sin commit ni push.
Se aplicó ECC review-pr en modo local (gh no está instalado), con revisión
de código/contratos, pruebas, comentarios y fallos silenciosos por subagentes.

## Decisión

La corrección de posiciones propias está implementada en ambas entradas.
Se encontraron y corrigieron fallos adicionales. Las pruebas de software
aprueban; no equivalen a demostrar precisión general del OCR ni velocidad
del lote de Colab. **No se aprueba todavía el sistema completo como preciso**:
la corrida original del video 61 mantiene un error de placa y registra dos veces
la misma furgoneta. Actualización del 15 de septiembre: la deduplicación del
detector elimina ese registro espurio en una nueva corrida completa (4 → 3);
el error de placa persiste. Véase [evidencia TDD](deduplicacion-cajas-20260915.tdd.md).
La validación completa de los 39 vehículos sigue pendiente.

## Correcciones realizadas

| Problema | Corrección y comprobación |
|---|---|
| Se comprimían todas las posiciones pequeñas | Candidatos desde área 40000 y solo la mejor evidencia por pista; pruebas de memoria estable, umbral inclusivo y referencias compartidas |
| JPEG cambió inadvertidamente de 92 a 95 | Caché restaurada a 92, conservando calidad 95 de la evidencia exportada |
| Fallos de JPEG/escritura producían rutas ficticias o se ocultaban | Errores explícitos; el video fallido no recibe checkpoint exitoso |
| Dos cajas del mismo grupo/cuadro sobrescribían evidencia | Representante por cuadro+caja y nombres que incluyen la caja |
| El CSV tomaba lecturas del último vehículo con igual cuadro | Número de lecturas transportado con la evidencia seleccionada por deduplicación |
| Se fusionaban placas pendientes o vehículos simultáneos | Ambos registros deben estar validados, sin sentidos opuestos ni solapamiento temporal; comparación con todos los miembros del grupo |
| La limpieza final podía volver a fusionar vehículos separados | Las filas con identidad ya procesada conservan la deduplicación anterior |
| Flags de movimiento ignorados | Conectados a sus constructores, manteniendo defaults; prueba con valores distintos de los defaults |

No se cambió el modelo, el umbral de confianza, la frecuencia predeterminada
ni la heurística espacial del seguidor. Las correcciones de deduplicación y
flags adelantan una parte del Paso 2 porque eran defectos comprobados.

## Pruebas de software

`.venv312/bin/pytest -q`, ejecutado fuera del sandbox: **288 passed in 6.51s**.
La prueba real de video también pasó por separado (1 passed in 1.40s).
Dentro del sandbox la misma apertura fallaba: no es evidencia de video dañado.

Las integraciones ejecutan seguimiento, registro, agenda, JPEG, consolidación,
deduplicación y archivos reales. Sustituyen video/detección/OCR para comprobar:

- A contiene temporalmente a B, sin recibir sus lecturas.
- Vehículos simultáneos con placas distintas o con el mismo OCR.
- Área exactamente 40000 y debajo del umbral.
- Evidencia posterior al último candidato de otro vehículo.
- OCR vacío o fallido conserva una foto verificable.
- Escritura/compresión fallida produce error y no checkpoint exitoso.
- Coincidencia de cuadro representativo no mezcla números de lecturas.

La prueba unitaria del límite de agenda también se corrigió: antes su última
observación de 500000 píxeles era candidata OCR y no reproducía lo que afirmaba
el nombre. Ahora incluye un segundo vehículo pequeño cuya evidencia es posterior.
Después del ajuste: **12 pruebas de agenda aprobadas**.

`pyflakes` pasó en módulos productivos modificados y en el script de validación.
`git diff --check` pasó. Los tests sintéticos comprueban funcionamiento, no
exactitud de reconocimiento sobre imágenes de la cámara.

## Método de comparación real

Script reproducible: `scripts/validar_recortes.py`. CPU explícita, mismo video
y detecciones compartidas. Para cada observación elegible se comparan:

1. JPEG del cuadro completo a calidad 92, después recorte con margen.
2. JPEG del recorte con el mismo margen y calidad 92.

Se agregan tres resultados por vehículo: baseline con contención temporal,
identidad corregida con imagen antigua, e identidad corregida con recorte nuevo.
Así se separa el efecto de identidad del de compresión. El programa ejecuta
ambos OCR y no representa el tiempo operativo de una sola variante.

Los bytes de JPEG completo son acumulados como en la caché anterior, pero no
se retienen simultáneamente en este experimento. Los bytes de recortes son el
pico de la caché nueva. No son memoria RSS del proceso. Los tiempos son una
corrida local, con posible variación por carga: no una garantía de aceleración.

## Límites y riesgos que permanecen

- Solo hay dos videos locales (60 y 61). La referencia de 39 vehículos abarca
  horas anteriores; no se puede repetir su recall global con estos archivos.
- La referencia JSON del video 60 contiene cinco vehículos y sentidos, sin
  placas. Igual número de registros o igualdad de OCR no demuestra exactitud.
- El Excel incluye PAC2573 a las 16:24:00 (fila 36), útil para la muestra 61;
  un solo caso tampoco certifica precisión general.
- La evaluación pareada comparte detecciones, no acredita mejoras del detector
  ni prueba por sí sola el conteo final del Excel. Los resultados guardados
  por el script son anteriores a la deduplicación.
- El seguidor y la fusión espacial aún pueden asociar vehículos incorrectos.
  Corregir la contaminación posterior no elimina ese riesgo previo.
- Checkpoints antiguos sin identidad conservan la depuración antigua. Usar
  carpetas de salida nuevas para verificar, sin mezclar variantes.
- Colab, GPU, Drive, reloj, tipo de vehículo y calibración de confianza requieren
  las siguientes etapas del plan. No se afirma que los cinco pasos estén hechos.

La documentación TDD previa conserva resultados históricos. Sus 3.30 GB por
video eran una extrapolación desde 1500 cuadros, no una medición completa, y
el script temporal de aquella medición no estaba versionado.

## Resultados reales: video 60

Comando ejecutado fuera del sandbox:

```sh
.venv312/bin/python scripts/validar_recortes.py 'Camara Placas 2_20260909105651-20260909163038(60).mp4' --out validacion/review_20260914/video60.json
```

Python 3.12.13, OpenCV 5.0.0, ONNX Runtime 1.23.2, macOS x86_64, CPU.
8222 cuadros decodificados hasta EOF; el contenedor declara 8223. Ninguna
trayectoria analizada llega a ese último cuadro discrepante. Se evaluaron
339 observaciones candidatas en cada variante OCR.

| Métrica medida en la corrida pareada | Cuadro completo | Recortes filtrados |
|---|---:|---:|
| Tiempo de compresión/almacenamiento | 158.876 s | 5.242 s |
| Bytes de JPEG acumulados / pico de caché | 1,948,134,697 | 59,502,629 |
| Tiempo OCR de las 339 observaciones | 25.505 s | 24.911 s |

El almacenamiento resultó ~30.3 veces más rápido y usó ~32.7 veces menos
bytes de imágenes en esta corrida. No son factores de aceleración global.
Hubo 51 cuadros con dos detecciones y cinco con tres: incluye concurrencia
real, pero no constituye una evaluación amplia de tráfico denso.
Decodificación consumió 113.457 s y detección 424.097 s. La GPU no participó.
El experimento completo tardó 782.584 s porque ejecuta ambas estrategias,
dos OCR y trabajo de comparación; no es el tiempo de la nueva aplicación.

### Conteo y atribución

Se aplicó la deduplicación del commit original `546ed11` a sus resultados
reconstruidos y la corregida a los nuevos. Resultado: **4 registros antes,
5 después**, frente a cinco vehículos de `validacion/muestra_60.json`.
El original fusionaba camión y camioneta con TAA2204. La contención temporal
aportaba 198 candidatos al camión; sus posiciones propias aportan 113.
Sumando agendas de los cinco vehículos, las llamadas OCR necesarias pasan de
447 a 338 al eliminar observaciones ajenas. Es una cuenta derivada de las
agendas reales; el experimento ejecutó 339 observaciones únicas por variante,
incluyendo una que no pertenece a los cinco registros finales.

Correspondencia de los cinco registros corregidos con la revisión manual,
usando segundos desde 16:17:17 y tolerancia de un segundo:

| Referencia manual | Inicio detectado | Sentido esperado / obtenido |
|---:|---:|---|
| 17 s | 17.565 s | sale / sale |
| 104 s | 104.586 s | entra / entra |
| 114 s | 114.354 s | entra / entra |
| 120 s | 120.142 s | entra / entra |
| 268 s | 268.540 s | entra / entra |

En esta muestra el conteo final reconstruido pasa de 4/5 a 5/5 y los cinco
sentidos coinciden. Es una reconstrucción sobre detecciones reales compartidas,
no una segunda ejecución completa de la aplicación antigua ni del Excel nuevo.

### Placas: resultado mixto, no certificación

Al aislar solo compresión, dos de cinco ganadoras cambian:
PCM7497 → PCM2497 y BI137 → JJ4306. Ambas siguen pendientes de revisión.
TAA2204 sigue validada; su texto no cambia, con 20 apoyos antes y 18 después.
La ganadora del camión cambia de TAA2204 a PCG3981 al corregir identidad,
pero sigue pendiente y no hay etiqueta de placa para ese vehículo en el JSON.

Por tanto, la prueba demuestra mejora de almacenamiento y eliminación de una
pérdida de conteo; **no demuestra que todas las placas sean correctas ni que
la precisión OCR global se conserve**. Puntuación alta y estado pendiente no
deben presentarse como una identificación confirmada.

Datos: `validacion/review_20260914/video60.json` (cada OCR y agregado) y
`validacion/review_20260914/conteo60.json` (deduplicación original/corregida).

## Resultados reales: aplicación completa sobre video 61

```sh
.venv312/bin/python scripts/procesar_lote.py validacion/review_20260914/entrada61 --out-dir validacion/review_20260914/informe61 --acelerador cpu
```

Entrada aislada mediante enlace al archivo original, sin modificarlo. Salida
nueva, sin reusar checkpoints. Ejecución finalizada con código 0; tiempo
informado 7 min 04 s, cuatro registros, cuatro imágenes existentes, cero
registros sin hora y un Excel que se abrió correctamente con cuatro imágenes
incrustadas. El tiempo informado se calcula antes de exportar el Excel; no
es un cronometraje independiente de la exportación.

| Etapa del medidor | Segundos | Porcentaje |
|---|---:|---:|
| Detección, incluyendo movimiento | 290.2 | 68.6 % |
| Decodificación | 106.1 | 25.1 % |
| OCR | 16.2 | 3.8 % |
| Guardar recortes | 3.6 | 0.8 % |

Esta prueba completa confirma que JPEG dejó de ser un coste dominante en esta
ejecución CPU; no prueba el tiempo del lote en Colab. El video declara 8231
cuadros y se decodificaron 8230, igual discrepancia de uno observada en el 60.

### Fallos que la prueba real aún encuentra

1. **PAC2573 → BAC2573.** La fila 36 de la referencia manual contiene PAC2573
   a las 16:24. La aplicación produce BAC2573, confianza 0.949 y consenso
   0.186: queda pendiente. La imagen exportada también permite leer PAC2573.
   El error conocido P/B persiste; una confianza media de 94.9 % no certifica
   una placa correcta. No se corrige sustituyendo B por P indiscriminadamente.
2. **Dos registros de la misma furgoneta.** Las imágenes de v01 (cuadro 1861)
   y v02 (cuadro 1933) muestran la misma furgoneta escolar amarilla, separadas
   por unos 2.9 s. El primer registro propone RR773 y el segundo BAC2573.
   Corrección del diagnóstico (15 de septiembre): el detector admite cajas
   idénticas con etiquetas bus/truck y siembra dos pistas. La prueba unitaria
   reproduce dos trayectorias antes de deduplicar y una después. Este caso
   no exige rediseñar el seguidor ni debilitar la guarda de solapamiento.
   La nueva ejecución y su resultado se documentan en
   [deduplicacion-cajas-20260915.tdd.md](deduplicacion-cajas-20260915.tdd.md).
3. **Tipo deducido por placa sigue siendo incorrecto.** La furgoneta RR773
   aparece como motocicleta; la foto de MZS872 es una moto etiquetada automóvil,
   y PAB6741 es un camión etiquetado automóvil. Esto confirma la necesidad de
   conservar la clase del detector, prevista en el plan, en lugar de usar el
   formato OCR como clasificación física.

No se cambia el OCR ni se introduce una regla de fusión ajustada a esta única
furgoneta como parte de esta revisión: sería un cambio del algoritmo que
requiere evaluación adicional. El punto 2 quedó resuelto posteriormente con
deduplicación de cajas en el detector; los puntos 1 y 3 permanecen abiertos y bloquean
una afirmación de precisión excelente o de conteo universalmente correcto.

La comprobación visual se hizo sobre las cuatro imágenes exportadas. No es
una anotación exhaustiva de todo el video 61 ni demuestra que no haya omitidos.

Evidencia: `validacion/review_20260914/informe61/avance.json`,
`validacion/review_20260914/informe61/placas_lastre.xlsx` y su carpeta `recortes`.
El directorio de revisión también conserva hashes del código y el diff de los
archivos ya versionados. Los módulos/tests nuevos permanecen en el workspace.
