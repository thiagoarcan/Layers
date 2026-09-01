import pandas as pd

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

    assert janela.transporte.cb_vel.currentData() == 0.0
    janela.b_play.click()
    grafico = janela.painel_graficos.grafico_atual()
    curva = janela._curva_de("REPLAY-MINUTOS")

    def segmento_foi_desenhado():
        grafico.area._repintar_se_sujo()
        x = grafico.area._itens[curva.id].xData
        return x is not None and len(x) >= 2

    qtbot.waitUntil(segmento_foi_desenhado, timeout=2500)
    assert janela.motor.estado in (st.REPRODUZINDO, st.PAUSADO)
    janela.close()
