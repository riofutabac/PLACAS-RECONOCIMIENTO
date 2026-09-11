"""Pruebas unitarias para el módulo lastre.deduplicacion."""

import pytest

from lastre.deduplicacion import DeduplicacionError, deduplicar_por_placa

VENTANA = 300


def _registro(cuadro, placa, confianza=0.9, sentido="entra", estado="validado"):
    return {
        "cuadro": cuadro,
        "placa": placa,
        "confianza": confianza,
        "sentido": sentido,
        "estado": estado,
        "imagen": f"placas/f{cuadro}.jpg",
    }


def test_misma_placa_cercana_en_el_tiempo_se_fusiona():
    """Reproduce el caso real de la camioneta TAA2204 registrada dos veces."""
    registros = [_registro(2600, "TAA2204", 0.95), _registro(2775, "TAA2204", 0.93)]

    finales = deduplicar_por_placa(registros, VENTANA)

    assert len(finales) == 1
    assert finales[0].fue_duplicado
    assert finales[0].registros_fusionados == 2
    # Conserva el cuadro de la primera aparicion y la lectura mas confiable
    assert finales[0].cuadro == 2600
    assert finales[0].confianza == pytest.approx(0.95)


def test_misma_placa_lejana_en_el_tiempo_son_dos_pasos():
    """Un vehículo puede volver a pasar más tarde; eso no es un duplicado."""
    registros = [_registro(700, "TAA2204"), _registro(7000, "TAA2204")]

    assert len(deduplicar_por_placa(registros, VENTANA)) == 2


def test_placas_distintas_no_se_fusionan():
    """Dos vehículos simultáneos con placas distintas son registros distintos."""
    registros = [_registro(2600, "TAA2204"), _registro(2620, "PCW2497")]

    assert len(deduplicar_por_placa(registros, VENTANA)) == 2


def test_registros_sin_placa_nunca_se_fusionan():
    """Sin placa no hay identidad, y perder un vehículo es peor que duplicarlo."""
    registros = [_registro(2600, None), _registro(2610, None), _registro(2620, "")]

    assert len(deduplicar_por_placa(registros, VENTANA)) == 3


def test_conserva_la_aparicion_mas_confiable():
    """La imagen y la placa provienen de la lectura de mayor confianza."""
    registros = [_registro(2600, "TAA2204", 0.60), _registro(2700, "TAA2204", 0.98)]

    final = deduplicar_por_placa(registros, VENTANA)[0]

    assert final.imagen == "placas/f2700.jpg"
    assert final.confianza == pytest.approx(0.98)


def test_orden_de_entrada_no_altera_el_resultado():
    """El resultado no depende del orden en que lleguen los registros."""
    registros = [_registro(2775, "TAA2204", 0.93), _registro(2600, "TAA2204", 0.95)]

    finales = deduplicar_por_placa(registros, VENTANA)

    assert len(finales) == 1
    assert finales[0].cuadro == 2600


def test_ventana_invalida():
    """Una ventana negativa se rechaza de forma explícita."""
    with pytest.raises(DeduplicacionError, match="ventana_cuadros"):
        deduplicar_por_placa([], -1)


def test_sin_registros_no_hay_resultado():
    """Una entrada vacía produce una salida vacía, no un error."""
    assert deduplicar_por_placa([], VENTANA) == ()
