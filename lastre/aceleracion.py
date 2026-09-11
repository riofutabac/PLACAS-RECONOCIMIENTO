"""Selección del proveedor de cómputo para los modelos ONNX.

En una máquina con GPU el modelo de detección corre varias veces más rápido.
El proveedor se elige explícitamente para que el mismo código sirva en un
portátil y en un entorno con tarjeta gráfica, sin sorpresas silenciosas.
"""

from typing import Sequence, Tuple


class AceleracionError(ValueError):
    """Excepción lanzada cuando se pide un proveedor no disponible."""


MODO_AUTO = "auto"
MODO_GPU = "gpu"
MODO_CPU = "cpu"
MODOS = (MODO_AUTO, MODO_GPU, MODO_CPU)

PROVEEDOR_CPU = "CPUExecutionProvider"
PROVEEDORES_GPU = ("CUDAExecutionProvider", "TensorrtExecutionProvider")


def proveedores_disponibles() -> Tuple[str, ...]:
    """Proveedores que onnxruntime reporta en esta máquina."""
    try:
        import onnxruntime
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise AceleracionError("onnxruntime no está instalado") from exc
    return tuple(onnxruntime.get_available_providers())


def hay_gpu(disponibles: Sequence[str] = None) -> bool:
    """Indica si alguno de los proveedores de GPU está disponible."""
    lista = tuple(disponibles) if disponibles is not None else proveedores_disponibles()
    return any(p in lista for p in PROVEEDORES_GPU)


def elegir_proveedores(modo: str, disponibles: Sequence[str] = None) -> Tuple[str, ...]:
    """Devuelve los proveedores a usar, en orden de preferencia.

    - 'auto' usa la GPU si está disponible y cae a procesador si no.
    - 'gpu' falla si no hay GPU, para no procesar horas sin darse cuenta.
    - 'cpu' fuerza el procesador.
    """
    if modo not in MODOS:
        raise AceleracionError(f"Modo desconocido: '{modo}'. Use uno de {MODOS}")

    lista = tuple(disponibles) if disponibles is not None else proveedores_disponibles()

    if modo == MODO_CPU:
        return (PROVEEDOR_CPU,)

    gpus = tuple(p for p in PROVEEDORES_GPU if p in lista)

    if modo == MODO_GPU:
        if not gpus:
            raise AceleracionError(
                "Se pidió GPU pero onnxruntime no reporta ningún proveedor de GPU. "
                f"Disponibles: {lista}. Instale 'onnxruntime-gpu'."
            )
        return gpus + (PROVEEDOR_CPU,)

    return (gpus + (PROVEEDOR_CPU,)) if gpus else (PROVEEDOR_CPU,)


def describir(proveedores: Sequence[str]) -> str:
    """Texto corto para informar al usuario qué se está usando."""
    if not proveedores:
        return "sin proveedor"
    if proveedores[0] == PROVEEDOR_CPU:
        return "procesador (CPU)"
    return f"GPU ({proveedores[0]})"
