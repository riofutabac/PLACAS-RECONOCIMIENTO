"""Integración de las dos entradas con video/modelos sustituidos.

Se conservan seguimiento, registro, agenda, JPEG, consolidación, deduplicación y archivos
reales. Estos tests verifican asociación y evidencia, no exactitud del OCR.
"""

import csv
from collections import Counter
from pathlib import Path
from types import SimpleNamespace as NS

import cv2
import numpy as np
import pytest

from lastre.deteccion import Deteccion
from lastre.placa import PlacaError
from lastre.trayectoria import Posicion, Trayectoria
from scripts import leer_placas, procesar_lote


def trayectoria(id_, cuadros, y, area=40000):
    posiciones = tuple(
        Posicion(n, (80 + i * 90, y + 100), (30 + i * 90, y, 200, 200), area)
        for i, n in enumerate(cuadros)
    )
    return Trayectoria(id_, cuadros[0], cuadros[-1], posiciones)


class LectorEspia:
    def __init__(self, modo="placas"):
        self.modo = modo
        self.vistos = []

    def leer(self, recorte):
        valor = int(recorte[recorte.shape[0] // 2, recorte.shape[1] // 2, 0])
        self.vistos.append(valor)
        if self.modo == "error":
            raise PlacaError("lectura fallida simulada")
        if self.modo == "vacio":
            return []
        return [NS(texto="PBA1234" if valor < 100 else "PBC5678",
                   confianza=0.99, confianza_minima=0.99)]


def ejecutar(entrada, monkeypatch, tmp_path, trayectorias, lector):
    ultimo = max(t.cuadro_fin for t in trayectorias)
    detecciones = {}
    cuadros = {}
    for numero in range(1, ultimo + 1):
        imagen = np.zeros((1000, 900, 3), np.uint8)
        detecciones[numero] = []
        for t in trayectorias:
            for p in t.posiciones:
                if p.cuadro != numero:
                    continue
                x, y, w, h = p.caja
                imagen[y:y+h, x:x+w] = 40 if t.id == 1 else 180
                detecciones[numero].append(Deteccion(p.caja, p.area, p.centro))
        cuadros[numero] = imagen

    visitados = []
    def video(*args, hasta_cuadro=None, **kwargs):
        for numero, imagen in cuadros.items():
            if hasta_cuadro is not None and numero > hasta_cuadro:
                break
            visitados.append(numero)
            yield numero, imagen

    args = NS(paso=3, paso_movimiento=1, escala_movimiento=0.25,
              observaciones_minimas=2, solo_salidas=False, umbral=0.75,
              minimo_lecturas=2, ventana_duplicados=300, fps=25,
              hora_inicio="16:00:00", config="unused", video="unused.mp4",
              out_dir=str(tmp_path))

    if entrada == "lote":
        class Detector:
            def __init__(self, *a, **kw):
                self.numero = 0
            def detectar(self, imagen):
                self.numero += 1
                return [NS(como_deteccion=d) for d in detecciones[self.numero]]

        monkeypatch.setattr(procesar_lote, "DetectorMovimiento", lambda *a, **k: None)
        monkeypatch.setattr(procesar_lote, "DetectorVehiculos", lambda *a, **k: None)
        monkeypatch.setattr(procesar_lote, "DetectorHibrido", Detector)
        monkeypatch.setattr(procesar_lote, "obtener_metadatos_video", lambda p: NS(fps=25))
        monkeypatch.setattr(procesar_lote, "iterar_cuadros", video)
        destino = tmp_path / "recortes"
        destino.mkdir()
        filas = procesar_lote.procesar_video(
            Path("video.mp4"), NS(seguimiento=NS(distancia_maxima=200, tolerancia_oclusion=1)), lector,
            NS(avanzar=lambda n: None, linea=lambda n: ""), args, destino, (),
        )
    else:
        archivo = tmp_path / "trayectorias.json"
        archivo.write_text("{}")
        args.trayectorias = str(archivo)
        monkeypatch.setattr(leer_placas, "parse_args", lambda: args)
        monkeypatch.setattr(leer_placas, "cargar_configuracion", lambda p: None)
        monkeypatch.setattr(leer_placas, "cargar_trayectorias", lambda p: trayectorias)
        monkeypatch.setattr(leer_placas, "LectorPlacas", lambda: lector)
        monkeypatch.setattr(leer_placas, "iterar_cuadros", video)
        leer_placas.main()
        with (tmp_path / "placas.csv").open(encoding="utf-8-sig") as f:
            filas = list(csv.DictReader(f))
    return filas, visitados


@pytest.mark.parametrize("entrada", ["lote", "independiente"])
def test_identidad_contenida_y_simultanea_en_ambas_entradas(entrada, monkeypatch, tmp_path):
    # B está íntegramente dentro del intervalo de A; comparten cuadros 2 y 3.
    trayectorias = [trayectoria(1, [1, 2, 3, 4], 30), trayectoria(2, [2, 3], 350)]
    lector = LectorEspia()
    filas, _ = ejecutar(entrada, monkeypatch, tmp_path, trayectorias, lector)
    assert Counter(lector.vistos) == {40: 4, 180: 2}
    por_placa = {f["placa"]: f for f in filas}
    assert set(por_placa) == {"PBA1234", "PBC5678"}
    assert int(por_placa["PBA1234"]["lecturas"]) == 4
    assert int(por_placa["PBC5678"]["lecturas"]) == 2
    for placa, valor in [("PBA1234", 40), ("PBC5678", 180)]:
        imagen = cv2.imread(str(tmp_path / por_placa[placa]["imagen"]))
        assert imagen is not None
        assert abs(int(imagen[imagen.shape[0] // 2, imagen.shape[1] // 2, 0]) - valor) <= 2


@pytest.mark.parametrize("entrada", ["lote", "independiente"])
@pytest.mark.parametrize("modo", ["vacio", "error"])
def test_evidencia_sin_ocr_y_posterior_al_ultimo_candidato(entrada, modo, monkeypatch, tmp_path):
    trayectorias = [trayectoria(1, [1, 2], 30), trayectoria(2, [5, 6], 650, area=39999)]
    lector = LectorEspia(modo)
    filas, visitados = ejecutar(entrada, monkeypatch, tmp_path, trayectorias, lector)
    assert len(filas) == 2
    assert lector.vistos == [40, 40]
    assert max(visitados) >= 5
    for fila in filas:
        assert not fila["placa"]
        assert fila["imagen"]
        assert cv2.imread(str(tmp_path / fila["imagen"])) is not None


@pytest.mark.parametrize("entrada", ["lote", "independiente"])
def test_fallo_escritura_no_produce_resultado_exitoso(entrada, monkeypatch, tmp_path):
    monkeypatch.setattr(cv2, "imwrite", lambda *a, **k: False)
    if entrada == "lote":
        with pytest.raises(OSError, match="guardar"):
            ejecutar(entrada, monkeypatch, tmp_path, [trayectoria(1, [1, 2], 30)], LectorEspia("vacio"))
    else:
        with pytest.raises(SystemExit) as error:
            ejecutar(entrada, monkeypatch, tmp_path, [trayectoria(1, [1, 2], 30)], LectorEspia("vacio"))
        assert error.value.code == 1
        assert not (tmp_path / "placas.csv").exists()


@pytest.mark.parametrize("entrada", ["lote", "independiente"])
def test_lecturas_de_vehiculos_con_misma_representante(entrada, monkeypatch, tmp_path):
    trayectorias = [trayectoria(1, [1, 2, 3, 4], 30), trayectoria(2, [1, 2], 350)]
    filas, _ = ejecutar(entrada, monkeypatch, tmp_path, trayectorias, LectorEspia())
    assert {f["placa"]: int(f["lecturas"]) for f in filas} == {
        "PBA1234": 4, "PBC5678": 2}


def test_fallo_compresion_no_se_oculta_en_lote(monkeypatch, tmp_path):
    from lastre.evidencia import EvidenciaError
    monkeypatch.setattr(cv2, "imencode", lambda *a, **k: (False, None))
    with pytest.raises(EvidenciaError, match="comprimir"):
        ejecutar("lote", monkeypatch, tmp_path,
                 [trayectoria(1, [1, 2], 30)], LectorEspia())


@pytest.mark.parametrize("entrada", ["lote", "independiente"])
def test_igual_ocr_no_borra_vehiculos_simultaneos(entrada, monkeypatch, tmp_path):
    class LectorIgual:
        def leer(self, recorte):
            return [NS(texto="PBA1234", confianza=0.99, confianza_minima=0.99)]
    trayectorias = [trayectoria(1, [1, 2, 3, 4], 30), trayectoria(2, [1, 2], 350)]
    filas, _ = ejecutar(entrada, monkeypatch, tmp_path, trayectorias, LectorIgual())
    assert len(filas) == 2
    if entrada == "lote":
        assert len(procesar_lote._depurar_filas(filas)) == 2
    assert sorted(int(f["lecturas"]) for f in filas) == [2, 4]
