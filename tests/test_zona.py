"""Pruebas unitarias para el módulo lastre.zona."""

import numpy as np
import pytest

from lastre.config import (
    BandaReloj,
    DeteccionConfig,
    Dimensiones,
    Poligono,
    Punto,
    Segmento,
    SeguimientoConfig,
    ZonaConfig,
)
from lastre.zona import (
    caja_en_zona,
    construir_mascara_zona,
    punto_en_zona,
    superponer_zona,
)

# Vértices que encierran la superficie de la vía de lastre en el cuadro de 2960x1664
VERTICES_LASTRE = (
    (1554, 636), (1820, 696), (1924, 858), (1983, 1066),
    (2146, 1302), (2442, 1554), (2649, 1664), (370, 1664),
    (340, 1125), (622, 918), (1036, 770), (1332, 681),
)

PUNTO_INTERIOR = (1500, 1400)
PUNTO_CARRETERA = (2800, 1000)
PUNTO_CIELO = (400, 300)


@pytest.fixture
def config_zona():
    """Configuración estándar de prueba con el polígono real de la vía."""
    return ZonaConfig(
        dimensiones=Dimensiones(ancho=2960, alto=1664),
        poligono=Poligono(vertices=tuple(Punto(x=x, y=y) for x, y in VERTICES_LASTRE)),
        banda_reloj=BandaReloj(alto=100),
        segmento_salida=Segmento(
            punto_inicio=Punto(1924, 858),
            punto_fin=Punto(2442, 1554),
        ),
        deteccion=DeteccionConfig(area_minima=3000),
        seguimiento=SeguimientoConfig(
            distancia_maxima=200,
            tolerancia_oclusion=15,
            minimo_cuadros=10,
        ),
    )


def test_dimensiones_y_tipo_mascara(config_zona):
    """Verifica forma, tipo y rango de valores de la máscara generada."""
    mascara = construir_mascara_zona(config_zona)
    assert mascara.shape == (1664, 2960)
    assert mascara.dtype == np.uint8
    assert set(np.unique(mascara)).issubset({0, 255})


def test_exclusion_banda_reloj(config_zona):
    """Verifica que la franja del reloj esté estrictamente en 0 en todo el ancho."""
    mascara = construir_mascara_zona(config_zona)
    assert np.all(mascara[0:config_zona.banda_reloj.alto, :] == 0)


def test_poligono_excluye_cielo_y_carretera(config_zona):
    """El contorno cerrado deja fuera el cielo y la carretera principal."""
    mascara = construir_mascara_zona(config_zona)

    assert mascara[PUNTO_CIELO[1], PUNTO_CIELO[0]] == 0
    assert mascara[PUNTO_CARRETERA[1], PUNTO_CARRETERA[0]] == 0
    assert mascara[PUNTO_INTERIOR[1], PUNTO_INTERIOR[0]] == 255

    # Las cuatro esquinas del cuadro quedan fuera de la vía
    assert mascara[0, 0] == 0
    assert mascara[0, 2959] == 0
    assert mascara[1663, 0] == 0
    assert mascara[1663, 2959] == 0


def test_area_acotada(config_zona):
    """El polígono cubre una fracción acotada del cuadro, no un semiplano."""
    mascara = construir_mascara_zona(config_zona)
    fraccion = float(mascara.mean()) / 255.0
    assert 0.10 < fraccion < 0.55


def test_punto_en_zona(config_zona):
    """Verifica punto_en_zona dentro, fuera y en la banda del reloj."""
    assert punto_en_zona(PUNTO_INTERIOR, config_zona)
    assert not punto_en_zona(PUNTO_CARRETERA, config_zona)
    assert not punto_en_zona(PUNTO_CIELO, config_zona)

    # Banda del reloj siempre excluida
    assert not punto_en_zona((100, config_zona.banda_reloj.alto - 1), config_zona)

    # Puntos fuera del cuadro
    assert not punto_en_zona((-10, 500), config_zona)
    assert not punto_en_zona((3000, 500), config_zona)
    assert not punto_en_zona((500, 2000), config_zona)


def test_concordancia_punto_y_mascara(config_zona):
    """punto_en_zona concuerda con la máscara salvo en píxeles de frontera."""
    mascara = construir_mascara_zona(config_zona)
    contorno = np.array(config_zona.poligono.como_lista, dtype=np.int32)
    import cv2

    for y in range(0, 1664, 150):
        for x in range(0, 2960, 200):
            if y < config_zona.banda_reloj.alto + 3:
                continue
            # Omitir los píxeles pegados al borde, donde el rasterizado varía
            if abs(cv2.pointPolygonTest(contorno, (float(x), float(y)), True)) < 5:
                continue
            esperado = bool(mascara[y, x] == 255)
            assert punto_en_zona((x, y), config_zona) == esperado, f"Discrepancia en ({x}, {y})"


def test_caja_en_zona(config_zona):
    """Verifica la evaluación de cajas delimitadoras con distintos criterios."""
    mascara = construir_mascara_zona(config_zona)

    caja_lastre = (1450, 1350, 100, 100)
    assert caja_en_zona(caja_lastre, config_zona, criterio="centro")
    assert caja_en_zona(caja_lastre, config_zona, criterio="centro", mascara=mascara)
    assert caja_en_zona(caja_lastre, config_zona, criterio="base")
    assert caja_en_zona(caja_lastre, config_zona, criterio="cualquiera")
    assert caja_en_zona(caja_lastre, config_zona, criterio="completa")

    caja_principal = (2700, 500, 100, 100)
    assert not caja_en_zona(caja_principal, config_zona, criterio="centro")
    assert not caja_en_zona(caja_principal, config_zona, criterio="centro", mascara=mascara)
    assert not caja_en_zona(caja_principal, config_zona, criterio="cualquiera")
    assert not caja_en_zona(caja_principal, config_zona, criterio="completa")

    caja_reloj = (200, 10, 100, 50)
    assert not caja_en_zona(caja_reloj, config_zona, criterio="centro")
    assert not caja_en_zona(caja_reloj, config_zona, criterio="completa")

    assert not caja_en_zona((100, 100, 0, 50), config_zona)
    assert not caja_en_zona((100, 100, 50, -10), config_zona)

    with pytest.raises(ValueError, match="Criterio desconocido"):
        caja_en_zona(caja_lastre, config_zona, criterio="invalido")


def test_inmutabilidad_superposicion(config_zona):
    """superponer_zona no altera el arreglo de la imagen original."""
    imagen_original = np.zeros((1664, 2960, 3), dtype=np.uint8)
    imagen_original[:, :, 0] = 50
    copia_referencia = imagen_original.copy()

    resultado = superponer_zona(imagen_original, config_zona)

    assert not np.array_equal(resultado, imagen_original)
    assert np.array_equal(imagen_original, copia_referencia)
