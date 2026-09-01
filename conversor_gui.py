#!/usr/bin/env python3
"""
conversor_gui.py — Interface estilo Excel 365 (tema cinza escuro) para converter
planilhas XLSX de sensores SCADA em CSV e/ou Parquet.

Depende de converter_scada.py na mesma pasta (lógica de leitura e escrita).

Uso:
    python conversor_gui.py

Dependências: PySide6, pandas, openpyxl, pyarrow
"""

from __future__ import annotations

import multiprocessing
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from PySide6.QtCore import (QAbstractTableModel, QModelIndex, QPoint, QRect,
                            QSize, Qt, QThread, Signal)
from PySide6.QtGui import (QAction, QColor, QFont, QIcon, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup,
                               QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox,
                               QProgressBar, QPushButton, QRadioButton,
                               QSizePolicy, QSpinBox, QSplitter, QStatusBar,
                               QTabBar, QTableView, QTabWidget, QToolButton,
                               QVBoxLayout, QWidget)

# Lógica de conversão vive no módulo irmão — fonte única de verdade.
try:
    import converter_scada as cs
    import graficos as gx
    import streaming as st
except ImportError:
    print("converter_scada.py precisa estar na mesma pasta que conversor_gui.py",
          file=sys.stderr)
    raise


# =========================================================================== #
# Paleta — tema Cinza Escuro do Office
# =========================================================================== #

class C:
    CHROME       = "#333333"   # ribbon e barras
    CHROME_ESC   = "#2B2B2B"   # barra de acesso rápido
    AREA         = "#262626"   # área de trabalho
    GRADE        = "#1F1F1F"   # fundo da tabela
    GRADE_ALT    = "#242424"   # linha alternada
    CABECALHO    = "#2D2D2D"   # cabeçalho de coluna/linha
    LINHA        = "#3F3F3F"   # bordas e linhas de grade
    HOVER        = "#3F3F3F"
    PRESSIONADO  = "#4A4A4A"
    TEXTO        = "#E6E6E6"
    TEXTO_FRACO  = "#9A9A9A"
    TEXTO_DESAB  = "#5E5E5E"
    VERDE        = "#107C41"   # verde do Excel
    VERDE_CLARO  = "#16A75C"
    SELECAO      = "#2F5D3F"


# =========================================================================== #
# Ícones desenhados em código (sem arquivos externos)
# =========================================================================== #

def _icone(desenhar, tamanho: int = 32, cor: str = C.TEXTO) -> QIcon:
    pm = QPixmap(tamanho, tamanho)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    caneta = QPen(QColor(cor))
    caneta.setWidthF(tamanho * 0.075)
    caneta.setJoinStyle(Qt.RoundJoin)
    caneta.setCapStyle(Qt.RoundCap)
    p.setPen(caneta)
    desenhar(p, tamanho, QColor(cor))
    p.end()
    return QIcon(pm)


def _d_pasta(p: QPainter, s: int, cor: QColor):
    p.drawPolyline([QPoint(int(s*.14), int(s*.76)), QPoint(int(s*.14), int(s*.26)),
                    QPoint(int(s*.42), int(s*.26)), QPoint(int(s*.50), int(s*.38)),
                    QPoint(int(s*.86), int(s*.38)), QPoint(int(s*.86), int(s*.76)),
                    QPoint(int(s*.14), int(s*.76))])


def _d_planilha(p: QPainter, s: int, cor: QColor):
    r = QRect(int(s*.20), int(s*.18), int(s*.60), int(s*.64))
    p.drawRect(r)
    p.drawLine(int(s*.20), int(s*.38), int(s*.80), int(s*.38))
    p.drawLine(int(s*.50), int(s*.38), int(s*.50), int(s*.82))


def _d_exportar(p: QPainter, s: int, cor: QColor):
    p.drawPolyline([QPoint(int(s*.30), int(s*.22)), QPoint(int(s*.18), int(s*.22)),
                    QPoint(int(s*.18), int(s*.82)), QPoint(int(s*.82), int(s*.82)),
                    QPoint(int(s*.82), int(s*.22)), QPoint(int(s*.70), int(s*.22))])
    p.drawLine(int(s*.50), int(s*.60), int(s*.50), int(s*.16))
    p.drawPolyline([QPoint(int(s*.36), int(s*.30)), QPoint(int(s*.50), int(s*.16)),
                    QPoint(int(s*.64), int(s*.30))])


def _d_converter(p: QPainter, s: int, cor: QColor):
    p.drawPolyline([QPoint(int(s*.20), int(s*.36)), QPoint(int(s*.70), int(s*.36))])
    p.drawPolyline([QPoint(int(s*.58), int(s*.24)), QPoint(int(s*.72), int(s*.36)),
                    QPoint(int(s*.58), int(s*.48))])
    p.drawPolyline([QPoint(int(s*.80), int(s*.64)), QPoint(int(s*.30), int(s*.64))])
    p.drawPolyline([QPoint(int(s*.42), int(s*.52)), QPoint(int(s*.28), int(s*.64)),
                    QPoint(int(s*.42), int(s*.76))])


def _d_lixeira(p: QPainter, s: int, cor: QColor):
    p.drawLine(int(s*.24), int(s*.30), int(s*.76), int(s*.30))
    p.drawPolyline([QPoint(int(s*.32), int(s*.30)), QPoint(int(s*.36), int(s*.80)),
                    QPoint(int(s*.64), int(s*.80)), QPoint(int(s*.68), int(s*.30))])
    p.drawPolyline([QPoint(int(s*.42), int(s*.30)), QPoint(int(s*.42), int(s*.22)),
                    QPoint(int(s*.58), int(s*.22)), QPoint(int(s*.58), int(s*.30))])


def _d_tabela(p: QPainter, s: int, cor: QColor):
    p.drawRect(QRect(int(s*.16), int(s*.22), int(s*.68), int(s*.56)))
    p.drawLine(int(s*.16), int(s*.40), int(s*.84), int(s*.40))
    p.drawLine(int(s*.16), int(s*.59), int(s*.84), int(s*.59))
    p.drawLine(int(s*.48), int(s*.22), int(s*.48), int(s*.78))


def _d_info(p: QPainter, s: int, cor: QColor):
    p.drawEllipse(QRect(int(s*.20), int(s*.20), int(s*.60), int(s*.60)))
    p.drawLine(int(s*.50), int(s*.46), int(s*.50), int(s*.66))
    p.drawPoint(int(s*.50), int(s*.36))


def _d_atualizar(p: QPainter, s: int, cor: QColor):
    caminho = QPainterPath()
    caminho.arcMoto = None
    p.drawArc(QRect(int(s*.24), int(s*.24), int(s*.52), int(s*.52)), 60*16, 260*16)
    p.drawPolyline([QPoint(int(s*.60), int(s*.16)), QPoint(int(s*.74), int(s*.30)),
                    QPoint(int(s*.58), int(s*.38))])


ICONES = {
    "pasta": _d_pasta, "planilha": _d_planilha, "exportar": _d_exportar,
    "converter": _d_converter, "lixeira": _d_lixeira, "tabela": _d_tabela,
    "info": _d_info, "atualizar": _d_atualizar,
}


def icone(nome: str, tamanho: int = 32, cor: str = C.TEXTO) -> QIcon:
    return _icone(ICONES[nome], tamanho, cor)


# =========================================================================== #
# Componentes do Ribbon
# =========================================================================== #

class BotaoGrande(QToolButton):
    def __init__(self, texto: str, nome_icone: str, dica: str = "", cor=C.TEXTO):
        super().__init__()
        self.setText(texto)
        self.setIcon(icone(nome_icone, 32, cor))
        self.setIconSize(QSize(30, 30))
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setFixedHeight(68)
        self.setMinimumWidth(58)
        self.setMaximumWidth(96)
        self.setCursor(Qt.PointingHandCursor)
        if dica:
            self.setToolTip(dica)
        self.setProperty("classe", "grande")


class BotaoPequeno(QToolButton):
    def __init__(self, texto: str, nome_icone: str, dica: str = ""):
        super().__init__()
        self.setText(texto)
        self.setIcon(icone(nome_icone, 16))
        self.setIconSize(QSize(16, 16))
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setFixedHeight(22)
        self.setCursor(Qt.PointingHandCursor)
        if dica:
            self.setToolTip(dica)
        self.setProperty("classe", "pequeno")


class GrupoRibbon(QFrame):
    """Bloco do ribbon: conteúdo em cima, rótulo do grupo embaixo, separador à direita."""

    def __init__(self, titulo: str):
        super().__init__()
        self.setProperty("classe", "grupo")
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(6, 4, 6, 2)
        raiz.setSpacing(2)

        self.corpo = QWidget()
        self.linha = QHBoxLayout(self.corpo)
        self.linha.setContentsMargins(0, 0, 0, 0)
        self.linha.setSpacing(3)
        self.linha.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        raiz.addWidget(self.corpo, 1)

        rotulo = QLabel(titulo)
        rotulo.setAlignment(Qt.AlignHCenter)
        rotulo.setProperty("classe", "rotulo_grupo")
        raiz.addWidget(rotulo)

    def add(self, w: QWidget):
        self.linha.addWidget(w)
        return w

    def coluna(self, *widgets: QWidget) -> QWidget:
        """Empilha widgets pequenos verticalmente, como o Excel faz."""
        caixa = QWidget()
        v = QVBoxLayout(caixa)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        v.setAlignment(Qt.AlignTop)
        for w in widgets:
            v.addWidget(w)
        self.linha.addWidget(caixa)
        return caixa


class AbaRibbon(QWidget):
    def __init__(self):
        super().__init__()
        self.linha = QHBoxLayout(self)
        self.linha.setContentsMargins(4, 3, 4, 0)
        self.linha.setSpacing(0)
        self.linha.setAlignment(Qt.AlignLeft)

    def grupo(self, titulo: str) -> GrupoRibbon:
        g = GrupoRibbon(titulo)
        self.linha.addWidget(g)
        return g

    def fechar(self):
        self.linha.addStretch(1)


# =========================================================================== #
# Modelo de tabela sobre DataFrame (virtualizado)
# =========================================================================== #

class ModeloDataFrame(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame | None = None):
        super().__init__()
        self._df = df if df is not None else pd.DataFrame()
        self._tag = ""

    def definir(self, df: pd.DataFrame, tag: str = ""):
        self.beginResetModel()
        self._df = df
        self._tag = tag
        self.endResetModel()

    def rowCount(self, pai=QModelIndex()) -> int:
        return 0 if pai.isValid() else len(self._df)

    def columnCount(self, pai=QModelIndex()) -> int:
        return 0 if pai.isValid() else len(self._df.columns)

    def data(self, idx: QModelIndex, papel=Qt.DisplayRole):
        if not idx.isValid():
            return None
        valor = self._df.iat[idx.row(), idx.column()]
        if papel == Qt.DisplayRole:
            if isinstance(valor, pd.Timestamp):
                return valor.strftime("%d/%m/%Y %H:%M:%S")
            if isinstance(valor, float):
                return f"{valor:,.3f}".replace(",", "@").replace(".", ",").replace("@", ".")
            return str(valor)
        if papel == Qt.TextAlignmentRole:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def headerData(self, secao: int, orientacao: Qt.Orientation, papel=Qt.DisplayRole):
        if papel == Qt.DisplayRole:
            if orientacao == Qt.Horizontal:
                nomes = ("Data e hora", self._tag or "Valor")
                return nomes[secao] if secao < len(nomes) else str(self._df.columns[secao])
            return str(secao + 1)
        if papel == Qt.TextAlignmentRole:
            return int(Qt.AlignCenter)
        return None


# =========================================================================== #
# Worker de leitura em paralelo
# =========================================================================== #

class WorkerLeitura(QThread):
    """
    Lê os XLSX num pool de processos e emite cada resultado assim que fica pronto.
    Multiprocessing dentro de QThread mantém a UI livre e ainda usa os cores.
    """
    progresso = Signal(int, int, str)          # feitos, total, nome
    pronto = Signal(str, object, str)          # tag, DataFrame, origem
    falhou = Signal(str, str)                  # origem, mensagem
    concluido = Signal(int)                    # total carregado

    def __init__(self, arquivos: list[Path], jobs: int):
        super().__init__()
        self._arquivos = arquivos
        self._jobs = max(1, jobs)
        self._cancelar = False

    def cancelar(self):
        self._cancelar = True

    def run(self):
        total = len(self._arquivos)
        feitos = 0
        ok = 0
        try:
            if self._jobs == 1:
                for caminho in self._arquivos:
                    if self._cancelar:
                        break
                    feitos += 1
                    ok += self._entregar(caminho, feitos, total)
            else:
                with ProcessPoolExecutor(max_workers=self._jobs) as pool:
                    futuros = {pool.submit(cs.ler_planilha, c): c
                               for c in self._arquivos}
                    for fut in as_completed(futuros):
                        caminho = futuros[fut]
                        feitos += 1
                        if self._cancelar:
                            break
                        try:
                            tag, df = fut.result()
                        except Exception as exc:
                            self.falhou.emit(caminho.name, str(exc))
                            self.progresso.emit(feitos, total, caminho.name)
                            continue
                        ok += self._emitir(tag, df, caminho, feitos, total)
        except Exception:
            self.falhou.emit("(pool)", traceback.format_exc(limit=3))
        self.concluido.emit(ok)

    def _entregar(self, caminho: Path, feitos: int, total: int) -> int:
        try:
            tag, df = cs.ler_planilha(caminho)
        except Exception as exc:
            self.falhou.emit(caminho.name, str(exc))
            self.progresso.emit(feitos, total, caminho.name)
            return 0
        return self._emitir(tag, df, caminho, feitos, total)

    def _emitir(self, tag: str, df: pd.DataFrame, caminho: Path,
                feitos: int, total: int) -> int:
        self.progresso.emit(feitos, total, caminho.name)
        if df.empty:
            self.falhou.emit(caminho.name, "nenhuma linha válida")
            return 0
        self.pronto.emit(tag, df, caminho.name)
        return 1


class WorkerExportacao(QThread):
    progresso = Signal(int, int, str)
    falhou = Signal(str, str)
    concluido = Signal(int, str)

    def __init__(self, dados: dict[str, pd.DataFrame], destino: Path, formato: str):
        super().__init__()
        self._dados = dados
        self._destino = destino
        self._formato = formato

    def run(self):
        total = len(self._dados)
        feitos = 0
        ok = 0
        linhas_manifesto = []
        for tag, df in self._dados.items():
            feitos += 1
            try:
                cs.escrever(df, tag, self._destino, self._formato)
                linhas_manifesto.append({
                    "tag": tag, "arquivo": cs.sanitizar(tag), "n_pontos": len(df),
                    "t_inicio": df["timestamp"].iloc[0].isoformat(),
                    "t_fim": df["timestamp"].iloc[-1].isoformat(),
                    "valor_min": float(df["valor"].min()),
                    "valor_max": float(df["valor"].max()),
                })
                ok += 1
            except Exception as exc:
                self.falhou.emit(tag, str(exc))
            self.progresso.emit(feitos, total, tag)
        if linhas_manifesto:
            try:
                pd.DataFrame(linhas_manifesto).sort_values("tag").to_csv(
                    self._destino / "_manifest.csv", index=False)
            except Exception as exc:
                self.falhou.emit("_manifest.csv", str(exc))
        self.concluido.emit(ok, str(self._destino))


# =========================================================================== #
# Janela principal
# =========================================================================== #

class Janela(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Conversor SCADA")
        self.resize(1280, 780)

        self.dados: dict[str, pd.DataFrame] = {}
        self.origens: dict[str, str] = {}
        self.destino: Path | None = None
        self.worker: QThread | None = None

        # o ribbon referencia o motor, então ele nasce primeiro
        self.painel_graficos = gx.PainelGraficos()
        self.stream = gx.FonteStreaming(self.painel_graficos)
        self.motor = st.MotorReproducao(self.painel_graficos)
        self.transporte = st.BarraTransporte(self.motor)
        self.fonte_vivo: st.FonteAoVivo | None = None

        raiz = QWidget()
        self.setCentralWidget(raiz)
        v = QVBoxLayout(raiz)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        v.addWidget(self._barra_acesso_rapido())
        v.addWidget(self._montar_ribbon())
        v.addWidget(self._area_trabalho(), 1)
        v.addWidget(self._guias_planilha())

        self._montar_status()
        self.motor.tempo_mudou.connect(self._tempo_reproducao)
        self.motor.estado_mudou.connect(self._estado_reproducao)
        self._atalhos = st.instalar_atalhos(self, self.motor)
        self._atualizar_estado()

    # ---------------------------------------------------------------- chrome

    def _barra_acesso_rapido(self) -> QWidget:
        barra = QFrame()
        barra.setProperty("classe", "qat")
        barra.setFixedHeight(30)
        h = QHBoxLayout(barra)
        h.setContentsMargins(8, 0, 8, 0)
        h.setSpacing(6)

        marca = QLabel("Conversor SCADA")
        marca.setProperty("classe", "marca")
        h.addWidget(marca)
        h.addSpacing(10)

        for texto, nome, slot in (("Abrir", "pasta", self.abrir_arquivos),
                                  ("Recarregar", "atualizar", self.recarregar)):
            b = QToolButton()
            b.setIcon(icone(nome, 16, C.TEXTO_FRACO))
            b.setIconSize(QSize(15, 15))
            b.setToolTip(texto)
            b.setProperty("classe", "qat_botao")
            b.clicked.connect(slot)
            h.addWidget(b)

        h.addStretch(1)
        self.lbl_titulo_doc = QLabel("Nenhuma pasta de trabalho")
        self.lbl_titulo_doc.setProperty("classe", "titulo_doc")
        h.addWidget(self.lbl_titulo_doc)
        h.addStretch(1)
        return barra

    def _montar_ribbon(self) -> QWidget:
        self.ribbon = QTabWidget()
        self.ribbon.setProperty("classe", "ribbon")
        self.ribbon.setFixedHeight(122)
        self.ribbon.addTab(self._aba_dados(), "Dados")
        self.ribbon.addTab(self._aba_converter(), "Converter")
        self.ribbon.addTab(self._aba_graficos(), "Gráficos")
        self.ribbon.addTab(self._aba_streaming(), "Streaming")
        self.ribbon.addTab(self._aba_exibir(), "Exibir")
        self.ribbon.addTab(self._aba_ajuda(), "Ajuda")
        return self.ribbon

    def _aba_dados(self) -> QWidget:
        aba = AbaRibbon()

        g = aba.grupo("Carregar")
        self.b_abrir = BotaoGrande("Abrir\nplanilhas", "planilha",
                                   "Selecionar arquivos .xlsx", C.VERDE_CLARO)
        self.b_abrir.clicked.connect(self.abrir_arquivos)
        g.add(self.b_abrir)

        self.b_pasta = BotaoGrande("Abrir\npasta", "pasta",
                                   "Carregar todos os .xlsx de uma pasta")
        self.b_pasta.clicked.connect(self.abrir_pasta)
        g.add(self.b_pasta)

        g2 = aba.grupo("Seleção")
        self.b_remover = BotaoPequeno("Remover sensor", "lixeira")
        self.b_remover.clicked.connect(self.remover_selecionado)
        self.b_limpar = BotaoPequeno("Limpar tudo", "lixeira")
        self.b_limpar.clicked.connect(self.limpar_tudo)
        self.b_recarregar = BotaoPequeno("Recarregar", "atualizar")
        self.b_recarregar.clicked.connect(self.recarregar)
        g2.coluna(self.b_remover, self.b_limpar, self.b_recarregar)

        g3 = aba.grupo("Leitura")
        cx = QWidget()
        f = QVBoxLayout(cx)
        f.setContentsMargins(0, 0, 0, 0)
        f.setSpacing(3)
        f.setAlignment(Qt.AlignTop)
        f.addWidget(QLabel("Processos paralelos"))
        linha = QHBoxLayout()
        linha.setSpacing(4)
        self.sp_jobs = QSpinBox()
        self.sp_jobs.setRange(1, 64)
        self.sp_jobs.setValue(max(1, (multiprocessing.cpu_count() or 2) // 2))
        self.sp_jobs.setFixedWidth(56)
        self.chk_auto = QCheckBox("Automático")
        self.chk_auto.setChecked(True)
        self.chk_auto.toggled.connect(lambda on: self.sp_jobs.setDisabled(on))
        self.sp_jobs.setDisabled(True)
        linha.addWidget(self.sp_jobs)
        linha.addWidget(self.chk_auto)
        linha.addStretch(1)
        f.addLayout(linha)
        g3.add(cx)

        aba.fechar()
        return aba

    def _aba_converter(self) -> QWidget:
        aba = AbaRibbon()

        g = aba.grupo("Formato de saída")
        cx = QWidget()
        f = QVBoxLayout(cx)
        f.setContentsMargins(0, 2, 0, 0)
        f.setSpacing(3)
        f.setAlignment(Qt.AlignTop)
        self.grupo_formato = QButtonGroup(self)
        for i, (rot, dica) in enumerate((
                ("Parquet", "Recomendado: tipado, comprimido, leitura por fatia"),
                ("CSV", "Interoperável, timestamp em ISO 8601"),
                ("Ambos", "Parquet para o app, CSV para intercâmbio"))):
            r = QRadioButton(rot)
            r.setToolTip(dica)
            if i == 0:
                r.setChecked(True)
            self.grupo_formato.addButton(r, i)
            f.addWidget(r)
        g.add(cx)

        g2 = aba.grupo("Destino")
        cx2 = QWidget()
        f2 = QVBoxLayout(cx2)
        f2.setContentsMargins(0, 2, 0, 0)
        f2.setSpacing(4)
        f2.setAlignment(Qt.AlignTop)
        f2.addWidget(QLabel("Pasta de saída"))
        linha = QHBoxLayout()
        linha.setSpacing(4)
        self.ed_destino = QLineEdit()
        self.ed_destino.setPlaceholderText("Escolha onde gravar os arquivos")
        self.ed_destino.setReadOnly(True)
        self.ed_destino.setFixedWidth(300)
        b = QPushButton("Procurar")
        b.setFixedWidth(78)
        b.clicked.connect(self.escolher_destino)
        linha.addWidget(self.ed_destino)
        linha.addWidget(b)
        f2.addLayout(linha)
        g2.add(cx2)

        g3 = aba.grupo("Executar")
        self.b_exportar = BotaoGrande("Exportar\ntudo", "exportar",
                                      "Gravar todos os sensores carregados", C.VERDE_CLARO)
        self.b_exportar.clicked.connect(self.exportar)
        g3.add(self.b_exportar)
        self.b_exportar_sel = BotaoGrande("Exportar\nseleção", "converter",
                                          "Gravar apenas o sensor selecionado")
        self.b_exportar_sel.clicked.connect(lambda: self.exportar(somente_selecao=True))
        g3.add(self.b_exportar_sel)

        aba.fechar()
        return aba

    def _aba_graficos(self) -> QWidget:
        aba = AbaRibbon()

        g = aba.grupo("Gráfico")
        self.b_novo_gráfico = BotaoGrande("Novo\ngráfico", "tabela",
                                          "Criar uma janela de gráfico vazia")
        self.b_novo_gráfico.clicked.connect(lambda: self.painel_graficos.novo_grafico())
        g.add(self.b_novo_gráfico)
        self.b_plotar = BotaoGrande("Plotar\nsensor", "converter",
                                    "Plotar o sensor selecionado", C.VERDE_CLARO)
        self.b_plotar.clicked.connect(self.plotar_selecionado)
        g.add(self.b_plotar)
        self.b_plotar_todos = BotaoGrande("Plotar\ntodos", "planilha",
                                          "Plotar todos os sensores carregados")
        self.b_plotar_todos.clicked.connect(self.plotar_todos)
        g.add(self.b_plotar_todos)

        g2 = aba.grupo("Sincronia")
        cx = QWidget(); f = QVBoxLayout(cx)
        f.setContentsMargins(0, 2, 0, 0); f.setSpacing(3); f.setAlignment(Qt.AlignTop)
        self.chk_sync_global = QCheckBox("Sincronizar eixo X")
        self.chk_sync_global.setChecked(True)
        self.chk_sync_global.toggled.connect(gx.SINCRONIA.definir_ativo)
        self.chk_hover = QCheckBox("Hover compartilhado")
        self.chk_hover.setChecked(True)
        self.chk_hover.setEnabled(False)
        self.chk_sync_global.toggled.connect(self.chk_hover.setChecked)
        f.addWidget(self.chk_sync_global); f.addWidget(self.chk_hover)
        b_lim = QPushButton("Recalcular limites")
        b_lim.clicked.connect(gx.SINCRONIA.recalcular_limites)
        f.addWidget(b_lim)
        g2.add(cx)

        g3 = aba.grupo("Aparência")
        cx3 = QWidget(); f3 = QVBoxLayout(cx3)
        f3.setContentsMargins(0, 2, 0, 0); f3.setSpacing(4); f3.setAlignment(Qt.AlignTop)
        f3.addWidget(QLabel("Tema"))
        self.cb_tema = QComboBox()
        for nome, tema in gx.TEMAS.items():
            self.cb_tema.addItem(tema.rotulo, nome)
        self.cb_tema.currentIndexChanged.connect(
            lambda i: gx.TEMA.aplicar(self.cb_tema.itemData(i)))
        self.cb_tema.setFixedWidth(150)
        f3.addWidget(self.cb_tema)
        linha_t = QHBoxLayout(); linha_t.setSpacing(4)
        b_exp = QPushButton("Exportar"); b_exp.clicked.connect(self.exportar_tema)
        b_imp = QPushButton("Importar"); b_imp.clicked.connect(self.importar_tema)
        for b in (b_exp, b_imp): b.setFixedWidth(72); linha_t.addWidget(b)
        linha_t.addStretch(1)
        f3.addLayout(linha_t)
        g3.add(cx3)

        aba.fechar()
        return aba

    def _aba_streaming(self) -> QWidget:
        aba = AbaRibbon()

        g = aba.grupo("Reprodução")
        self.b_play = BotaoGrande("Reproduzir\npausar", "converter",
                                  "Espaço", C.VERDE_CLARO)
        self.b_play.clicked.connect(self.motor.alternar)
        g.add(self.b_play)
        self.b_stop = BotaoGrande("Parar", "lixeira", "Volta ao início e para")
        self.b_stop.clicked.connect(self.motor.parar)
        g.add(self.b_stop)

        g2 = aba.grupo("Navegação")
        b1 = BotaoPequeno("Início (Home)", "atualizar")
        b1.clicked.connect(self.motor.ir_para_inicio)
        b2 = BotaoPequeno("Fim (End)", "atualizar")
        b2.clicked.connect(self.motor.ir_para_fim)
        b3 = BotaoPequeno("Marcar instante (M)", "info")
        b3.clicked.connect(lambda: self.motor.adicionar_marcador())
        g2.coluna(b1, b2, b3)

        g3 = aba.grupo("Trecho")
        b4 = BotaoPequeno("Usar recorte do gráfico", "tabela")
        b4.clicked.connect(self.usar_recorte)
        b5 = BotaoPequeno("Trecho completo", "tabela")
        b5.clicked.connect(self.motor.recalcular_faixa)
        b6 = BotaoPequeno("Limpar marcadores", "lixeira")
        b6.clicked.connect(self.motor.remover_marcadores)
        g3.coluna(b4, b5, b6)

        g4 = aba.grupo("Fonte ao vivo")
        self.b_simular = BotaoGrande("Simular\nfeed", "planilha",
                                     "Gera dado por exceção para testar o modo ao vivo")
        self.b_simular.clicked.connect(self.alternar_simulador)
        g4.add(self.b_simular)
        cx = QWidget(); f = QVBoxLayout(cx)
        f.setContentsMargins(0, 2, 0, 0); f.setSpacing(3); f.setAlignment(Qt.AlignTop)
        f.addWidget(QLabel("Taxa (amostras/s)"))
        self.sp_hz = QSpinBox(); self.sp_hz.setRange(1, 1000); self.sp_hz.setValue(20)
        self.sp_hz.setFixedWidth(70)
        f.addWidget(self.sp_hz)
        self.lbl_vivo = QLabel("Parado")
        f.addWidget(self.lbl_vivo)
        g4.add(cx)

        aba.fechar()
        return aba

    def _aba_exibir(self) -> QWidget:
        aba = AbaRibbon()

        g = aba.grupo("Tabela")
        cx = QWidget()
        f = QVBoxLayout(cx)
        f.setContentsMargins(0, 2, 0, 0)
        f.setSpacing(3)
        f.setAlignment(Qt.AlignTop)
        self.chk_zebra = QCheckBox("Linhas alternadas")
        self.chk_zebra.setChecked(True)
        self.chk_zebra.toggled.connect(
            lambda on: self.tabela.setAlternatingRowColors(on))
        self.chk_grade = QCheckBox("Linhas de grade")
        self.chk_grade.setChecked(True)
        self.chk_grade.toggled.connect(lambda on: self.tabela.setShowGrid(on))
        self.chk_painel = QCheckBox("Painel de sensores")
        self.chk_painel.setChecked(True)
        self.chk_painel.toggled.connect(
            lambda on: self.painel_esq.setVisible(on))
        f.addWidget(self.chk_zebra)
        f.addWidget(self.chk_grade)
        f.addWidget(self.chk_painel)
        g.add(cx)

        g2 = aba.grupo("Estatísticas")
        self.lbl_stats = QLabel("Nenhum sensor selecionado")
        self.lbl_stats.setProperty("classe", "stats")
        self.lbl_stats.setMinimumWidth(320)
        self.lbl_stats.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        g2.add(self.lbl_stats)

        aba.fechar()
        return aba

    def _aba_ajuda(self) -> QWidget:
        aba = AbaRibbon()
        g = aba.grupo("Sobre")
        txt = QLabel(
            "Layout esperado do .xlsx: coluna A com data e hora (dd/mm/aaaa hh:mm:ss),\n"
            "coluna B com o valor e o TAG do sensor no cabeçalho. Uma aba por arquivo.\n"
            "Linhas de metadado acima do cabeçalho são detectadas e descartadas."
        )
        txt.setProperty("classe", "stats")
        g.add(txt)
        aba.fechar()
        return aba

    # ------------------------------------------------------------ área central

    def _area_trabalho(self) -> QWidget:
        divisor = QSplitter(Qt.Horizontal)
        divisor.setProperty("classe", "divisor")
        divisor.setHandleWidth(1)

        self.painel_esq = QWidget()
        pv = QVBoxLayout(self.painel_esq)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(0)
        cab = QLabel("Sensores")
        cab.setProperty("classe", "cabecalho_painel")
        cab.setFixedHeight(28)
        pv.addWidget(cab)
        self.lista = QListWidget()
        self.lista.currentItemChanged.connect(self._trocar_sensor)
        pv.addWidget(self.lista, 1)
        self.painel_esq.setMinimumWidth(170)
        self.painel_esq.setMaximumWidth(340)

        self.tabela = QTableView()
        self.modelo = ModeloDataFrame()
        self.tabela.setModel(self.modelo)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.tabela.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.verticalHeader().setDefaultSectionSize(21)
        self.tabela.verticalHeader().setFixedWidth(52)
        cab = self.tabela.horizontalHeader()
        cab.setDefaultSectionSize(200)
        cab.setHighlightSections(False)
        cab.setSectionResizeMode(QHeaderView.Interactive)
        cab.setStretchLastSection(True)   # 'valor' preenche a largura restante
        self.tabela.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.tabela.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

        caixa_graf = QWidget()
        vg = QVBoxLayout(caixa_graf)
        vg.setContentsMargins(0, 0, 0, 0); vg.setSpacing(0)
        vg.addWidget(self.painel_graficos, 1)
        vg.addWidget(self.transporte)

        self.abas_centro = QTabWidget()
        self.abas_centro.addTab(self.tabela, "Dados")
        self.abas_centro.addTab(caixa_graf, "Gráficos")

        divisor.addWidget(self.painel_esq)
        divisor.addWidget(self.abas_centro)
        divisor.setStretchFactor(0, 0)
        divisor.setStretchFactor(1, 1)
        divisor.setSizes([210, 1000])
        return divisor

    def _guias_planilha(self) -> QWidget:
        barra = QFrame()
        barra.setProperty("classe", "rodape_guias")
        barra.setFixedHeight(28)
        h = QHBoxLayout(barra)
        h.setContentsMargins(6, 0, 6, 0)
        h.setSpacing(4)
        self.guias = QTabBar()
        self.guias.setProperty("classe", "guias")
        self.guias.setExpanding(False)
        self.guias.setDrawBase(False)
        self.guias.currentChanged.connect(self._trocar_guia)
        h.addWidget(self.guias)
        h.addStretch(1)
        return barra

    def _montar_status(self):
        st = QStatusBar()
        st.setSizeGripEnabled(False)
        self.setStatusBar(st)
        self.lbl_status = QLabel("Pronto")
        st.addWidget(self.lbl_status)
        self.barra = QProgressBar()
        self.barra.setFixedWidth(190)
        self.barra.setFixedHeight(14)
        self.barra.setTextVisible(False)
        self.barra.hide()
        st.addPermanentWidget(self.barra)
        self.lbl_contagem = QLabel("0 sensores")
        st.addPermanentWidget(self.lbl_contagem)

    # ------------------------------------------------------------------ ações

    def abrir_arquivos(self):
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, "Selecionar planilhas de sensores", "",
            "Planilhas do Excel (*.xlsx);;Todos os arquivos (*)")
        if caminhos:
            self._carregar([Path(c) for c in caminhos])

    def abrir_pasta(self):
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar pasta com .xlsx")
        if not pasta:
            return
        arquivos = [c for c in sorted(Path(pasta).glob("*.xlsx"))
                    if not c.name.startswith("~$")]
        if not arquivos:
            self._aviso("Nenhum arquivo", f"Não há .xlsx em {pasta}.")
            return
        self._carregar(arquivos)

    def recarregar(self):
        if not self.origens:
            return
        caminhos = [Path(p) for p in self.origens.values() if Path(p).exists()]
        if caminhos:
            self._carregar(caminhos)

    def _carregar(self, arquivos: list[Path]):
        if self.worker and self.worker.isRunning():
            return
        arquivos.sort(key=lambda c: c.stat().st_size, reverse=True)
        jobs = (cs.dimensionar_jobs(arquivos, verbose=False)
                if self.chk_auto.isChecked() else self.sp_jobs.value())
        jobs = max(1, min(jobs, len(arquivos)))

        for c in arquivos:
            self.origens[c.name] = str(c)

        self.barra.setRange(0, len(arquivos))
        self.barra.setValue(0)
        self.barra.show()
        self._ocupado(True)
        self.lbl_status.setText(f"Lendo {len(arquivos)} arquivo(s) em {jobs} processo(s)…")

        self.worker = WorkerLeitura(arquivos, jobs)
        self.worker.progresso.connect(self._progresso)
        self.worker.pronto.connect(self._sensor_carregado)
        self.worker.falhou.connect(self._registrar_falha)
        self.worker.concluido.connect(self._leitura_concluida)
        self.worker.start()

    def _sensor_carregado(self, tag: str, df: pd.DataFrame, origem: str):
        novo = tag not in self.dados
        self.dados[tag] = df
        self.origens[tag] = self.origens.get(origem, origem)
        if novo:
            item = QListWidgetItem(f"{tag}   ({len(df):,})".replace(",", "."))
            item.setData(Qt.UserRole, tag)
            self.lista.addItem(item)
            self.guias.addTab(tag)
        if self.lista.currentRow() < 0:
            self.lista.setCurrentRow(0)

    def _leitura_concluida(self, ok: int):
        self.barra.hide()
        self._ocupado(False)
        self.lbl_status.setText(f"{ok} sensor(es) carregado(s)")
        self._atualizar_estado()

    def escolher_destino(self):
        pasta = QFileDialog.getExistingDirectory(self, "Pasta de saída")
        if pasta:
            self.destino = Path(pasta)
            self.ed_destino.setText(pasta)
            self._atualizar_estado()

    def exportar(self, somente_selecao: bool = False):
        if not self.dados:
            return
        if self.destino is None:
            self.escolher_destino()
            if self.destino is None:
                return
        if somente_selecao:
            tag = self._tag_atual()
            if tag is None:
                return
            dados = {tag: self.dados[tag]}
        else:
            dados = dict(self.dados)

        formato = ("parquet", "csv", "ambos")[self.grupo_formato.checkedId()]
        self.destino.mkdir(parents=True, exist_ok=True)

        self.barra.setRange(0, len(dados))
        self.barra.setValue(0)
        self.barra.show()
        self._ocupado(True)
        self.lbl_status.setText(f"Gravando {len(dados)} sensor(es) em {formato}…")

        self.worker = WorkerExportacao(dados, self.destino, formato)
        self.worker.progresso.connect(self._progresso)
        self.worker.falhou.connect(self._registrar_falha)
        self.worker.concluido.connect(self._exportacao_concluida)
        self.worker.start()

    def _exportacao_concluida(self, ok: int, destino: str):
        self.barra.hide()
        self._ocupado(False)
        self.lbl_status.setText(f"{ok} arquivo(s) gravado(s) em {destino}")
        self._atualizar_estado()

    def remover_selecionado(self):
        tag = self._tag_atual()
        if tag is None:
            return
        self.dados.pop(tag, None)
        for i in range(self.lista.count()):
            if self.lista.item(i).data(Qt.UserRole) == tag:
                self.lista.takeItem(i)
                self.guias.removeTab(i)
                break
        if not self.dados:
            self.modelo.definir(pd.DataFrame())
        self._atualizar_estado()

    def limpar_tudo(self):
        self.dados.clear()
        self.origens.clear()
        self.lista.clear()
        while self.guias.count():
            self.guias.removeTab(0)
        self.modelo.definir(pd.DataFrame())
        self.lbl_status.setText("Pronto")
        self._atualizar_estado()

    # ---------------------------------------------------------------- gráficos

    def _curva_de(self, tag: str) -> "gx.Curva":
        """Reaproveita a curva já criada para este TAG em vez de duplicar buffer."""
        for c in gx.CATALOGO:
            if c.nome == tag:
                return c
        df = self.dados[tag]
        curva = gx.Curva.de_dataframe(tag, df, unidade="", grandeza=tag)
        return gx.CATALOGO.adicionar(curva)

    def plotar_selecionado(self):
        tag = self._tag_atual()
        if tag is None:
            return
        janela = self.painel_graficos.grafico_atual() or self.painel_graficos.novo_grafico()
        curva = self._curva_de(tag)
        janela.adicionar_curva(curva)
        self.motor.registrar(curva)
        self.stream.invalidar_cache()
        self.abas_centro.setCurrentIndex(1)

    def plotar_todos(self):
        if not self.dados:
            return
        janela = self.painel_graficos.novo_grafico("Todos os sensores")
        for i, tag in enumerate(self.dados):
            curva = self._curva_de(tag)
            curva.eixo = gx.EIXOS[min(i, 2)] if len(self.dados) > 1 else "Y1"
            janela.adicionar_curva(curva)
            self.motor.registrar(curva)
        self.stream.invalidar_cache()
        self.abas_centro.setCurrentIndex(1)
        gx.SINCRONIA.recalcular_limites()

    def exportar_tema(self):
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar tema", "tema.json", "JSON (*.json)")
        if caminho:
            gx.TEMA.exportar(Path(caminho))
            self.lbl_status.setText(f"Tema salvo em {caminho}")

    def importar_tema(self):
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Carregar tema", "", "JSON (*.json)")
        if not caminho:
            return
        try:
            nome = gx.TEMA.importar(Path(caminho))
        except Exception as exc:
            self.lbl_status.setText(f"Tema não carregado: {exc}")
            return
        problemas = gx.TEMA.validar_contraste()
        if problemas:
            campos = ", ".join(f"{c} ({r:.1f}:1)" for c, r in problemas)
            self._aviso("Contraste abaixo do recomendado",
                        f"O tema foi aplicado, mas estes elementos ficam difíceis "
                        f"de ler sobre o fundo do gráfico:\n\n{campos}\n\n"
                        f"O mínimo da WCAG para texto é 4,5:1.")
        self.lbl_status.setText(f"Tema '{nome}' aplicado")

    # --------------------------------------------------------------- streaming

    def usar_recorte(self):
        """Transforma o recorte por drag lines no trecho a reproduzir."""
        janela = self.painel_graficos.grafico_atual()
        if janela is None:
            return
        faixa = janela.area.faixa_recorte()
        if faixa is None:
            self.lbl_status.setText(
                "Ative o recorte temporal no gráfico (clique direito) antes.")
            return
        self.motor.definir_faixa(*faixa)
        self.lbl_status.setText(
            f"Trecho: {st.formatar_instante(faixa[0])} → "
            f"{st.formatar_instante(faixa[1])}")

    def alternar_simulador(self):
        if self.fonte_vivo is not None:
            self.fonte_vivo.parar()
            self.fonte_vivo.wait(2000)
            self.fonte_vivo = None
            self.motor.sair_ao_vivo()
            self.transporte.b_vivo.setChecked(False)
            self.lbl_vivo.setText("Parado")
            return

        curvas = [c for c in gx.CATALOGO]
        if not curvas:
            janela = self.painel_graficos.grafico_atual() or \
                self.painel_graficos.novo_grafico("Ao vivo")
            curva = gx.CATALOGO.adicionar(
                gx.Curva.de_series("SIM-PT-01", [time.time()], [50.0],
                                   capacidade=500_000, grandeza="Pressão",
                                   unidade="bar"))
            janela.adicionar_curva(curva)
            self.motor.registrar(curva)
            curvas = [curva]

        self.fonte_vivo = st.SimuladorSCADA(curvas, hz=self.sp_hz.value())
        self.fonte_vivo.lote_pronto.connect(self._lote_recebido)
        self.fonte_vivo.erro.connect(
            lambda m: self.lbl_status.setText(f"Feed: {m}"))
        self.fonte_vivo.start()
        self.transporte.b_vivo.setChecked(True)
        self.lbl_vivo.setText("Recebendo…")

    def _lote_recebido(self, id_curva: str, xs, ys):
        curva = gx.CATALOGO.obter(id_curva)
        if curva is not None:
            self.motor.ingerir(curva, xs, ys)

    def _tempo_reproducao(self, t: float):
        if self.motor.estado in (st.REPRODUZINDO, st.AO_VIVO):
            self.lbl_status.setText(f"t = {st.formatar_instante(t)}")

    def _estado_reproducao(self, estado: str):
        rotulos = {st.PARADO: "Parado", st.REPRODUZINDO: "Reproduzindo",
                   st.PAUSADO: "Pausado", st.AO_VIVO: "Ao vivo"}
        self.lbl_status.setText(rotulos.get(estado, estado))

    # -------------------------------------------------------------- auxiliares

    def _tag_atual(self) -> str | None:
        item = self.lista.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _trocar_sensor(self, atual: QListWidgetItem, _anterior=None):
        if atual is None:
            return
        tag = atual.data(Qt.UserRole)
        df = self.dados.get(tag)
        if df is None:
            return
        self.modelo.definir(df, tag)
        self.tabela.scrollToTop()
        idx = self.lista.row(atual)
        if self.guias.currentIndex() != idx:
            self.guias.blockSignals(True)
            self.guias.setCurrentIndex(idx)
            self.guias.blockSignals(False)
        self.lbl_titulo_doc.setText(f"{tag} — Conversor SCADA")
        self._mostrar_estatisticas(tag, df)

    def _trocar_guia(self, indice: int):
        if 0 <= indice < self.lista.count():
            self.lista.setCurrentRow(indice)

    @staticmethod
    def _formatar_duracao(delta) -> str:
        seg = int(delta.total_seconds())
        dias, resto = divmod(seg, 86400)
        horas, resto = divmod(resto, 3600)
        minutos, segundos = divmod(resto, 60)
        partes = []
        if dias:
            partes.append(f"{dias} d")
        if horas or dias:
            partes.append(f"{horas} h")
        partes.append(f"{minutos} min")
        partes.append(f"{segundos} s")
        return " ".join(partes)

    @staticmethod
    def _num(valor: float, casas: int = 3) -> str:
        """Formata no padrão pt-BR: ponto como milhar, vírgula como decimal."""
        return f"{valor:,.{casas}f}".replace(",", "@").replace(".", ",").replace("@", ".")

    def _mostrar_estatisticas(self, tag: str, df: pd.DataFrame):
        ini, fim = df["timestamp"].iloc[0], df["timestamp"].iloc[-1]
        self.lbl_stats.setText(
            f"TAG: {tag}\n"
            f"Pontos: {self._num(len(df), 0)}\n"
            f"Início: {ini:%d/%m/%Y %H:%M:%S}    Fim: {fim:%d/%m/%Y %H:%M:%S}\n"
            f"Duração: {self._formatar_duracao(fim - ini)}\n"
            f"Mínimo: {self._num(df['valor'].min())}    "
            f"Máximo: {self._num(df['valor'].max())}"
        )

    def _progresso(self, feitos: int, total: int, nome: str):
        self.barra.setValue(feitos)
        self.lbl_status.setText(f"{feitos}/{total} — {nome}")

    def _registrar_falha(self, origem: str, mensagem: str):
        self.lbl_status.setText(f"{origem}: {mensagem}")

    def _ocupado(self, ocupado: bool):
        for b in (self.b_abrir, self.b_pasta, self.b_exportar,
                  self.b_exportar_sel, self.b_limpar, self.b_recarregar):
            b.setEnabled(not ocupado)

    def _atualizar_estado(self):
        tem = bool(self.dados)
        self.lbl_contagem.setText(
            f"{len(self.dados)} sensor" + ("es" if len(self.dados) != 1 else ""))
        self.b_exportar.setEnabled(tem)
        self.b_exportar_sel.setEnabled(tem)
        self.b_plotar.setEnabled(tem)
        self.b_plotar_todos.setEnabled(tem)
        self.b_remover.setEnabled(tem)
        self.b_limpar.setEnabled(tem)
        self.b_recarregar.setEnabled(bool(self.origens))
        if not tem:
            self.lbl_titulo_doc.setText("Nenhuma pasta de trabalho")
            self.lbl_stats.setText("Nenhum sensor selecionado")

    def _aviso(self, titulo: str, texto: str):
        cx = QMessageBox(self)
        cx.setWindowTitle(titulo)
        cx.setText(texto)
        cx.setIcon(QMessageBox.Information)
        cx.exec()

    def closeEvent(self, evento):
        if self.fonte_vivo is not None:
            self.fonte_vivo.parar()
            self.fonte_vivo.wait(2000)
        if self.worker and self.worker.isRunning():
            if hasattr(self.worker, "cancelar"):
                self.worker.cancelar()
            self.worker.wait(3000)
        evento.accept()


# =========================================================================== #
# Folha de estilo
# =========================================================================== #

QSS = f"""
QWidget {{
    background: {C.AREA};
    color: {C.TEXTO};
    font-family: "Segoe UI", "Noto Sans", sans-serif;
    font-size: 12px;
}}

/* ---------- barra de acesso rápido ---------- */
QFrame[classe="qat"] {{ background: {C.CHROME_ESC}; border: none; }}
QFrame[classe="qat"] QLabel {{ background: transparent; }}
QLabel[classe="marca"] {{ color: {C.VERDE_CLARO}; font-weight: 600; }}
QLabel[classe="titulo_doc"] {{ color: {C.TEXTO_FRACO}; }}
QToolButton[classe="qat_botao"] {{
    background: transparent; border: none; border-radius: 3px; padding: 3px;
}}
QToolButton[classe="qat_botao"]:hover {{ background: {C.HOVER}; }}

/* ---------- ribbon ---------- */
QTabWidget[classe="ribbon"]::pane {{
    background: {C.CHROME};
    border: none;
    border-bottom: 1px solid {C.LINHA};
}}
QTabWidget[classe="ribbon"] > QTabBar {{ background: {C.CHROME_ESC}; }}
QTabWidget[classe="ribbon"] > QTabBar::tab {{
    background: transparent;
    color: {C.TEXTO_FRACO};
    padding: 6px 16px;
    margin: 0px;
    border: none;
    border-bottom: 2px solid transparent;
}}
QTabWidget[classe="ribbon"] > QTabBar::tab:hover {{ color: {C.TEXTO}; }}
QTabWidget[classe="ribbon"] > QTabBar::tab:selected {{
    background: {C.CHROME};
    color: #FFFFFF;
    border-bottom: 2px solid {C.VERDE_CLARO};
}}
QWidget#aba, AbaRibbon {{ background: {C.CHROME}; }}

QFrame[classe="grupo"] {{
    background: {C.CHROME};
    border: none;
    border-right: 1px solid {C.LINHA};
}}
QFrame[classe="grupo"] QWidget {{ background: transparent; }}
QLabel[classe="rotulo_grupo"] {{
    color: {C.TEXTO_FRACO};
    font-size: 11px;
    padding-top: 1px;
}}
QLabel[classe="stats"] {{ color: {C.TEXTO_FRACO}; font-size: 11px; }}

QToolButton[classe="grande"], QToolButton[classe="pequeno"] {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 3px;
    color: {C.TEXTO};
}}
QToolButton[classe="grande"]:hover, QToolButton[classe="pequeno"]:hover {{
    background: {C.HOVER}; border-color: {C.LINHA};
}}
QToolButton[classe="grande"]:pressed, QToolButton[classe="pequeno"]:pressed {{
    background: {C.PRESSIONADO};
}}
QToolButton:disabled {{ color: {C.TEXTO_DESAB}; }}

/* ---------- controles ---------- */
QCheckBox, QRadioButton {{ background: transparent; spacing: 6px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 13px; height: 13px; }}
QCheckBox::indicator {{ border: 1px solid #6E6E6E; border-radius: 2px; background: {C.GRADE}; }}
QRadioButton::indicator {{ border: 1px solid #6E6E6E; border-radius: 7px; background: {C.GRADE}; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {C.VERDE}; border-color: {C.VERDE_CLARO};
}}
QLineEdit, QSpinBox {{
    background: {C.GRADE};
    border: 1px solid {C.LINHA};
    border-radius: 2px;
    padding: 3px 5px;
    selection-background-color: {C.VERDE};
}}
QLineEdit:focus, QSpinBox:focus {{ border-color: {C.VERDE_CLARO}; }}
QPushButton {{
    background: {C.HOVER};
    border: 1px solid {C.LINHA};
    border-radius: 2px;
    padding: 4px 10px;
}}
QPushButton:hover {{ background: {C.PRESSIONADO}; border-color: #5A5A5A; }}
QPushButton:pressed {{ background: {C.VERDE}; }}

/* ---------- painel de sensores ---------- */
QLabel[classe="cabecalho_painel"] {{
    background: {C.CABECALHO};
    color: {C.TEXTO_FRACO};
    padding-left: 10px;
    border-bottom: 1px solid {C.LINHA};
}}
QListWidget {{
    background: {C.AREA};
    border: none;
    border-right: 1px solid {C.LINHA};
    outline: none;
}}
QListWidget::item {{ padding: 6px 10px; border-bottom: 1px solid #2E2E2E; }}
QListWidget::item:hover {{ background: {C.HOVER}; }}
QListWidget::item:selected {{
    background: {C.SELECAO};
    color: #FFFFFF;
    border-left: 3px solid {C.VERDE_CLARO};
}}

/* ---------- tabela ---------- */
QTableView {{
    background: {C.GRADE};
    alternate-background-color: {C.GRADE_ALT};
    gridline-color: {C.LINHA};
    border: none;
    selection-background-color: {C.SELECAO};
    selection-color: #FFFFFF;
}}
QHeaderView::section {{
    background: {C.CABECALHO};
    color: {C.TEXTO_FRACO};
    padding: 4px 6px;
    border: none;
    border-right: 1px solid {C.LINHA};
    border-bottom: 1px solid {C.LINHA};
    font-weight: normal;
}}
QHeaderView::section:hover {{ background: {C.HOVER}; color: {C.TEXTO}; }}
QTableCornerButton::section {{ background: {C.CABECALHO}; border: none; }}

/* ---------- guias de planilha ---------- */
QFrame[classe="rodape_guias"] {{
    background: {C.CHROME_ESC};
    border-top: 1px solid {C.LINHA};
}}
QTabBar[classe="guias"]::tab {{
    background: transparent;
    color: {C.TEXTO_FRACO};
    padding: 4px 14px;
    margin-right: 2px;
    border: none;
    border-top: 2px solid transparent;
}}
QTabBar[classe="guias"]::tab:hover {{ background: {C.HOVER}; color: {C.TEXTO}; }}
QTabBar[classe="guias"]::tab:selected {{
    background: {C.GRADE};
    color: #FFFFFF;
    border-top: 2px solid {C.VERDE_CLARO};
}}

/* ---------- status e barras ---------- */
QStatusBar {{
    background: {C.VERDE};
    color: #FFFFFF;
    border: none;
}}
QStatusBar QLabel {{ background: transparent; color: #FFFFFF; }}
QProgressBar {{
    background: #0C4A27;
    border: none;
    border-radius: 2px;
}}
QProgressBar::chunk {{ background: #7BD8A6; border-radius: 2px; }}

QScrollBar:vertical, QScrollBar:horizontal {{
    background: {C.AREA}; border: none;
}}
QScrollBar:vertical {{ width: 12px; }}
QScrollBar:horizontal {{ height: 12px; }}
QScrollBar::handle {{ background: #565656; border-radius: 6px; min-height: 28px; min-width: 28px; }}
QScrollBar::handle:hover {{ background: #6E6E6E; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0px; width: 0px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QSplitter::handle {{ background: {C.LINHA}; }}
QToolTip {{
    background: #1B1B1B; color: {C.TEXTO};
    border: 1px solid {C.LINHA}; padding: 4px;
}}
"""


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Conversor SCADA")
    fonte = QFont("Segoe UI", 9)
    app.setFont(fonte)
    app.setStyleSheet(QSS)

    janela = Janela()
    janela.show()
    return app.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()   # necessário no Windows (spawn)
    raise SystemExit(main())
