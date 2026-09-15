"""Comparación pareada de geometría JPEG/OCR sobre detecciones compartidas.

No es un benchmark del tiempo total del lote: comparte detección y ejecuta
ambas variantes OCR en la misma pasada. Incluye toda observación candidata,
sin seleccionar por su resultado. Guarda datos para auditar cada comparación.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from lastre.config import cargar_configuracion
from lastre.deteccion import DetectorMovimiento
from lastre.evidencia import AlmacenRecortes, clave_de
from lastre.lectura import Lectura, consolidar_lecturas
from lastre.placa import LectorPlacas, recortar_vehiculo
from lastre.registro import registrar_vehiculos
from lastre.seguimiento import SeguidorTrayectorias
from lastre.vehiculos import DetectorHibrido, DetectorVehiculos
from lastre.video import iterar_cuadros, obtener_metadatos_video


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--max-cuadros', type=int, default=0)
    args = parser.parse_args()
    config = cargar_configuracion('config/zona.json')
    meta = obtener_metadatos_video(args.video)
    providers = ['CPUExecutionProvider']
    detector = DetectorHibrido(DetectorMovimiento(config, factor_escala=.25),
                              DetectorVehiculos(config, modelo='rf-detr-nano-384-coco',
                                                proveedores=providers), paso=3)
    lector = LectorPlacas(proveedores=providers)
    seguidor = SeguidorTrayectorias(config)
    almacen = AlmacenRecortes()
    tiempos = Counter()
    llamadas = Counter()
    resultados = {'cuadro92': {}, 'recorte92': {}}
    detalle = []
    trayectorias = []
    bytes_antes = 0
    max_bytes_despues = 0
    densidad = Counter()
    inicio = time.perf_counter()
    generador = iterar_cuadros(args.video, hasta_cuadro=args.max_cuadros or None)
    numero = 0
    while True:
        t = time.perf_counter()
        try:
            numero, cuadro = next(generador)
        except StopIteration:
            break
        tiempos['decodificar'] += time.perf_counter() - t
        t = time.perf_counter()
        dets = tuple(d.como_deteccion for d in detector.detectar(cuadro))
        tiempos['detectar'] += time.perf_counter() - t
        t = time.perf_counter()
        trayectorias.extend(seguidor.actualizar(numero, dets))
        tiempos['seguimiento'] += time.perf_counter() - t
        densidad[len(dets)] += 1
        codificado = None
        if dets or seguidor.hay_pistas_activas:
            t = time.perf_counter()
            ok, codificado = cv2.imencode('.jpg', cuadro, [cv2.IMWRITE_JPEG_QUALITY, 92])
            if not ok:
                raise RuntimeError('No se pudo comprimir el cuadro de referencia')
            tiempos['jpeg_cuadro92'] += time.perf_counter() - t
            llamadas['jpeg_cuadro92'] += 1
            bytes_antes += codificado.nbytes
        observaciones = seguidor.observaciones_en_cuadro(numero)
        t = time.perf_counter()
        for pista, pos in observaciones:
            almacen.guardar_observacion(pista, pos, cuadro, 40000)
        tiempos['guardar_recortes92'] += time.perf_counter() - t
        max_bytes_despues = max(max_bytes_despues, almacen.bytes_totales)
        original_jpeg = None
        for _, pos in observaciones:
            if pos.area < 40000:
                continue
            if original_jpeg is None:
                original_jpeg = cv2.imdecode(codificado, cv2.IMREAD_COLOR)
            clave = clave_de(numero, pos.caja)
            entradas = {'cuadro92': recortar_vehiculo(original_jpeg, pos.caja),
                        'recorte92': almacen.obtener(numero, pos.caja)}
            fila = {'cuadro': numero, 'caja': pos.caja}
            # Alternar orden para evitar siempre favorecer la segunda inferencia.
            orden = list(entradas) if numero % 2 else list(reversed(entradas))
            for variante in orden:
                t = time.perf_counter()
                lecturas = lector.leer(entradas[variante])
                tiempos['ocr_' + variante] += time.perf_counter() - t
                llamadas['ocr_' + variante] += 1
                resultados[variante][clave] = [
                    Lectura(numero, l.texto, l.confianza,
                            confianza_minima=l.confianza_minima) for l in lecturas]
                fila[variante] = [asdict(l) for l in lecturas]
            detalle.append(fila)
        if numero % 250 == 0:
            print(f'{numero}/{meta.total_cuadros} cuadros; '
                  f'{time.perf_counter()-inicio:.1f}s; candidatos={len(detalle)}', flush=True)
    trayectorias.extend(seguidor.finalizar())
    vehiculos = registrar_vehiculos(trayectorias, 10, 150)
    resumen = []
    for v in vehiculos:
        fila = {'id': v.trayectoria_id, 'inicio': v.cuadro_inicio,
                'fin': v.cuadro_fin, 'representativo': v.cuadro_representativo,
                'sentido': v.sentido, 'observaciones': v.observaciones}
        propias = [clave_de(p.cuadro, p.caja) for p in v.posiciones if p.area >= 40000]
        anteriores = [clave_de(p.cuadro, p.caja) for tr in trayectorias
                      if v.cuadro_inicio <= tr.cuadro_inicio and tr.cuadro_fin <= v.cuadro_fin
                      for p in tr.posiciones if p.area >= 40000]
        for etiqueta, variante, claves in [('baseline_intervalo', 'cuadro92', anteriores),
                                           ('identidad_corregida', 'cuadro92', propias),
                                           ('recortes_corregidos', 'recorte92', propias)]:
            lecturas = [l for k in claves for l in resultados[variante].get(k, ())]
            fila[etiqueta] = asdict(consolidar_lecturas(lecturas, .75, 2))
            fila[etiqueta]['candidatos'] = len(claves)
        resumen.append(fila)
    import onnxruntime
    informe = {
        'video': str(args.video), 'fps': meta.fps, 'cuadros': numero,
        'revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'nota_revision': 'Incluye cambios locales; conservar git diff junto al informe',
        'python': sys.version, 'plataforma': platform.platform(),
        'opencv': cv2.__version__, 'onnxruntime': onnxruntime.__version__,
        'proveedores_solicitados': providers,
        'segundos_experimento': time.perf_counter()-inicio,
        'segundos_etapas': dict(tiempos), 'llamadas': dict(llamadas),
        'densidad_detecciones_por_cuadro': dict(densidad),
        'bytes_jpeg_cuadros_acumulados': bytes_antes,
        'bytes_recortes_pico': max_bytes_despues,
        'nota_memoria': 'Bytes de imágenes, no RSS. Referencia completa no se retiene.',
        'vehiculos_antes_deduplicacion': resumen, 'ocr_por_observacion': detalle,
        'limite': 'Detecciones compartidas; no mide lote end-to-end ni acredita precisión sin etiquetas.',
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(informe, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in informe.items() if k != 'ocr_por_observacion'},
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
