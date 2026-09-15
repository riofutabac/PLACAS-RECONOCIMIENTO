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


def proveedores_activos(objeto) -> Tuple[str, ...]:
    """Proveedores que la sesión ONNX está usando realmente.

    Pedir un proveedor no garantiza obtenerlo: si las librerías de la tarjeta
    no coinciden con la versión de onnxruntime, la carga falla y el trabajo
    sigue en procesador sin aviso. Este es el único dato fiable.
    """
    for atributo in ("model", "session", "_session", "ort_session"):
        sesion = getattr(objeto, atributo, None)
        if sesion is not None and hasattr(sesion, "get_providers"):
            return tuple(sesion.get_providers())
    return ()


def confirmar_gpu_activa(objeto, modo: str) -> Tuple[bool, str]:
    """Comprueba que la GPU pedida esté realmente en uso.

    Devuelve si está activa y un mensaje explicativo. En modo 'gpu' el
    llamador debe detenerse cuando no lo está: procesar decenas de horas
    creyendo usar la tarjeta es peor que fallar de entrada.
    """
    activos = proveedores_activos(objeto)
    if not activos:
        return False, "No se pudo determinar el proveedor en uso."

    usa_gpu = any(p in activos for p in PROVEEDORES_GPU)
    if usa_gpu:
        return True, f"GPU activa: {activos[0]}"

    if modo == MODO_CPU:
        return False, "Procesando en CPU, como se solicitó."

    return False, (
        "Se solicitó GPU pero la sesión quedó en procesador. "
        f"Proveedores activos: {activos}. "
        "Causa habitual: la version de onnxruntime-gpu no coincide con la "
        "version de CUDA instalada. Reinstale la que corresponda."
    )


def describir(proveedores: Sequence[str]) -> str:
    """Texto corto para informar al usuario qué se está usando."""
    if not proveedores:
        return "sin proveedor"
    if proveedores[0] == PROVEEDOR_CPU:
        return "procesador (CPU)"
    return f"GPU ({proveedores[0]})"


def verificar_sesiones(modelos: dict, modo: str) -> Tuple[bool, Tuple[str, ...]]:
    """Comprueba el proveedor efectivo de cada modelo ya cargado.

    El lote carga varios modelos y cada uno abre su propia sesión ONNX. Que
    uno consiga la tarjeta no dice nada de los demás, y basta que uno caiga a
    procesador para que el tiempo del lote deje de ser interpretable.

    Devuelve si la configuración pedida se cumplió y un informe por modelo.
    En modo 'gpu' un solo modelo en procesador es un fallo; en 'auto' y 'cpu'
    el procesador es un resultado aceptable y solo se informa.
    """
    if modo not in MODOS:
        raise AceleracionError(f"Modo desconocido: '{modo}'. Use uno de {MODOS}")
    if not modelos:
        raise AceleracionError(
            "No hay modelos que verificar. Informar que todo está correcto sin "
            "haber comprobado ninguna sesión sería engañoso."
        )

    informes = []
    todo_bien = True

    for nombre, modelo in modelos.items():
        activa, mensaje = confirmar_gpu_activa(modelo, modo)
        informes.append(f"{nombre}: {mensaje}")
        if modo == MODO_GPU and not activa:
            todo_bien = False

    return todo_bien, tuple(informes)


def preparar_bibliotecas_gpu(modulo=None) -> bool:
    """Carga las bibliotecas CUDA que onnxruntime-gpu instala como wheels.

    Desde onnxruntime 1.21 las bibliotecas de NVIDIA llegan por pip y no por
    el sistema, asi que hay que anunciarlas antes de abrir cualquier sesion.
    Sin esto la sesion no encuentra libcublas ni libcudnn y cae a procesador
    en silencio, aunque `CUDAExecutionProvider` figure entre los disponibles.

    Devuelve si la carga se realizo. Una version que no lo soporte no es un
    error: simplemente no hay nada que precargar.
    """
    if modulo is None:
        try:
            import onnxruntime as modulo
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise AceleracionError("onnxruntime no esta instalado") from exc

    preload = getattr(modulo, "preload_dlls", None)
    if preload is None:
        return False

    preload(directory="")
    return True
