import pandas as pd
import pytest

import conversor_gui as gui
import converter_scada as cs
import streaming as st


def carregar_serie_realista(janela, tag):
    df = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2024-01-01 00:00:00",
            "2024-01-01 00:01:00",
            "2024-01-01 00:02:00",
        ]),
        "valor": pd.Series([10.0, 20.0, 15.0], dtype="float64"),
    })
    janela.origens[f"{tag}.parquet"] = f"{tag}.parquet"
    janela._sensor_carregado(
        tag, cs.serializar_parquet(df), f"{tag}.parquet", False
    )
    janela._atualizar_estado()


def test_primeira_amostra_do_replay_e_visivel(qtbot):
    janela = gui.Janela()
    qtbot.addWidget(janela)
    janela.show()
    carregar_serie_realista(janela, "REPLAY-VISIVEL")

    janela.b_play.click()
    grafico = janela.painel_graficos.grafico_atual()
    curva = janela._curva_de("REPLAY-VISIVEL")
    grafico.area._repintar_se_sujo()
    item = grafico.area._itens[curva.id]

    assert len(item.xData) == 1
    assert item.opts["symbol"] == "o"
    janela.close()


def test_replay_com_amostras_a_cada_minuto_desenha_segmento_sem_esperar(qtbot):
    janela = gui.Janela()
    qtbot.addWidget(janela)
    janela.show()
    carregar_serie_realista(janela, "REPLAY-MINUTOS")

    assert janela.transporte.cb_vel.currentData() == 1.0
    janela.transporte.cb_janela.setCurrentIndex(1)  # 30 s
    janela.b_play.click()
    grafico = janela.painel_graficos.grafico_atual()
    curva = janela._curva_de("REPLAY-MINUTOS")

    def segmento_foi_desenhado():
        grafico.area._repintar_se_sujo()
        x = grafico.area._progresso_itens[curva.id].xData
        return x is not None and len(x) >= 2

    qtbot.waitUntil(segmento_foi_desenhado, timeout=2500)
    progresso_x = grafico.area._progresso_itens[curva.id].xData
    assert len(grafico.area._itens[curva.id].xData) == 1
    assert grafico.area.getPlotItem().viewRange()[0][1] == pytest.approx(
        progresso_x[-1]
    )
    assert janela.motor.estado == st.REPRODUZINDO
    janela.close()


def test_velocidade_1x_avanca_um_segundo_de_timestamp_por_segundo_real(
    qtbot, monkeypatch
):
    janela = gui.Janela()
    qtbot.addWidget(janela)
    carregar_serie_realista(janela, "REPLAY-1X")
    assert janela._preparar_replay()
    inicio = janela.motor.faixa[0]
    janela.motor.definir_velocidade(1.0)
    janela.motor._relogio = 100.0
    monkeypatch.setattr(st.time, "perf_counter", lambda: 101.25)

    janela.motor._passo_relogio()

    assert janela.motor.t == pytest.approx(inicio + 1.25)
    janela.close()
