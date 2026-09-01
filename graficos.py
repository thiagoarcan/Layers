#!/usr/bin/env python3
"""
graficos.py — Camada gráfica do Conversor/Player SCADA.

Implementa os Grupos 1 a 5 dos Recursos Gráficos sobre PyQtGraph:
  Grupo 1 — temas, paletas, cores semânticas, contraste WCAG, tema em JSON
  Grupo 2 — curva como objeto persistente, tipo/eixo/cor/espessura, buffer circular
  Grupo 3 — janelas de gráfico (abas, flutuante, min/max/restaurar, fit, drag-and-drop)
  Grupo 4 — 3 eixos Y, eixo de tempo, sincronia de X, legenda interativa, crosshair,
            tooltip multissérie, hover compartilhado, anotações, isolamento de falha
  Grupo 5 — recorte por drag lines, slider de deslocamento, painel de propriedades

Preparado para a fase de streaming: cada curva guarda os dados num buffer circular
com append O(1), e o repaint é conduzido por um único timer por janela — a chegada
de dado nunca dispara desenho.

Dependências: PySide6, pyqtgraph, numpy
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import (QEvent, QMimeData, QObject, QPoint, QSize, Qt,
                            QTimer, Signal)
from PySide6.QtGui import QAction, QColor, QCursor, QDrag, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox,
                               QDoubleSpinBox, QFileDialog, QFrame, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPushButton, QScrollArea,
                               QSlider, QTabWidget, QToolButton, QVBoxLayout,
                               QWidget)

pg.setConfigOption("antialias", True)
pg.setConfigOption("imageAxisOrder", "row-major")


# =========================================================================== #
# GRUPO 1 — Sistema de temas e cores
# =========================================================================== #

# Item 5: as 9 cores das pranchas têm significado físico fixo.
SIGNIFICADO_PRANCHA = {
    "comprimento_exato": "Comprimento de trecho conhecido com exatidão",
    "celeridade_estimada": "Celeridade estimada a partir do processo",
    "valido": "Resultado dentro do critério de aceitação",
    "invalido": "Resultado reprovado pelo critério",
    "referencia": "Valor normativo ou de projeto",
    "medido": "Amostra medida em campo",
    "modelado": "Saída do modelo hidráulico",
    "residuo": "Diferença entre medido e modelado",
    "incerteza": "Faixa de incerteza associada",
}


@dataclass
class Tema:
    """Item 1: tema visual completo — chrome, plot e semântica num só objeto."""
    nome: str
    rotulo: str
    fundo: str
    fundo_plot: str
    grade: str
    texto: str
    texto_fraco: str
    borda: str
    # cores semânticas (item 3): significado fixo, independem do tema
    sucesso: str
    erro: str
    aviso: str
    selecao: str
    regua: str
    anotacao: str
    crosshair: str
    # item 2: ciclo de 8 cores para curvas novas
    paleta: list[str]
    # item 5: paleta das pranchas de diagnóstico
    prancha: dict[str, str]

    def para_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        return d

    @staticmethod
    def de_dict(d: dict) -> "Tema":
        return Tema(**d)


TEMA_ESCURO = Tema(
    nome="escuro_industrial", rotulo="Escuro industrial",
    fundo="#262626", fundo_plot="#1B1B1B", grade="#3A3A3A",
    texto="#E6E6E6", texto_fraco="#9A9A9A", borda="#3F3F3F",
    sucesso="#3FBF6F", erro="#EE5A5F", aviso="#F5A524",
    selecao="#2F5D3F", regua="#F5A524", anotacao="#8AB4F8", crosshair="#7A7A7A",
    paleta=["#4FA3F7", "#F5A524", "#3FBF6F", "#EE5A5F",
            "#B07CE8", "#26C2C2", "#E87CB0", "#C9CC4A"],
    prancha={"comprimento_exato": "#C9A227", "celeridade_estimada": "#8C6D3F",
             "valido": "#3FBF6F", "invalido": "#EE5A5F", "referencia": "#8AB4F8",
             "medido": "#4FA3F7", "modelado": "#F5A524", "residuo": "#B07CE8",
             "incerteza": "#5A5A5A"},
)

TEMA_CLARO = Tema(
    nome="claro_tecnico", rotulo="Claro técnico",
    fundo="#F3F3F3", fundo_plot="#FFFFFF", grade="#D8D8D8",
    texto="#1F1F1F", texto_fraco="#5E5E5E", borda="#C6C6C6",
    sucesso="#1E7F45", erro="#C0272D", aviso="#8F5400",
    selecao="#CFE6D8", regua="#8F5400", anotacao="#1A4FA0", crosshair="#8A8A8A",
    paleta=["#1A6FC4", "#8F5400", "#1E7F45", "#C0272D",
            "#7A44BE", "#0E8A8A", "#B33A80", "#7A7F14"],
    prancha={"comprimento_exato": "#8A6D1F", "celeridade_estimada": "#5C4526",
             "valido": "#1E7F45", "invalido": "#C0272D", "referencia": "#1A4FA0",
             "medido": "#1A6FC4", "modelado": "#8F5400", "residuo": "#7A44BE",
             "incerteza": "#A8A8A8"},
)

TEMA_CONTRASTE = Tema(
    nome="alto_contraste", rotulo="Alto contraste",
    fundo="#000000", fundo_plot="#000000", grade="#5A5A5A",
    texto="#FFFFFF", texto_fraco="#D0D0D0", borda="#FFFFFF",
    sucesso="#00E676", erro="#FF3B3B", aviso="#FFD500",
    selecao="#004C99", regua="#FFD500", anotacao="#00E5FF", crosshair="#FFFFFF",
    paleta=["#00E5FF", "#FFD500", "#00E676", "#FF3B3B",
            "#D08CFF", "#00FFC8", "#FF8AD8", "#EEFF41"],
    prancha={"comprimento_exato": "#FFD500", "celeridade_estimada": "#FF9E00",
             "valido": "#00E676", "invalido": "#FF3B3B", "referencia": "#00E5FF",
             "medido": "#00E5FF", "modelado": "#FFD500", "residuo": "#D08CFF",
             "incerteza": "#9E9E9E"},
)

TEMAS = {t.nome: t for t in (TEMA_ESCURO, TEMA_CLARO, TEMA_CONTRASTE)}


def _luminancia(cor: str) -> float:
    c = QColor(cor)
    canais = []
    for v in (c.redF(), c.greenF(), c.blueF()):
        canais.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def contraste(cor_a: str, cor_b: str) -> float:
    """Item 4: razão de contraste WCAG entre duas cores (1:1 a 21:1)."""
    la, lb = _luminancia(cor_a), _luminancia(cor_b)
    claro, escuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (escuro + 0.05)


class GerenciadorTema(QObject):
    """
    Item 6: fonte única do tema ativo. Quem desenha se inscreve em tema_mudou e
    se repinta — por isso trocar de tema atualiza gráficos e pranchas juntos.
    """
    tema_mudou = Signal(object)

    def __init__(self, nome: str = "escuro_industrial"):
        super().__init__()
        self._tema = TEMAS[nome]
        self._personalizados: dict[str, Tema] = {}

    @property
    def tema(self) -> Tema:
        return self._tema

    def disponiveis(self) -> dict[str, Tema]:
        return {**TEMAS, **self._personalizados}

    def aplicar(self, nome: str):
        temas = self.disponiveis()
        if nome in temas and temas[nome] is not self._tema:
            self._tema = temas[nome]
            self.tema_mudou.emit(self._tema)

    def definir_cor(self, campo: str, valor: str):
        """Item 7: edição ao vivo — altera um campo e repinta tudo na hora."""
        if not hasattr(self._tema, campo):
            return
        setattr(self._tema, campo, valor)
        self.tema_mudou.emit(self._tema)

    def validar_contraste(self, minimo: float = 4.5) -> list[tuple[str, float]]:
        """Item 4: campos de texto cujo contraste contra o fundo está abaixo do mínimo."""
        problemas = []
        for campo in ("texto", "texto_fraco", "sucesso", "erro", "aviso",
                      "regua", "anotacao"):
            r = contraste(getattr(self._tema, campo), self._tema.fundo_plot)
            if r < minimo:
                problemas.append((campo, r))
        return problemas

    def exportar(self, caminho: Path):
        """Item 8: tema em JSON, versionável e compartilhável."""
        caminho.write_text(json.dumps(self._tema.para_dict(), indent=2,
                                      ensure_ascii=False), encoding="utf-8")

    def importar(self, caminho: Path) -> str:
        d = json.loads(Path(caminho).read_text(encoding="utf-8"))
        tema = Tema.de_dict(d)
        self._personalizados[tema.nome] = tema
        self._tema = tema
        self.tema_mudou.emit(tema)
        return tema.nome


TEMA = GerenciadorTema()


# =========================================================================== #
# GRUPO 2 — Modelo de dados de curvas
# =========================================================================== #

class BufferCircular:
    """
    Armazenamento pré-alocado com append O(1) — a base da fase de streaming.
    Escreve em posição fixa e só reordena na leitura, então a taxa de ingestão
    não depende do tamanho do histórico.
    """

    def __init__(self, capacidade: int = 1_000_000):
        self.capacidade = int(capacidade)
        self._x = np.empty(self.capacidade, dtype="float64")
        self._y = np.empty(self.capacidade, dtype="float64")
        self._n = 0        # total já escrito
        self._inicio = 0   # índice do mais antigo quando circulou

    def __len__(self) -> int:
        return min(self._n, self.capacidade)

    @property
    def cheio(self) -> bool:
        return self._n >= self.capacidade

    def limpar(self):
        self._n = 0
        self._inicio = 0

    def append(self, x: float, y: float):
        i = self._n % self.capacidade
        self._x[i] = x
        self._y[i] = y
        self._n += 1
        if self._n > self.capacidade:
            self._inicio = self._n % self.capacidade

    def estender(self, xs: np.ndarray, ys: np.ndarray):
        xs = np.asarray(xs, dtype="float64").ravel()
        ys = np.asarray(ys, dtype="float64").ravel()
        if xs.size != ys.size:
            raise ValueError("xs e ys precisam ter o mesmo tamanho")
        if xs.size >= self.capacidade:            # só o rabo cabe
            xs, ys = xs[-self.capacidade:], ys[-self.capacidade:]
        i = self._n % self.capacidade
        fim = i + xs.size
        if fim <= self.capacidade:
            self._x[i:fim] = xs
            self._y[i:fim] = ys
        else:
            corte = self.capacidade - i
            self._x[i:] = xs[:corte]
            self._y[i:] = ys[:corte]
            self._x[:fim - self.capacidade] = xs[corte:]
            self._y[:fim - self.capacidade] = ys[corte:]
        self._n += xs.size
        if self._n > self.capacidade:
            self._inicio = self._n % self.capacidade

    def dados(self) -> tuple[np.ndarray, np.ndarray]:
        n = len(self)
        if n == 0:
            return np.empty(0), np.empty(0)
        if self._n <= self.capacidade:
            return self._x[:n], self._y[:n]
        return (np.concatenate((self._x[self._inicio:], self._x[:self._inicio])),
                np.concatenate((self._y[self._inicio:], self._y[:self._inicio])))


TIPO_LINHA = "linha"
TIPO_SCATTER = "scatter"
EIXOS = ("Y1", "Y2", "Y3")


@dataclass
class Curva:
    """
    Item 10: a curva existe fora dos gráficos. Sai de um plot e continua no
    catálogo, com todas as suas propriedades visuais preservadas.
    """
    nome: str
    buffer: BufferCircular
    cor: str = "#4FA3F7"
    tipo: str = TIPO_LINHA
    eixo: str = "Y1"
    espessura: float = 1.5          # item 13
    visivel: bool = True            # item 15
    unidade: str = ""               # item 25
    grandeza: str = ""
    eixo_x_tempo: bool = True       # item 30
    deslocamento_s: float = 0.0     # item 48 — offset visual, não altera dados
    limite_t: float | None = None   # revelação progressiva no replay
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    # -------------------------------------------------------------- fábricas

    @staticmethod
    def de_series(nome: str, x, y, capacidade: int | None = None, **kw) -> "Curva":
        """Item 17: aceita qualquer array numérico e normaliza para float64."""
        x = np.asarray(x)
        if np.issubdtype(x.dtype, np.datetime64):
            x = x.astype("datetime64[ns]").astype("int64") / 1e9
        elif len(x) and isinstance(x[0], datetime):
            x = np.array([t.timestamp() for t in x], dtype="float64")
        x = np.asarray(x, dtype="float64").ravel()
        y = np.asarray(y, dtype="float64").ravel()
        buf = BufferCircular(capacidade or max(1024, x.size * 2))
        buf.estender(x, y)
        return Curva(nome=nome, buffer=buf, **kw)

    @staticmethod
    def de_dataframe(nome: str, df, col_x: str = "timestamp",
                     col_y: str = "valor", **kw) -> "Curva":
        return Curva.de_series(nome, df[col_x].values, df[col_y].values, **kw)

    # ----------------------------------------------------------------- dados

    def dados_plot(self, ignorar_limite: bool = False
                   ) -> tuple[np.ndarray, np.ndarray]:
        """
        Dados prontos para desenhar. `limite_t` corta por fatia de array — uma
        view, não uma cópia — então avançar o replay não realoca nada, mesmo
        com milhões de amostras no buffer.
        """
        x, y = self.buffer.dados()
        if self.deslocamento_s:
            x = x + self.deslocamento_s
        if self.limite_t is not None and not ignorar_limite and x.size:
            i = int(np.searchsorted(x, self.limite_t, side="right"))
            x, y = x[:i], y[:i]
        return x, y

    def rotulo_eixo(self) -> str:
        """Item 25: 'Pressão (bar)' a partir dos metadados, sem digitar nada."""
        if self.grandeza and self.unidade:
            return f"{self.grandeza} ({self.unidade})"
        return self.grandeza or self.unidade or self.nome

    def ponto_proximo(self, x_alvo: float) -> tuple[float, float] | None:
        """
        Item 16: busca binária — O(log n). Em 200 mil pontos são ~18 comparações,
        então o tooltip responde igual com mil ou com milhões de amostras.
        """
        x, y = self.dados_plot()
        if x.size == 0:
            return None
        i = int(np.searchsorted(x, x_alvo))
        if i <= 0:
            return float(x[0]), float(y[0])
        if i >= x.size:
            return float(x[-1]), float(y[-1])
        j = i if abs(x[i] - x_alvo) < abs(x[i - 1] - x_alvo) else i - 1
        return float(x[j]), float(y[j])

    # ------------------------------------------------------------- streaming

    def append(self, x: float, y: float):
        self.buffer.append(x, y)

    def estender(self, xs, ys):
        self.buffer.estender(xs, ys)


@dataclass
class Artefato:
    """
    Item 18: contrato único de saída dos cálculos de engenharia. Qualquer módulo
    (hidráulica, PipeID, perturbações) devolve isto e o gráfico já sabe plotar.
    """
    titulo: str
    curvas: list[Curva]
    status: str = "ok"               # ok | alerta | erro
    mensagem: str = ""
    unidades: dict[str, str] = field(default_factory=dict)
    metadados: dict = field(default_factory=dict)


class CatalogoCurvas(QObject):
    """Item 2 + 10: guarda todas as curvas da sessão e distribui cores da paleta."""
    curva_adicionada = Signal(object)
    curva_removida = Signal(str)
    curva_alterada = Signal(object)

    def __init__(self):
        super().__init__()
        self._curvas: dict[str, Curva] = {}
        self._proxima_cor = 0

    def __len__(self) -> int:
        return len(self._curvas)

    def __iter__(self):
        return iter(self._curvas.values())

    def obter(self, id_curva: str) -> Curva | None:
        return self._curvas.get(id_curva)

    def cor_automatica(self) -> str:
        paleta = TEMA.tema.paleta
        cor = paleta[self._proxima_cor % len(paleta)]
        self._proxima_cor += 1
        return cor

    def adicionar(self, curva: Curva, cor_automatica: bool = True) -> Curva:
        if cor_automatica:
            curva.cor = self.cor_automatica()
        self._curvas[curva.id] = curva
        self.curva_adicionada.emit(curva)
        return curva

    def remover(self, id_curva: str):
        if self._curvas.pop(id_curva, None) is not None:
            self.curva_removida.emit(id_curva)

    def notificar(self, curva: Curva):
        self.curva_alterada.emit(curva)

    def adicionar_artefato(self, art: Artefato) -> list[Curva]:
        return [self.adicionar(c) for c in art.curvas]


CATALOGO = CatalogoCurvas()


# =========================================================================== #
# GRUPO 4 — Área de plotagem
# =========================================================================== #

class AreaPlot(pg.PlotWidget):
    """
    Núcleo de renderização: 3 eixos Y, eixo de tempo, crosshair, tooltip
    multissérie, anotações e menu de contexto.
    """
    mouse_moveu = Signal(float)        # x em coordenadas de dados
    mouse_saiu = Signal()
    faixa_x_mudou = Signal(float, float)
    pediu_comentario = Signal(float, float)
    pediu_acao = Signal(str, float, float)

    def __init__(self, titulo: str = ""):
        self._eixo_tempo = pg.DateAxisItem(orientation="bottom")  # item 30
        super().__init__(axisItems={"bottom": self._eixo_tempo})
        self.titulo = titulo
        self._curvas: dict[str, Curva] = {}
        self._itens: dict[str, pg.PlotDataItem] = {}
        self._falhadas: set[str] = set()     # item 45
        self._anotacoes: list[pg.TextItem] = []
        self._sujo = True
        self._fechado = False
        self._silencio_sinal = False
        self.janela_rolagem_s: float | None = None   # rolagem no modo streaming

        pi = self.getPlotItem()
        pi.showGrid(x=True, y=True, alpha=0.25)
        pi.setMenuEnabled(False)          # menu próprio (item 41)
        pi.setClipToView(True)            # não desenha fora da janela visível
        pi.setDownsampling(auto=True, mode="peak")  # preserva picos e vales

        self._montar_eixos_extras()
        self._montar_crosshair()
        self._montar_recorte()

        self.setMouseTracking(True)
        self.scene().sigMouseMoved.connect(self._ao_mover)
        pi.vb.sigXRangeChanged.connect(self._ao_mudar_x)

        # Item 26 + streaming: um único timer conduz o repaint. A chegada de
        # dado marca o estado como sujo; quem redesenha é o relógio.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._repintar_se_sujo)
        self._timer.start(33)                       # ~30 Hz

        self.aplicar_tema(TEMA.tema)
        TEMA.tema_mudou.connect(self.aplicar_tema)

    # ------------------------------------------------------- eixos adicionais

    def _montar_eixos_extras(self):
        """Item 12 / 29: Y2 e Y3 em ViewBoxes próprios, com X ligado ao principal."""
        pi = self.getPlotItem()
        self._vbs = {"Y1": pi.vb}
        self._eixos = {}
        for i, nome in enumerate(("Y2", "Y3"), start=1):
            vb = pg.ViewBox()
            eixo = pg.AxisItem("right")
            pi.layout.addItem(eixo, 2, 2 + i)
            pi.scene().addItem(vb)
            eixo.linkToView(vb)
            vb.setXLink(pi.vb)
            eixo.setZValue(-10000)
            self._vbs[nome] = vb
            self._eixos[nome] = eixo
            eixo.hide()
        pi.vb.sigResized.connect(self._sincronizar_geometria)

    def _sincronizar_geometria(self):
        principal = self.getPlotItem().vb
        for nome in ("Y2", "Y3"):
            self._vbs[nome].setGeometry(principal.sceneBoundingRect())
            self._vbs[nome].linkedViewChanged(principal, self._vbs[nome].XAxis)

    # ---------------------------------------------------------- sobreposições

    def _montar_crosshair(self):
        """Itens 35, 37, 39: mira, tooltip multissérie e marcador no eixo X."""
        cor = TEMA.tema.crosshair
        caneta = pg.mkPen(cor, width=1, style=Qt.DashLine)
        self._v = pg.InfiniteLine(angle=90, movable=False, pen=caneta)
        self._h = pg.InfiniteLine(angle=0, movable=False, pen=caneta)
        for ln in (self._v, self._h):
            ln.setZValue(1000)
            self.addItem(ln, ignoreBounds=True)
            ln.hide()

        self._tooltip = pg.TextItem(anchor=(0, 1), fill=pg.mkBrush(0, 0, 0, 205))
        self._tooltip.setZValue(1001)
        self.addItem(self._tooltip, ignoreBounds=True)
        self._tooltip.hide()

        # marcador de X sobre o eixo (item 39)
        self._tag_x = pg.TextItem(anchor=(0.5, 0), color="#FFFFFF",
                                  fill=pg.mkBrush(TEMA.tema.regua))
        self._tag_x.setZValue(1002)
        self.addItem(self._tag_x, ignoreBounds=True)
        self._tag_x.hide()

        # linha vertical vinda de outro gráfico (item 38)
        self._v_remota = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen(TEMA.tema.regua, width=1, style=Qt.DotLine))
        self._v_remota.setZValue(999)
        self.addItem(self._v_remota, ignoreBounds=True)
        self._v_remota.hide()

    def _montar_recorte(self):
        """Item 47: par de linhas arrastáveis para recorte temporal."""
        self._regiao = pg.LinearRegionItem(
            brush=pg.mkBrush(245, 165, 36, 38),
            pen=pg.mkPen(TEMA.tema.regua, width=1.5), movable=True)
        self._regiao.setZValue(-100)
        self._regiao.hide()
        self.addItem(self._regiao, ignoreBounds=True)

    # ------------------------------------------------------------------ tema

    def aplicar_tema(self, tema: Tema):
        self.setBackground(tema.fundo_plot)
        pi = self.getPlotItem()
        for lado in ("left", "bottom", "right", "top"):
            eixo = pi.getAxis(lado)
            eixo.setPen(pg.mkPen(tema.borda))
            eixo.setTextPen(pg.mkPen(tema.texto_fraco))
        for eixo in self._eixos.values():
            eixo.setPen(pg.mkPen(tema.borda))
            eixo.setTextPen(pg.mkPen(tema.texto_fraco))
        caneta = pg.mkPen(tema.crosshair, width=1, style=Qt.DashLine)
        self._v.setPen(caneta)
        self._h.setPen(caneta)
        self._tag_x.fill = pg.mkBrush(tema.regua)
        self._regiao.setBrush(pg.mkBrush(QColor(tema.regua).red(),
                                         QColor(tema.regua).green(),
                                         QColor(tema.regua).blue(), 38))
        for texto in self._anotacoes:
            texto.setColor(tema.anotacao)
        self._sujo = True

    def closeEvent(self, evento):
        self._fechado = True
        self._timer.stop()
        super().closeEvent(evento)

    # ---------------------------------------------------------------- curvas

    def adicionar_curva(self, curva: Curva, ajustar: bool = True):
        if curva.id in self._curvas:
            return
        self._curvas[curva.id] = curva
        item = pg.PlotDataItem()
        item.setZValue(10)
        self._itens[curva.id] = item
        alvo = self._vbs.get(curva.eixo, self._vbs["Y1"])
        (self.addItem(item) if curva.eixo == "Y1" else alvo.addItem(item))
        if curva.eixo in self._eixos:
            self._eixos[curva.eixo].show()
        self._sujo = True
        self._atualizar_rotulos()
        if ajustar:
            QTimer.singleShot(0, self.ajustar_tudo)   # item 23

    def remover_curva(self, id_curva: str):
        curva = self._curvas.pop(id_curva, None)
        item = self._itens.pop(id_curva, None)
        if item is None:
            return
        (self.removeItem(item) if curva.eixo == "Y1"
         else self._vbs[curva.eixo].removeItem(item))
        self._falhadas.discard(id_curva)
        for nome, eixo in self._eixos.items():
            if not any(c.eixo == nome for c in self._curvas.values()):
                eixo.hide()
        self._sujo = True
        self._atualizar_rotulos()

    def mover_para_eixo(self, curva: Curva, eixo_novo: str):
        """Item 12: reatribuir eixo sem recriar a curva."""
        if eixo_novo not in self._vbs or curva.id not in self._itens:
            return
        item = self._itens[curva.id]
        (self.removeItem(item) if curva.eixo == "Y1"
         else self._vbs[curva.eixo].removeItem(item))
        curva.eixo = eixo_novo
        (self.addItem(item) if eixo_novo == "Y1"
         else self._vbs[eixo_novo].addItem(item))
        for nome, eixo in self._eixos.items():
            eixo.setVisible(any(c.eixo == nome for c in self._curvas.values()))
        self._sujo = True
        self._atualizar_rotulos()

    def marcar_sujo(self):
        """Chamado pela ingestão de streaming — barato de propósito."""
        self._sujo = True

    def _repintar_se_sujo(self):
        if self._fechado or not self._sujo:
            return
        self._sujo = False
        for id_curva, curva in self._curvas.items():
            item = self._itens[id_curva]
            if not curva.visivel:
                item.setData([], [])
                continue
            try:
                x, y = curva.dados_plot()
                if curva.tipo == TIPO_SCATTER:
                    item.setData(x, y, pen=None, symbol="o", symbolSize=5,
                                 symbolBrush=curva.cor, symbolPen=None)
                else:
                    item.setData(x, y, pen=pg.mkPen(curva.cor,
                                                    width=curva.espessura),
                                 symbol=None)
                self._falhadas.discard(id_curva)
            except Exception as exc:
                # Item 45: a curva ruim é isolada; as outras seguem desenhando.
                if id_curva not in self._falhadas:
                    self._falhadas.add(id_curva)
                    print(f"[gráfico] curva '{curva.nome}' ignorada: {exc}")
                item.setData([], [])
        self._rolar_janela()

    def _rolar_janela(self):
        """
        A rolagem acompanha o repaint, não a ingestão: mexer no eixo é caro e
        só precisa acontecer uma vez por quadro, não uma vez por amostra.
        """
        if not self.janela_rolagem_s:
            return
        ultimo = None
        for curva in self._curvas.values():
            if not curva.visivel:
                continue
            x, _ = curva.dados_plot()
            if x.size:
                ultimo = x[-1] if ultimo is None else max(ultimo, x[-1])
        if ultimo is not None:
            self.definir_faixa_x(float(ultimo) - self.janela_rolagem_s, float(ultimo))

    def _atualizar_rotulos(self):
        """Item 25: cada eixo recebe o rótulo das curvas que hospeda."""
        pi = self.getPlotItem()
        por_eixo: dict[str, list[str]] = {e: [] for e in EIXOS}
        for c in self._curvas.values():
            rot = c.rotulo_eixo()
            if rot not in por_eixo[c.eixo]:
                por_eixo[c.eixo].append(rot)
        pi.setLabel("left", " · ".join(por_eixo["Y1"]) or "")
        for nome in ("Y2", "Y3"):
            self._eixos[nome].setLabel(" · ".join(por_eixo[nome]) or "")
        tempo = any(c.eixo_x_tempo for c in self._curvas.values())
        pi.setLabel("bottom", "" if tempo else "Amostra")

    def ajustar_tudo(self):
        """Item 23: fit automático em todos os eixos."""
        if self._fechado:
            return
        self._repintar_se_sujo()
        self.getPlotItem().enableAutoRange()
        self.getPlotItem().autoRange()
        for nome in ("Y2", "Y3"):
            self._vbs[nome].enableAutoRange(axis=pg.ViewBox.YAxis)
            self._vbs[nome].autoRange()

    # ------------------------------------------------------------ interação

    def _ao_mover(self, pos):
        pi = self.getPlotItem()
        if not pi.sceneBoundingRect().contains(pos):
            self._esconder_hover()
            self.mouse_saiu.emit()
            return
        ponto = pi.vb.mapSceneToView(pos)          # item 36: coords de dados
        self._v.setPos(ponto.x())
        self._h.setPos(ponto.y())
        self._v.show()
        self._h.show()
        self._mostrar_tooltip(ponto.x(), ponto.y())
        self.mouse_moveu.emit(ponto.x())

    def _mostrar_tooltip(self, x: float, y: float):
        """Item 37: um instante, todas as curvas visíveis."""
        linhas = []
        tempo = any(c.eixo_x_tempo for c in self._curvas.values())
        rotulo_x = (datetime.fromtimestamp(x).strftime("%d/%m/%Y %H:%M:%S")
                    if tempo else f"{x:.4g}")
        linhas.append(f"<b>{rotulo_x}</b>")
        for curva in self._curvas.values():
            if not curva.visivel or curva.id in self._falhadas:
                continue
            p = curva.ponto_proximo(x)
            if p is None:
                continue
            unid = f" {curva.unidade}" if curva.unidade else ""
            linhas.append(
                f'<span style="color:{curva.cor}">&#9632;</span> '
                f"{curva.nome}: {p[1]:,.4g}{unid}".replace(",", "."))
        if len(linhas) == 1:
            self._tooltip.hide()
            self._tag_x.hide()
            return
        self._tooltip.setHtml(
            f'<div style="color:{TEMA.tema.texto};font-size:11px">'
            + "<br>".join(linhas) + "</div>")
        self._tooltip.setPos(x, y)
        self._tooltip.show()

        faixa_y = self.getPlotItem().vb.viewRange()[1]
        self._tag_x.setText(rotulo_x.split(" ")[-1] if tempo else rotulo_x)
        self._tag_x.setPos(x, faixa_y[0])
        self._tag_x.show()

    def _esconder_hover(self):
        for it in (self._v, self._h, self._tooltip, self._tag_x):
            it.hide()

    def marcar_x_remoto(self, x: float | None):
        """Item 38: linha espelhada quando o mouse está em outro gráfico."""
        if x is None:
            self._v_remota.hide()
            return
        self._v_remota.setPos(x)
        self._v_remota.show()

    def _ao_mudar_x(self, _vb, faixa):
        if not self._silencio_sinal:
            self.faixa_x_mudou.emit(float(faixa[0]), float(faixa[1]))

    def definir_faixa_x(self, x0: float, x1: float):
        """Aplicada pela sincronia; silencia o sinal para não realimentar."""
        self._silencio_sinal = True
        self.getPlotItem().vb.setXRange(x0, x1, padding=0)
        self._silencio_sinal = False

    # ---------------------------------------------------------- menu (it. 41)

    def contextMenuEvent(self, evento):
        pi = self.getPlotItem()
        ponto = pi.vb.mapSceneToView(self.mapToScene(evento.pos()))
        x, y = ponto.x(), ponto.y()

        menu = QMenu(self)
        menu.addAction("Comparação multivariável",
                       lambda: self.pediu_acao.emit("comparacao", x, y))
        menu.addAction("Hidráulica de oleodutos",
                       lambda: self.pediu_acao.emit("hidraulica", x, y))
        menu.addSeparator()
        menu.addAction("Adicionar comentário aqui",
                       lambda: self.pediu_comentario.emit(x, y))
        menu.addSeparator()
        acao_rec = menu.addAction("Recorte temporal")
        acao_rec.setCheckable(True)
        acao_rec.setChecked(self._regiao.isVisible())
        acao_rec.toggled.connect(self.alternar_recorte)
        menu.addAction("Ajustar aos dados", self.ajustar_tudo)
        menu.exec(evento.globalPos())

    # ------------------------------------------------- anotações e marcadores

    def adicionar_anotacao(self, x: float, y: float, texto: str):
        """Itens 40 e 42: texto ancorado em coordenadas de dados."""
        item = pg.TextItem(texto, color=TEMA.tema.anotacao, anchor=(0, 1),
                           border=pg.mkPen(TEMA.tema.anotacao, width=1),
                           fill=pg.mkBrush(0, 0, 0, 160))
        item.setPos(x, y)
        item.setZValue(900)
        self.addItem(item, ignoreBounds=True)
        self._anotacoes.append(item)
        return item

    def limpar_anotacoes(self):
        for it in self._anotacoes:
            self.removeItem(it)
        self._anotacoes.clear()

    def linha_vertical(self, x: float, cor: str | None = None):
        """Item 43: marcador vertical permanente."""
        ln = pg.InfiniteLine(pos=x, angle=90, movable=False,
                             pen=pg.mkPen(cor or TEMA.tema.regua, width=1.5))
        self.addItem(ln, ignoreBounds=True)
        return ln

    def linha_horizontal(self, y: float, cor: str | None = None, rotulo: str = ""):
        """Item 44: limiar normativo ou valor de referência."""
        ln = pg.InfiniteLine(pos=y, angle=0, movable=False,
                             pen=pg.mkPen(cor or TEMA.tema.aviso,
                                          width=1.5, style=Qt.DashLine),
                             label=rotulo or None,
                             labelOpts={"position": 0.05,
                                        "color": cor or TEMA.tema.aviso})
        self.addItem(ln, ignoreBounds=True)
        return ln

    # --------------------------------------------------------- recorte (47)

    def alternar_recorte(self, ligado: bool):
        if ligado:
            x0, x1 = self.getPlotItem().vb.viewRange()[0]
            largura = (x1 - x0) * 0.25
            self._regiao.setRegion((x0 + largura, x1 - largura))
            self._regiao.show()
        else:
            self._regiao.hide()

    def faixa_recorte(self) -> tuple[float, float] | None:
        if not self._regiao.isVisible():
            return None
        a, b = self._regiao.getRegion()
        return float(a), float(b)

    # -------------------------------------------------- drop de curva (it. 24)

    def dragEnterEvent(self, evento):
        if evento.mimeData().hasFormat("application/x-curva-id"):
            evento.acceptProposedAction()

    def dragMoveEvent(self, evento):
        if evento.mimeData().hasFormat("application/x-curva-id"):
            evento.acceptProposedAction()

    def dropEvent(self, evento):
        dados = evento.mimeData().data("application/x-curva-id")
        id_curva = bytes(dados).decode()
        curva = CATALOGO.obter(id_curva)
        if curva is not None:
            self.adicionar_curva(curva)
            evento.acceptProposedAction()


# =========================================================================== #
# GRUPO 4 — Legenda interativa (itens 33 e 34)
# =========================================================================== #

class LegendaInterativa(QFrame):
    """Sobreposição no canto superior direito; clique direito abre as ações."""
    pediu_propriedades = Signal(object)
    pediu_deslocamento = Signal(object)
    pediu_remocao = Signal(object)
    pediu_calculos = Signal(object)
    visibilidade_mudou = Signal(object)

    def __init__(self, area: AreaPlot):
        super().__init__(area)
        self.area = area
        self.setObjectName("legenda")
        self.setCursor(Qt.ArrowCursor)
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(8, 6, 8, 6)
        self._v.setSpacing(3)
        self._itens: dict[str, QLabel] = {}
        self.aplicar_tema(TEMA.tema)
        TEMA.tema_mudou.connect(self.aplicar_tema)
        self.hide()

    def aplicar_tema(self, tema: Tema):
        self.setStyleSheet(
            f"#legenda {{ background: rgba(0,0,0,150); "
            f"border: 1px solid {tema.borda}; border-radius: 3px; }}"
            f"QLabel {{ color: {tema.texto}; font-size: 11px; background: transparent; }}")

    def reconstruir(self, curvas: list[Curva]):
        # remover do layout explicitamente: deleteLater() só age quando o event
        # loop roda, e até lá o widget continua ocupando espaço na legenda
        for lbl in self._itens.values():
            self._v.removeWidget(lbl)
            lbl.setParent(None)
            lbl.deleteLater()
        self._itens.clear()
        for curva in curvas:
            lbl = QLabel(self._html(curva))
            lbl.setContextMenuPolicy(Qt.CustomContextMenu)
            lbl.customContextMenuRequested.connect(
                lambda p, c=curva, w=None: self._menu(c))
            lbl.setCursor(Qt.PointingHandCursor)
            self._v.addWidget(lbl)
            self._itens[curva.id] = lbl
        self.setVisible(bool(curvas))
        self.adjustSize()
        self.reposicionar()

    def atualizar_item(self, curva: Curva):
        lbl = self._itens.get(curva.id)
        if lbl:
            lbl.setText(self._html(curva))

    @staticmethod
    def _html(curva: Curva) -> str:
        opacidade = "1.0" if curva.visivel else "0.35"
        traco = "line-through" if not curva.visivel else "none"
        return (f'<span style="color:{curva.cor};opacity:{opacidade}">&#9632;</span> '
                f'<span style="text-decoration:{traco};opacity:{opacidade}">'
                f'{curva.nome}</span>')

    def _menu(self, curva: Curva):
        m = QMenu(self)
        a = m.addAction("Ocultar" if curva.visivel else "Mostrar")
        a.triggered.connect(lambda: self.visibilidade_mudou.emit(curva))
        m.addAction("Slider de deslocamento…",
                    lambda: self.pediu_deslocamento.emit(curva))
        m.addAction("Propriedades…", lambda: self.pediu_propriedades.emit(curva))
        m.addAction("Cálculos…", lambda: self.pediu_calculos.emit(curva))
        m.addSeparator()
        m.addAction("Remover do gráfico", lambda: self.pediu_remocao.emit(curva))
        m.exec(QCursor.pos())

    def reposicionar(self):
        if self.parent():
            self.move(max(6, self.parent().width() - self.width() - 14), 10)


# =========================================================================== #
# GRUPO 5 — Painéis flutuantes
# =========================================================================== #

def posicionar_perto(painel: QWidget, origem: QWidget):
    """
    Item 50: encosta o painel na origem sem cobrir a área de dados; se não
    couber de nenhum lado, centraliza na tela.
    """
    tela = QApplication.primaryScreen().availableGeometry()
    canto = origem.mapToGlobal(QPoint(origem.width(), 0))
    x, y = canto.x() + 8, canto.y() + 8
    if x + painel.width() > tela.right():
        esq = origem.mapToGlobal(QPoint(0, 0))
        x = esq.x() - painel.width() - 8
    if x < tela.left() or x + painel.width() > tela.right():
        x = tela.center().x() - painel.width() // 2
        y = tela.center().y() - painel.height() // 2
    y = min(max(y, tela.top() + 8), tela.bottom() - painel.height() - 8)
    painel.move(x, y)


class PainelPropriedades(QWidget):
    """Item 49: cor, espessura, tipo, eixo e visibilidade num só lugar."""
    alterou = Signal(object)

    def __init__(self, curva: Curva, area: AreaPlot, pai=None):
        super().__init__(pai, Qt.Tool)
        self.curva = curva
        self.area = area
        self.setWindowTitle(f"Propriedades — {curva.nome}")
        self.setMinimumWidth(280)

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        linha_cor = QHBoxLayout()
        linha_cor.addWidget(QLabel("Cor"))
        self.b_cor = QPushButton()
        self.b_cor.setFixedSize(52, 22)
        self.b_cor.clicked.connect(self._escolher_cor)
        self._pintar_botao()
        linha_cor.addWidget(self.b_cor)
        linha_cor.addStretch(1)
        v.addLayout(linha_cor)

        v.addWidget(QLabel("Espessura"))
        linha_esp = QHBoxLayout()
        self.sl_esp = QSlider(Qt.Horizontal)
        self.sl_esp.setRange(5, 100)                 # 0,5 a 10,0 px
        self.sl_esp.setValue(int(curva.espessura * 10))
        self.lbl_esp = QLabel(f"{curva.espessura:.1f} px")
        self.lbl_esp.setFixedWidth(52)
        self.sl_esp.valueChanged.connect(self._mudar_espessura)
        linha_esp.addWidget(self.sl_esp, 1)
        linha_esp.addWidget(self.lbl_esp)
        v.addLayout(linha_esp)

        linha_tipo = QHBoxLayout()
        linha_tipo.addWidget(QLabel("Tipo"))
        self.cb_tipo = QComboBox()
        self.cb_tipo.addItems(["Linha", "Scatter"])
        self.cb_tipo.setCurrentIndex(0 if curva.tipo == TIPO_LINHA else 1)
        self.cb_tipo.currentIndexChanged.connect(self._mudar_tipo)
        linha_tipo.addWidget(self.cb_tipo, 1)
        v.addLayout(linha_tipo)

        linha_eixo = QHBoxLayout()
        linha_eixo.addWidget(QLabel("Eixo Y"))
        self.cb_eixo = QComboBox()
        self.cb_eixo.addItems(list(EIXOS))
        self.cb_eixo.setCurrentText(curva.eixo)
        self.cb_eixo.currentTextChanged.connect(self._mudar_eixo)
        linha_eixo.addWidget(self.cb_eixo, 1)
        v.addLayout(linha_eixo)

        self.chk_vis = QCheckBox("Visível no gráfico")
        self.chk_vis.setChecked(curva.visivel)
        self.chk_vis.toggled.connect(self._mudar_visibilidade)
        v.addWidget(self.chk_vis)

    def _pintar_botao(self):
        self.b_cor.setStyleSheet(
            f"background:{self.curva.cor}; border:1px solid #666; border-radius:2px;")

    def _escolher_cor(self):
        cor = QColorDialog.getColor(QColor(self.curva.cor), self, "Cor da curva")
        if cor.isValid():
            self.curva.cor = cor.name()
            self._pintar_botao()
            self._notificar()

    def _mudar_espessura(self, valor: int):
        self.curva.espessura = valor / 10.0
        self.lbl_esp.setText(f"{self.curva.espessura:.1f} px")
        self._notificar()

    def _mudar_tipo(self, indice: int):
        self.curva.tipo = TIPO_LINHA if indice == 0 else TIPO_SCATTER
        self._notificar()

    def _mudar_eixo(self, texto: str):
        self.area.mover_para_eixo(self.curva, texto)
        self._notificar()

    def _mudar_visibilidade(self, ligado: bool):
        self.curva.visivel = ligado
        self._notificar()

    def _notificar(self):
        self.area.marcar_sujo()
        CATALOGO.notificar(self.curva)
        self.alterou.emit(self.curva)


class PainelDeslocamento(QWidget):
    """
    Item 48: desloca a curva no tempo só para leitura. Os dados no buffer não
    são tocados — o offset entra na hora de plotar, então o reset é exato.
    """
    alterou = Signal(object)

    def __init__(self, curva: Curva, area: AreaPlot, pai=None):
        super().__init__(pai, Qt.Tool)
        self.curva = curva
        self.area = area
        self.setWindowTitle(f"Deslocamento — {curva.nome}")
        self.setMinimumWidth(330)

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)
        v.addWidget(QLabel("Deslocar no tempo (minutos)"))

        linha = QHBoxLayout()
        self.sl = QSlider(Qt.Horizontal)
        self.sl.setRange(-1440, 1440)                 # ±24 h
        self.sl.setValue(int(curva.deslocamento_s / 60))
        self.sl.valueChanged.connect(self._mudar)
        self.sp = QDoubleSpinBox()
        self.sp.setRange(-1440, 1440)
        self.sp.setDecimals(2)
        self.sp.setValue(curva.deslocamento_s / 60)
        self.sp.setFixedWidth(90)
        self.sp.valueChanged.connect(self._mudar_spin)
        linha.addWidget(self.sl, 1)
        linha.addWidget(self.sp)
        v.addLayout(linha)

        b = QPushButton("Restaurar original")
        b.clicked.connect(self._resetar)
        v.addWidget(b)

    def _mudar(self, minutos: int):
        self.curva.deslocamento_s = minutos * 60.0
        self.sp.blockSignals(True)
        self.sp.setValue(minutos)
        self.sp.blockSignals(False)
        self._aplicar()

    def _mudar_spin(self, minutos: float):
        self.curva.deslocamento_s = minutos * 60.0
        self.sl.blockSignals(True)
        self.sl.setValue(int(minutos))
        self.sl.blockSignals(False)
        self._aplicar()

    def _resetar(self):
        self.curva.deslocamento_s = 0.0
        self.sl.setValue(0)
        self.sp.setValue(0)
        self._aplicar()

    def _aplicar(self):
        self.area.marcar_sujo()
        self.alterou.emit(self.curva)


# =========================================================================== #
# GRUPO 3 — Janela de gráfico
# =========================================================================== #

class JanelaGrafico(QFrame):
    """
    Itens 19 a 22: barra de título própria, botões de minimizar, maximizar,
    restaurar e descolar. Descolada, vira janela do sistema (multi-monitor).
    """
    pediu_maximizar = Signal(object)
    pediu_restaurar = Signal(object)
    pediu_descolar = Signal(object)
    pediu_fechar = Signal(object)
    estado_mudou = Signal(object)

    def __init__(self, titulo: str = "Gráfico"):
        super().__init__()
        self.setObjectName("janela_grafico")
        self.titulo = titulo
        self.estado = "encaixado"      # encaixado | minimizado | maximizado | flutuante
        self.setAcceptDrops(True)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.barra = self._montar_barra()
        v.addWidget(self.barra)

        self.area = AreaPlot(titulo)
        self.area.setAcceptDrops(True)
        v.addWidget(self.area, 1)

        self.legenda = LegendaInterativa(self.area)
        self.legenda.visibilidade_mudou.connect(self._alternar_visibilidade)
        self.legenda.pediu_remocao.connect(self._remover_curva)
        self.legenda.pediu_propriedades.connect(self._abrir_propriedades)
        self.legenda.pediu_deslocamento.connect(self._abrir_deslocamento)

        self.area.pediu_comentario.connect(self._novo_comentario)
        self._paineis: list[QWidget] = []

        self.aplicar_tema(TEMA.tema)
        TEMA.tema_mudou.connect(self.aplicar_tema)

    # ------------------------------------------------------------------ chrome

    def _montar_barra(self) -> QWidget:
        barra = QFrame()
        barra.setObjectName("barra_grafico")
        barra.setFixedHeight(26)
        h = QHBoxLayout(barra)
        h.setContentsMargins(8, 0, 4, 0)
        h.setSpacing(2)

        self.lbl_titulo = QLabel(self.titulo)
        self.lbl_titulo.setObjectName("titulo_grafico")
        h.addWidget(self.lbl_titulo)
        h.addStretch(1)

        self.chk_sync = QCheckBox("Sincronizar X")     # item 32
        self.chk_sync.setChecked(True)
        h.addWidget(self.chk_sync)
        h.addSpacing(6)

        for glifo, dica, slot in (
                ("⤢", "Ajustar aos dados", lambda: self.area.ajustar_tudo()),
                ("▁", "Minimizar", self.minimizar),
                ("□", "Maximizar", self.maximizar),
                ("⧉", "Descolar para janela própria", self.descolar),
                ("✕", "Fechar", lambda: self.pediu_fechar.emit(self))):
            b = QToolButton()
            b.setText(glifo)
            b.setToolTip(dica)
            b.setFixedSize(22, 20)
            b.setObjectName("botao_grafico")
            b.clicked.connect(slot)
            h.addWidget(b)
        return barra

    def aplicar_tema(self, tema: Tema):
        self.setStyleSheet(f"""
            #janela_grafico {{ background: {tema.fundo}; border: 1px solid {tema.borda}; }}
            #barra_grafico {{ background: {tema.fundo}; border-bottom: 1px solid {tema.borda}; }}
            #titulo_grafico {{ color: {tema.texto}; font-weight: 600; }}
            QCheckBox {{ color: {tema.texto_fraco}; font-size: 11px; }}
            QToolButton#botao_grafico {{
                background: transparent; border: none; border-radius: 2px;
                color: {tema.texto_fraco}; font-size: 12px;
            }}
            QToolButton#botao_grafico:hover {{ background: {tema.borda}; color: {tema.texto}; }}
        """)

    # ------------------------------------------------------------ estados (21)

    def minimizar(self):
        self.estado = "minimizado"
        self.area.hide()
        self.setFixedHeight(self.barra.height() + 2)
        self.estado_mudou.emit(self)

    def maximizar(self):
        if self.estado == "maximizado":
            self.restaurar()
            return
        self.estado = "maximizado"
        self.area.show()
        self.setMaximumHeight(16777215)
        self.pediu_maximizar.emit(self)
        self.estado_mudou.emit(self)

    def restaurar(self):
        self.estado = "encaixado"
        self.area.show()
        self.setMaximumHeight(16777215)
        self.setMinimumHeight(0)
        self.pediu_restaurar.emit(self)
        self.estado_mudou.emit(self)

    def descolar(self):
        """Item 20: vira janela independente do OS, arrastável para outro monitor."""
        if self.estado == "flutuante":
            self.pediu_restaurar.emit(self)
            return
        self.estado = "flutuante"
        self.area.show()
        self.pediu_descolar.emit(self)
        self.estado_mudou.emit(self)

    # ---------------------------------------------------------------- curvas

    def adicionar_curva(self, curva: Curva):
        self.area.adicionar_curva(curva)
        self.legenda.reconstruir(list(self.area._curvas.values()))

    def _remover_curva(self, curva: Curva):
        self.area.remover_curva(curva.id)
        self.legenda.reconstruir(list(self.area._curvas.values()))

    def _alternar_visibilidade(self, curva: Curva):
        curva.visivel = not curva.visivel          # item 15
        self.area.marcar_sujo()
        self.legenda.atualizar_item(curva)

    def _abrir_propriedades(self, curva: Curva):
        p = PainelPropriedades(curva, self.area, self)
        p.alterou.connect(self.legenda.atualizar_item)
        p.show()
        posicionar_perto(p, self)
        self._paineis.append(p)

    def _abrir_deslocamento(self, curva: Curva):
        p = PainelDeslocamento(curva, self.area, self)
        p.show()
        posicionar_perto(p, self)
        self._paineis.append(p)

    def _novo_comentario(self, x: float, y: float):
        texto, ok = QInputDialog.getText(self, "Adicionar comentário",
                                         "Texto da anotação:")
        if ok and texto.strip():
            self.area.adicionar_anotacao(x, y, texto.strip())

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        self.legenda.reposicionar()


# =========================================================================== #
# GRUPO 4 — Sincronização entre gráficos (itens 31, 32, 38)
# =========================================================================== #

class GerenciadorSincronia(QObject):
    """
    Mantém a janela de tempo e a posição do cursor coerentes entre gráficos.
    A guarda de reentrância evita o laço A→B→A quando dois gráficos se ligam.
    """

    def __init__(self):
        super().__init__()
        self._janelas: list[JanelaGrafico] = []
        self._propagando = False
        self.ativo = True

    def registrar(self, janela: JanelaGrafico):
        self._janelas.append(janela)
        janela.area.faixa_x_mudou.connect(
            lambda a, b, j=janela: self._propagar_x(j, a, b))
        janela.area.mouse_moveu.connect(
            lambda x, j=janela: self._propagar_hover(j, x))
        janela.area.mouse_saiu.connect(lambda j=janela: self._propagar_hover(j, None))
        janela.chk_sync.toggled.connect(lambda _on: self.recalcular_limites())

    def remover(self, janela: JanelaGrafico):
        if janela in self._janelas:
            self._janelas.remove(janela)

    def definir_ativo(self, ligado: bool):
        self.ativo = ligado
        if ligado:
            self.recalcular_limites()

    def _pares(self, origem: JanelaGrafico) -> list[JanelaGrafico]:
        if not self.ativo or not origem.chk_sync.isChecked():
            return []
        return [j for j in self._janelas
                if j is not origem and j.chk_sync.isChecked()]

    def _propagar_x(self, origem: JanelaGrafico, x0: float, x1: float):
        if self._propagando:
            return
        self._propagando = True
        try:
            for j in self._pares(origem):
                j.area.definir_faixa_x(x0, x1)
        finally:
            self._propagando = False

    def _propagar_hover(self, origem: JanelaGrafico, x: float | None):
        for j in self._pares(origem):
            j.area.marcar_x_remoto(x)

    def recalcular_limites(self):
        """Item 32: ao religar a sincronia, todos passam a ver a união dos dados."""
        ativos = [j for j in self._janelas if j.chk_sync.isChecked()]
        if len(ativos) < 2:
            return
        minimos, maximos = [], []
        for j in ativos:
            for curva in j.area._curvas.values():
                x, _ = curva.dados_plot()
                if x.size:
                    minimos.append(float(x[0]))
                    maximos.append(float(x[-1]))
        if not minimos:
            return
        x0, x1 = min(minimos), max(maximos)
        for j in ativos:
            j.area.definir_faixa_x(x0, x1)


SINCRONIA = GerenciadorSincronia()


# =========================================================================== #
# GRUPO 3 — Catálogo visual com drag-and-drop (item 24)
# =========================================================================== #

class ListaCurvas(QListWidget):
    """Arrasta a curva daqui e solta em qualquer gráfico."""

    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setSelectionMode(QListWidget.SingleSelection)
        CATALOGO.curva_adicionada.connect(self._adicionar)
        CATALOGO.curva_removida.connect(self._remover)
        CATALOGO.curva_alterada.connect(self._atualizar)

    def _adicionar(self, curva: Curva):
        item = QListWidgetItem(curva.nome)
        item.setData(Qt.UserRole, curva.id)
        item.setIcon(self._amostra(curva.cor))
        self.addItem(item)

    def _remover(self, id_curva: str):
        for i in range(self.count()):
            if self.item(i).data(Qt.UserRole) == id_curva:
                self.takeItem(i)
                return

    def _atualizar(self, curva: Curva):
        for i in range(self.count()):
            if self.item(i).data(Qt.UserRole) == curva.id:
                self.item(i).setIcon(self._amostra(curva.cor))
                self.item(i).setText(curva.nome)
                return

    @staticmethod
    def _amostra(cor: str):
        from PySide6.QtGui import QIcon
        pm = QPixmap(12, 12)
        pm.fill(QColor(cor))
        return QIcon(pm)

    def startDrag(self, acoes):
        item = self.currentItem()
        if item is None:
            return
        mime = QMimeData()
        mime.setData("application/x-curva-id",
                     str(item.data(Qt.UserRole)).encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self._amostra_grande(item))
        drag.exec(Qt.CopyAction)

    def _amostra_grande(self, item) -> QPixmap:
        curva = CATALOGO.obter(item.data(Qt.UserRole))
        pm = QPixmap(150, 20)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(0, 0, 150, 20, QColor(0, 0, 0, 170))
        p.fillRect(4, 5, 10, 10, QColor(curva.cor if curva else "#888"))
        p.setPen(QColor(TEMA.tema.texto))
        p.drawText(20, 14, item.text()[:20])
        p.end()
        return pm


# =========================================================================== #
# GRUPO 3 — Área com abas de gráficos (item 22)
# =========================================================================== #

class PainelGraficos(QWidget):
    """
    Hospeda as janelas de gráfico em abas, cuida de descolar/reencaixar e
    registra cada uma na sincronia.
    """

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.abas = QTabWidget()
        self.abas.setTabsClosable(True)
        self.abas.setMovable(True)
        self.abas.tabCloseRequested.connect(self._fechar_aba)
        v.addWidget(self.abas)
        self._flutuantes: dict[JanelaGrafico, int] = {}
        self._contador = 0

    def novo_grafico(self, titulo: str = "") -> JanelaGrafico:
        self._contador += 1
        janela = JanelaGrafico(titulo or f"Gráfico {self._contador}")
        janela.pediu_descolar.connect(self._descolar)
        janela.pediu_restaurar.connect(self._reencaixar)
        janela.pediu_fechar.connect(self._fechar)
        SINCRONIA.registrar(janela)
        self.abas.addTab(janela, janela.titulo)
        self.abas.setCurrentWidget(janela)
        return janela

    def grafico_atual(self) -> JanelaGrafico | None:
        w = self.abas.currentWidget()
        return w if isinstance(w, JanelaGrafico) else None

    def _descolar(self, janela: JanelaGrafico):
        idx = self.abas.indexOf(janela)
        if idx < 0:
            return
        self._flutuantes[janela] = idx
        self.abas.removeTab(idx)
        janela.setParent(None)
        janela.setWindowFlag(Qt.Window, True)
        janela.setWindowTitle(janela.titulo)
        janela.resize(900, 520)
        janela.show()

    def _reencaixar(self, janela: JanelaGrafico):
        if janela not in self._flutuantes:
            return
        self._flutuantes.pop(janela)
        janela.setWindowFlag(Qt.Window, False)
        janela.estado = "encaixado"
        self.abas.addTab(janela, janela.titulo)
        self.abas.setCurrentWidget(janela)

    def _fechar_aba(self, indice: int):
        w = self.abas.widget(indice)
        if isinstance(w, JanelaGrafico):
            self._fechar(w)

    def _fechar(self, janela: JanelaGrafico):
        SINCRONIA.remover(janela)
        idx = self.abas.indexOf(janela)
        if idx >= 0:
            self.abas.removeTab(idx)
        self._flutuantes.pop(janela, None)
        janela.deleteLater()


# =========================================================================== #
# Ingestão de streaming (fase seguinte)
# =========================================================================== #

class FonteStreaming(QObject):
    """
    Ponte entre o feed de dados e os gráficos. `empurrar` é O(1) e não desenha:
    marca as áreas como sujas e o timer de cada AreaPlot repinta no seu ritmo.
    Isso mantém a taxa de ingestão desacoplada da taxa de quadros.
    """

    def __init__(self, painel: PainelGraficos):
        super().__init__()
        self.painel = painel
        self._janela_s: float | None = None
        self._destinos: dict[str, list[AreaPlot]] = {}   # cache curva -> áreas

    def definir_janela(self, curva: Curva, segundos: float | None):
        """
        Rolagem de janela fixa, aplicada só aos gráficos que hospedam esta curva.
        Global seria errado: um gráfico histórico ao lado de um ao vivo não deve
        ser arrastado junto pelo relógio.
        """
        self._janela_s = segundos
        for area in self._alvos(curva):
            area.janela_rolagem_s = segundos

    def _areas(self) -> list[AreaPlot]:
        return [self.painel.abas.widget(i).area
                for i in range(self.painel.abas.count())
                if isinstance(self.painel.abas.widget(i), JanelaGrafico)]

    def invalidar_cache(self):
        """Chamar ao adicionar ou remover curvas de gráficos."""
        self._destinos.clear()

    def _alvos(self, curva: Curva) -> list[AreaPlot]:
        alvos = self._destinos.get(curva.id)
        if alvos is None:
            alvos = [a for a in self._areas() if curva.id in a._curvas]
            for a in alvos:
                a.janela_rolagem_s = self._janela_s
            self._destinos[curva.id] = alvos
        return alvos

    def empurrar(self, curva: Curva, x: float, y: float):
        """
        Caminho quente: um append no buffer e um flag por área. Nada de desenho
        nem de mexer em eixo — quem faz isso é o timer de cada AreaPlot.
        """
        curva.buffer.append(x, y)
        for area in self._alvos(curva):
            area._sujo = True

    def empurrar_lote(self, curva: Curva, xs, ys):
        curva.buffer.estender(xs, ys)
        for area in self._alvos(curva):
            area._sujo = True
