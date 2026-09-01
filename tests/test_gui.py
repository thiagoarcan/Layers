from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

import conversor_gui as gui
import graficos as gx


def dados_teste():
    return pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-01 00:00:01"], format="mixed"),
        "valor": [10.0, 12.0],
    })


def test_janela_inicializa_com_abas_e_botoes(qtbot):
    janela = gui.Janela()
    qtbot.addWidget(janela)

    assert janela.windowTitle() == "Conversor SCADA"
    assert janela.ribbon.count() == 6
    assert janela.abas_centro.count() == 2
    assert janela.lbl_contagem.text() == "0 sensores"
    assert not janela.b_exportar.isEnabled()
    assert not janela.b_plotar.isEnabled()
    assert janela.b_novo_gráfico.isEnabled()


def test_botoes_de_dados_selecao_graficos_e_exibicao(qtbot, monkeypatch, tmp_path):
    janela = gui.Janela()
    qtbot.addWidget(janela)
    janela.show()

    janela._sensor_carregado("PT-01", dados_teste(), "pt.xlsx")
    janela._atualizar_estado()
    qtbot.waitUntil(lambda: janela.lista.count() == 1)

    assert janela.b_exportar.isEnabled()
    assert janela.b_plotar.isEnabled()
    assert janela.b_plotar_todos.isEnabled()

    janela.b_plotar.click()
    assert janela.painel_graficos.grafico_atual() is not None
    janela.b_plotar_todos.click()
    assert janela.painel_graficos.abas.count() >= 2

    janela.chk_sync_global.setChecked(False)
    assert not janela.chk_hover.isChecked()
    janela.chk_sync_global.setChecked(True)
    assert janela.chk_hover.isChecked()

    janela.chk_zebra.setChecked(False)
    janela.chk_grade.setChecked(False)
    janela.chk_painel.setChecked(False)
    assert not janela.tabela.alternatingRowColors()
    assert not janela.tabela.showGrid()
    assert not janela.painel_esq.isVisible()

    janela.b_remover.click()
    assert not janela.dados

    janela.close()


def test_botoes_de_selecao_de_pasta_e_tema(qtbot, monkeypatch, tmp_path):
    janela = gui.Janela()
    qtbot.addWidget(janela)
    destino = tmp_path / "saida"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(destino))
    janela.escolher_destino()
    assert janela.destino == destino
    assert janela.ed_destino.text() == str(destino)

    tema = tmp_path / "tema.json"
    janela.exportar_tema = lambda: gx.TEMA.exportar(tema)
    janela.exportar_tema()
    assert tema.exists()

    janela.close()


def test_tabela_modelo_e_a_toggle_de_simulacao(qtbot, tmp_path):
    modelo = gui.ModeloDataFrame()
    modelo.definir(dados_teste(), "PT-01")
    assert modelo.rowCount() == 2
    assert modelo.columnCount() == 2
    assert modelo.headerData(0, Qt.Horizontal, Qt.DisplayRole) == "Data e hora"
    assert modelo.headerData(1, Qt.Horizontal, Qt.DisplayRole) == "PT-01"
    assert modelo.data(modelo.index(0, 1), Qt.DisplayRole) == "10,000"

    janela = gui.Janela()
    qtbot.addWidget(janela)
    origem = tmp_path / "STREAM-PT.xlsx"
    origem.touch()
    janela.origens[origem.name] = str(origem)
    janela._sensor_carregado("STREAM-PT", dados_teste(), origem.name)
    janela._atualizar_estado()
    janela.b_plotar.click()
    curva = janela._curva_de("STREAM-PT")
    pontos_antes = len(curva.buffer)
    janela.b_simular.click()
    qtbot.waitUntil(lambda: janela.fonte_vivo is not None, timeout=2000)
    assert janela.motor.estado == gui.st.AO_VIVO
    qtbot.waitUntil(lambda: len(curva.buffer) > pontos_antes, timeout=3000)
    janela.b_simular.click()
    qtbot.waitUntil(lambda: janela.fonte_vivo is None, timeout=3000)
    assert janela.motor.estado == gui.st.PAUSADO
    janela.close()


def test_reproduzir_prepara_selecao_e_avanca_o_grafico(qtbot, tmp_path):
    janela = gui.Janela()
    qtbot.addWidget(janela)
    janela.show()
    origem = tmp_path / "REPLAY-PT.xlsx"
    origem.touch()
    dados = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2024-01-01 00:00:00.000",
            "2024-01-01 00:00:00.050",
            "2024-01-01 00:00:00.100",
            "2024-01-01 00:00:00.150",
        ]),
        "valor": [10.0, 11.0, 12.0, 13.0],
    })
    janela.origens[origem.name] = str(origem)
    janela._sensor_carregado("REPLAY-PT", dados, origem.name)
    janela._atualizar_estado()

    # O usuario deve poder iniciar pela aba Streaming, sem plotar antes.
    janela.b_play.click()
    qtbot.waitUntil(lambda: janela.motor.estado == gui.st.REPRODUZINDO)
    grafico = janela.painel_graficos.grafico_atual()
    assert grafico is not None
    curva = janela._curva_de("REPLAY-PT")
    assert curva.id in grafico.area._curvas

    def pontos_renderizados():
        grafico.area._repintar_se_sujo()
        x = grafico.area._itens[curva.id].xData
        return 0 if x is None else len(x)

    qtbot.waitUntil(lambda: pontos_renderizados() >= 2, timeout=2000)

    janela.b_play.click()
    assert janela.motor.estado == gui.st.PAUSADO
    janela.transporte._botoes["inicio"].click()
    assert janela.motor.t == janela.motor.faixa[0]
    janela.transporte._botoes["amostra_prox"].click()
    assert janela.motor.t > janela.motor.faixa[0]
    janela.transporte._botoes["fim"].click()
    assert pontos_renderizados() == 4
    janela.transporte._botoes["play"].click()
    assert janela.motor.estado == gui.st.REPRODUZINDO
    janela.transporte._botoes["parar"].click()
    assert janela.motor.estado == gui.st.PARADO
    assert janela.motor.t == janela.motor.faixa[0]
    janela.close()


def test_botao_ao_vivo_inicia_feed_e_atualiza_item_plotado(qtbot, tmp_path):
    janela = gui.Janela()
    qtbot.addWidget(janela)
    janela.show()
    origem = tmp_path / "LIVE-PT.xlsx"
    origem.touch()
    janela.origens[origem.name] = str(origem)
    janela._sensor_carregado("LIVE-PT", dados_teste(), origem.name)
    janela._atualizar_estado()

    janela.transporte.b_vivo.click()
    qtbot.waitUntil(lambda: janela.fonte_vivo is not None, timeout=2000)
    curva = janela._curva_de("LIVE-PT")
    grafico = janela.painel_graficos.grafico_atual()
    assert grafico is not None

    def pontos_renderizados():
        grafico.area._repintar_se_sujo()
        x = grafico.area._itens[curva.id].xData
        return 0 if x is None else len(x)

    qtbot.waitUntil(lambda: pontos_renderizados() > 2, timeout=3000)
    ultimo_x = float(curva.buffer.dados()[0][-1])
    faixa_x = grafico.area.getPlotItem().viewRange()[0]
    assert faixa_x[0] <= ultimo_x <= faixa_x[1]
    assert janela.motor.estado == gui.st.AO_VIVO

    janela.transporte.b_vivo.click()
    qtbot.waitUntil(lambda: janela.fonte_vivo is None, timeout=3000)
    janela.close()


def test_fluxo_real_abre_xlsx_e_reproduz_serie(qtbot, monkeypatch, tmp_path):
    origem = tmp_path / "E2E-STREAM.xlsx"
    pd.DataFrame({
        "Data": pd.to_datetime([
            "2024-01-01 00:00:00.000",
            "2024-01-01 00:00:00.050",
            "2024-01-01 00:00:00.100",
            "2024-01-01 00:00:00.150",
        ]),
        "E2E-STREAM": [1.0, 2.0, 3.0, 4.0],
    }).to_excel(origem, index=False)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *args: ([str(origem)], "Planilhas do Excel (*.xlsx)"),
    )

    janela = gui.Janela()
    qtbot.addWidget(janela)
    janela.show()
    janela.b_abrir.click()
    qtbot.waitUntil(
        lambda: janela.worker is not None and not janela.worker.isRunning(),
        timeout=5000,
    )
    qtbot.waitUntil(lambda: janela.lista.count() == 1, timeout=2000)
    assert janela.lista.currentItem().data(Qt.UserRole) == "E2E-STREAM"

    janela.b_play.click()
    qtbot.waitUntil(lambda: janela.motor.estado == gui.st.REPRODUZINDO)
    curva = janela._curva_de("E2E-STREAM")
    grafico = janela.painel_graficos.grafico_atual()

    def pontos_renderizados():
        grafico.area._repintar_se_sujo()
        x = grafico.area._itens[curva.id].xData
        return 0 if x is None else len(x)

    qtbot.waitUntil(lambda: pontos_renderizados() >= 2, timeout=2000)
    assert janela.transporte.slider.value() > 0
    janela.transporte._botoes["parar"].click()
    qtbot.keyClick(janela, Qt.Key_Space)
    assert janela.motor.estado == gui.st.REPRODUZINDO
    qtbot.keyClick(janela, Qt.Key_Space)
    assert janela.motor.estado == gui.st.PAUSADO
    janela.close()


def test_comentarios_sao_salvos_e_recarregados(qtbot, tmp_path):
    origem = tmp_path / "PT-SIDECAR.xlsx"
    origem.touch()
    comentario = {"id": "abc", "x": 1.0, "y": 2.0, "texto": "evento"}

    janela = gui.Janela()
    qtbot.addWidget(janela)
    janela.origens[origem.name] = str(origem)
    janela._sensor_carregado("PT-SIDECAR", dados_teste(), origem.name)
    curva = janela._curva_de("PT-SIDECAR")
    curva.comentarios.append(comentario)
    janela._salvar_comentarios([curva], comentario)

    sidecar = janela._arquivo_comentarios(origem)
    assert sidecar.exists()

    nova = gui.Janela()
    qtbot.addWidget(nova)
    nova.origens[origem.name] = str(origem)
    nova._sensor_carregado("PT-SIDECAR", dados_teste(), origem.name)
    assert nova.comentarios["PT-SIDECAR"] == [comentario]
