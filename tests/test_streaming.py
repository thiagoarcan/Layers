import time
from datetime import datetime

import numpy as np

import graficos as gx
import streaming as st


def curva_teste():
    return gx.Curva.de_series("PT-01", [0, 1, 2, 3], [10, 11, 12, 13])


def test_formatadores_de_tempo():
    assert st.formatar_duracao(-1) == "00:00:00"
    assert st.formatar_duracao(65) == "00:01:05"
    assert st.formatar_instante(0) == datetime.fromtimestamp(0).strftime(
        "%d/%m/%Y %H:%M:%S"
    )
    assert st.formatar_instante(12.5, com_data=False) == datetime.fromtimestamp(
        12.5
    ).strftime("%H:%M:%S")


def test_motor_controla_replay_e_comandos(qtbot):
    painel = gx.PainelGraficos()
    qtbot.addWidget(painel)
    janela = painel.novo_grafico("Replay")
    curva = curva_teste()
    janela.area.adicionar_curva(curva, ajustar=False)

    motor = st.MotorReproducao(painel)
    motor.registrar(curva)
    assert motor.faixa == (0.0, 3.0)
    assert motor.duracao == 3.0

    motor.buscar_fracao(0.5)
    assert motor.t == 1.5
    motor.passo_tempo(10)
    assert motor.t == 3.0
    motor.ir_para_inicio()
    assert motor.t == 0.0
    motor.passo_amostra()
    assert motor.t == 1.0
    motor.passo_amostra(-1)
    assert motor.t == 0.0

    motor.definir_faixa(0.5, 2.5)
    assert motor.faixa == (0.5, 2.5)
    motor.definir_velocidade(2.0)
    assert motor.velocidade == 2.0
    motor.definir_janela(1.0)
    assert motor.janela_s == 1.0
    motor.definir_janela(None)
    assert motor.janela_s is None

    marcador = motor.adicionar_marcador("evento", 1.0)
    assert motor.marcadores == [marcador]
    motor.buscar(0.5)
    motor.marcador_seguinte()
    assert motor.t == 1.0
    motor.buscar(1.5)
    motor.marcador_anterior()
    assert motor.t == 1.0
    motor.remover_marcadores()
    assert motor.marcadores == []

    motor.reproduzir()
    assert motor.estado == st.REPRODUZINDO
    motor.pausar()
    assert motor.estado == st.PAUSADO
    motor.parar()
    assert motor.estado == st.PARADO
    motor.limpar()
    assert motor.faixa == (0.0, 0.0)


def test_motor_termina_e_respeita_laco(qtbot):
    painel = gx.PainelGraficos()
    qtbot.addWidget(painel)
    janela = painel.novo_grafico("Replay")
    curva = curva_teste()
    janela.area.adicionar_curva(curva, ajustar=False)
    motor = st.MotorReproducao(painel)
    motor.registrar(curva)
    terminou = []
    motor.terminou.connect(lambda: terminou.append(True))

    motor.buscar(2.9)
    motor.reproduzir()
    motor._relogio = time.perf_counter() - 1
    motor._passo_relogio()
    assert motor.estado == st.PAUSADO
    assert terminou

    motor.laco = True
    motor.buscar(2.9)
    motor.reproduzir()
    motor._relogio = time.perf_counter() - 1
    motor._passo_relogio()
    assert motor.estado == st.REPRODUZINDO
    assert motor.t == motor.faixa[0]


def test_streaming_simulado_e_fonte():
    curva = curva_teste()
    fonte = st.SimuladorSCADA([curva], hz=10)
    lotes = fonte.ler_lote()
    assert len(lotes) == 1
    identificador, xs, ys = lotes[0]
    assert identificador == curva.id
    assert len(xs) == len(ys) == 1
    assert np.isfinite(ys[0])
    fonte.parar()
