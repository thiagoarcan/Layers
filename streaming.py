#!/usr/bin/env python3
"""
streaming.py — Motor de reprodução e ingestão ao vivo para o player SCADA.

Dois modos sobre a mesma linha do tempo:

  REPLAY   — os dados já estão no buffer; o motor revela progressivamente até
             o instante virtual t. Nada é copiado: `Curva.limite_t` faz o corte
             por fatia de array, então avançar o tempo custa O(1) por curva.

  AO VIVO  — um feed externo empurra amostras no buffer circular. A thread de
             ingestão nunca desenha; ela só escreve e marca sujo.

Comandos de transporte: reproduzir, pausar, parar, ir ao início/fim, passo de
amostra, passo de tempo, busca, velocidade, laço, janela deslizante, marcadores.

Dependências: PySide6, pyqtgraph, numpy, graficos.py
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFrame,
                               QHBoxLayout, QLabel, QMenu, QSlider, QToolButton,
                               QVBoxLayout, QWidget)

from graficos import (TEMA, AreaPlot, Curva, JanelaGrafico, PainelGraficos,
                      Tema)

# --------------------------------------------------------------------------- #
# Estados e velocidades
# --------------------------------------------------------------------------- #

PARADO = "parado"
REPRODUZINDO = "reproduzindo"
PAUSADO = "pausado"
AO_VIVO = "ao_vivo"

VELOCIDADES = [
    ("0,25×", 0.25), ("0,5×", 0.5), ("1×", 1.0), ("2×", 2.0), ("5×", 5.0),
    ("10×", 10.0), ("30×", 30.0), ("1 min/s", 60.0), ("5 min/s", 300.0),
    ("1 h/s", 3600.0), ("Máxima", 0.0),      # 0 = sem espera de relógio
]

TICK_MS = 33          # ~30 Hz: o motor avança no mesmo ritmo do repaint


def formatar_instante(t: float, com_data: bool = True) -> str:
    try:
        dt = datetime.fromtimestamp(t)
    except (OverflowError, OSError, ValueError):
        return f"{t:.3f}"
    return dt.strftime("%d/%m/%Y %H:%M:%S" if com_data else "%H:%M:%S")


def formatar_duracao(seg: float) -> str:
    seg = max(0, int(seg))
    d, r = divmod(seg, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    if d:
        return f"{d}d {h:02d}:{m:02d}:{s:02d}"
    return f"{h:02d}:{m:02d}:{s:02d}"


@dataclass
class Marcador:
    """Ponto de interesse na linha do tempo, navegável com os comandos de salto."""
    t: float
    rotulo: str
    cor: str = ""
    itens: list = field(default_factory=list)   # InfiniteLine por gráfico


# =========================================================================== #
# Motor de reprodução
# =========================================================================== #

class MotorReproducao(QObject):
    """
    Relógio virtual único da aplicação. Todos os gráficos e curvas seguem ele,
    o que garante que painéis distintos mostrem sempre o mesmo instante.
    """

    tempo_mudou = Signal(float)          # instante virtual atual
    estado_mudou = Signal(str)
    faixa_mudou = Signal(float, float)   # início, fim do material disponível
    terminou = Signal()

    def __init__(self, painel: PainelGraficos):
        super().__init__()
        self.painel = painel
        self._curvas: dict[str, Curva] = {}
        self._estado = PARADO
        self._t0 = 0.0
        self._t1 = 0.0
        self._t = 0.0
        self.velocidade = 1.0
        self.laco = False
        self.janela_s: float | None = None    # None = eixo livre
        self.marcadores: list[Marcador] = []

        self._relogio = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._passo_relogio)

    # ------------------------------------------------------------- propriedades

    @property
    def estado(self) -> str:
        return self._estado

    @property
    def t(self) -> float:
        return self._t

    @property
    def faixa(self) -> tuple[float, float]:
        return self._t0, self._t1

    @property
    def duracao(self) -> float:
        return max(0.0, self._t1 - self._t0)

    @property
    def progresso(self) -> float:
        return 0.0 if self.duracao <= 0 else (self._t - self._t0) / self.duracao

    # ------------------------------------------------------------------ curvas

    def registrar(self, *curvas: Curva):
        for c in curvas:
            self._curvas[c.id] = c
        self.recalcular_faixa()

    def remover(self, curva: Curva):
        c = self._curvas.pop(curva.id, None)
        if c is not None:
            c.limite_t = None
        self.recalcular_faixa()

    def limpar(self):
        for c in self._curvas.values():
            c.limite_t = None
        self._curvas.clear()
        self.parar()
        self.recalcular_faixa()

    def recalcular_faixa(self):
        """Faixa reproduzível = união temporal de todas as curvas registradas."""
        inicios, fins = [], []
        for c in self._curvas.values():
            x, _ = c.buffer.dados()
            if x.size:
                desloc = c.deslocamento_s
                inicios.append(float(x[0]) + desloc)
                fins.append(float(x[-1]) + desloc)
        if inicios:
            self._t0, self._t1 = min(inicios), max(fins)
        else:
            self._t0 = self._t1 = 0.0
        self._t = min(max(self._t, self._t0), self._t1)
        self.faixa_mudou.emit(self._t0, self._t1)

    def definir_faixa(self, t0: float, t1: float):
        """Item 47: usa o recorte por drag lines como trecho a reproduzir."""
        self._t0, self._t1 = min(t0, t1), max(t0, t1)
        self._t = min(max(self._t, self._t0), self._t1)
        self.faixa_mudou.emit(self._t0, self._t1)
        self._aplicar()

    # ------------------------------------------------------------- transporte

    def reproduzir(self):
        if self._estado == REPRODUZINDO or self.duracao <= 0:
            return
        if self._t >= self._t1:
            self._t = self._t0
        self._aplicar()
        self._estado = REPRODUZINDO
        self._relogio = time.perf_counter()
        self._timer.start(TICK_MS)
        self.estado_mudou.emit(self._estado)

    def pausar(self):
        if self._estado != REPRODUZINDO:
            return
        self._timer.stop()
        self._estado = PAUSADO
        self.estado_mudou.emit(self._estado)

    def alternar(self):
        self.pausar() if self._estado == REPRODUZINDO else self.reproduzir()

    def parar(self):
        self._timer.stop()
        self._estado = PARADO
        self._t = self._t0
        self._aplicar()
        self.estado_mudou.emit(self._estado)

    def ir_para_inicio(self):
        self.buscar(self._t0)

    def ir_para_fim(self):
        self.buscar(self._t1)

    def buscar(self, t: float):
        self._t = min(max(t, self._t0), self._t1)
        self._aplicar()

    def buscar_fracao(self, fracao: float):
        self.buscar(self._t0 + self.duracao * min(max(fracao, 0.0), 1.0))

    def passo_tempo(self, segundos: float):
        self.buscar(self._t + segundos)

    def passo_amostra(self, direcao: int = 1):
        """
        Avança até a próxima amostra real de qualquer curva. Em dado por
        exceção isso é mais útil que um passo fixo: pula o vazio entre eventos.
        """
        alvo = None
        for c in self._curvas.values():
            x, _ = c.dados_plot(ignorar_limite=True)
            if x.size == 0:
                continue
            if direcao > 0:
                i = int(np.searchsorted(x, self._t, side="right"))
                if i < x.size:
                    cand = float(x[i])
                    alvo = cand if alvo is None else min(alvo, cand)
            else:
                i = int(np.searchsorted(x, self._t, side="left")) - 1
                if i >= 0:
                    cand = float(x[i])
                    alvo = cand if alvo is None else max(alvo, cand)
        if alvo is not None:
            self.buscar(alvo)

    def definir_velocidade(self, fator: float):
        self.velocidade = fator
        self._relogio = time.perf_counter()

    def definir_janela(self, segundos: float | None):
        self.janela_s = segundos
        for area in self._areas():
            area.janela_rolagem_s = segundos
        self._aplicar()
        if segundos is None:
            # "Tudo" reenquadra: sem isso o eixo ficaria preso na janela anterior
            for area in self._areas():
                area.ajustar_tudo()

    # ------------------------------------------------------------ marcadores

    def adicionar_marcador(self, rotulo: str = "", t: float | None = None) -> Marcador:
        instante = self._t if t is None else t
        m = Marcador(instante, rotulo or formatar_instante(instante, False),
                     TEMA.tema.regua)
        for area in self._areas():
            m.itens.append(area.linha_vertical(instante, m.cor))
        self.marcadores.append(m)
        self.marcadores.sort(key=lambda x: x.t)
        return m

    def remover_marcadores(self):
        for m in self.marcadores:
            for item in m.itens:
                for area in self._areas():
                    try:
                        area.removeItem(item)
                    except Exception:
                        pass
        self.marcadores.clear()

    def marcador_seguinte(self):
        posteriores = [m for m in self.marcadores if m.t > self._t + 1e-6]
        if posteriores:
            self.buscar(posteriores[0].t)

    def marcador_anterior(self):
        anteriores = [m for m in self.marcadores if m.t < self._t - 1e-6]
        if anteriores:
            self.buscar(anteriores[-1].t)

    # ------------------------------------------------------------------ ao vivo

    def entrar_ao_vivo(self, janela_s: float = 120.0):
        """No modo ao vivo o relógio é o dado que chega, não o motor."""
        self._timer.stop()
        self._estado = AO_VIVO
        self.janela_s = janela_s
        for area in self._areas():
            area.janela_rolagem_s = janela_s
        for c in self._curvas.values():
            c.limite_t = None            # nada de revelação progressiva
        self.estado_mudou.emit(self._estado)

    def sair_ao_vivo(self):
        if self._estado != AO_VIVO:
            return
        self._estado = PAUSADO
        self.recalcular_faixa()
        self._t = self._t1
        self._aplicar()
        self.estado_mudou.emit(self._estado)

    def ingerir(self, curva: Curva, xs, ys):
        """Chamado pelo feed (na thread da UI, via sinal em fila)."""
        curva.buffer.estender(np.atleast_1d(xs), np.atleast_1d(ys))
        if self._estado == AO_VIVO:
            x, _ = curva.buffer.dados()
            if x.size:
                self._t = float(x[-1]) + curva.deslocamento_s
                self._t1 = max(self._t1, self._t)
            self.tempo_mudou.emit(self._t)
        for area in self._areas_de(curva):
            area.janela_rolagem_s = self.janela_s
            area._sujo = True

    # ------------------------------------------------------------------ motor

    def _passo_relogio(self):
        agora = time.perf_counter()
        dt_real = agora - self._relogio
        self._relogio = agora

        if self.velocidade <= 0:                    # "Máxima": 2 % do total/quadro
            avanco = max(self.duracao * 0.02, 1e-6)
        else:
            avanco = dt_real * self.velocidade

        self._t += avanco
        if self._t >= self._t1:
            if self.laco:
                self._t = self._t0
            else:
                self._t = self._t1
                self._timer.stop()
                self._estado = PAUSADO
                self._aplicar()
                self.estado_mudou.emit(self._estado)
                self.terminou.emit()
                return
        self._aplicar()

    def _aplicar(self):
        """
        Caminho quente da reprodução: um atributo por curva e um flag por área.
        Sem cópia de array e sem chamada de desenho — o repaint é do timer da
        AreaPlot, que roda no seu próprio ritmo.
        """
        for c in self._curvas.values():
            c.limite_t = self._t
        for area in self._areas():
            area.janela_rolagem_s = self.janela_s
            area._sujo = True
        self.tempo_mudou.emit(self._t)

    def _areas(self) -> list[AreaPlot]:
        return [self.painel.abas.widget(i).area
                for i in range(self.painel.abas.count())
                if isinstance(self.painel.abas.widget(i), JanelaGrafico)]

    def _areas_de(self, curva: Curva) -> list[AreaPlot]:
        return [a for a in self._areas() if curva.id in a._curvas]


# =========================================================================== #
# Feed ao vivo
# =========================================================================== #

class FonteAoVivo(QThread):
    """
    Base para feeds externos (OPC UA, driver SCADA, socket). Emite lotes em vez
    de amostras isoladas: a travessia de thread custa mais que o append, então
    agrupar reduz muito o overhead sem atrasar a leitura de forma perceptível.
    """

    lote_pronto = Signal(str, object, object)   # id da curva, xs, ys
    erro = Signal(str)

    def __init__(self, intervalo_ms: int = 100):
        super().__init__()
        self.intervalo_ms = intervalo_ms
        self._rodando = False

    def parar(self):
        self._rodando = False
        self.requestInterruption()

    def run(self):
        self._rodando = True
        self.setTerminationEnabled(True)
        while self._rodando and not self.isInterruptionRequested():
            try:
                for id_curva, xs, ys in self.ler_lote():
                    if len(xs):
                        self.lote_pronto.emit(id_curva, xs, ys)
            except Exception as exc:
                self.erro.emit(str(exc))
            self.msleep(self.intervalo_ms)

    def ler_lote(self):
        """Sobrescreva devolvendo uma lista de (id_curva, xs, ys)."""
        return []


class SimuladorSCADA(FonteAoVivo):
    """
    Gera dado por exceção para testar o caminho ao vivo sem um driver real:
    amostras em instantes irregulares, com deadband — só reporta o que mudou.
    """

    def __init__(self, curvas: list[Curva], hz: float = 20.0,
                 deadband: float = 0.05, intervalo_ms: int = 100):
        super().__init__(intervalo_ms)
        self.curvas = curvas
        self.hz = hz
        self.deadband = deadband
        self._ultimo_valor: dict[str, float] = {}
        self._fase = 0.0

    def ler_lote(self):
        n = max(1, int(self.hz * self.intervalo_ms / 1000))
        agora = time.time()
        saida = []
        for k, curva in enumerate(self.curvas):
            t = agora + np.arange(n) / self.hz
            base = 50 + 20 * np.sin(self._fase + t / 7.0 + k)
            ruido = np.random.normal(0, 0.6, n)
            v = base + ruido
            anterior = self._ultimo_valor.get(curva.id)
            if anterior is not None:                     # deadband
                manter = np.abs(v - anterior) > self.deadband
                manter[-1] = True
                t, v = t[manter], v[manter]
            if v.size:
                self._ultimo_valor[curva.id] = float(v[-1])
                saida.append((curva.id, t, v))
        self._fase += 0.01
        return saida


# =========================================================================== #
# Barra de transporte
# =========================================================================== #

class BarraTransporte(QFrame):
    """Controles de reprodução sob a área de gráficos, no estilo de um player."""

    def __init__(
        self,
        motor: MotorReproducao,
        preparar_replay: Callable[[], bool] | None = None,
        alternar_vivo: Callable[[bool], None] | None = None,
    ):
        super().__init__()
        self.motor = motor
        self._preparar_replay = preparar_replay
        self._alternar_fonte_vivo = alternar_vivo
        self.setObjectName("transporte")
        self.setFixedHeight(42)
        self._arrastando = False

        h = QHBoxLayout(self)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(4)

        self._botoes = {}
        for chave, glifo, dica, slot in (
                ("inicio", "⏮", "Ir para o início (Home)", motor.ir_para_inicio),
                ("marc_ant", "⤒", "Marcador anterior", motor.marcador_anterior),
                ("amostra_ant", "◂|", "Amostra anterior (←)",
                 lambda: motor.passo_amostra(-1)),
                ("play", "▶", "Reproduzir / pausar (Espaço)",
                 self.alternar_replay),
                ("parar", "■", "Parar", motor.parar),
                ("amostra_prox", "|▸", "Próxima amostra (→)",
                 lambda: motor.passo_amostra(1)),
                ("marc_prox", "⤓", "Próximo marcador", motor.marcador_seguinte),
                ("fim", "⏭", "Ir para o fim (End)", motor.ir_para_fim)):
            b = QToolButton()
            b.setText(glifo)
            b.setToolTip(dica)
            b.setFixedSize(28, 26)
            b.setObjectName("botao_transporte")
            b.clicked.connect(slot)
            h.addWidget(b)
            self._botoes[chave] = b

        h.addSpacing(8)
        self.lbl_atual = QLabel("--:--:--")
        self.lbl_atual.setObjectName("relogio")
        h.addWidget(self.lbl_atual)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 10_000)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_arrastando", True))
        self.slider.sliderReleased.connect(self._soltar)
        self.slider.sliderMoved.connect(self._arrastar)
        h.addWidget(self.slider, 1)

        self.lbl_total = QLabel("00:00:00")
        self.lbl_total.setObjectName("relogio_fraco")
        h.addWidget(self.lbl_total)

        h.addSpacing(8)
        h.addWidget(QLabel("Velocidade"))
        self.cb_vel = QComboBox()
        for rotulo, fator in VELOCIDADES:
            self.cb_vel.addItem(rotulo, fator)
        self.cb_vel.setCurrentIndex(2)                 # 1×
        self.cb_vel.currentIndexChanged.connect(
            lambda i: motor.definir_velocidade(self.cb_vel.itemData(i)))
        motor.definir_velocidade(self.cb_vel.currentData())
        self.cb_vel.setFixedWidth(88)
        h.addWidget(self.cb_vel)

        self.chk_laco = QCheckBox("Repetir")
        self.chk_laco.toggled.connect(lambda on: setattr(motor, "laco", on))
        h.addWidget(self.chk_laco)

        h.addSpacing(10)
        h.addWidget(QLabel("Janela"))
        self.cb_janela = QComboBox()
        for rotulo, seg in (("Tudo", None), ("30 s", 30.0), ("1 min", 60.0),
                            ("5 min", 300.0), ("15 min", 900.0), ("1 h", 3600.0)):
            self.cb_janela.addItem(rotulo, seg)
        self.cb_janela.currentIndexChanged.connect(
            lambda i: motor.definir_janela(self.cb_janela.itemData(i)))
        self.cb_janela.setFixedWidth(78)
        h.addWidget(self.cb_janela)
        h.addSpacing(6)

        b_marc = QToolButton()
        b_marc.setText("⚑")
        b_marc.setToolTip("Marcar este instante (M)")
        b_marc.setFixedSize(28, 26)
        b_marc.setObjectName("botao_transporte")
        b_marc.clicked.connect(lambda: motor.adicionar_marcador())
        h.addWidget(b_marc)

        self.b_vivo = QToolButton()
        self.b_vivo.setText("● AO VIVO")
        self.b_vivo.setCheckable(True)
        self.b_vivo.setToolTip("Seguir o dado que está chegando")
        self.b_vivo.setObjectName("botao_vivo")
        self.b_vivo.toggled.connect(self._alternar_vivo)
        h.addWidget(self.b_vivo)

        motor.tempo_mudou.connect(self._atualizar_tempo)
        motor.estado_mudou.connect(self._atualizar_estado)
        motor.faixa_mudou.connect(self._atualizar_faixa)

        self.aplicar_tema(TEMA.tema)
        TEMA.tema_mudou.connect(self.aplicar_tema)
        self._atualizar_estado(motor.estado)

    # ---------------------------------------------------------------- reações

    def alternar_replay(self):
        if self.motor.estado == REPRODUZINDO:
            self.motor.pausar()
            return
        if self._preparar_replay is not None and not self._preparar_replay():
            return
        self.motor.reproduzir()

    def _arrastar(self, valor: int):
        self.motor.buscar_fracao(valor / 10_000)

    def _soltar(self):
        self._arrastando = False
        self.motor.buscar_fracao(self.slider.value() / 10_000)

    def _alternar_vivo(self, ligado: bool):
        if self._alternar_fonte_vivo is not None:
            self._alternar_fonte_vivo(ligado)
            return
        if ligado:
            self.motor.entrar_ao_vivo(self.cb_janela.currentData() or 120.0)
        else:
            self.motor.sair_ao_vivo()
            self.motor.definir_janela(self.cb_janela.currentData())

    def _atualizar_tempo(self, t: float):
        self.lbl_atual.setText(formatar_instante(t))
        if not self._arrastando:
            self.slider.blockSignals(True)
            self.slider.setValue(int(self.motor.progresso * 10_000))
            self.slider.blockSignals(False)

    def _atualizar_faixa(self, t0: float, t1: float):
        self.lbl_total.setText(formatar_duracao(t1 - t0))
        habilitado = (t1 - t0) > 0
        for b in self._botoes.values():
            b.setEnabled(habilitado)
        self.slider.setEnabled(habilitado)
        self._atualizar_estado(self.motor.estado)

    def _atualizar_estado(self, estado: str):
        self._botoes["play"].setText("❚❚" if estado == REPRODUZINDO else "▶")
        vivo = estado == AO_VIVO
        for chave in ("inicio", "fim", "amostra_ant", "amostra_prox", "play", "parar"):
            pode_preparar = chave == "play" and self._preparar_replay is not None
            self._botoes[chave].setEnabled(
                not vivo and (self.motor.duracao > 0 or pode_preparar)
            )
        self.slider.setEnabled(not vivo and self.motor.duracao > 0)
        self.cb_vel.setEnabled(not vivo)
        if self.b_vivo.isChecked() != vivo:
            self.b_vivo.blockSignals(True)
            self.b_vivo.setChecked(vivo)
            self.b_vivo.blockSignals(False)

    def aplicar_tema(self, tema: Tema):
        self.setStyleSheet(f"""
            #transporte {{ background: {tema.fundo}; border-top: 1px solid {tema.borda}; }}
            #transporte QLabel {{ color: {tema.texto_fraco}; font-size: 11px; }}
            #relogio {{ color: {tema.texto}; font-family: "Consolas", monospace;
                        font-size: 12px; }}
            #relogio_fraco {{ font-family: "Consolas", monospace; }}
            QToolButton#botao_transporte {{
                background: transparent; border: 1px solid transparent;
                border-radius: 3px; color: {tema.texto}; font-size: 13px;
            }}
            QToolButton#botao_transporte:hover {{
                background: {tema.borda}; border-color: {tema.borda};
            }}
            QToolButton#botao_transporte:disabled {{ color: {tema.texto_fraco}; }}
            QToolButton#botao_vivo {{
                background: transparent; border: 1px solid {tema.borda};
                border-radius: 3px; padding: 3px 8px;
                color: {tema.texto_fraco}; font-size: 10px; font-weight: 600;
            }}
            QToolButton#botao_vivo:checked {{
                background: {tema.erro}; border-color: {tema.erro}; color: #FFFFFF;
            }}
            QSlider::groove:horizontal {{
                height: 4px; background: {tema.borda}; border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {tema.sucesso}; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {tema.texto}; width: 11px; margin: -4px 0;
                border-radius: 5px;
            }}
        """)


def instalar_atalhos(
    alvo: QWidget,
    motor: MotorReproducao,
    alternar_replay: Callable[[], None] | None = None,
):
    """Teclas do player: espaço, setas, Home/End, M e L."""
    mapa = [
        ("Space", alternar_replay or motor.alternar),
        ("Left", lambda: motor.passo_amostra(-1)),
        ("Right", lambda: motor.passo_amostra(1)),
        ("Shift+Left", lambda: motor.passo_tempo(-60)),
        ("Shift+Right", lambda: motor.passo_tempo(60)),
        ("Home", motor.ir_para_inicio),
        ("End", motor.ir_para_fim),
        ("M", lambda: motor.adicionar_marcador()),
        ("L", lambda: setattr(motor, "laco", not motor.laco)),
    ]
    atalhos = []
    for tecla, slot in mapa:
        a = QShortcut(QKeySequence(tecla), alvo)
        a.setContext(Qt.ApplicationShortcut)
        a.activated.connect(slot)
        atalhos.append(a)
    return atalhos
