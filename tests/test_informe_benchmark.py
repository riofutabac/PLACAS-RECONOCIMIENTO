import json
from pathlib import Path

from scripts.comparar_antes_despues_lote import regenerar_informe, parsear_desglose_medidor


def test_regenera_sin_reprocesar_y_preserva_metricas(tmp_path):
    base = Path(__file__).resolve().parents[1] / "validacion/comparacion_antes_despues"
    # Solo necesita los checkpoints; jamás ejecuta modelos.
    import shutil
    for original in base.glob("ronda_*"):
        destino = tmp_path / original.name
        destino.mkdir()
        for nombre in ("avance.json", "metricas_corrida.json"):
            shutil.copyfile(original / nombre, destino / nombre)
    referencia = base.parent / "referencia_base.json"
    informe = regenerar_informe(tmp_path, referencia)
    assert len(informe["corridas"]) == 6
    assert all(r["vehiculos_totales"] == 8 for r in informe["corridas"])
    assert informe["estadisticas"]["comparacion"]["ahorro_porcentaje"] == 24.15
    for filas in informe["auditoria_vehiculos"].values():
        for fila in filas:
            assert all(c["hallado"] and c["resultado_coincide"] for c in fila["corridas"].values())


def test_parsea_cabecera_real():
    salida = '  etapa segundos % llamadas ms c/u\n  modelo de vehiculos 10.0 50.0% 20 500.0\n TOTAL 20.0'
    assert parsear_desglose_medidor(salida)["modelo de vehiculos"]["llamadas"] == 20
