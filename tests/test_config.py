"""Pruebas unitarias para el módulo lastre.config."""

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import pytest

from lastre.config import (
    ConfiguracionError,
    DeteccionConfig,
    Dimensiones,
    Poligono,
    Punto,
    Segmento,
    SeguimientoConfig,
    ZonaConfig,
    cargar_configuracion,
    validar_configuracion,
)


@pytest.fixture
def config_valida_dict():
    """Diccionario con una configuración válida base completa."""
    return {
        "dimensiones": {
            "ancho": 2960,
            "alto": 1664
        },
        "poligono": [
            [1554, 636], [1820, 696], [1924, 858], [1983, 1066],
            [2146, 1302], [2442, 1554], [2649, 1664], [370, 1664],
            [340, 1125], [622, 918], [1036, 770], [1332, 681],
        ],
        "banda_reloj": {
            "alto": 100
        },
        "segmento_salida": {
            "punto_inicio": [1924, 858],
            "punto_fin": [2442, 1554]
        },
        "deteccion": {
            "area_minima": 3000
        },
        "seguimiento": {
            "distancia_maxima": 200,
            "tolerancia_oclusion": 15,
            "minimo_cuadros": 10
        }
    }


def test_cargar_configuracion_defecto_valida():
    """Verifica que el archivo default config/zona.json se cargue y valide correctamente."""
    cfg = cargar_configuracion("config/zona.json")
    assert isinstance(cfg, ZonaConfig)
    assert cfg.dimensiones.ancho == 2960
    assert cfg.dimensiones.alto == 1664
    assert len(cfg.poligono.vertices) >= 3
    assert len(cfg.poligono.como_lista[0]) == 2
    assert cfg.banda_reloj.alto == 100
    assert cfg.segmento_salida.punto_inicio.tupla != cfg.segmento_salida.punto_fin.tupla
    assert len(cfg.segmento_salida.punto_inicio.tupla) == 2
    assert cfg.deteccion.area_minima > 0
    assert cfg.seguimiento.distancia_maxima > 0
    assert cfg.seguimiento.tolerancia_oclusion > 0
    assert cfg.seguimiento.minimo_cuadros > 0


def test_inmutabilidad_configuracion(config_valida_dict):
    """Verifica que las instancias de configuración sean inmutables (patrón frozen)."""
    cfg = validar_configuracion(config_valida_dict)
    with pytest.raises(FrozenInstanceError):
        cfg.dimensiones = Dimensiones(1920, 1080)
    with pytest.raises(FrozenInstanceError):
        cfg.banda_reloj.alto = 200
    with pytest.raises(FrozenInstanceError):
        cfg.deteccion.area_minima = 5000


def test_archivo_no_encontrado():
    """Verifica fallo temprano cuando el archivo no existe."""
    with pytest.raises(ConfiguracionError, match="no encontrado"):
        cargar_configuracion("config/archivo_inexistente.json")


def test_json_invalido(tmp_path: Path):
    """Verifica fallo temprano cuando el archivo no tiene JSON válido."""
    archivo_malo = tmp_path / "malo.json"
    archivo_malo.write_text("{este no es un json valido", encoding="utf-8")
    with pytest.raises(ConfiguracionError, match="Error de sintaxis JSON"):
        cargar_configuracion(archivo_malo)


def test_falta_seccion_raiz(config_valida_dict):
    """Verifica que falte una sección raíz obligatoria dispare ConfiguracionError."""
    secciones = [
        "dimensiones", "poligono", "banda_reloj",
        "segmento_salida", "deteccion", "seguimiento"
    ]
    for seccion in secciones:
        copia = dict(config_valida_dict)
        del copia[seccion]
        with pytest.raises(ConfiguracionError, match=f"Falta la sección requerida '{seccion}'"):
            validar_configuracion(copia)


def test_dimensiones_invalidas(config_valida_dict):
    """Verifica que dimensiones negativas, cero o booleanas sean rechazadas."""
    datos = dict(config_valida_dict)
    datos["dimensiones"] = {"ancho": 0, "alto": 1664}
    with pytest.raises(ConfiguracionError, match="mayor o igual a 1"):
        validar_configuracion(datos)

    datos["dimensiones"] = {"ancho": 2960, "alto": -50}
    with pytest.raises(ConfiguracionError, match="mayor o igual a 1"):
        validar_configuracion(datos)

    datos["dimensiones"] = {"ancho": True, "alto": 1664}
    with pytest.raises(ConfiguracionError, match="debe ser un número entero"):
        validar_configuracion(datos)


def test_vertice_fuera_de_limites(config_valida_dict):
    """Coordenadas de vértice fuera del cuadro son rechazadas."""
    datos = dict(config_valida_dict)
    datos["poligono"] = [[3000, 100], [500, 500], [100, 900]]
    with pytest.raises(ConfiguracionError, match="no puede exceder"):
        validar_configuracion(datos)

    datos["poligono"] = [[1658, -10], [500, 500], [100, 900]]
    with pytest.raises(ConfiguracionError, match="mayor o igual a 0"):
        validar_configuracion(datos)


def test_poligono_con_pocos_vertices(config_valida_dict):
    """Un polígono de menos de tres vértices no encierra área."""
    datos = dict(config_valida_dict)
    datos["poligono"] = [[100, 100], [500, 500]]
    with pytest.raises(ConfiguracionError, match="al menos 3 vértices"):
        validar_configuracion(datos)


def test_poligono_con_vertices_repetidos(config_valida_dict):
    """Los vértices repetidos indican un contorno mal definido."""
    datos = dict(config_valida_dict)
    datos["poligono"] = [[100, 100], [500, 500], [100, 100]]
    with pytest.raises(ConfiguracionError, match="vértices repetidos"):
        validar_configuracion(datos)


def test_segmento_salida_invalido(config_valida_dict):
    """Verifica validación de segmento de salida."""
    datos = dict(config_valida_dict)
    datos["segmento_salida"] = {
        "punto_inicio": [100, 100],
        "punto_fin": [100, 100]
    }
    with pytest.raises(ConfiguracionError, match="no pueden ser iguales"):
        validar_configuracion(datos)

    datos["segmento_salida"] = {
        "punto_inicio": [-10, 100],
        "punto_fin": [200, 200]
    }
    with pytest.raises(ConfiguracionError, match="mayor o igual a 0"):
        validar_configuracion(datos)


def test_deteccion_invalida(config_valida_dict):
    """Verifica validación de parámetros de detección."""
    datos = dict(config_valida_dict)
    datos["deteccion"] = {"area_minima": 0}
    with pytest.raises(ConfiguracionError, match="mayor o igual a 1"):
        validar_configuracion(datos)

    datos["deteccion"] = {"area_minima": "grande"}
    with pytest.raises(ConfiguracionError, match="debe ser un número entero"):
        validar_configuracion(datos)


def test_seguimiento_invalido(config_valida_dict):
    """Verifica validación de parámetros de seguimiento."""
    datos = dict(config_valida_dict)
    datos["seguimiento"] = {
        "distancia_maxima": 0,
        "tolerancia_oclusion": 15,
        "minimo_cuadros": 10
    }
    with pytest.raises(ConfiguracionError, match="distancia_maxima.*mayor o igual a 1"):
        validar_configuracion(datos)

    datos["seguimiento"] = {
        "distancia_maxima": 200,
        "tolerancia_oclusion": -1,
        "minimo_cuadros": 10
    }
    with pytest.raises(ConfiguracionError, match="tolerancia_oclusion.*mayor o igual a 0"):
        validar_configuracion(datos)
