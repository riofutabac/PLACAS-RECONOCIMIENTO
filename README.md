# Reconocimiento de placas en vía de lastre

Proceso automatizado que, a partir de grabaciones de una cámara de peaje,
identifica los vehículos que circulan por una vía de lastre alterna, determina
su sentido de circulación y lee sus placas, entregando un listado en Excel con
la foto de respaldo de cada registro.

## El problema

Junto al peaje existe una vía alterna de lastre que algunos vehículos usan
para evadir la estación de cobro. La cámara instalada para registrarlos abarca
también la carretera principal, de modo que la grabación mezcla el tránsito de
interés con el que no lo es. Revisar a mano 6 horas y media de video a 25
cuadros por segundo no es viable.

## Cómo funciona

1. **Delimitación.** Un polígono definido en `config/zona.json` acota el
   análisis a la superficie de la vía de lastre. Un semiplano no sirve: incluía
   el cielo y el tramo lejano de la carretera principal.
2. **Detección.** El movimiento actúa como filtro barato y un modelo de
   reconocimiento de objetos confirma que lo detectado es un vehículo. Sin esa
   confirmación, las sombras de la carretera principal se contaban como autos.
3. **Seguimiento.** Cada vehículo se sigue entre cuadros. Las trayectorias que
   se interrumpen y reaparecen cerca se fusionan, para no contar dos veces al
   mismo vehículo.
4. **Sentido.** El desplazamiento horizontal neto distingue a quien entra al
   lastre de quien sale hacia la carretera.
5. **Lectura de placa.** Sobre el recorte del vehículo, nunca sobre el cuadro
   completo, donde la placa es demasiado pequeña para el modelo.
6. **Consolidación.** Las decenas de lecturas de un mismo vehículo se resuelven
   por votación ponderada, se validan contra el formato ecuatoriano y se
   corrigen las confusiones de caracteres según la posición.

## Criterio de confianza

Dentro de una lectura manda el carácter más dudoso, porque una sola letra
equivocada invalida la placa entera. Entre lecturas manda la mejor: basta un
cuadro nítido para dar la placa por buena.

Este criterio nació de un caso real. La placa PCW-2497 se leyó como PCM2497
con 94 % de confianza promedio, pero los dos caracteres equivocados tenían
confianzas de 0,59 y 0,50. El promedio los ocultaba.

## Instalación

Requiere **Python 3.12**. En 3.14 no existe `onnxruntime`.

```bash
python3.12 -m venv .venv312
.venv312/bin/pip install -r requirements.txt
```

## Uso

### Verificar la delimitación de la zona

Antes de procesar, confirme visualmente que el polígono cubre la vía:

```bash
.venv312/bin/python scripts/verificar_zona.py <video> --frame 2697
```

Si la cámara cambió de posición, corrija los vértices en `config/zona.json`.
La geometría es configuración, no código.

### Procesar una carpeta de videos

```bash
.venv312/bin/python scripts/procesar_lote.py <carpeta> --out-dir informe
```

Opciones útiles:

| Opción | Efecto |
|---|---|
| `--solo-salidas` | Registra únicamente los vehículos que salen |
| `--acelerador gpu` | Usa GPU; falla de inmediato si no la encuentra |
| `--limite 3` | Procesa solo los primeros videos, para medir tiempos |
| `--reiniciar` | Ignora el avance guardado y reprocesa todo |
| `--solo-informe` | Regenera el Excel con lo ya procesado |

### Reanudar tras una interrupción

El avance se guarda al terminar cada video. Vuelva a ejecutar el mismo comando
y los videos ya procesados se omiten.

## Resultado

En la carpeta de salida:

- `placas_lastre.xlsx` con una fila por vehículo y su foto incrustada. Las
  filas se colorean según estado: validado, pendiente de revisión o sin placa
  identificable. Una segunda hoja resume los totales del lote.
- `recortes/` con las imágenes sueltas.
- `avance.json` con el estado del procesamiento.

Todo vehículo detectado genera una fila y al menos una imagen, incluso cuando
no expone placa legible. El conteo queda completo aunque la identificación no.

## Ejecutar en Google Colab

Ver [`colab/README.md`](colab/README.md).

## Precisión

Validado contra revisión manual de una muestra de 5 minutos 30 segundos:

| Métrica | Resultado |
|---|---|
| Vehículos detectados | 5 de 5 |
| Sentido correcto | 5 de 5 |
| Vehículos perdidos | 0 |
| Falsos positivos | 0 |

La referencia de esa validación está en `validacion/muestra_60.json`.

## Limitaciones

La precisión depende de la legibilidad de la imagen. Si una placa no se lee a
simple vista en el video, ningún sistema automático la leerá con certeza.

Algunos vehículos circulan sin placa frontal y en el tramo cercano cruzan de
costado, de modo que la lectura se intenta a lo largo de todo el recorrido y
no en un punto fijo.

## Pruebas

```bash
.venv312/bin/pytest -q
```
