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

    janela.dados["PT-01"] = dados_teste()
    janela._atualizar_estado()
    janela._sensor_carregado("PT-01", dados_teste(), "pt.xlsx")
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


def test_tabela_modelo_e_a_toggle_de_simulacao(qtbot):
    modelo = gui.ModeloDataFrame()
    modelo.definir(dados_teste(), "PT-01")
    assert modelo.rowCount() == 2
    assert modelo.columnCount() == 2
    assert modelo.headerData(0, Qt.Horizontal, Qt.DisplayRole) == "timestamp"
    assert modelo.headerData(1, Qt.Horizontal, Qt.DisplayRole) == "valor"
    assert modelo.data(modelo.index(0, 1), Qt.DisplayRole) == "10"

    janela = gui.Janela()
    qtbot.addWidget(janela)
    janela.dados["PT-01"] = dados_teste()
    janela._sensor_carregado("PT-01", dados_teste(), "pt.xlsx")
    janela.b_plotar.click()
    janela.b_simular.click()
    qtbot.waitUntil(lambda: janela.fonte_vivo is not None, timeout=2000)
    assert janela.motor.estado == gui.st.AO_VIVO
    janela.b_simular.click()
    qtbot.waitUntil(lambda: janela.fonte_vivo is None, timeout=3000)
    assert janela.motor.estado == gui.st.PAUSADO
    janela.close()
