from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

import conversor_gui as gui
import converter_scada as cs
import graficos as gx


def dados_teste():
    return pd.DataFrame({
        "timestamp": pd.to_datetime(
            ["2024-01-01", "2024-01-01 00:00:01"], format="mixed"
        ),
        "valor": pd.Series([10.0, 12.0], dtype="float64"),
    })


def cache_teste():
    return cs.serializar_parquet(dados_teste())


def carregar_sensor(janela, tag, origem):
    janela.origens[Path(origem).name] = str(origem)
    janela._sensor_carregado(tag, cache_teste(), Path(origem).name, True)
    janela._atualizar_estado()


def test_janela_inicializa_com_abas_e_botoes(qtbot):
    janela = gui.Janela()
    qtbot.addWidget(janela)

    assert janela.windowTitle() == "Conversor SCADA"
    assert janela.ribbon.count() == 6
    assert janela.abas_centro.count() == 2
    assert janela.lbl_contagem.text() == "0 sensores"
    assert not janela.b_exportar.isEnabled()
    assert not janela.b_plotar.isEnabled()
    assert getattr(janela, "b_novo_gr\u00e1fico").isEnabled()


def test_dados_selecao_graficos_e_exibicao(qtbot, tmp_path):
    janela = gui.Janela()
    qtbot.addWidget(janela)
    janela.show()
    carregar_sensor(janela, "PT-GUI", tmp_path / "PT-GUI.xlsx")

    assert janela.b_exportar.isEnabled()
    assert janela.b_plotar.isEnabled()
    assert janela.parquets["PT-GUI"].startswith(b"PAR1")

    janela.b_plotar.click()
    grafico = janela.painel_graficos.grafico_atual()
    curva = janela._curva_de("PT-GUI")
    assert curva.id in grafico.area._curvas
    assert list(curva.buffer.dados()[1]) == [10.0, 12.0]

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
    assert not janela.parquets
    janela.close()


def test_selecao_de_pasta_e_tema(qtbot, monkeypatch, tmp_path):
    janela = gui.Janela()
    qtbot.addWidget(janela)
    destino = tmp_path / "saida"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(destino))
    janela.escolher_destino()
    assert janela.destino == destino
    assert janela.ed_destino.text() == str(destino)

    tema = tmp_path / "tema.json"
    gx.TEMA.exportar(tema)
    assert tema.exists()
    janela.close()


def test_modelo_dataframe(qtbot):
    modelo = gui.ModeloDataFrame()
    modelo.definir(dados_teste(), "PT-01")
    assert modelo.rowCount() == 2
    assert modelo.columnCount() == 2
    assert modelo.headerData(0, Qt.Horizontal, Qt.DisplayRole) == "Data e hora"
    assert modelo.headerData(1, Qt.Horizontal, Qt.DisplayRole) == "PT-01"
    assert modelo.data(modelo.index(0, 1), Qt.DisplayRole) == "10,000"


def test_comentarios_sao_salvos_e_recarregados(qtbot, tmp_path):
    origem = tmp_path / "PT-SIDECAR.xlsx"
    origem.touch()
    comentario = {"id": "abc", "x": 1.0, "y": 2.0, "texto": "evento"}

    janela = gui.Janela()
    qtbot.addWidget(janela)
    carregar_sensor(janela, "PT-SIDECAR", origem)
    curva = janela._curva_de("PT-SIDECAR")
    curva.comentarios.append(comentario)
    janela._salvar_comentarios([curva], comentario)

    sidecar = janela._arquivo_comentarios(origem)
    assert sidecar.exists()

    nova = gui.Janela()
    qtbot.addWidget(nova)
    carregar_sensor(nova, "PT-SIDECAR-NOVO", origem)
    assert nova.comentarios["PT-SIDECAR-NOVO"] == [comentario]
