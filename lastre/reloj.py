"""Lectura del reloj que la cámara graba sobre cada cuadro.

El nombre del archivo no sirve para fechar un registro: codifica el rango de
toda la grabación, no el inicio de cada fragmento. El reloj impreso en la
esquina superior del cuadro es la única fuente confiable de la hora real.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from pathlib import Path
from typing import Optional, Tuple

import numpy as np


class RelojError(ValueError):
    """Excepción lanzada cuando el reloj del cuadro no puede leerse."""


# La cámara imprime la marca como DD/MM/AAAA HH:MM:SS en la esquina superior
PATRON = re.compile(r"(\d{2})[/\-](\d{2})[/\-](\d{4})\s+(\d{2})\s*:\s*(\d{2})\s*:\s*(\d{2})")

# Fracción del cuadro donde vive la marca: banda superior, mitad derecha
FRANJA_ALTO = 0.06
FRANJA_IZQUIERDA = 0.55


@dataclass(frozen=True)
class MarcaTemporal:
    """Fecha y hora leídas de un cuadro, con el número de cuadro de origen."""
    cuadro: int
    momento: datetime

    def en_cuadro(self, numero: int, fps: float) -> datetime:
        """Extrapola la hora de otro cuadro a partir de esta referencia."""
        if fps <= 0:
            raise RelojError(f"fps debe ser positivo, se recibió: {fps}")
        return self.momento + timedelta(seconds=(numero - self.cuadro) / fps)


def recortar_franja_reloj(cuadro: np.ndarray) -> np.ndarray:
    """Extrae la zona del cuadro donde la cámara imprime la fecha y hora."""
    if not isinstance(cuadro, np.ndarray):
        raise RelojError(f"El cuadro debe ser un numpy.ndarray, se recibió: {type(cuadro).__name__}")

    alto, ancho = cuadro.shape[:2]
    y2 = max(1, int(alto * FRANJA_ALTO))
    x1 = int(ancho * FRANJA_IZQUIERDA)
    return cuadro[0:y2, x1:ancho].copy()


def interpretar(texto: str) -> Optional[datetime]:
    """Convierte el texto leído del reloj en una fecha y hora.

    Devuelve None si el texto no contiene una marca reconocible, en lugar de
    inventar una fecha: una hora equivocada contamina todo el informe.
    """
    if not isinstance(texto, str):
        return None

    coincidencia = PATRON.search(texto)
    if not coincidencia:
        return None

    dia, mes, anio, hora, minuto, segundo = (int(g) for g in coincidencia.groups())
    try:
        return datetime(anio, mes, dia, hora, minuto, segundo)
    except ValueError:
        # Una lectura como 32/13/2026 es un error de reconocimiento, no una fecha
        return None


def es_coherente(momento: datetime, referencia: datetime, margen_horas: float = 24.0) -> bool:
    """Comprueba que la hora leída caiga cerca de la fecha esperada.

    Protege contra lecturas erróneas de un dígito que producirían fechas
    imposibles o desplazadas por años.
    """
    return abs((momento - referencia).total_seconds()) <= margen_horas * 3600


# Un dígito de la marca mide unos 60 píxeles de alto; los dos puntos, unos 10
ALTO_MINIMO_DIGITO = 25
AREA_MINIMA_COMPONENTE = 30
TOLERANCIA_ALTURA = 3
UMBRAL_BLANCO = 200
TAMANO_PLANTILLA = (32, 48)
CORRELACION_MINIMA = 0.55
DIRECTORIO_PLANTILLAS = Path("config/reloj")


def segmentar_digitos(franja: np.ndarray):
    """Aísla cada dígito de la franja del reloj, de izquierda a derecha.

    Devuelve la lista de imágenes normalizadas al mismo tamaño, lista para
    comparar contra las plantillas.
    """
    import cv2

    if franja.ndim == 3:
        gris = cv2.cvtColor(franja, cv2.COLOR_BGR2GRAY)
    else:
        gris = franja

    _, binaria = cv2.threshold(gris, UMBRAL_BLANCO, 255, cv2.THRESH_BINARY)
    contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    cajas = [
        cv2.boundingRect(c)
        for c in contornos
        if cv2.contourArea(c) >= AREA_MINIMA_COMPONENTE
    ]
    cajas = [b for b in cajas if b[3] >= ALTO_MINIMO_DIGITO]
    if not cajas:
        return []

    # Los dos puntos quedan fuera por bajos y las barras de la fecha por altas:
    # los dígitos comparten una misma altura, que es la predominante.
    alturas = sorted(b[3] for b in cajas)
    altura_tipica = alturas[len(alturas) // 2]
    cajas = [b for b in cajas if abs(b[3] - altura_tipica) <= TOLERANCIA_ALTURA]
    cajas.sort(key=lambda b: b[0])

    recortes = []
    for x, y, ancho, alto in cajas:
        recorte = binaria[y:y + alto, x:x + ancho]
        recortes.append(cv2.resize(recorte, TAMANO_PLANTILLA, interpolation=cv2.INTER_NEAREST))
    return recortes


def _correlacion(a: np.ndarray, b: np.ndarray) -> float:
    """Similitud entre dos imágenes binarias del mismo tamaño."""
    x = a.astype(np.float32).ravel() / 255.0
    y = b.astype(np.float32).ravel() / 255.0
    x -= x.mean()
    y -= y.mean()
    denominador = float(np.linalg.norm(x) * np.linalg.norm(y))
    return float(np.dot(x, y) / denominador) if denominador else 0.0


def leer_digitos(franja: np.ndarray, plantillas) -> Optional[str]:
    """Reconoce la secuencia de dígitos de la franja usando las plantillas.

    Devuelve None si algún dígito no alcanza la similitud mínima: una marca
    a medio leer es peor que ninguna, porque contamina la hora del informe.
    """
    recortes = segmentar_digitos(franja)
    if len(recortes) != 14:
        # La marca completa tiene 14 dígitos: DDMMAAAA HHMMSS
        return None

    leidos = []
    for recorte in recortes:
        mejor_digito, mejor_puntaje = None, -1.0
        for digito, plantilla in plantillas.items():
            puntaje = _correlacion(recorte, plantilla)
            if puntaje > mejor_puntaje:
                mejor_digito, mejor_puntaje = digito, puntaje
        if mejor_puntaje < CORRELACION_MINIMA:
            return None
        leidos.append(mejor_digito)

    return "".join(leidos)


def componer(digitos: str) -> Optional[datetime]:
    """Arma la fecha a partir de los catorce dígitos DDMMAAAAHHMMSS."""
    if not digitos or len(digitos) != 14 or not digitos.isdigit():
        return None
    return interpretar(
        f"{digitos[0:2]}/{digitos[2:4]}/{digitos[4:8]} "
        f"{digitos[8:10]}:{digitos[10:12]}:{digitos[12:14]}"
    )


def cargar_plantillas(directorio=DIRECTORIO_PLANTILLAS):
    """Carga las plantillas de dígitos generadas por la calibración."""
    import cv2

    ruta = Path(directorio)
    plantillas = {}
    for digito in "0123456789":
        archivo = ruta / f"{digito}.png"
        if not archivo.is_file():
            raise RelojError(
                f"Falta la plantilla del dígito '{digito}' en '{ruta}'. "
                "Ejecute scripts/calibrar_reloj.py para generarlas."
            )
        plantillas[digito] = cv2.imread(str(archivo), cv2.IMREAD_GRAYSCALE)
    return plantillas


def leer_marca(cuadro: np.ndarray, plantillas) -> Optional[datetime]:
    """Lee la fecha y hora impresas por la cámara sobre un cuadro."""
    digitos = leer_digitos(recortar_franja_reloj(cuadro), plantillas)
    return componer(digitos) if digitos else None


def rango_de_nombre(nombre: str) -> Optional[Tuple[datetime, datetime]]:
    """Extrae del nombre de archivo el rango completo de la grabación.

    Sirve como referencia para validar la lectura del reloj, nunca como
    origen de la hora de un fragmento: el rango abarca todos los fragmentos.
    """
    coincidencia = re.search(r"(\d{14})-(\d{14})", nombre or "")
    if not coincidencia:
        return None
    try:
        inicio = datetime.strptime(coincidencia.group(1), "%Y%m%d%H%M%S")
        fin = datetime.strptime(coincidencia.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return inicio, fin
