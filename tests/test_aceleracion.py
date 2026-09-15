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


class _SesionFalsa:
    def __init__(self, proveedores):
        self._proveedores = proveedores

    def get_providers(self):
        return list(self._proveedores)


class _ModeloFalso:
    def __init__(self, proveedores):
        self.model = _SesionFalsa(proveedores)


def test_lee_los_proveedores_realmente_activos():
    """El proveedor en uso se consulta a la sesión, no a lo solicitado."""
    from lastre.aceleracion import proveedores_activos

    assert proveedores_activos(_ModeloFalso(CON_GPU)) == CON_GPU


def test_detecta_la_caida_silenciosa_a_procesador():
    """Pedir GPU y terminar en CPU debe reportarse, no pasar inadvertido.

    Reproduce el caso real de Colab: onnxruntime-gpu compilado para otra
    version de CUDA carga mal y el trabajo sigue en procesador sin aviso.
    """
    from lastre.aceleracion import confirmar_gpu_activa

    activa, mensaje = confirmar_gpu_activa(_ModeloFalso((PROVEEDOR_CPU,)), "gpu")

    assert not activa
    assert "onnxruntime-gpu" in mensaje


def test_confirma_la_gpu_cuando_esta_en_uso():
    """Con la GPU realmente activa el mensaje lo confirma."""
    from lastre.aceleracion import confirmar_gpu_activa

    activa, mensaje = confirmar_gpu_activa(_ModeloFalso(CON_GPU), "gpu")

    assert activa
    assert "GPU activa" in mensaje


def test_modo_procesador_no_reporta_problema():
    """Quien pidió procesador no debe recibir una advertencia."""
    from lastre.aceleracion import confirmar_gpu_activa

    activa, mensaje = confirmar_gpu_activa(_ModeloFalso((PROVEEDOR_CPU,)), "cpu")

    assert not activa
    assert "como se solicitó" in mensaje


def test_objeto_sin_sesion_no_rompe():
    """Un objeto que no expone sesión se informa sin lanzar excepción."""
    from lastre.aceleracion import confirmar_gpu_activa

    activa, mensaje = confirmar_gpu_activa(object(), "auto")

    assert not activa
    assert "No se pudo determinar" in mensaje


# --- Verificacion conjunta de los modelos cargados --------------------------

def test_verificar_sesiones_confirma_todos_los_modelos_en_gpu():
    """El lote carga tres modelos; basta que uno caiga para invalidar la medida."""
    from lastre.aceleracion import verificar_sesiones

    todo_bien, informes = verificar_sesiones(
        {"detector": _ModeloFalso(CON_GPU), "lector": _ModeloFalso(CON_GPU)}, "gpu"
    )

    assert todo_bien
    assert len(informes) == 2


def test_verificar_sesiones_delata_el_modelo_que_cayo_a_procesador():
    """Nombrar cuál cayó evita buscar a ciegas en un lote de horas."""
    from lastre.aceleracion import verificar_sesiones

    todo_bien, informes = verificar_sesiones(
        {"detector": _ModeloFalso(CON_GPU), "lector": _ModeloFalso((PROVEEDOR_CPU,))},
        "gpu",
    )

    assert not todo_bien
    assert any("lector" in i and "procesador" in i.lower() for i in informes)


def test_verificar_sesiones_en_modo_procesador_no_es_un_fallo():
    """Pedir CPU y obtener CPU es el resultado correcto, no una degradacion."""
    from lastre.aceleracion import verificar_sesiones

    todo_bien, _ = verificar_sesiones(
        {"detector": _ModeloFalso((PROVEEDOR_CPU,))}, "cpu"
    )

    assert todo_bien


def test_verificar_sesiones_en_auto_no_falla_sin_gpu():
    """'auto' acepta el procesador: solo informa, no bloquea el lote."""
    from lastre.aceleracion import verificar_sesiones

    todo_bien, informes = verificar_sesiones(
        {"detector": _ModeloFalso((PROVEEDOR_CPU,))}, "auto"
    )

    assert todo_bien
    assert informes


def test_verificar_sesiones_sin_modelos_se_rechaza():
    """Informar 'todo correcto' sin haber comprobado nada seria enganoso."""
    from lastre.aceleracion import AceleracionError, verificar_sesiones

    with pytest.raises(AceleracionError):
        verificar_sesiones({}, "gpu")
