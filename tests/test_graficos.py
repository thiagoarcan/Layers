from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import Qt

import graficos as gx


def test_buffer_circular_preserva_apenas_o_rabo():
    buffer = gx.BufferCircular(3)
    buffer.estender(np.array([1, 2]), np.array([10, 20]))
    buffer.append(3, 30)
    buffer.append(4, 40)

    x, y = buffer.dados()
    assert buffer.cheio
    assert np.array_equal(x, [2, 3, 4])
    assert np.array_equal(y, [20, 30, 40])

    buffer.limpar()
    assert len(buffer) == 0
    assert buffer.dados()[0].size == 0


def test_buffer_rejeita_series_com_tamanhos_diferentes():
    with pytest.raises(ValueError, match="mesmo tamanho"):
        gx.BufferCircular(3).estender([1, 2], [1])


def test_curva_normaliza_datas_limite_offset_e_ponto_proximo():
    curva = gx.Curva.de_series(
        "PT-01",
        [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)],
        [10, 20, 30],
        capacidade=10,
        unidade="bar",
        grandeza="Pressao",
    )

    x, y = curva.dados_plot()
    assert len(x) == 3
    assert curva.rotulo_eixo() == "Pressao (bar)"
    assert curva.ponto_proximo(x[1] + 1000)[1] == 20

    curva.deslocamento_s = 60
    curva.limite_t = x[1] + 60
    limitado_x, limitado_y = curva.dados_plot()
    assert len(limitado_x) == 2
    assert limitado_y[-1] == 20


def test_catalogo_emite_adicao_alteracao_e_remocao(qtbot):
    catalogo = gx.CatalogoCurvas()
    eventos = []
    catalogo.curva_adicionada.connect(lambda curva: eventos.append(("add", curva.id)))
    catalogo.curva_alterada.connect(lambda curva: eventos.append(("change", curva.id)))
    catalogo.curva_removida.connect(lambda identificador: eventos.append(("remove", identificador)))

    curva = gx.Curva.de_series("A", [0, 1], [2, 3])
    catalogo.adicionar(curva)
    catalogo.notificar(curva)
    catalogo.remover(curva.id)

    assert [evento[0] for evento in eventos] == ["add", "change", "remove"]
    assert len(catalogo) == 0


def test_temas_contraste_e_json(tmp_path):
    gerenciador = gx.GerenciadorTema("escuro_industrial")
    assert set(gerenciador.disponiveis()) == {
        "escuro_industrial", "claro_tecnico", "alto_contraste"
    }
    assert gerenciador.validar_contraste(1.0) == []

    caminho = tmp_path / "tema.json"
    gerenciador.exportar(caminho)
    nome = gerenciador.importar(caminho)
    assert nome == "escuro_industrial"
    assert gerenciador.tema.nome == "escuro_industrial"


def test_area_plot_cobre_curvas_e_interacoes(qtbot):
    area = gx.AreaPlot("Teste")
    qtbot.addWidget(area)
    curva = gx.Curva.de_series("PT-01", [0, 1, 2], [10, 20, 15], eixo="Y2")
    area.adicionar_curva(curva, ajustar=False)
    area._repintar_se_sujo()

    assert curva.id in area._curvas
    assert area._eixos["Y2"].isVisible()
    assert area.getPlotItem().getAxis("left").labelText == ""
    assert "PT-01" in area._eixos["Y2"].labelText

    area.alternar_recorte(True)
    assert area.faixa_recorte() is not None
    area.alternar_recorte(False)
    assert area.faixa_recorte() is None

    anotacao = area.adicionar_anotacao(1, 20, "evento")
    html_anotacao = anotacao.textItem.toHtml()
    assert "evento" in html_anotacao
    assert "X:" in html_anotacao and "Y:" in html_anotacao
    area.linha_vertical(1)
    area.linha_horizontal(20, rotulo="limite")
    assert anotacao in area._anotacoes
    area.limpar_anotacoes()
    assert not area._anotacoes

    area.mover_para_eixo(curva, "Y3")
    assert curva.eixo == "Y3"
    area.remover_curva(curva.id)
    assert curva.id not in area._curvas


def test_menu_contexto_so_expoe_acoes_funcionais(qtbot):
    area = gx.AreaPlot("Menu")
    qtbot.addWidget(area)

    textos = [acao.text() for acao in area._menu_contexto(1, 2).actions()
              if not acao.isSeparator()]

    assert textos == [
        "Adicionar comentário aqui", "Recorte temporal", "Ajustar aos dados"
    ]


def test_clique_duplo_retorna_a_visao_inicial(qtbot, monkeypatch):
    area = gx.AreaPlot("Duplo clique")
    qtbot.addWidget(area)
    chamadas = []
    monkeypatch.setattr(area, "ajustar_tudo", lambda: chamadas.append(True))

    class Evento:
        aceito = False

        def accept(self):
            self.aceito = True

    evento = Evento()
    area.mouseDoubleClickEvent(evento)

    assert chamadas == [True]
    assert evento.aceito


def test_comentario_permanece_ao_reabrir_curva(qtbot, monkeypatch):
    curva = gx.Curva.de_series("PT-COM", [0, 1], [10, 20])
    primeira = gx.JanelaGrafico("Primeira")
    qtbot.addWidget(primeira)
    primeira.adicionar_curva(curva)
    monkeypatch.setattr(gx.QInputDialog, "getText", lambda *args: ("evento", True))

    primeira._novo_comentario(1, 20)
    assert len(curva.comentarios) == 1

    segunda = gx.JanelaGrafico("Segunda")
    qtbot.addWidget(segunda)
    segunda.adicionar_curva(curva)

    assert len(segunda.area._anotacoes) == 1
    assert curva.comentarios[0]["texto"] == "evento"


def test_painel_graficos_cria_fecha_e_reencaixa_janelas(qtbot):
    painel = gx.PainelGraficos()
    qtbot.addWidget(painel)
    janela = painel.novo_grafico("Teste")
    assert painel.abas.count() == 1
    assert painel.grafico_atual() is janela

    curva = gx.Curva.de_series("A", [0, 1], [1, 2])
    janela.adicionar_curva(curva)
    janela.minimizar()
    janela.restaurar()
    janela.maximizar()
    janela.restaurar()
    janela.descolar()
    janela.restaurar()

    painel._fechar(janela)
    assert painel.abas.count() == 0
