"""Módulo de definición inmutable de trayectorias vehiculares."""

from dataclasses import dataclass
import math
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class Posicion:
    """Posición y dimensiones observadas de un vehículo en un cuadro particular."""
    cuadro: int
    centro: Tuple[int, int]
    caja: Tuple[int, int, int, int]
    area: int


@dataclass(frozen=True)
class Trayectoria:
    """Representación temporal inmutable de un vehículo seguido a través de cuadros."""
    id: int
    cuadro_inicio: int
    cuadro_fin: int
    posiciones: Tuple[Posicion, ...]

    @property
    def total_observaciones(self) -> int:
        """Cantidad de cuadros en que el vehículo fue efectivamente detectado."""
        return len(self.posiciones)

    @property
    def extension_cuadros(self) -> int:
        """Amplitud temporal total entre el primer y último cuadro observado."""
        return self.cuadro_fin - self.cuadro_inicio + 1

    @property
    def centro_inicial(self) -> Tuple[int, int]:
        """Centroide en la primera observación."""
        return self.posiciones[0].centro

    @property
    def centro_final(self) -> Tuple[int, int]:
        """Centroide en la última observación."""
        return self.posiciones[-1].centro

    @property
    def caja_final(self) -> Tuple[int, int, int, int]:
        """Caja delimitadora en la última observación."""
        return self.posiciones[-1].caja

    @property
    def desplazamiento_neto(self) -> float:
        """Distancia euclidiana neta entre la primera y la última posición."""
        if not self.posiciones:
            return 0.0
        p0 = self.posiciones[0].centro
        pf = self.posiciones[-1].centro
        return math.hypot(pf[0] - p0[0], pf[1] - p0[1])

    def como_dict(self) -> Dict[str, Any]:
        """Serializa la trayectoria a una estructura de diccionario compatible con JSON."""
        return {
            "id": self.id,
            "cuadro_inicio": self.cuadro_inicio,
            "cuadro_fin": self.cuadro_fin,
            "total_observaciones": self.total_observaciones,
            "extension_cuadros": self.extension_cuadros,
            "desplazamiento_neto": round(self.desplazamiento_neto, 2),
            "posiciones": [
                {
                    "cuadro": p.cuadro,
                    "centro": list(p.centro),
                    "caja": list(p.caja),
                    "area": p.area,
                }
                for p in self.posiciones
            ],
        }
