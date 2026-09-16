"""Procesa una carpeta completa de videos y entrega un único informe en Excel.

Uso:
    python scripts/procesar_lote.py <carpeta_videos> [--out-dir <ruta>]

Recorre cada video, detecta los vehículos que circulan por la vía de lastre,
determina su sentido, lee su placa y acumula todo en un solo listado con la
foto de respaldo de cada registro incrustada en la fila.
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

# Permite ejecutar el script sin instalar el paquete
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lastre.aceleracion import (AceleracionError, describir, elegir_proveedores,
                                preparar_bibliotecas_gpu, verificar_sesiones)
from lastre.adelanto import cuadros_adelantados
from lastre.checkpoint import Checkpoint
from lastre.config import cargar_configuracion, ConfiguracionError
from lastre.deduplicacion import deduplicar_por_placa
from lastre.agenda import construir_agenda, tareas_por_vehiculo
from lastre.deteccion import DetectorMovimiento
from lastre.evidencia import AlmacenRecortes, EvidenciaError
from lastre.imagenes import guardar_imagen
from lastre.excel import escribir_listado
from lastre.lectura import ESTADO_VALIDADO, Lectura, consolidar_lecturas
from lastre.medicion import Medidor
from lastre.placa import LectorPlacas, PlacaError
from lastre.progreso import Progreso
from lastre.formato_ecuador import TIPO_MOTOCICLETA, tipo_de_placa
from lastre.registro import registrar_vehiculos
from lastre.reloj import RelojError, cargar_plantillas, leer_marca
from lastre.seguimiento import SeguidorTrayectorias
from lastre.vehiculos import (DetectorHibrido, DetectorVehiculos,
                              VehiculoDeteccionError)
from lastre.video import iterar_cuadros, obtener_metadatos_video, VideoLecturaError

EXTENSIONES = (".mp4", ".avi", ".mkv", ".mov")

# Un vehículo demasiado pequeño en pantalla nunca tendrá una placa legible
AREA_MINIMA_PARA_LEER = 40000

# Ventana para considerar que dos lecturas iguales son el mismo vehiculo
VENTANA_DUPLICADOS = 750


def _tipo_de_vehiculo(placa):
    """Deduce el tipo a partir del formato de la placa.

    Las motocicletas usan dos letras y los automoviles tres, de modo que el
    propio formato distingue el tipo sin necesidad de volver a mirar el video.
    """
    if not placa:
        return ""
    tipo = tipo_de_placa(placa)
    if tipo is None:
        return ""
    return "motocicleta" if tipo == TIPO_MOTOCICLETA else "automovil"

# El nombre de archivo de la cámara codifica el inicio de la grabación
PATRON_FECHA = re.compile(r"(\d{14})-(\d{14})")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Procesa una carpeta de videos y genera el listado de placas en Excel.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("carpeta", type=str, help="Carpeta que contiene los videos.")
    parser.add_argument("--out-dir", type=str, default="informe",
                        help="Carpeta donde se escriben el Excel y los recortes.")
    parser.add_argument("--config", type=str, default="config/zona.json",
                        help="Archivo de configuración de la zona.")
    parser.add_argument("--paso", type=int, default=3,
                        help="Confirmar con el modelo 1 de cada N cuadros con movimiento.")
    parser.add_argument("--paso-movimiento", type=int, default=1,
                        help="Buscar movimiento 1 de cada N cuadros. Subirlo acelera mucho.")
    parser.add_argument("--escala-movimiento", type=float, default=0.25,
                        help="Escala del filtro de movimiento. Bajarla acelera mucho.")
    parser.add_argument("--umbral", type=float, default=0.75,
                        help="Confianza mínima para dar una placa por validada.")
    parser.add_argument("--minimo-lecturas", type=int, default=2,
                        help="Lecturas coincidentes mínimas para validar una placa.")
    parser.add_argument("--observaciones-minimas", type=int, default=10,
                        help="Detecciones mínimas para considerar que hubo un vehículo.")
    parser.add_argument("--modelo-vehiculos", type=str, default="rf-detr-nano-384-coco",
                        choices=("rf-detr-nano-384-coco", "yolo26n", "yolo26s"),
                        help="Modelo para la detección de vehículos.")
    parser.add_argument("--hilos", type=int, default=None,
                        help="Número de hilos de cómputo del modelo en CPU (None para automático).")
    parser.add_argument("--disco-local", type=str, default=None,
                        help="Directorio local para copiar y procesar los videos de uno en uno (útil en Colab).")
    parser.add_argument("--lista-videos", type=str, default=None,
                        help="Archivo de texto con la lista de rutas exactas de videos a procesar.")
    parser.add_argument("--solo-salidas", action="store_true",
                        help="Incluir únicamente los vehículos que salen por el lastre.")
    parser.add_argument("--acelerador", choices=("auto", "gpu", "cpu"), default="auto",
                        help="Usar GPU si esta disponible, forzarla, o forzar procesador.")
    parser.add_argument("--reiniciar", action="store_true",
                        help="Ignorar el avance guardado y procesar todos los videos de nuevo.")
    parser.add_argument("--solo-informe", action="store_true",
                        help="No procesar nada: regenerar el Excel con el avance ya guardado.")
    parser.add_argument("--limite", type=int, default=None,
                        help="Procesar solo los primeros N videos (útil para probar).")
    return parser.parse_args()


def listar_videos(carpeta: Path, limite=None):
    """Devuelve los videos de la carpeta en orden alfabético."""
    videos = sorted(v for v in carpeta.iterdir() if v.suffix.lower() in EXTENSIONES)
    return videos[:limite] if limite else videos


def inicio_de_grabacion(nombre: str):
    """Extrae del nombre de archivo la fecha y hora de inicio de la grabación."""
    coincidencia = PATRON_FECHA.search(nombre)
    if not coincidencia:
        return None
    try:
        return datetime.strptime(coincidencia.group(1), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def procesar_video(ruta, config, lector, progreso, args, dir_recortes, proveedores,
                   plantillas_reloj=None, medidor=None, detector_vehiculos=None):
    """Detecta, sigue y lee las placas de un video. Devuelve sus filas."""
    metadatos = obtener_metadatos_video(ruta)
    fps = metadatos.fps or 25.0

    medidor = medidor or Medidor()
    if detector_vehiculos is None:
        detector_vehiculos = DetectorVehiculos(
            config,
            modelo=getattr(args, "modelo_vehiculos", "rf-detr-nano-384-coco"),
            proveedores=proveedores,
            hilos=getattr(args, "hilos", None),
        )
    detector = DetectorHibrido(
        DetectorMovimiento(config, factor_escala=args.escala_movimiento),
        detector_vehiculos,
        paso=args.paso,
        paso_movimiento=args.paso_movimiento,
        medidor=medidor,
    )
    seguidor = SeguidorTrayectorias(config)

    trayectorias = []
    almacen = AlmacenRecortes()
    ultimo_informe = time.time()
    marca_referencia = None

    generador = cuadros_adelantados(
        iterar_cuadros(ruta),
        al_leer=lambda segundos: medidor.anotar("decodificar video", segundos),
    )

    while True:
        try:
            numero, cuadro = next(generador)
        except StopIteration:
            break

        # La hora real proviene del reloj impreso por la camara. El nombre del
        # archivo codifica el rango de toda la grabacion, no el inicio de este
        # fragmento, y usarlo desplazaba cada registro varias horas.
        if plantillas_reloj is not None and marca_referencia is None:
            with medidor.fase("leer reloj"):
                momento = leer_marca(cuadro, plantillas_reloj)
            if momento is not None:
                marca_referencia = (numero, momento)

        detecciones = tuple(d.como_deteccion for d in detector.detectar(cuadro))
        with medidor.fase("seguimiento"):
            trayectorias.extend(seguidor.actualizar(numero, detecciones))

        # Candidatos OCR y mejor evidencia de cada pista, incluso sin placa.
        if detecciones:
            with medidor.fase("guardar recortes"):
                for id_pista, posicion in seguidor.observaciones_en_cuadro(numero):
                    almacen.guardar_observacion(
                        id_pista, posicion, cuadro, AREA_MINIMA_PARA_LEER)

        progreso.avanzar(1)
        if time.time() - ultimo_informe >= 5:
            print(progreso.linea(ruta.name), flush=True)
            ultimo_informe = time.time()

    trayectorias.extend(seguidor.finalizar())

    estadisticas = getattr(detector, "estadisticas", None)
    if estadisticas is not None:
        print("Detector: "
              f"{estadisticas['cuadros_vistos']} cuadros vistos, "
              f"{estadisticas['cuadros_con_movimiento']} con movimiento, "
              f"{estadisticas['cuadros_confirmados']} inferencias de vehículos", flush=True)

    vehiculos = registrar_vehiculos(
        trayectorias,
        observaciones_minimas=args.observaciones_minimas,
        desplazamiento_minimo=150,
    )

    crudos = []

    # La misma seleccion de observaciones que usa el script independiente: solo
    # las propias de cada vehiculo, candidatas a OCR por area y una evidencia.
    agenda = tareas_por_vehiculo(construir_agenda(vehiculos, AREA_MINIMA_PARA_LEER))

    for indice, vehiculo in enumerate(vehiculos):
        if args.solo_salidas and vehiculo.sentido != "sale":
            continue

        lecturas = []
        evidencia = ""

        for tarea in agenda.get(indice, ()):
            recorte = almacen.obtener(tarea.cuadro, tarea.caja)
            if recorte is None:
                raise EvidenciaError(
                    f"Falta el recorte requerido: cuadro {tarea.cuadro}, caja {tarea.caja}")

            coordenadas = "_".join(str(v) for v in tarea.caja)
            nombre = f"{ruta.stem}_v{indice + 1:02d}_f{tarea.cuadro}_{coordenadas}.jpg"
            ruta_recorte = f"recortes/{nombre}"

            # La evidencia se guarda sin esperar al OCR: un vehiculo sin placa
            # legible sigue necesitando su foto para verificarlo a mano.
            guardado = False

            if tarea.es_evidencia:
                guardar_imagen(dir_recortes / nombre, recorte)
                evidencia = ruta_recorte
                guardado = True

            if not tarea.es_candidato:
                continue

            try:
                with medidor.fase("leer placa"):
                    # El recorte ya trae el margen del lector: aplicarlo otra
                    # vez agrandaria la ventana hasta el vehiculo vecino.
                    encontradas = lector.leer(recorte)
            except PlacaError:
                continue

            # Un solo archivo por observacion: escribirlo por cada placa
            # encontrada reescribia el mismo contenido varias veces.
            if encontradas and not guardado:
                guardar_imagen(dir_recortes / nombre, recorte)

            for encontrada in encontradas:
                lecturas.append(Lectura(
                    cuadro=tarea.cuadro,
                    texto=encontrada.texto,
                    confianza=encontrada.confianza,
                    imagen_recorte=ruta_recorte,
                    confianza_minima=encontrada.confianza_minima,
                ))

        resultado = consolidar_lecturas(lecturas, args.umbral, args.minimo_lecturas)
        crudos.append({
            "trayectoria_id": vehiculo.trayectoria_id,
            "cuadro_inicio": vehiculo.cuadro_inicio,
            "cuadro_fin": vehiculo.cuadro_fin,
            "cuadro": vehiculo.cuadro_representativo,
            "placa": resultado.placa,
            "sentido": vehiculo.sentido,
            "confianza": resultado.confianza,
            "consenso": resultado.dominancia,
            "estado": resultado.estado,
            "imagen": resultado.imagen_recorte or evidencia,
            "lecturas": resultado.lecturas_coincidentes,
        })

    # Un vehiculo puede quedar registrado dos veces cuando el seguimiento lo
    # pierde durante segundos. Treinta segundos cubre esas interrupciones sin
    # fusionar vehiculos distintos, que rara vez repiten placa tan seguido.
    finales = deduplicar_por_placa(crudos, ventana_cuadros=VENTANA_DUPLICADOS)
    por_imagen = {c["imagen"]: c for c in crudos if c["imagen"]}

    filas = []
    for final in finales:
        segundos = final.cuadro / fps
        if marca_referencia is not None:
            cuadro_ref, momento_ref = marca_referencia
            hora = (momento_ref + timedelta(seconds=(final.cuadro - cuadro_ref) / fps)
                    ).strftime("%Y-%m-%d %H:%M:%S")
        else:
            hora = ""
        # El consenso debe venir del mismo registro que aporta placa y estado
        origen = por_imagen.get(final.imagen, {})
        filas.append({
            "trayectoria_id": final.trayectoria_id,
            "placa": final.placa or "",
            "hora_paso": hora,
            "tiempo_video": f"{int(segundos) // 60:02d}:{int(segundos) % 60:02d}",
            "video": ruta.name,
            "tipo_vehiculo": _tipo_de_vehiculo(final.placa),
            "sentido": final.sentido,
            "confianza": round(final.confianza, 3),
            "consenso": round(origen.get("consenso", 0.0), 3),
            "lecturas": origen.get("lecturas", 0),
            "estado": final.estado,
            "imagen": final.imagen,
        })

    return filas


def main():
    args = parse_args()

    lista_videos = getattr(args, "lista_videos", None)
    if lista_videos:
        archivo_lista = Path(lista_videos)
        if not archivo_lista.is_file():
            print(f"No existe el archivo de lista de videos: '{archivo_lista}'", file=sys.stderr)
            sys.exit(1)
        videos = [
            Path(line.strip())
            for line in archivo_lista.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        carpeta = Path(args.carpeta) if Path(args.carpeta).is_dir() else (videos[0].parent if videos else Path("."))
        if getattr(args, "limite", None):
            videos = videos[:args.limite]
    else:
        carpeta = Path(args.carpeta)
        if not carpeta.is_dir():
            print(f"No es una carpeta: '{carpeta}'", file=sys.stderr)
            sys.exit(1)
        videos = listar_videos(carpeta, getattr(args, "limite", None))

    try:
        config = cargar_configuracion(args.config)
    except ConfiguracionError as err:
        print(f"Error de configuración: {err}", file=sys.stderr)
        sys.exit(1)

    try:
        proveedores = elegir_proveedores(args.acelerador)
    except AceleracionError as err:
        print(f"Error de aceleracion: {err}", file=sys.stderr)
        sys.exit(1)

    if not videos:
        print(f"No se encontraron videos en '{carpeta}'", file=sys.stderr)
        sys.exit(1)

    dir_salida = Path(args.out_dir)
    dir_recortes = dir_salida / "recortes"
    dir_recortes.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("PROCESAMIENTO DE LOTE")
    print("=" * 78)
    print(f"Carpeta:  {carpeta}")
    print(f"Videos:   {len(videos)}")
    print(f"Computo solicitado: {describir(proveedores)}")
    print("Midiendo duracion total del lote...", flush=True)

    total_cuadros = 0
    for video in videos:
        try:
            total_cuadros += obtener_metadatos_video(video).total_cuadros
        except VideoLecturaError as err:
            print(f"  Aviso: no se pudo leer '{video.name}': {err}", file=sys.stderr)

    if args.solo_informe:
        avance = Checkpoint(dir_salida)
        progreso = Progreso(total_cuadros=total_cuadros, videos_totales=len(videos))
        progreso.avanzar(avance.cuadros_hechos())
        progreso.videos_hechos = sum(1 for v in videos if avance.esta_hecho(v.name))
        todas_las_filas = avance.todas_las_filas()
        _entregar(todas_las_filas, dir_salida, carpeta, videos, total_cuadros, [], progreso)
        return

    try:
        plantillas_reloj = cargar_plantillas()
        print("Reloj: plantillas de digitos cargadas")
    except RelojError as err:
        plantillas_reloj = None
        print(f"Aviso: {err}", file=sys.stderr)
        print("Los registros quedaran sin hora real.", file=sys.stderr)

    # Antes de abrir cualquier sesion: onnxruntime-gpu trae CUDA como wheels de
    # pip y sin anunciarlas la sesion cae a procesador sin decir nada.
    if args.acelerador != "cpu":
        try:
            preparar_bibliotecas_gpu()
        except AceleracionError as err:
            print(f"Error de aceleracion: {err}", file=sys.stderr)
            sys.exit(1)

    try:
        lector = LectorPlacas(proveedores=proveedores, hilos=getattr(args, "hilos", None))
    except PlacaError as err:
        print(f"Error al iniciar el lector de placas: {err}", file=sys.stderr)
        sys.exit(1)

    # Pedir GPU no garantiza obtenerla: si onnxruntime-gpu no casa con la
    # version de CUDA, la sesion cae a procesador sin aviso y el lote corre
    # horas creyendo usar la tarjeta. Solo la sesion dice donde se ejecuta.
    # getattr: los dobles de prueba no exponen sesiones y no deben romper.
    modelos = dict(getattr(lector, "sesiones", {}) or {})
    modelo_vehiculos = getattr(args, "modelo_vehiculos", "rf-detr-nano-384-coco")
    try:
        detector_vehiculos = DetectorVehiculos(
            config, modelo=modelo_vehiculos, proveedores=proveedores,
            hilos=getattr(args, "hilos", None))
        modelos["detector de vehiculos"] = getattr(detector_vehiculos, "sesion", None)
    except VehiculoDeteccionError as err:
        print(f"Error al iniciar el detector de vehiculos: {err}", file=sys.stderr)
        sys.exit(1)

    manifiesto_ejecucion = {
        "modelo_vehiculos": modelo_vehiculos,
        "confianza_minima": 0.5,
        "tamano_entrada": [640, 640] if "yolo" in modelo_vehiculos else [384, 384],
        "paso": args.paso,
        "paso_movimiento": args.paso_movimiento,
        "escala_movimiento": args.escala_movimiento,
        "observaciones_minimas": args.observaciones_minimas,
        "umbral_ocr": args.umbral,
        "minimo_lecturas": args.minimo_lecturas,
    }
    sesion_interna = getattr(detector_vehiculos, "sesion", None)
    peso_hash = getattr(sesion_interna, "peso_hash", None)
    if isinstance(peso_hash, str):
        manifiesto_ejecucion["peso_hash"] = peso_hash

    if args.reiniciar:
        archivo_avance = dir_salida / "avance.json"
        if archivo_avance.is_file():
            archivo_avance.unlink(missing_ok=True)

    try:
        avance = Checkpoint(dir_salida, manifiesto=manifiesto_ejecucion)
    except CheckpointError as err:
        print(f"Error de checkpoint: {err}", file=sys.stderr)
        sys.exit(1)

    progreso = Progreso(total_cuadros=total_cuadros, videos_totales=len(videos))
    progreso.avanzar(avance.cuadros_hechos())
    progreso.videos_hechos = sum(1 for v in videos if avance.esta_hecho(v.name))

    print(f"Cuadros totales: {total_cuadros:,}")
    if avance.videos_hechos:
        print(f"Reanudando: {len(avance.videos_hechos)} videos ya procesados")
    print(f"Avance: {avance.ruta}")
    print("=" * 78, flush=True)

    try:
        todo_bien, informes = verificar_sesiones(modelos, args.acelerador)
    except AceleracionError as err:
        print(f"Error de aceleracion: {err}", file=sys.stderr)
        sys.exit(1)

    print("Computo efectivo:")
    for informe in informes:
        print(f"  {informe}")
    if not todo_bien:
        print("Se pidio GPU y algun modelo quedo en procesador. El lote se "
              "detiene: procesar horas con una medicion enganosa es peor que "
              "fallar de entrada.", file=sys.stderr)
        sys.exit(1)

    fallidos = []
    medidor = Medidor()

    for video in videos:
        if avance.esta_hecho(video.name):
            print(f"\n--- {video.name} (ya procesado, se omite) ---", flush=True)
            progreso.terminar_video()
            continue

        print(f"\n--- {video.name} ---", flush=True)
        ruta_video = video
        temp_dir = None
        disco_local = getattr(args, "disco_local", None)
        if disco_local:
            dir_local = Path(disco_local)
            if not dir_local.is_dir():
                print(f"No existe el directorio local: {dir_local}", file=sys.stderr)
                sys.exit(1)
            espacio_libre = shutil.disk_usage(dir_local).free
            espacio_req = video.stat().st_size + 1024**3
            if espacio_libre < espacio_req:
                print(f"Falta espacio local en {dir_local} para copiar {video.name} "
                      f"({espacio_libre / (1024**2):.1f} MB libres, se requieren {espacio_req / (1024**2):.1f} MB)",
                      file=sys.stderr)
                sys.exit(1)
            print(f"    Copiando a disco local ({dir_local})...", flush=True)
            temp_dir = tempfile.TemporaryDirectory(prefix="lastre-video-", dir=dir_local)
            ruta_video = Path(temp_dir.name) / video.name
            shutil.copy2(video, ruta_video)
            if ruta_video.stat().st_size != video.stat().st_size:
                temp_dir.cleanup()
                raise OSError(f"La copia quedó incompleta: {video.name}")

        try:
            filas = procesar_video(ruta_video, config, lector, progreso, args,
                                   dir_recortes, proveedores, plantillas_reloj, medidor,
                                   detector_vehiculos=detector_vehiculos)
            cuadros = obtener_metadatos_video(ruta_video).total_cuadros
            avance.guardar_video(video.name, filas, cuadros=cuadros)
            print(f"    {len(filas)} vehiculos registrados y guardados", flush=True)
        except (VideoLecturaError, OSError, EvidenciaError) as err:
            fallidos.append((video.name, str(err)))
            print(f"    ERROR: {err}", file=sys.stderr)
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()
            import gc
            gc.collect()
        progreso.terminar_video()
        print(progreso.linea(), flush=True)

    todas_las_filas = avance.todas_las_filas()

    if medidor.etapas:
        print(medidor.informe(), flush=True)

    _entregar(todas_las_filas, dir_salida, carpeta, videos, total_cuadros, fallidos, progreso)


def _segundos_de(tiempo_video):
    """Convierte el texto mm:ss de la columna de tiempo a segundos."""
    try:
        minutos, segundos = str(tiempo_video).split(":")
        return int(minutos) * 60 + int(segundos)
    except (ValueError, AttributeError):
        return None


def _depurar_filas(filas, ventana_segundos=30):
    """Completa el tipo y descarta repeticiones del mismo vehiculo.

    Se aplica tambien sobre lo ya guardado, de modo que regenerar el informe
    corrige registros antiguos sin volver a procesar ningun video.

    Solo se fusionan registros cuya placa esta validada. Una placa dudosa no
    sirve como identidad: en la muestra verificada, un camion cisterna y una
    camioneta que circulaban juntos recibieron la misma placa porque el
    recorte de uno capturo la placa del otro, y fusionarlos borraba un
    vehiculo real del informe.
    """
    depuradas = []
    vistos = {}

    for fila in sorted(filas, key=lambda f: (f.get("video", ""), _segundos_de(f.get("tiempo_video")) or 0)):
        fila = dict(fila)
        if not fila.get("tipo_vehiculo"):
            fila["tipo_vehiculo"] = _tipo_de_vehiculo(fila.get("placa"))

        # Estos registros ya pasaron la deduplicación con intervalos e identidad.
        # Repetirla aquí usando solo placa borraría vehículos coexistentes.
        if fila.get("trayectoria_id") is not None:
            depuradas.append(fila)
            continue

        placa = fila.get("placa")
        segundos = _segundos_de(fila.get("tiempo_video"))
        clave = (fila.get("video"), placa)

        # Sin placa, o con una placa que no se dio por buena, no hay identidad:
        # nunca se descarta, porque perder un vehiculo es peor que dejar un
        # duplicado.
        if fila.get("estado") != ESTADO_VALIDADO:
            depuradas.append(fila)
            continue

        if placa and segundos is not None and clave in vistos:
            if segundos - vistos[clave] <= ventana_segundos:
                vistos[clave] = segundos
                continue

        if placa and segundos is not None:
            vistos[clave] = segundos
        depuradas.append(fila)

    return depuradas


def _entregar(todas_las_filas, dir_salida, carpeta, videos, total_cuadros, fallidos, progreso):
    """Ordena los registros, arma el resumen y escribe el Excel final."""
    todas_las_filas = _depurar_filas(todas_las_filas)
    todas_las_filas.sort(key=lambda f: (f["hora_paso"] or "", f["video"]))
    for numero, fila in enumerate(todas_las_filas, start=1):
        fila["registro"] = f"V{numero:04d}"

    validados = sum(1 for f in todas_las_filas if f["estado"] == "validado")
    sin_placa = sum(1 for f in todas_las_filas if f["estado"] == "sin placa identificable")
    salidas = sum(1 for f in todas_las_filas if f["sentido"] == "sale")
    entradas = sum(1 for f in todas_las_filas if f["sentido"] == "entra")
    indeterminados = sum(1 for f in todas_las_filas if f["sentido"] == "indeterminado")
    sin_hora = sum(1 for f in todas_las_filas if not f.get("hora_paso"))

    resumen = {
        "Carpeta procesada": str(carpeta),
        "Videos procesados": len(videos) - len(fallidos),
        "Videos con error": len(fallidos),
        "Cuadros analizados": total_cuadros,
        "Vehiculos registrados": len(todas_las_filas),
        "Vehiculos que salen": salidas,
        "Vehiculos que entran": entradas,
        "Sentido indeterminado": indeterminados,
        "Registros sin hora real": sin_hora,
        "Placas validadas": validados,
        "Pendientes de revision": len(todas_las_filas) - validados - sin_placa,
        "Sin placa identificable": sin_placa,
        "Tiempo total": progreso.linea().split("transcurrido")[1].split("falta")[0].strip(),
        "Generado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    ruta_excel = dir_salida / "placas_lastre.xlsx"
    escribir_listado(todas_las_filas, ruta_excel, dir_salida, resumen=resumen)

    print("\n" + "=" * 78)
    print("INFORME FINAL")
    print("=" * 78)
    for clave, valor in resumen.items():
        print(f"  {clave:26s} {valor}")
    if fallidos:
        print("\n  Videos con error:")
        for nombre, error in fallidos:
            print(f"    - {nombre}: {error}")
    print("-" * 78)
    print(f"  Excel: {ruta_excel}")
    print("=" * 78)


if __name__ == "__main__":
    main()
