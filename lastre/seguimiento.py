"""Módulo de seguimiento temporal y asociación de detecciones entre cuadros."""

import math
from typing import Dict, List, Sequence, Tuple

from lastre.config import ZonaConfig
from lastre.deteccion import Deteccion
from lastre.trayectoria import Posicion, Trayectoria


class SeguimientoError(RuntimeError):
    """Excepción lanzada cuando ocurre un error durante el seguimiento temporal."""
    pass


class _PistaActiva:
    """Estructura interna mutable para acumular observaciones mientras la pista permanezca activa."""

    def __init__(self, id_pista: int, cuadro_inicio: int, deteccion: Deteccion) -> None:
        self.id: int = id_pista
        self.cuadro_inicio: int = cuadro_inicio
        self.cuadro_ultimo: int = cuadro_inicio
        self.cuadros_sin_deteccion: int = 0
        self.observaciones: List[Posicion] = [
            Posicion(
                cuadro=cuadro_inicio,
                centro=deteccion.centro,
                caja=deteccion.caja,
                area=deteccion.area,
            )
        ]

    @property
    def ultimo_centro(self) -> Tuple[int, int]:
        return self.observaciones[-1].centro

    def actualizar(self, numero_cuadro: int, deteccion: Deteccion) -> None:
        self.cuadro_ultimo = numero_cuadro
        self.cuadros_sin_deteccion = 0
        self.observaciones.append(
            Posicion(
                cuadro=numero_cuadro,
                centro=deteccion.centro,
                caja=deteccion.caja,
                area=deteccion.area,
            )
        )

    def marcar_no_detectada(self) -> None:
        self.cuadros_sin_deteccion += 1

    def a_trayectoria_inmutable(self) -> Trayectoria:
        return Trayectoria(
            id=self.id,
            cuadro_inicio=self.cuadro_inicio,
            cuadro_fin=self.cuadro_ultimo,
            posiciones=tuple(self.observaciones),
        )


class SeguidorTrayectorias:
    """Asocia detecciones cuadro a cuadro para construir trayectorias continuas."""

    def __init__(self, config: ZonaConfig) -> None:
        self._config = config
        self._distancia_maxima = config.seguimiento.distancia_maxima
        self._tolerancia_oclusion = config.seguimiento.tolerancia_oclusion
        self._siguiente_id = 1
        self._pistas_activas: Dict[int, _PistaActiva] = {}
        self._trayectorias_cerradas: List[Trayectoria] = []

    @property
    def hay_pistas_activas(self) -> bool:
        """Indica si algún vehículo está siendo seguido en este momento."""
        return bool(self._pistas_activas)

    def observaciones_en_cuadro(
        self, numero_cuadro: int,
    ) -> Tuple[Tuple[int, Posicion], ...]:
        """Expone observaciones recién asociadas, sin inventar cajas en oclusión.

        Consultar después de actualizar el cuadro y antes de finalizar.
        """
        return tuple(
            (pista.id, pista.observaciones[-1])
            for pista in self._pistas_activas.values()
            if pista.cuadro_ultimo == numero_cuadro
        )

    def actualizar(
        self,
        numero_cuadro: int,
        detecciones: Sequence[Deteccion],
    ) -> Tuple[Trayectoria, ...]:
        """Procesa las detecciones de un cuadro y actualiza el estado de las trayectorias.

        Retorna una tupla con las trayectorias que finalizaron (se cerraron) en este cuadro.
        """
        if numero_cuadro < 1:
            raise SeguimientoError(f"numero_cuadro debe ser >= 1, se recibió: {numero_cuadro}")

        ids_pistas = list(self._pistas_activas.keys())
        pistas_lista = [self._pistas_activas[i] for i in ids_pistas]

        # 1. Matriz de distancias entre pistas activas y detecciones actuales
        emparejamientos: List[Tuple[float, int, int]] = []
        for idx_pista, pista in enumerate(pistas_lista):
            px, py = pista.ultimo_centro
            for idx_det, det in enumerate(detecciones):
                dx = px - det.centro[0]
                dy = py - det.centro[1]
                dist = math.hypot(dx, dy)
                if dist <= self._distancia_maxima:
                    emparejamientos.append((dist, idx_pista, idx_det))

        # 2. Emparejamiento codicioso (greedy) priorizando menores distancias
        emparejamientos.sort(key=lambda item: item[0])
        pistas_asignadas = set()
        detecciones_asignadas = set()

        for dist, idx_pista, idx_det in emparejamientos:
            if idx_pista in pistas_asignadas or idx_det in detecciones_asignadas:
                continue
            pistas_lista[idx_pista].actualizar(numero_cuadro, detecciones[idx_det])
            pistas_asignadas.add(idx_pista)
            detecciones_asignadas.add(idx_det)

        # 3. Pistas no emparejadas: incrementar contador de cuadros sin detección
        nuevas_cerradas: List[Trayectoria] = []
        ids_a_eliminar = []

        for idx_pista, pista in enumerate(pistas_lista):
            if idx_pista not in pistas_asignadas:
                pista.marcar_no_detectada()
                if pista.cuadros_sin_deteccion > self._tolerancia_oclusion:
                    tray = pista.a_trayectoria_inmutable()
                    nuevas_cerradas.append(tray)
                    self._trayectorias_cerradas.append(tray)
                    ids_a_eliminar.append(pista.id)

        for id_pista in ids_a_eliminar:
            del self._pistas_activas[id_pista]

        # 4. Detecciones no emparejadas: iniciar nuevas pistas
        for idx_det, det in enumerate(detecciones):
            if idx_det not in detecciones_asignadas:
                nueva_pista = _PistaActiva(
                    id_pista=self._siguiente_id,
                    cuadro_inicio=numero_cuadro,
                    deteccion=det,
                )
                self._pistas_activas[self._siguiente_id] = nueva_pista
                self._siguiente_id += 1

        return tuple(nuevas_cerradas)

    def finalizar(self) -> Tuple[Trayectoria, ...]:
        """Cierra todas las pistas que aún permanezcan activas y retorna las cerradas en este paso."""
        cerradas_finales: List[Trayectoria] = []
        for pista in self._pistas_activas.values():
            tray = pista.a_trayectoria_inmutable()
            cerradas_finales.append(tray)
            self._trayectorias_cerradas.append(tray)
        self._pistas_activas.clear()
        return tuple(cerradas_finales)

    def obtener_todas_las_trayectorias(self) -> Tuple[Trayectoria, ...]:
        """Devuelve todas las trayectorias concluidas hasta el momento."""
        return tuple(self._trayectorias_cerradas)
