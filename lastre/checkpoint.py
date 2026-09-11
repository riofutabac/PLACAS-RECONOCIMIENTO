"""Persistencia del avance de un lote para poder reanudarlo.

Procesar decenas de videos toma horas, y en un entorno como Colab la sesión
se corta antes de terminar. Guardar el resultado de cada video apenas está
listo convierte una desconexión en una pausa, no en la pérdida del trabajo.
"""

import json
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


class CheckpointError(ValueError):
    """Excepción lanzada cuando el archivo de avance no puede usarse."""


NOMBRE_ARCHIVO = "avance.json"
VERSION = 1


class Checkpoint:
    """Registro en disco de los videos ya procesados y sus resultados."""

    def __init__(self, directorio) -> None:
        self._ruta = Path(directorio) / NOMBRE_ARCHIVO
        self._datos: Dict[str, dict] = {"version": VERSION, "videos": {}}
        if self._ruta.is_file():
            self._cargar()

    def _cargar(self) -> None:
        """Lee el avance previo, tolerando un archivo truncado por un corte."""
        try:
            with self._ruta.open(encoding="utf-8") as f:
                datos = json.load(f)
        except (json.JSONDecodeError, OSError):
            # Un corte a mitad de escritura deja el archivo inservible; se
            # prefiere empezar de nuevo antes que trabajar con datos corruptos.
            return
        if isinstance(datos, dict) and isinstance(datos.get("videos"), dict):
            self._datos = datos

    @property
    def ruta(self) -> Path:
        """Ubicación del archivo de avance."""
        return self._ruta

    @property
    def videos_hechos(self) -> Tuple[str, ...]:
        """Nombres de los videos ya procesados."""
        return tuple(self._datos["videos"].keys())

    def esta_hecho(self, nombre: str) -> bool:
        """Indica si un video ya fue procesado en una corrida anterior."""
        return nombre in self._datos["videos"]

    def filas_de(self, nombre: str) -> List[dict]:
        """Devuelve las filas guardadas de un video ya procesado."""
        return list(self._datos["videos"].get(nombre, {}).get("filas", []))

    def todas_las_filas(self) -> List[dict]:
        """Devuelve las filas de todos los videos procesados hasta ahora."""
        filas = []
        for nombre in sorted(self._datos["videos"]):
            filas.extend(self._datos["videos"][nombre].get("filas", []))
        return filas

    def guardar_video(self, nombre: str, filas: Sequence[dict], cuadros: int = 0) -> None:
        """Registra el resultado de un video y lo escribe a disco de inmediato.

        La escritura pasa por un archivo temporal para que una interrupción
        nunca deje el avance a medio escribir.
        """
        if not nombre:
            raise CheckpointError("El nombre del video no puede estar vacío")

        self._datos["videos"][nombre] = {"filas": list(filas), "cuadros": cuadros}
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = self._ruta.with_suffix(".tmp")
        with temporal.open("w", encoding="utf-8") as f:
            json.dump(self._datos, f, ensure_ascii=False, indent=1)
        temporal.replace(self._ruta)

    def cuadros_hechos(self) -> int:
        """Total de cuadros ya procesados, para retomar el porcentaje."""
        return sum(v.get("cuadros", 0) for v in self._datos["videos"].values())

    def olvidar(self, nombre: str) -> None:
        """Elimina un video del avance para volver a procesarlo."""
        if nombre in self._datos["videos"]:
            del self._datos["videos"][nombre]
            temporal = self._ruta.with_suffix(".tmp")
            with temporal.open("w", encoding="utf-8") as f:
                json.dump(self._datos, f, ensure_ascii=False, indent=1)
            temporal.replace(self._ruta)
