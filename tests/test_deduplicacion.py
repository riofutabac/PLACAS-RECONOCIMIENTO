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


def test_lecturas_pertenecen_a_la_evidencia_elegida():
    primero = {**_registro(100, "PBA1234", 0.8), "lecturas": 2}
    mejor = {**_registro(200, "PBA1234", 0.99), "lecturas": 8}
    final = deduplicar_por_placa([primero, mejor], VENTANA)[0]
    assert final.cuadro == 100
    assert final.imagen == mejor["imagen"]
    assert final.lecturas == 8


def test_lecturas_independientes_en_el_mismo_cuadro():
    a = {**_registro(100, "PBA1234"), "lecturas": 2}
    b = {**_registro(100, "PBC5678"), "lecturas": 8}
    assert {r.placa: r.lecturas for r in deduplicar_por_placa([a, b], VENTANA)} == {
        "PBA1234": 2, "PBC5678": 8}


@pytest.mark.parametrize("estados", [("pendiente", "pendiente"),
                                    ("validado", "pendiente"),
                                    ("pendiente", "validado")])
def test_placa_pendiente_no_borra_otro_vehiculo(estados):
    registros = [_registro(100, "PBA1234", estado=estados[0]),
                 _registro(110, "PBA1234", estado=estados[1])]
    assert len(deduplicar_por_placa(registros, VENTANA)) == 2


def test_direcciones_opuestas_no_se_fusionan():
    registros = [_registro(100, "PBA1234", sentido="entra"),
                 _registro(110, "PBA1234", sentido="sale")]
    assert len(deduplicar_por_placa(registros, VENTANA)) == 2


def test_direccion_indeterminada_no_oculta_incompatibilidad_previa():
    registros = [_registro(100, "PBA1234", sentido="entra"),
                 _registro(110, "PBA1234", sentido="indeterminado"),
                 _registro(120, "PBA1234", sentido="sale")]
    assert len(deduplicar_por_placa(registros, VENTANA)) == 2


def _con_intervalo(cuadro, inicio, fin, pista):
    return {**_registro(cuadro, "PBA1234"), "cuadro_inicio": inicio,
            "cuadro_fin": fin, "trayectoria_id": pista}


@pytest.mark.parametrize("segundo_inicio", [50, 100])
def test_coexistencia_incluso_en_cuadro_limite_no_se_fusiona(segundo_inicio):
    registros = [_con_intervalo(10, 1, 100, 1),
                 _con_intervalo(110, segundo_inicio, 120, 2)]
    assert len(deduplicar_por_placa(registros, VENTANA)) == 2


def test_coexistencia_se_comprueba_con_todo_el_grupo():
    # Un miembro legacy intermedio no debe ocultar la coexistencia conocida.
    registros = [_con_intervalo(10, 1, 100, 1),
                 _registro(120, "PBA1234"),
                 _con_intervalo(140, 90, 150, 3)]
    finales = deduplicar_por_placa(registros, VENTANA)
    assert len(finales) == 2
    assert finales[0].registros_fusionados == 2


def test_fragmentos_separados_conservan_intervalo_grupo_e_identidad():
    registros = [_con_intervalo(10, 1, 100, 1),
                 {**_con_intervalo(120, 110, 130, 2), "confianza": 0.99, "lecturas": 8}]
    final = deduplicar_por_placa(registros, VENTANA)[0]
    assert final.registros_fusionados == 2
    assert final.trayectoria_id == 1
    assert (final.cuadro_inicio, final.cuadro_fin) == (1, 130)
    assert final.lecturas == 8


def test_entrada_legacy_no_inventa_intervalos():
    final = deduplicar_por_placa([_registro(10, "PBA1234"),
                                 _con_intervalo(120, 110, 130, 2)], VENTANA)[0]
    assert final.registros_fusionados == 2
    assert final.cuadro_inicio is None and final.cuadro_fin is None
    assert final.trayectoria_id is None
