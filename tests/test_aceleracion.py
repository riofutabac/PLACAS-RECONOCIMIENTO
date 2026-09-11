"""Pruebas unitarias para el módulo lastre.aceleracion."""

import pytest

from lastre.aceleracion import (
    AceleracionError,
    PROVEEDOR_CPU,
    describir,
    elegir_proveedores,
    hay_gpu,
)

CON_GPU = ("TensorrtExecutionProvider", "CUDAExecutionProvider", PROVEEDOR_CPU)
SIN_GPU = ("CoreMLExecutionProvider", PROVEEDOR_CPU)


def test_detecta_la_presencia_de_gpu():
    """La GPU se reconoce por el proveedor que reporta onnxruntime."""
    assert hay_gpu(CON_GPU)
    assert not hay_gpu(SIN_GPU)


def test_auto_usa_gpu_cuando_existe():
    """En modo automático la GPU se prefiere por rendimiento."""
    elegidos = elegir_proveedores("auto", CON_GPU)

    assert elegidos[0] in ("CUDAExecutionProvider", "TensorrtExecutionProvider")
    assert elegidos[-1] == PROVEEDOR_CPU


def test_auto_cae_a_procesador_sin_gpu():
    """Sin GPU el modo automático sigue funcionando en procesador."""
    assert elegir_proveedores("auto", SIN_GPU) == (PROVEEDOR_CPU,)


def test_cpu_fuerza_procesador_aunque_haya_gpu():
    """El modo procesador ignora la GPU disponible."""
    assert elegir_proveedores("cpu", CON_GPU) == (PROVEEDOR_CPU,)


def test_gpu_falla_si_no_hay_gpu():
    """Pedir GPU sin tenerla debe fallar, no procesar horas en procesador."""
    with pytest.raises(AceleracionError, match="onnxruntime-gpu"):
        elegir_proveedores("gpu", SIN_GPU)


def test_modo_desconocido_se_rechaza():
    """Un modo mal escrito se rechaza de forma explícita."""
    with pytest.raises(AceleracionError, match="Modo desconocido"):
        elegir_proveedores("turbo", CON_GPU)


def test_descripcion_legible():
    """El usuario debe poder ver con qué se está procesando."""
    assert "GPU" in describir(elegir_proveedores("auto", CON_GPU))
    assert "CPU" in describir(elegir_proveedores("auto", SIN_GPU))
