"""Validación y corrección de placas según el formato vehicular ecuatoriano.

Formato de automóvil: tres letras seguidas de tres o cuatro dígitos (ABC1234).
Formato de motocicleta: dos letras seguidas de tres o cuatro dígitos (AB123A
no se contempla; se usa la variante numérica vigente).

La primera letra corresponde a la provincia de matriculación.
"""

import re
from typing import Optional, Tuple


class FormatoError(ValueError):
    """Excepción lanzada cuando la entrada al validador es inválida."""


# Letras asignadas a provincias en el sistema ecuatoriano de placas
LETRAS_PROVINCIA = frozenset("ABCEGHIJKLMNOPQRSTUVXYZUW")

PATRON_AUTOMOVIL = re.compile(r"^[A-Z]{3}[0-9]{3,4}$")
PATRON_MOTOCICLETA = re.compile(r"^[A-Z]{2}[0-9]{3,4}$")

# Confusiones habituales del reconocimiento óptico.
# Se corrigen solo cuando la posición exige un tipo de carácter concreto.
A_DIGITO = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2",
            "B": "8", "S": "5", "G": "6", "T": "7"}
A_LETRA = {"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"}

# Caracteres que nunca forman parte de una placa
CARACTERES_IGNORADOS = frozenset(" -.·_/\\|")

TIPO_AUTOMOVIL = "automovil"
TIPO_MOTOCICLETA = "motocicleta"


def normalizar(texto: str) -> str:
    """Deja el texto en mayúsculas y sin separadores ni espacios.

    Devuelve una cadena nueva sin alterar la entrada.
    """
    if not isinstance(texto, str):
        raise FormatoError(f"El texto debe ser una cadena, se recibió: {type(texto).__name__}")
    return "".join(c for c in texto.upper() if c not in CARACTERES_IGNORADOS and c.isalnum())


def tipo_de_placa(texto: str) -> Optional[str]:
    """Devuelve el tipo de vehículo según el formato, o None si no encaja."""
    limpio = normalizar(texto)
    if PATRON_AUTOMOVIL.match(limpio):
        return TIPO_AUTOMOVIL
    if PATRON_MOTOCICLETA.match(limpio):
        return TIPO_MOTOCICLETA
    return None


def es_valida(texto: str) -> bool:
    """Indica si el texto cumple algún formato de placa ecuatoriano."""
    return tipo_de_placa(texto) is not None


def _corregir_con_longitud(limpio: str, letras: int) -> Optional[str]:
    """Intenta forzar el texto al formato de `letras` letras más dígitos."""
    if len(limpio) < letras + 3 or len(limpio) > letras + 4:
        return None

    corregido = []
    for posicion, caracter in enumerate(limpio):
        if posicion < letras:
            corregido.append(A_LETRA.get(caracter, caracter) if caracter.isdigit() else caracter)
        else:
            corregido.append(A_DIGITO.get(caracter, caracter) if caracter.isalpha() else caracter)

    candidato = "".join(corregido)
    return candidato if es_valida(candidato) else None


def corregir(texto: str) -> Optional[str]:
    """Corrige confusiones de caracteres según la posición dentro de la placa.

    Devuelve la placa corregida si alcanza un formato válido, o None si no.
    Nunca inventa un carácter que la lectura no vio: solo sustituye un
    carácter por su homólogo visual en la posición que lo exige.
    """
    limpio = normalizar(texto)
    if es_valida(limpio):
        return limpio

    for letras in (3, 2):
        candidato = _corregir_con_longitud(limpio, letras)
        if candidato is not None:
            return candidato
    return None


def validar_o_corregir(texto: str) -> Tuple[Optional[str], bool]:
    """Devuelve la placa final y si hubo que corregirla.

    El segundo elemento es True cuando la placa original no era válida y se
    obtuvo por corrección posicional.
    """
    limpio = normalizar(texto)
    if es_valida(limpio):
        return limpio, False
    corregida = corregir(limpio)
    return corregida, corregida is not None
