# Contexto y problemas abiertos

Documento de traspaso. Describe el estado del proyecto y los problemas
pendientes. No propone implementaciones.

## Qué se está resolviendo

Junto al peaje de Pintag existe una vía alterna de lastre por la que algunos
vehículos evaden el cobro. Hay **dos cámaras** en extremos opuestos de una vía
de doble sentido, y el recorrido entre ambas toma de 10 a 15 minutos.

- **Cámara ANPR**: ya entrega placa, tipo de vehículo y hora en un CSV. 1.756
  capturas del 2026-09-09, que corresponden a 787 pasos reales de vehículo.
- **Cámara del lastre**: solo entrega video. 63 archivos de 5,5 minutos que
  cubren de 10:56 a 16:30. Es la que este proyecto procesa.

El objetivo es cuantificar la evasión y su costo. Tarifas: camión de 4 a 6
dólares, automóvil y motocicleta 1 dólar.

## Cómo funciona hoy el proceso

1. Un polígono configurable acota el análisis a la superficie del lastre y
   excluye la franja del reloj impreso en el cuadro.
2. Un filtro de movimiento barato señala dónde mirar.
3. Un modelo de objetos confirma que lo detectado es un vehículo, lo que
   elimina las sombras. Se exige que el punto de contacto con el suelo caiga
   dentro del polígono.
4. Se sigue cada vehículo entre cuadros y se determina su sentido por el
   desplazamiento horizontal neto.
5. La placa se lee sobre el recorte del vehículo, nunca sobre el cuadro
   completo, donde el modelo no la encuentra. Decenas de lecturas por vehículo
   se consolidan por votación ponderada.
6. La hora real se obtiene del reloj que la cámara imprime sobre la imagen.
7. Se entrega un Excel con la foto de respaldo de cada registro.

## Verdad de referencia

`validacion/revision_manual_bypass_pintag.xlsx` contiene **39 vehículos
verificados a mano**, con placa, tipo, horas de ambas cámaras y número de ejes.
Es la única referencia fiable para saber si un cambio mejora o empeora.

De esos 39, **29 son camiones**. La proporción de camiones domina el cálculo
económico.

## Estado medido

| Métrica | Valor |
|---|---|
| Vehículos detectados por el proceso | 223 |
| Recall contra el informe humano | 90 % (35 de 39) |
| Con placa exacta | 29 |
| Con un carácter distinto | 6 |
| No encontrados | 4, todos camiones |
| Placas validadas | 78 de 223 |
| Tiempo de proceso | 2 h 30 min para los 63 videos |

## Problemas abiertos, de mayor a menor impacto

### 1. El seguimiento une vehículos que circulan juntos

Corrompe dos cosas a la vez: pierde vehículos del conteo y le asigna a uno la
placa de otro. Confirmado en la muestra verificada, donde un camión cisterna y
una camioneta que iban a la par quedaron como un solo registro con el doble de
lecturas de lo normal.

Contamina todo lo demás: un conteo bajo subestima la pérdida y una placa mal
atribuida ensucia el cruce entre cámaras.

El seguimiento admite hasta 400 píxeles de desplazamiento entre cuadros para
considerar que es el mismo vehículo, sobre una imagen de 2960 de ancho.

Invalida datos ya producidos. Exige reprocesar.

### 2. Faltan 71 horas de 17 videos

Un tercio de los registros no tiene hora real porque la lectura del reloj falla
en esos videos, y en ellos falla siempre, nunca a medias. La sospecha es la luz
del mediodía sobre el texto blanco de la marca.

Sin hora, esos registros quedan fuera del cruce entre cámaras, que depende de
la ventana de tiempo. Por eso solo se cruzaron 142 de 223.

### 3. No se guarda el tipo de vehículo

El modelo ya distingue camión, bus, automóvil y motocicleta en cada detección,
pero ese dato se descarta. El tipo del informe se deduce del formato de placa,
que separa motos de automóviles pero nunca reconoce un camión.

Es lo que impide dar una cifra de pérdida en lugar de un rango de 1.100 a 1.800
dólares diarios.

### 4. Confusiones sistemáticas de caracteres

Seis de los 39 vehículos se leyeron con un carácter distinto al real:

| Real | Lectura del sistema |
|---|---|
| PAD2161 | PAD2141 |
| PAB7882 | PAB7862 |
| PAZ1513 | PAE1513 |
| TBF2754 | TBG2754 |
| PAC2573 | BAC2573 |
| IBB5477 | IEB5477 |

La primera letra es el punto más débil, casi siempre una P leída como B, F o I.
Corregir estas confusiones no exige reprocesar video.

### 5. El cruce entre cámaras produce falsos emparejamientos largos

De 54 correspondencias de placa, 17 superan la hora y 7 las dos horas, con
casos de hasta 297 minutos. El informe humano registra solo 4 por encima de la
hora. La mayoría de los emparejamientos largos son coincidencias casuales de
placas parecidas.

No se pueden descartar todos por regla: el informe humano incluye un caso
legítimo de 222 minutos.

### 6. Hay 59 registros con sentido indeterminado

Uno de cada cuatro. Son vehículos que maniobraron o se detuvieron dentro de la
zona sin un desplazamiento horizontal claro.

### 7. El proceso tarda dos horas y media

La medición por etapas mostró que el tiempo se reparte casi mitad y mitad entre
decodificar el video y el filtro de movimiento. El modelo de objetos, y por
tanto la GPU, apenas participa: en un video sin tránsito no corre ni una vez.

Dentro del filtro, la sustracción de fondo consume 11 de los 17 milisegundos
por cuadro.

Las palancas disponibles para acelerar sacrifican sensibilidad, de modo que
conviene medirlas contra la verdad de referencia antes de adoptarlas.

### 8. Dos videos dañados

De 63, dos no se pudieron abrir por estar incompletos. Queda constando en el
informe.

## Restricciones a tener en cuenta

- El entorno exige **Python 3.12**. En 3.14 no existe `onnxruntime`.
- En Google Colab hay que fijar `onnxruntime-gpu==1.22.0`. Las versiones más
  nuevas exigen CUDA 13 y Colab trae CUDA 12: cargan mal y el proceso cae a
  procesador sin avisar.
- Los videos deben leerse **en secuencia**. Saltar a un cuadro concreto
  devuelve cuadros equivocados en estos archivos.
- El avance se guarda al terminar cada video, de modo que una desconexión es
  una pausa y no una pérdida.
