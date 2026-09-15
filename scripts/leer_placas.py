"""Lee la placa de cada vehículo registrado y produce el listado final.

Uso:
    python scripts/leer_placas.py <video> --trayectorias <ruta.json>

Recorre el video una sola vez. En los cuadros que pertenecen a un vehículo
registrado, recorta el vehículo y busca la placa. Todas las lecturas de un
mismo vehículo se consolidan en un único resultado por votación ponderada.
"""

import argparse
import csv
import json
from pathlib import Path
import sys
import time

# Permite ejecutar el script sin instalar el paquete
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from lastre.config import cargar_configuracion, ConfiguracionError
from lastre.deduplicacion import deduplicar_por_placa
from lastre.lectura import Lectura, consolidar_lecturas
from lastre.placa import LectorPlacas, PlacaError, recortar_vehiculo
from lastre.agenda import construir_agenda, ultimo_cuadro_necesario
from lastre.registro import registrar_vehiculos
from lastre.trayectoria import Posicion, Trayectoria
from lastre.video import iterar_cuadros, VideoLecturaError

# Un vehículo demasiado pequeño en pantalla nunca tendrá una placa legible
AREA_MINIMA_PARA_LEER = 40000

COLUMNAS = [
    "registro", "placa", "hora_paso", "tiempo_video", "tipo_vehiculo",
    "sentido", "confianza", "lecturas", "imagen", "estado",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Lee las placas de los vehículos registrados en la vía de lastre.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("video", type=str, help="Ruta al archivo de video.")
    parser.add_argument("--trayectorias", type=str, default="out_v2/trayectorias.json",
                        help="Archivo de trayectorias producido por contar_salidas.py.")
    parser.add_argument("--config", type=str, default="config/zona.json",
                        help="Ruta al archivo de configuración de la zona.")
    parser.add_argument("--out-dir", type=str, default="resultado",
                        help="Directorio donde se escriben el listado y los recortes.")
    parser.add_argument("--fps", type=float, default=24.88,
                        help="Cuadros por segundo del video, para calcular tiempos.")
    parser.add_argument("--hora-inicio", type=str, default="16:17:17",
                        help="Hora real del primer cuadro, leída del reloj del video.")
    parser.add_argument("--umbral", type=float, default=0.75,
                        help="Confianza mínima para dar una placa por validada.")
    parser.add_argument("--minimo-lecturas", type=int, default=2,
                        help="Lecturas coincidentes mínimas para validar una placa.")
    parser.add_argument("--ventana-duplicados", type=int, default=300,
                        help="Cuadros dentro de los cuales dos lecturas iguales son el mismo vehiculo.")
    parser.add_argument("--observaciones-minimas", type=int, default=10,
                        help="Detecciones mínimas para considerar que hubo un vehículo.")
    return parser.parse_args()


def cargar_trayectorias(ruta):
    """Reconstruye las trayectorias desde el archivo del conteo."""
    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    return [
        Trayectoria(
            id=t["id"],
            cuadro_inicio=t["cuadro_inicio"],
            cuadro_fin=t["cuadro_fin"],
            posiciones=tuple(
                Posicion(p["cuadro"], tuple(p["centro"]), tuple(p["caja"]), p["area"])
                for p in t["posiciones"]
            ),
        )
        for t in datos["todas_las_trayectorias"]
    ]


def hora_real(hora_inicio: str, segundos: float) -> str:
    """Suma los segundos transcurridos a la hora del primer cuadro."""
    h, m, s = (int(x) for x in hora_inicio.split(":"))
    total = h * 3600 + m * 60 + s + int(segundos)
    return f"{total // 3600 % 24:02d}:{total // 60 % 60:02d}:{total % 60:02d}"


def tiempo_video(segundos: float) -> str:
    """Posición dentro de la grabación, para poder verificar a mano."""
    return f"{int(segundos) // 60:02d}:{int(segundos) % 60:02d}.{int(segundos * 100) % 100:02d}"


def main():
    args = parse_args()

    try:
        cargar_configuracion(args.config)
    except ConfiguracionError as err:
        print(f"Error de configuración: {err}", file=sys.stderr)
        sys.exit(1)

    ruta_trayectorias = Path(args.trayectorias)
    if not ruta_trayectorias.is_file():
        print(f"No se encontró el archivo de trayectorias: '{ruta_trayectorias}'", file=sys.stderr)
        print("Ejecute primero scripts/contar_salidas.py", file=sys.stderr)
        sys.exit(1)

    dir_salida = Path(args.out_dir)
    dir_recortes = dir_salida / "placas"
    dir_recortes.mkdir(parents=True, exist_ok=True)

    trayectorias = cargar_trayectorias(ruta_trayectorias)
    vehiculos = registrar_vehiculos(
        trayectorias,
        observaciones_minimas=args.observaciones_minimas,
        desplazamiento_minimo=150,
    )

    if not vehiculos:
        print("No hay vehículos registrados en el archivo de trayectorias.")
        sys.exit(0)

    print("=" * 70)
    print("LECTURA DE PLACAS")
    print("=" * 70)
    print(f"Vehículos a procesar: {len(vehiculos)}")

    # Qué observación recortar en cada cuadro. Solo las propias de cada
    # vehículo: asociar por contención temporal le entregaba las de cualquier
    # otro que pasara entretanto.
    agenda = construir_agenda(vehiculos, AREA_MINIMA_PARA_LEER)

    total_candidatos = sum(
        1 for tareas in agenda.values() for t in tareas if t.es_candidato
    )
    total_recortes = sum(len(v) for v in agenda.values())
    print(f"Cuadros a analizar: {len(agenda)} ({total_recortes} recortes, "
          f"{total_candidatos} con lectura)")

    try:
        lector = LectorPlacas()
    except PlacaError as err:
        print(f"Error al iniciar el lector: {err}", file=sys.stderr)
        sys.exit(1)

    lecturas_por_vehiculo = {i: [] for i in range(len(vehiculos))}
    # La evidencia de cada vehículo, para los que no dejen ninguna lectura.
    evidencia_por_vehiculo = {}
    ultimo_cuadro = ultimo_cuadro_necesario(agenda)
    t0 = time.time()
    analizados = 0

    try:
        for numero, cuadro in iterar_cuadros(args.video, hasta_cuadro=ultimo_cuadro):
            pendientes = agenda.get(numero)
            if not pendientes:
                continue

            for tarea in pendientes:
                nombre = f"v{tarea.indice + 1:02d}_f{numero}.jpg"
                ruta_recorte = f"placas/{nombre}"

                # Un solo recorte por observación: recalcularlo por cada placa
                # encontrada repetía el trabajo y reescribía el mismo archivo.
                try:
                    recorte = recortar_vehiculo(cuadro, tarea.caja)
                except PlacaError:
                    continue

                guardado = False

                # La evidencia se guarda sin esperar al OCR: un vehículo sin
                # placa legible sigue necesitando su foto.
                if tarea.es_evidencia:
                    cv2.imwrite(str(dir_recortes / nombre), recorte,
                                [cv2.IMWRITE_JPEG_QUALITY, 95])
                    evidencia_por_vehiculo[tarea.indice] = ruta_recorte
                    guardado = True

                if not tarea.es_candidato:
                    continue

                analizados += 1
                try:
                    # El recorte ya trae el margen del lector: leer_vehiculo lo
                    # aplicaría por segunda vez sobre el cuadro completo.
                    encontradas = lector.leer(recorte)
                except PlacaError:
                    continue

                if encontradas and not guardado:
                    cv2.imwrite(str(dir_recortes / nombre), recorte,
                                [cv2.IMWRITE_JPEG_QUALITY, 95])

                for encontrada in encontradas:
                    lecturas_por_vehiculo[tarea.indice].append(
                        Lectura(
                            cuadro=numero,
                            texto=encontrada.texto,
                            confianza=encontrada.confianza,
                            imagen_recorte=ruta_recorte,
                            confianza_minima=encontrada.confianza_minima,
                        )
                    )

            if analizados % 50 == 0:
                print(f"  {analizados}/{total_candidatos} recortes analizados", flush=True)
    except VideoLecturaError as err:
        print(f"Error al leer el video: {err}", file=sys.stderr)
        sys.exit(1)

    crudos = []
    for indice, vehiculo in enumerate(vehiculos):
        resultado = consolidar_lecturas(
            lecturas_por_vehiculo[indice], args.umbral, args.minimo_lecturas
        )
        crudos.append({
            "cuadro": vehiculo.cuadro_representativo,
            "placa": resultado.placa,
            "sentido": vehiculo.sentido,
            "confianza": resultado.confianza,
            "confianza_minima": resultado.confianza_minima,
            "lecturas": resultado.lecturas_coincidentes,
            "estado": resultado.estado,
            "imagen": resultado.imagen_recorte or evidencia_por_vehiculo.get(indice, ""),
        })

    # Un mismo vehículo puede quedar registrado dos veces cuando el seguimiento
    # lo pierde durante segundos; la placa lo identifica sin ambigüedad.
    finales = deduplicar_por_placa(crudos, ventana_cuadros=args.ventana_duplicados)
    por_cuadro_crudo = {c["cuadro"]: c for c in crudos}

    filas = []
    for indice, final in enumerate(finales):
        segundos = final.cuadro / args.fps
        origen = por_cuadro_crudo.get(final.cuadro, {})
        filas.append({
            "registro": f"V{indice + 1:03d}",
            "placa": final.placa or "",
            "hora_paso": hora_real(args.hora_inicio, segundos),
            "tiempo_video": tiempo_video(segundos),
            "tipo_vehiculo": "",
            "sentido": final.sentido,
            "confianza": f"{final.confianza:.3f}",
            "lecturas": origen.get("lecturas", 0),
            "imagen": final.imagen,
            "estado": final.estado,
        })

    ruta_csv = dir_salida / "placas.csv"
    with open(ruta_csv, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
        escritor.writeheader()
        escritor.writerows(filas)

    print("\n" + "=" * 70)
    print("RESULTADO")
    print("=" * 70)
    for fila in filas:
        placa = fila["placa"] or "(sin placa)"
        print(f"  {fila['registro']}  {fila['hora_paso']}  {fila['sentido']:6s}  "
              f"{placa:10s} conf={fila['confianza']}  {fila['estado']}")
    print("-" * 70)
    print(f"Tiempo: {time.time() - t0:.1f} s")
    print(f"Listado: {ruta_csv}")
    print(f"Recortes: {dir_recortes}")
    print("=" * 70)


if __name__ == "__main__":
    main()
