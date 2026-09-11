"""Consolidación de múltiples lecturas de placa en un único resultado.

Un vehículo permanece visible durante decenas de cuadros y produce una
lectura por cuadro. El resultado del vehículo es el texto más votado,
ponderando cada voto por la confianza de su lectura.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from lastre.formato_ecuador import validar_o_corregir


class LecturaError(ValueError):
    """Excepción lanzada cuando los parámetros de consolidación son inválidos."""


ESTADO_VALIDADO = "validado"
ESTADO_PENDIENTE = "pendiente de revision"
ESTADO_SIN_PLACA = "sin placa identificable"


@dataclass(frozen=True)
class Lectura:
    """Una lectura individual de placa en un cuadro concreto."""
    cuadro: int
    texto: str
    confianza: float
    imagen_recorte: str = ""
    confianza_minima: Optional[float] = None

    @property
    def confianza_del_peor_caracter(self) -> float:
        """Confianza del carácter menos seguro, o la global si no se informó."""
        return self.confianza if self.confianza_minima is None else self.confianza_minima


@dataclass(frozen=True)
class ResultadoPlaca:
    """Resultado consolidado de todas las lecturas de un vehículo."""
    placa: Optional[str]
    confianza: float
    total_lecturas: int
    lecturas_coincidentes: int
    fue_corregida: bool
    estado: str
    imagen_recorte: str
    confianza_minima: float = 0.0

    @property
    def requiere_revision(self) -> bool:
        """Indica si el registro debe ser revisado manualmente."""
        return self.estado != ESTADO_VALIDADO


def _sin_placa() -> ResultadoPlaca:
    """Resultado para un vehículo sin ninguna lectura aprovechable."""
    return ResultadoPlaca(
        placa=None,
        confianza=0.0,
        total_lecturas=0,
        lecturas_coincidentes=0,
        fue_corregida=False,
        estado=ESTADO_SIN_PLACA,
        imagen_recorte="",
        confianza_minima=0.0,
    )


def consolidar_lecturas(
    lecturas: Sequence[Lectura],
    umbral_confianza: float,
    minimo_coincidencias: int,
) -> ResultadoPlaca:
    """Elige la placa más votada entre las lecturas, ponderando por confianza.

    Cada lectura se normaliza y se corrige según el formato ecuatoriano antes
    de votar. Las lecturas que no alcanzan un formato válido se descartan.
    El resultado queda validado cuando supera el umbral de confianza y reúne
    al menos `minimo_coincidencias` lecturas; en otro caso queda pendiente.
    """
    if not 0.0 <= umbral_confianza <= 1.0:
        raise LecturaError(f"umbral_confianza debe estar entre 0 y 1, se recibió: {umbral_confianza}")
    if minimo_coincidencias < 1:
        raise LecturaError(f"minimo_coincidencias debe ser >= 1, se recibió: {minimo_coincidencias}")

    votos = defaultdict(float)
    apoyos = defaultdict(list)
    corregidas = defaultdict(bool)

    for lectura in lecturas:
        placa, fue_corregida = validar_o_corregir(lectura.texto)
        if placa is None:
            continue
        votos[placa] += lectura.confianza
        apoyos[placa].append(lectura)
        # Basta que una sola lectura fuera limpia para no marcarla como corregida
        corregidas[placa] = corregidas.get(placa, True) and fue_corregida

    if not votos:
        return _sin_placa()

    ganadora = max(votos, key=lambda p: (votos[p], len(apoyos[p])))
    soporte = apoyos[ganadora]
    confianza = sum(l.confianza for l in soporte) / len(soporte)
    mejor = max(soporte, key=lambda l: l.confianza)

    # Dentro de una lectura manda su carácter más dudoso, porque una sola letra
    # equivocada invalida la placa entera. Entre lecturas manda la mejor: basta
    # un cuadro nítido para dar la placa por buena, aunque otros salgan borrosos.
    peor_caracter = max(l.confianza_del_peor_caracter for l in soporte)

    alcanza_umbral = confianza >= umbral_confianza
    alcanza_apoyo = len(soporte) >= minimo_coincidencias
    sin_caracter_dudoso = peor_caracter >= umbral_confianza
    estado = (
        ESTADO_VALIDADO
        if (alcanza_umbral and alcanza_apoyo and sin_caracter_dudoso)
        else ESTADO_PENDIENTE
    )

    return ResultadoPlaca(
        placa=ganadora,
        confianza=round(confianza, 4),
        total_lecturas=len(lecturas),
        lecturas_coincidentes=len(soporte),
        fue_corregida=corregidas[ganadora],
        estado=estado,
        imagen_recorte=mejor.imagen_recorte,
        confianza_minima=round(peor_caracter, 4),
    )
