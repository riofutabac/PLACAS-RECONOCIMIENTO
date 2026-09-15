# Diagnóstico de rendimiento y fiabilidad

Actualización 2026-09-14: el usuario aportó un perfil CPU de 1500 cuadros y
confirmó apertura de los videos con .venv312. El orden de ejecución de este
diagnóstico queda sustituido por [el plan ECC](plans/base-rapida-fiable.md):
primero posiciones propias y recortes JPEG, con medición acotada al cambio.
Las cifras aportadas y sus límites están documentados allí. No se mantiene
la conservación de IDs miembros como solución preferida: devolver las
posiciones ya ensambladas es más directo.

Revisión del código local: 14 de septiembre de 2026. Alcance: procesamiento
por lote, cuaderno Colab, detección, seguimiento, OCR, reloj y consolidación.
No se modificó el algoritmo. Las más de seis horas reportadas por el usuario
son la referencia actual; las 2 h 30 min de CONTEXTO.md no se han reproducido.

## Conclusión

Hay trabajo evitable y fallos de identidad que afectan simultáneamente tiempo
y precisión. Activar GPU no acelera automáticamente lectura de archivos,
decodificación, MOG2, JPEG ni escrituras. No hay evidencia suficiente para
atribuir un porcentaje de las seis horas a cada componente.

## Hallazgos comprobados en código

1. **Opciones de aceleración desconectadas.** `scripts/procesar_lote.py:124`
   fija escala 0.25 y no pasa `paso_movimiento`. Los argumentos
   `--escala-movimiento` y `--paso-movimiento` se aceptan pero no afectan al
   detector. `--paso` solo reduce confirmaciones del modelo: no evita
   decodificar ni ejecutar movimiento sobre cada cuadro.
2. **Movimiento sobre todos los cuadros.** `lastre/deteccion.py`,
   `DetectorMovimiento.detectar`, reduce la imagen completa y ejecuta MOG2
   antes de aplicar la máscara. Excluir zonas mediante máscara no elimina
   su coste previo. A la resolución configurada, MOG2 trabaja sobre 740×416.
   Reducir frecuencia o región es un experimento pendiente, no una mejora
   garantizada: puede afectar motos, vehículos lejanos y detenciones.
3. **JPEG completo por cuadro activo.** `scripts/procesar_lote.py:160`
   comprime imágenes de 2960×1664 mientras hay pistas, incluso en cuadros
   sin detecciones. Conserva todos esos JPEG hasta acabar el video. El OCR
   solo consulta cuadros con posiciones: parte de ese almacenamiento nunca
   se usa. Después decodifica de nuevo la imagen completa por posición.
4. **OCR sin selección ni presupuesto por vehículo.** Desde la línea 190 se
   leen todas las posiciones con área >= 40000. No se filtra por nitidez,
   visibilidad de placa o diversidad temporal; tampoco hay parada temprana.
   Se escribe un recorte por lectura, aunque el informe escoja una evidencia.
   El cuaderno usa Drive directamente para entrada y salida: su contribución
   real al tiempo debe medirse frente a almacenamiento local de Colab.
5. **La identidad se sustituye por contención temporal.** Líneas 186–189:
   cada vehículo recoge cualquier trayectoria contenida en su intervalo.
   Reproducción sintética ejecutada: A ocupa cuadros 1–100 y B 20–80;
   A recibe [A,B] para OCR y B recibe [B]. Esto mezcla evidencia y repite OCR,
   incluso si el seguidor había mantenido correctamente las identidades.
   Hay que conservar todos los IDs miembros de cada grupo de continuaciones.
6. **Asociación espacial frágil.** `lastre/seguimiento.py` asocia por menor
   distancia al último centro, con radio de 400 px, sin predicción de
   movimiento, tamaño, solapamiento ni clase. `lastre/registro.py` fusiona
   continuaciones con el primer grupo cercano admisible. Son riesgos de
   intercambio de identidad; su incidencia real exige casos etiquetados.
7. **Deduplicación de placas pendientes.** `lastre/deduplicacion.py` fusiona
   por placa y ventana sin exigir estado validado ni comprobar coexistencia.
   Se ejecuta antes de `_depurar_filas`, cuya protección para pendientes
   llega demasiado tarde para recuperar registros eliminados.
8. **Reintentos de reloj ilimitados.** Líneas 149–153: se intenta cada cuadro
   hasta obtener una fecha. Si falla todo el video, se repite miles de veces.
   La primera fecha sintácticamente válida se acepta sin corroboración
   temporal; las utilidades de coherencia no se usan aquí. Conviene espaciar
   intentos y confirmar varias anclas, preservando registros sin hora cuando
   no exista evidencia fiable.
9. **GPU sin verificación en el lote.** El código tiene
   `confirmar_gpu_activa`, pero este script no la llama. Comprueba proveedores
   disponibles, no las sesiones efectivas de los tres modelos. El cuaderno
   comprueba un detector separado, no las sesiones del proceso posterior.
   Además, el detector de vehículos se crea de nuevo por video; el lector
   de placas sí se reutiliza. No está probado que haya caída a CPU en la
   ejecución del usuario: falta el registro de esa sesión.
10. **Perfil incompleto.** La etapa «detectar vehiculos» agrupa movimiento e
    inferencia. Decodificar JPEG y escribir recortes quedan sin atribución
    específica. El informe temporal se imprime antes de generar el Excel;
    la carga inicial del lector precede al medidor. Faltan métricas por video,
    intentos OCR, memoria máxima y coste de transferencias.
11. **Confianza sin calibración empírica.** `lastre/lectura.py` valida con
    promedio, apoyos, mejor mínimo por carácter y dominancia. Dos lecturas
    próximas no son evidencia independiente. Un error sistemático puede
    repetirse con alta puntuación. «0.95» no demuestra un 95 % de aciertos.
12. **Pérdida de información útil.** `como_deteccion` elimina clase y
    confianza del vehículo; el informe deduce tipo por placa. No permite
    clasificar camiones de forma fiable. Cuando no hay lectura aprovechable,
    `_sin_placa` deja imagen vacía: no se cumple la evidencia por cada vehículo
    prometida en README. El recorte del OCR puede contener varias placas y
    todas se agregan sin resolver a qué vehículo pertenecen.

## Base propuesta

Mantener una lectura secuencial y desacoplar sus etapas con colas acotadas:
decodificación → detección económica → seguimiento con identidad persistente
→ selección de recortes originales → OCR selectivo → evento y evidencia.

- Conservar resolución original para las placas y trabajar con imágenes
  reducidas para localizar vehículos. Guardar pocos candidatos por pista,
  con margen y calidad suficiente; no recomprimir todo el cuadro para OCR.
- Seleccionar candidatos por calidad y separación temporal. Aumentar intentos
  cuando haya desacuerdo y finalizar cuando la evidencia sea suficiente,
  utilizando umbrales calibrados. Conservar los casos ambiguos para revisión.
- Separar «cuadro no evaluado» de «evaluado sin detección». El seguidor actual
  recibe vacío en ambos casos y acumula ausencias. Al reducir frecuencia deben
  ajustarse tolerancias y observaciones mínimas en función del tiempo real.
- Cargar modelos una vez y verificar cada sesión. Evaluar procesamiento por
  lotes de recortes después de eliminar trabajo redundante. No lanzar muchos
  procesos por defecto: pueden competir por CPU, GPU, memoria y Drive.
- En Colab, ensayar copia de un video a disco local, procesamiento y publicación
  de evidencia/checkpoint al acabar, con recuperación verificada. Medir copia
  incluida, capacidad de disco y persistencia; no trasladar simplemente toda
  la salida a almacenamiento efímero.
- Mantener trazabilidad: identidad, cuadros, cajas, clase, lecturas originales,
  motivo de descarte y versión de configuración. El checkpoint debe distinguir
  configuraciones; hoy omitir por nombre puede reutilizar resultados antiguos
  durante una comparación de parámetros.

## Orden de ejecución y aceptación

1. Instrumentar tiempos independientes de lectura, movimiento, inferencias,
   JPEG, escrituras, carga de modelos, checkpoint y Excel; guardar hardware,
   proveedores efectivos, versiones, parámetros y revisión del código.
2. Corregir identidad temporal y deduplicación; agregar pruebas de dos
   vehículos simultáneos y continuaciones. Garantizar una foto sin OCR.
3. Eliminar JPEG y OCR redundantes, reutilizar modelos y limitar reintentos
   del reloj. Comparar exactamente los mismos videos antes y después.
4. Conectar parámetros y evaluar frecuencias/escalas conjuntamente con el
   seguimiento; después ensayar almacenamiento local y concurrencia acotada.
5. Mejorar seguimiento y calibrar confianza con datos separados de los usados
   para ajustar reglas. Evaluar el lote completo tras aprobar la muestra.

El conjunto de 39 vehículos sirve como regresión inicial, pero no demuestra
precisión general ni permite medir todos los falsos positivos del lote sin
anotar exhaustivamente segmentos. Incluir escenas vacías, camiones juntos,
motos, detenciones, oclusiones, límites de archivo y relojes fallidos.

Medir recall y precisión de conteo, placa exacta por vehículo, porcentaje
correcto entre autoaceptados, cobertura automática, intercambios de identidad,
tipo, sentido, hora, memoria y tiempo total. Reportar camiones por separado.
No aceptar más velocidad si baja el conteo fiable o aumenta la atribución
incorrecta; registrar siempre cobertura junto con precisión.

Definir rapidez como tiempo de proceso/duración efectiva de video. Objetivo
inicial propuesto: factor <=1 en hardware definido; siguiente experimento
<=0.25 conservando calidad. Son metas, no resultados ni estimaciones. Para
operación en vivo medir también latencia desde el paso hasta el evento.

## Cámara sencilla

El diseño debe desacoplarse de la geometría fija y del reloj impreso. Con una
fuente en vivo, conservar marcas temporales de captura y sincronización.
Probar datos reales de la cámara candidata en día/noche y con movimiento:
tamaño visible de placa, exposición, compresión y ángulo limitan la información
disponible. Contar un vehículo e identificar su placa son capacidades distintas.
Una placa ilegible debe poder producir un conteo fiable sin inventar identidad.
No se puede prometer lectura excelente con cualquier cámara a partir de esta
muestra; primero debe definirse el rango de captura que el sistema soporta.

## Verificación realizada y límites

- Pruebas existentes: **222 aprobadas, 1 fallida**, en 9.37 s.
- Fallo: `tests/test_video.py::test_video_real_metadatos_y_lectura`;
  OpenCV no pudo abrir el archivo local (60). No se diagnosticó su causa.
- Reproducción sintética: confirmada contaminación temporal de trayectorias.
- Se intentó medir 250 cuadros locales, pero no se decodificó ninguno. Los
  ceros impresos por ese intento no constituyen una medición válida.
- No se ejecutaron los 63 videos ni se accedió al entorno Colab del usuario.
  No se atribuyen porcentajes ni aceleraciones sin ese perfil.
