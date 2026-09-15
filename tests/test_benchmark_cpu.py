from lastre.medicion import Medidor
from scripts import comparar_cpu_hilos as benchmark


def test_medicion_excluye_tiempo_del_consumidor(monkeypatch):
    reloj = [0.0]
    monkeypatch.setattr(benchmark.time, "perf_counter", lambda: reloj[0])

    def origen():
        for indice in range(2):
            reloj[0] += 2.0
            yield indice

    medidor = Medidor()
    for _ in benchmark.cuadros_medidos(origen(), medidor):
        reloj[0] += 100.0

    assert medidor.etapas["decodificar video"].segundos == 4.0
    assert medidor.etapas["decodificar video"].llamadas == 2
