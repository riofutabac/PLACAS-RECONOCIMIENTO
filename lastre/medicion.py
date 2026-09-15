"""Medicion del tiempo que consume cada etapa del procesamiento.

Optimizar sin medir es adivinar. Este modulo reparte el tiempo entre las
etapas reales, de modo que se vea si el costo esta en decodificar el video,
en el filtro de movimiento, en el modelo de vehiculos o en leer las placas.
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
import time
from typing import Dict, Tuple


class MedicionError(ValueError):
    """Excepción lanzada cuando se mide una etapa de forma inválida."""


@dataclass
class Etapa:
    """Tiempo acumulado y llamadas de una etapa del proceso."""
    nombre: str
    segundos: float = 0.0
    llamadas: int = 0

    @property
    def milisegundos_por_llamada(self) -> float:
        """Costo medio de una sola ejecución de esta etapa."""
        return (self.segundos * 1000.0 / self.llamadas) if self.llamadas else 0.0


@dataclass
class Medidor:
    """Reparte el tiempo total entre las etapas que lo consumen."""
    etapas: Dict[str, Etapa] = field(default_factory=dict)
    inicio: float = field(default_factory=time.perf_counter)
    _candado: Lock = field(default_factory=Lock, repr=False)

    @contextmanager
    def fase(self, nombre: str):
        """Mide el bloque que envuelve y lo suma a la etapa indicada."""
        if not nombre:
            raise MedicionError("La etapa necesita un nombre")
        arranque = time.perf_counter()
        try:
            yield
        finally:
            self.anotar(nombre, time.perf_counter() - arranque)

    def anotar(self, nombre: str, segundos: float) -> None:
        """Suma tiempo a una etapa sin usar el contexto."""
        if segundos < 0:
            raise MedicionError(f"El tiempo no puede ser negativo: {segundos}")
        with self._candado:
            etapa = self.etapas.setdefault(nombre, Etapa(nombre))
            etapa.segundos += segundos
            etapa.llamadas += 1

    @property
    def total(self) -> float:
        """Segundos transcurridos desde que empezó la medicion."""
        return time.perf_counter() - self.inicio

    @property
    def medido(self) -> float:
        """Suma de lo atribuido a etapas concretas."""
        with self._candado:
            return sum(e.segundos for e in self.etapas.values())

    def reparto(self) -> Tuple[Tuple[str, float, float, int], ...]:
        """Etapas ordenadas de mayor a menor costo.

        Cada entrada trae nombre, segundos, porcentaje del total y llamadas.
        El porcentaje se calcula sobre el tiempo total, no sobre lo medido,
        para que el resto sin atribuir quede a la vista.
        """
        total = self.total or 1.0
        with self._candado:
            filas = [(e.nombre, e.segundos, 100.0 * e.segundos / total, e.llamadas)
                     for e in self.etapas.values()]
        filas.sort(key=lambda f: -f[1])
        return tuple(filas)

    def informe(self) -> str:
        """Tabla legible del reparto de tiempo, lista para la consola."""
        lineas = ["", "REPARTO DEL TIEMPO", "-" * 66,
                  f"  {'etapa':22s} {'segundos':>10s} {'%':>7s} {'llamadas':>10s} {'ms c/u':>9s}"]
        for nombre, segundos, porcentaje, llamadas in self.reparto():
            etapa = self.etapas[nombre]
            lineas.append(f"  {nombre:22s} {segundos:10.1f} {porcentaje:6.1f}% "
                          f"{llamadas:10d} {etapa.milisegundos_por_llamada:9.1f}")
        sin_atribuir = max(0.0, self.total - self.medido)
        solapado = max(0.0, self.medido - self.total)
        lineas.append("-" * 66)
        lineas.append(f"  {'sin atribuir':22s} {sin_atribuir:10.1f} "
                      f"{100.0 * sin_atribuir / (self.total or 1):6.1f}%")
        if solapado:
            lineas.append(f"  {'solapado entre etapas':22s} {solapado:10.1f} "
                          f"{100.0 * solapado / (self.total or 1):6.1f}%")
        lineas.append(f"  {'TOTAL':22s} {self.total:10.1f}")
        return "\n".join(lineas)
