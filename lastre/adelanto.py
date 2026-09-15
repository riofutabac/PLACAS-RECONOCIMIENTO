"""Lectura anticipada, ordenada y acotada de cuadros de video."""

from queue import Empty, Full, Queue
from threading import Event, Thread
import time


class AdelantoError(ValueError):
    """Error de configuración de la lectura anticipada."""


def cuadros_adelantados(origen, capacidad: int = 2, al_leer=None):
    """Entrega `origen` en orden, leyéndolo en un hilo previo.

    La cola pequeña limita memoria. `al_leer(segundos)` mide el trabajo real
    del productor; los errores del origen reaparecen en el consumidor.
    """
    if capacidad < 1:
        raise AdelantoError("capacidad debe ser >= 1")

    cola = Queue(maxsize=capacidad)
    cancelar = Event()
    fin = object()

    def poner(elemento):
        while not cancelar.is_set():
            try:
                cola.put(elemento, timeout=0.05)
                return True
            except Full:
                continue
        return False

    def productor():
        iterador = iter(origen)
        try:
            while not cancelar.is_set():
                inicio = time.perf_counter()
                try:
                    cuadro = next(iterador)
                except StopIteration:
                    poner((fin, None))
                    return
                except BaseException as error:
                    poner((fin, error))
                    return
                if al_leer is not None:
                    al_leer(time.perf_counter() - inicio)
                if not poner((None, cuadro)):
                    return
        finally:
            cerrar = getattr(iterador, "close", None)
            if cerrar is not None:
                cerrar()

    hilo = Thread(target=productor, name="lectura-video", daemon=True)
    hilo.start()
    try:
        while True:
            try:
                etiqueta, valor = cola.get(timeout=0.05)
            except Empty:
                if not hilo.is_alive():
                    raise RuntimeError("El lector anticipado terminó sin resultado")
                continue
            if etiqueta is fin:
                if valor is not None:
                    raise valor
                return
            yield valor
    finally:
        cancelar.set()
        hilo.join(timeout=1.0)
