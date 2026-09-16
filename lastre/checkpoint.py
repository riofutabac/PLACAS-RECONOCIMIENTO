"""Persistencia del avance de un lote para poder reanudarlo.

Procesar decenas de videos toma horas, y en un entorno como Colab la sesión
se corta antes de terminar. Guardar el resultado de cada video apenas está
listo convierte una desconexión en una pausa, no en la pérdida del trabajo.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


class CheckpointError(ValueError):
    """Excepción lanzada cuando el archivo de avance no puede usarse."""


NOMBRE_ARCHIVO = "avance.json"
VERSION = 1


class Checkpoint:
    """Registro en disco de los videos ya procesados y sus resultados."""

    def __init__(self, directorio, manifiesto: Optional[dict] = None) -> None:
        self._ruta = Path(directorio) / NOMBRE_ARCHIVO
        self._datos: Dict[str, Any] = {"version": VERSION, "videos": {}}
        if manifiesto:
            self._datos["manifiesto"] = dict(manifiesto)
        if self._ruta.is_file():
            self._cargar(manifiesto)

    def _cargar(self, manifiesto_esperado: Optional[dict] = None) -> None:
        """Lee el avance previo, tolerando un archivo truncado por un corte."""
        try:
            with self._ruta.open(encoding="utf-8") as f:
                datos = json.load(f)
        except (json.JSONDecodeError, OSError):
            # Un corte a mitad de escritura deja el archivo inservible; se
            # prefiere empezar de nuevo antes que trabajar con datos corruptos.
            return
        if isinstance(datos, dict) and isinstance(datos.get("videos"), dict):
            guardado = datos.get("manifiesto")
            if manifiesto_esperado and manifiesto_esperado.get("modelo_vehiculos"):
                if not guardado or not guardado.get("modelo_vehiculos"):
                    raise CheckpointError(
                        f"Conflicto en checkpoint: el avance guardado en '{self._ruta}' no tiene "
                        f"manifiesto de identidad de modelo, pero la corrida actual requiere "
                        f"'{manifiesto_esperado.get('modelo_vehiculos')}'. "
                        "Para evitar mezclar resultados de distintos modelos, use otra carpeta de salida o la opción --reiniciar."
                    )
            if manifiesto_esperado and guardado:
                for campo in manifiesto_esperado:
                    val_esp = manifiesto_esperado.get(campo)
                    val_guar = guardado.get(campo)
                    if val_esp != val_guar:
                        raise CheckpointError(
                            f"Conflicto en checkpoint: el avance guardado usa {campo}='{val_guar}', "
                            f"pero la corrida actual solicita '{val_esp}'. "
                            "Use otra carpeta de salida o la opción --reiniciar."
                        )
            self._datos = datos
            if manifiesto_esperado and "manifiesto" not in self._datos:
                self._datos["manifiesto"] = dict(manifiesto_esperado)

    @property
    def manifiesto(self) -> dict:
        """Manifiesto de configuración de la corrida que generó el checkpoint."""
        return dict(self._datos.get("manifiesto", {}))

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
