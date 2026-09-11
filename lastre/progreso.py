"""Seguimiento del avance de un lote de videos, de 0 a 100 por ciento.

Con decenas de videos por procesar, el avance debe medirse sobre el total de
cuadros del lote y no sobre los videos terminados: un video a medias también
es trabajo hecho, y un porcentaje que solo salta al terminar cada archivo no
sirve para estimar cuánto falta.
"""

from dataclasses import dataclass, field
import time
from typing import Optional


class ProgresoError(ValueError):
    """Excepción lanzada cuando los parámetros de progreso son inválidos."""


@dataclass
class Progreso:
    """Avance acumulado de un lote medido en cuadros."""
    total_cuadros: int
    cuadros_hechos: int = 0
    videos_totales: int = 0
    videos_hechos: int = 0
    inicio: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.total_cuadros < 0:
            raise ProgresoError(
                f"total_cuadros debe ser >= 0, se recibió: {self.total_cuadros}"
            )

    @property
    def porcentaje(self) -> float:
        """Avance de 0 a 100. Un lote vacío se considera terminado."""
        if self.total_cuadros <= 0:
            return 100.0
        return min(100.0, 100.0 * self.cuadros_hechos / self.total_cuadros)

    @property
    def transcurrido(self) -> float:
        """Segundos desde que empezó el lote."""
        return time.time() - self.inicio

    @property
    def restante_estimado(self) -> Optional[float]:
        """Segundos que faltan, estimados según el ritmo observado.

        Devuelve None mientras no haya avance suficiente para estimar.
        """
        if self.cuadros_hechos <= 0 or self.total_cuadros <= 0:
            return None
        ritmo = self.cuadros_hechos / self.transcurrido
        if ritmo <= 0:
            return None
        return max(0.0, (self.total_cuadros - self.cuadros_hechos) / ritmo)

    def avanzar(self, cuadros: int) -> None:
        """Suma cuadros procesados al avance del lote."""
        if cuadros < 0:
            raise ProgresoError(f"cuadros debe ser >= 0, se recibió: {cuadros}")
        self.cuadros_hechos = min(self.total_cuadros, self.cuadros_hechos + cuadros)

    def terminar_video(self) -> None:
        """Marca un video como completado."""
        self.videos_hechos = min(self.videos_totales, self.videos_hechos + 1)

    def linea(self, detalle: str = "") -> str:
        """Línea de avance lista para mostrar en la consola."""
        barra_largo = 30
        llenas = int(barra_largo * self.porcentaje / 100)
        barra = "#" * llenas + "-" * (barra_largo - llenas)
        restante = self.restante_estimado
        falta = _formatear_duracion(restante) if restante is not None else "estimando"
        cabeza = (
            f"[{barra}] {self.porcentaje:5.1f}%  "
            f"video {self.videos_hechos}/{self.videos_totales}  "
            f"transcurrido {_formatear_duracion(self.transcurrido)}  falta {falta}"
        )
        return f"{cabeza}  {detalle}" if detalle else cabeza


def _formatear_duracion(segundos: float) -> str:
    """Convierte segundos en un texto legible de horas y minutos."""
    segundos = int(max(0, segundos))
    horas, resto = divmod(segundos, 3600)
    minutos, seg = divmod(resto, 60)
    if horas:
        return f"{horas}h {minutos:02d}m"
    if minutos:
        return f"{minutos}m {seg:02d}s"
    return f"{seg}s"
