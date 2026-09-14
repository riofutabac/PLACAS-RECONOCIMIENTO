"""Cruce de registros entre dos camaras para reconstruir el recorrido.

Un vehiculo que entra por una camara debe salir por la otra dentro de un
intervalo conocido. Cruzar ambos registros permite saber quien completo el
recorrido, quien entro y no salio, y quien salio sin haber entrado.

Dos obstaculos hacen que la igualdad exacta de placa no alcance. El primero
es que cada camara fotografia al mismo vehiculo muchas veces, de modo que
primero hay que agrupar las capturas en pasos. El segundo es que dos lectores
distintos, y hasta el mismo lector, leen la misma placa de formas distintas:
en los datos reales aparecen PBN2792 y PBN2T92, o PCY2297 y PCV2297.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Sequence, Tuple


class CruceError(ValueError):
    """Excepción lanzada cuando los parámetros del cruce son inválidos."""


# Caracteres que los lectores confunden entre si. Sustituir uno por otro
# cuesta menos que un cambio cualquiera, porque es un error esperable.
CONFUSIONES = (
    frozenset("0OQD"), frozenset("1IL"), frozenset("2Z"), frozenset("5S"),
    frozenset("8B"), frozenset("6G"), frozenset("7T"), frozenset("VYW"),
    frozenset("MW"), frozenset("4A"), frozenset("9G"), frozenset("3E"),
)

COSTO_CONFUSION = 0.5
COSTO_CAMBIO = 1.0


@dataclass(frozen=True)
class Paso:
    """Un vehiculo atravesando el campo de una camara."""
    placa: str
    momento: datetime
    tipo: str = ""
    capturas: int = 1
    origen: str = ""
    imagen: str = ""

    @property
    def fecha_hora(self) -> str:
        """Momento en texto, para el informe."""
        return self.momento.strftime("%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class Emparejamiento:
    """Un vehiculo visto por ambas camaras."""
    paso_a: Paso
    paso_b: Paso
    distancia_placa: float
    minutos: float

    @property
    def placa_coincide_exacta(self) -> bool:
        """Indica si ambas camaras leyeron exactamente la misma placa."""
        return self.distancia_placa == 0.0


def _confundibles(a: str, b: str) -> bool:
    """Indica si dos caracteres se confunden habitualmente entre si."""
    return any(a in grupo and b in grupo for grupo in CONFUSIONES)


def distancia_placa(a: str, b: str) -> float:
    """Distancia entre dos placas, penalizando menos las confusiones conocidas.

    Es una distancia de edicion donde sustituir un caracter por otro que se le
    parece cuesta la mitad. Asi PBN2792 y PBN2T92 quedan mucho mas cerca que
    dos placas realmente distintas.
    """
    if a is None or b is None:
        raise CruceError("Las placas no pueden ser nulas")

    a, b = a.upper(), b.upper()
    filas, columnas = len(a) + 1, len(b) + 1
    d = [[0.0] * columnas for _ in range(filas)]

    for i in range(filas):
        d[i][0] = float(i)
    for j in range(columnas):
        d[0][j] = float(j)

    for i in range(1, filas):
        for j in range(1, columnas):
            if a[i - 1] == b[j - 1]:
                costo = 0.0
            elif _confundibles(a[i - 1], b[j - 1]):
                costo = COSTO_CONFUSION
            else:
                costo = COSTO_CAMBIO
            d[i][j] = min(d[i - 1][j] + 1.0, d[i][j - 1] + 1.0, d[i - 1][j - 1] + costo)

    return d[filas - 1][columnas - 1]


def consolidar_capturas(
    capturas: Sequence[dict],
    ventana_segundos: int = 180,
) -> Tuple[Paso, ...]:
    """Agrupa capturas repetidas de un mismo vehiculo en un solo paso.

    Una camara fotografia decenas de veces al mismo vehiculo mientras lo tiene
    a la vista. Las capturas con la misma placa separadas por menos de
    `ventana_segundos` corresponden al mismo paso.
    """
    if ventana_segundos < 0:
        raise CruceError(f"ventana_segundos debe ser >= 0, se recibió: {ventana_segundos}")

    ordenadas = sorted(capturas, key=lambda c: (c["placa"], c["momento"]))
    pasos = []
    grupo = []

    def cerrar(grupo):
        if not grupo:
            return
        pasos.append(Paso(
            placa=grupo[0]["placa"],
            momento=grupo[0]["momento"],
            tipo=grupo[0].get("tipo", ""),
            capturas=len(grupo),
            origen=grupo[0].get("origen", ""),
            imagen=grupo[0].get("imagen", ""),
        ))

    for captura in ordenadas:
        if grupo and captura["placa"] == grupo[-1]["placa"] and \
                (captura["momento"] - grupo[-1]["momento"]).total_seconds() <= ventana_segundos:
            grupo.append(captura)
            continue
        cerrar(grupo)
        grupo = [captura]
    cerrar(grupo)

    return tuple(sorted(pasos, key=lambda p: p.momento))


def emparejar(
    pasos_a: Sequence[Paso],
    pasos_b: Sequence[Paso],
    minutos_min: float = 5.0,
    minutos_max: float = 25.0,
    distancia_maxima: float = 1.5,
) -> Tuple[Tuple[Emparejamiento, ...], Tuple[Paso, ...], Tuple[Paso, ...]]:
    """Empareja los pasos de dos camaras por placa y ventana de tiempo.

    Devuelve los emparejamientos, los pasos de A sin pareja y los de B sin
    pareja. Se prefiere siempre la pareja de placa mas parecida, y a igualdad
    de placa, la mas cercana en el tiempo esperado.
    """
    if minutos_min > minutos_max:
        raise CruceError(
            f"minutos_min ({minutos_min}) no puede superar a minutos_max ({minutos_max})"
        )
    if distancia_maxima < 0:
        raise CruceError(f"distancia_maxima debe ser >= 0, se recibió: {distancia_maxima}")

    candidatos = []
    for ia, a in enumerate(pasos_a):
        for ib, b in enumerate(pasos_b):
            minutos = (b.momento - a.momento).total_seconds() / 60.0
            if not minutos_min <= abs(minutos) <= minutos_max:
                continue
            d = distancia_placa(a.placa, b.placa)
            if d > distancia_maxima:
                continue
            candidatos.append((d, abs(minutos), ia, ib))

    candidatos.sort()
    usados_a, usados_b = set(), set()
    emparejados = []

    for d, _, ia, ib in candidatos:
        if ia in usados_a or ib in usados_b:
            continue
        usados_a.add(ia)
        usados_b.add(ib)
        a, b = pasos_a[ia], pasos_b[ib]
        emparejados.append(Emparejamiento(
            paso_a=a, paso_b=b, distancia_placa=d,
            minutos=round((b.momento - a.momento).total_seconds() / 60.0, 2),
        ))

    emparejados.sort(key=lambda e: e.paso_a.momento)
    sueltos_a = tuple(p for i, p in enumerate(pasos_a) if i not in usados_a)
    sueltos_b = tuple(p for i, p in enumerate(pasos_b) if i not in usados_b)

    return tuple(emparejados), sueltos_a, sueltos_b


# Clasificacion de una correspondencia entre dos lecturas de placa
COINCIDENCIA_EXACTA = "identica"
COINCIDENCIA_LETRA = "difiere una letra"
COINCIDENCIA_LETRAS = "difieren varias letras"
COINCIDENCIA_NUMERO = "difiere un numero"
COINCIDENCIA_MIXTA = "difieren letras y numeros"
SIN_COINCIDENCIA = "sin correspondencia"


def partes_placa(placa: str) -> Tuple[str, str]:
    """Separa la placa en su parte de letras y su parte de numeros."""
    if not placa:
        return "", ""
    letras = "".join(c for c in placa.upper() if c.isalpha())
    numeros = "".join(c for c in placa.upper() if c.isdigit())
    return letras, numeros


def _difieren_en(a: str, b: str) -> int:
    """Cantidad de posiciones distintas entre dos cadenas de igual longitud."""
    if len(a) != len(b):
        return max(len(a), len(b))
    return sum(1 for x, y in zip(a, b) if x != y)


def clasificar_coincidencia(placa_a: str, placa_b: str) -> str:
    """Describe en que se parecen dos lecturas de una misma placa.

    La parte numerica es la mas fiable: si los numeros coinciden exactamente y
    solo cambia una letra, casi con certeza es el mismo vehiculo leido de dos
    formas. Aun asi se marca, porque casi con certeza no es certeza.
    """
    if not placa_a or not placa_b:
        return SIN_COINCIDENCIA
    if placa_a.upper() == placa_b.upper():
        return COINCIDENCIA_EXACTA

    letras_a, numeros_a = partes_placa(placa_a)
    letras_b, numeros_b = partes_placa(placa_b)

    numeros_iguales = numeros_a == numeros_b
    letras_iguales = letras_a == letras_b

    if numeros_iguales and not letras_iguales:
        return COINCIDENCIA_LETRA if _difieren_en(letras_a, letras_b) == 1 else COINCIDENCIA_LETRAS
    if letras_iguales and not numeros_iguales:
        return COINCIDENCIA_NUMERO
    return COINCIDENCIA_MIXTA


def requiere_revision(clasificacion: str) -> bool:
    """Indica si la correspondencia debe verificarse a mano antes de usarla."""
    return clasificacion != COINCIDENCIA_EXACTA
