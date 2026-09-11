"""Módulo de configuración y validación de la zona de análisis."""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Tuple, Union


class ConfiguracionError(ValueError):
    """Excepción lanzada cuando la configuración de la zona es inválida o no se puede cargar."""
    pass


@dataclass(frozen=True)
class Dimensiones:
    """Dimensiones en píxeles del cuadro de video."""
    ancho: int
    alto: int


@dataclass(frozen=True)
class Punto:
    """Coordenada bidimensional (x, y)."""
    x: int
    y: int

    @property
    def tupla(self) -> Tuple[int, int]:
        """Devuelve el punto como una tupla (x, y)."""
        return (self.x, self.y)


# Un polígono necesita al menos tres vértices para encerrar área
MINIMO_VERTICES = 3


@dataclass(frozen=True)
class Poligono:
    """Contorno cerrado que encierra la superficie de la vía de lastre."""
    vertices: Tuple[Punto, ...]

    @property
    def como_lista(self) -> Tuple[Tuple[int, int], ...]:
        """Devuelve los vértices como tuplas (x, y)."""
        return tuple(v.tupla for v in self.vertices)


@dataclass(frozen=True)
class BandaReloj:
    """Banda horizontal superior donde se ubica el reloj grabado en el video."""
    alto: int


@dataclass(frozen=True)
class Segmento:
    """Segmento de recta definido por dos puntos extremos."""
    punto_inicio: Punto
    punto_fin: Punto


@dataclass(frozen=True)
class DeteccionConfig:
    """Parámetros para la detección de movimiento en la zona."""
    area_minima: int


@dataclass(frozen=True)
class SeguimientoConfig:
    """Parámetros para la asociación temporal de trayectorias."""
    distancia_maxima: int
    tolerancia_oclusion: int
    minimo_cuadros: int


@dataclass(frozen=True)
class ZonaConfig:
    """Configuración inmutable de la zona de análisis, detección y seguimiento."""
    dimensiones: Dimensiones
    poligono: Poligono
    banda_reloj: BandaReloj
    segmento_salida: Segmento
    deteccion: DeteccionConfig
    seguimiento: SeguimientoConfig


def _validar_entero(valor: Any, nombre: str, minimo: int = 0, maximo: Union[int, None] = None) -> int:
    """Valida que un valor sea un entero dentro del rango permitido (rechaza booleanos)."""
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ConfiguracionError(f"El campo '{nombre}' debe ser un número entero, se recibió: {type(valor).__name__}")
    if valor < minimo:
        raise ConfiguracionError(f"El campo '{nombre}' ({valor}) debe ser mayor o igual a {minimo}")
    if maximo is not None and valor > maximo:
        raise ConfiguracionError(f"El campo '{nombre}' ({valor}) no puede exceder {maximo}")
    return valor


def _validar_punto(datos_punto: Any, nombre: str, ancho_max: int, alto_max: int) -> Punto:
    """Valida una coordenada [x, y] asegurando que pertenezca al espacio del cuadro."""
    if not isinstance(datos_punto, (list, tuple)) or len(datos_punto) != 2:
        raise ConfiguracionError(f"El punto '{nombre}' debe ser una lista o tupla de 2 enteros [x, y]")
    
    x = _validar_entero(datos_punto[0], f"{nombre}.x", minimo=0, maximo=ancho_max)
    y = _validar_entero(datos_punto[1], f"{nombre}.y", minimo=0, maximo=alto_max)
    return Punto(x=x, y=y)


def validar_configuracion(datos: Any) -> ZonaConfig:
    """Valida la estructura y los rangos de un diccionario de configuración.

    Lanza ConfiguracionError con mensaje descriptivo si cualquier campo
    falta, tiene un tipo incorrecto o cae fuera del espacio del cuadro.
    """
    if not isinstance(datos, dict):
        raise ConfiguracionError(f"La configuración debe ser un diccionario, se recibió: {type(datos).__name__}")

    # 1. Validar dimensiones
    if "dimensiones" not in datos or not isinstance(datos["dimensiones"], dict):
        raise ConfiguracionError("Falta la sección requerida 'dimensiones' en la configuración")
    
    dim_dict = datos["dimensiones"]
    if "ancho" not in dim_dict or "alto" not in dim_dict:
        raise ConfiguracionError("La sección 'dimensiones' debe contener 'ancho' y 'alto'")
    
    ancho = _validar_entero(dim_dict["ancho"], "dimensiones.ancho", minimo=1)
    alto = _validar_entero(dim_dict["alto"], "dimensiones.alto", minimo=1)
    dimensiones = Dimensiones(ancho=ancho, alto=alto)

    # 2. Validar el polígono que encierra la vía de lastre
    if "poligono" not in datos or not isinstance(datos["poligono"], list):
        raise ConfiguracionError("Falta la sección requerida 'poligono' (lista de vértices) en la configuración")

    vertices_crudos = datos["poligono"]
    if len(vertices_crudos) < MINIMO_VERTICES:
        raise ConfiguracionError(
            f"El polígono requiere al menos {MINIMO_VERTICES} vértices, se recibieron {len(vertices_crudos)}"
        )

    vertices = tuple(
        _validar_punto(v, f"poligono[{i}]", ancho, alto)
        for i, v in enumerate(vertices_crudos)
    )

    if len(set(v.tupla for v in vertices)) != len(vertices):
        raise ConfiguracionError("El polígono no puede contener vértices repetidos")

    poligono = Poligono(vertices=vertices)

    # 3. Validar banda del reloj
    if "banda_reloj" not in datos or not isinstance(datos["banda_reloj"], dict):
        raise ConfiguracionError("Falta la sección requerida 'banda_reloj' en la configuración")
    
    reloj_dict = datos["banda_reloj"]
    if "alto" not in reloj_dict:
        raise ConfiguracionError("La sección 'banda_reloj' debe contener 'alto'")
    
    alto_reloj = _validar_entero(reloj_dict["alto"], "banda_reloj.alto", minimo=0, maximo=alto - 1)
    banda_reloj = BandaReloj(alto=alto_reloj)

    # 4. Validar segmento de salida
    if "segmento_salida" not in datos or not isinstance(datos["segmento_salida"], dict):
        raise ConfiguracionError("Falta la sección requerida 'segmento_salida' en la configuración")
    
    seg_dict = datos["segmento_salida"]
    if "punto_inicio" not in seg_dict or "punto_fin" not in seg_dict:
        raise ConfiguracionError("La sección 'segmento_salida' debe contener 'punto_inicio' y 'punto_fin'")
    
    p_ini = _validar_punto(seg_dict["punto_inicio"], "segmento_salida.punto_inicio", ancho, alto)
    p_fin = _validar_punto(seg_dict["punto_fin"], "segmento_salida.punto_fin", ancho, alto)

    if p_ini.tupla == p_fin.tupla:
        raise ConfiguracionError("Los puntos de inicio y fin del segmento de salida no pueden ser iguales")

    segmento_salida = Segmento(punto_inicio=p_ini, punto_fin=p_fin)

    # 5. Validar detección
    if "deteccion" not in datos or not isinstance(datos["deteccion"], dict):
        raise ConfiguracionError("Falta la sección requerida 'deteccion' en la configuración")
    
    det_dict = datos["deteccion"]
    if "area_minima" not in det_dict:
        raise ConfiguracionError("La sección 'deteccion' debe contener 'area_minima'")
    
    area_minima = _validar_entero(det_dict["area_minima"], "deteccion.area_minima", minimo=1)
    deteccion = DeteccionConfig(area_minima=area_minima)

    # 6. Validar seguimiento
    if "seguimiento" not in datos or not isinstance(datos["seguimiento"], dict):
        raise ConfiguracionError("Falta la sección requerida 'seguimiento' en la configuración")
    
    seg_cfg_dict = datos["seguimiento"]
    for campo in ["distancia_maxima", "tolerancia_oclusion", "minimo_cuadros"]:
        if campo not in seg_cfg_dict:
            raise ConfiguracionError(f"La sección 'seguimiento' debe contener '{campo}'")
    
    distancia_max = _validar_entero(seg_cfg_dict["distancia_maxima"], "seguimiento.distancia_maxima", minimo=1)
    tolerancia = _validar_entero(seg_cfg_dict["tolerancia_oclusion"], "seguimiento.tolerancia_oclusion", minimo=0)
    min_cuadros = _validar_entero(seg_cfg_dict["minimo_cuadros"], "seguimiento.minimo_cuadros", minimo=1)

    seguimiento = SeguimientoConfig(
        distancia_maxima=distancia_max,
        tolerancia_oclusion=tolerancia,
        minimo_cuadros=min_cuadros,
    )

    return ZonaConfig(
        dimensiones=dimensiones,
        poligono=poligono,
        banda_reloj=banda_reloj,
        segmento_salida=segmento_salida,
        deteccion=deteccion,
        seguimiento=seguimiento,
    )


def cargar_configuracion(ruta: Union[str, Path] = "config/zona.json") -> ZonaConfig:
    """Carga y valida el archivo de configuración JSON de la zona.

    Falla temprano con ConfiguracionError si el archivo no existe,
    no es JSON válido o contiene datos fuera de especificación.
    """
    ruta_path = Path(ruta)
    if not ruta_path.is_file():
        raise ConfiguracionError(f"Archivo de configuración no encontrado: '{ruta}'")
    
    try:
        with ruta_path.open("r", encoding="utf-8") as f:
            datos = json.load(f)
    except json.JSONDecodeError as exc:
        raise ConfiguracionError(f"Error de sintaxis JSON en '{ruta}': {exc.msg} (línea {exc.lineno})") from exc
    except OSError as exc:
        raise ConfiguracionError(f"Error al leer '{ruta}': {exc}") from exc

    return validar_configuracion(datos)
