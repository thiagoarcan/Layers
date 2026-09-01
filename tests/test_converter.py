from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import Workbook

import converter_scada as cs


def criar_planilha(caminho: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["Data", "PT-01"])
    ws.append(["01/01/2024 00:00:02", "1,5"])
    ws.append(["01/01/2024 00:00:01", "2"])
    ws.append(["01/01/2024 00:00:01", "3,25"])
    ws.append(["nao e data", "invalido"])
    wb.save(caminho)


def test_parse_timestamp_e_valor_pt_br():
    instante = datetime(2024, 1, 2, 3, 4, 5)
    assert cs.parse_timestamp(instante) == instante
    assert cs.parse_timestamp("02/01/2024 03:04:05") == instante
    assert cs.parse_timestamp("2024-01-02T03:04:05") == instante
    assert cs.parse_timestamp("invalido") is None

    assert cs.parse_valor(12) == 12.0
    assert cs.parse_valor("1.234,56") == 1234.56
    assert cs.parse_valor("12,5") == 12.5
    assert cs.parse_valor("invalido") is None


def test_sanitizar_e_leitura_streaming(tmp_path):
    origem = tmp_path / "sensor de teste.xlsx"
    criar_planilha(origem)

    assert cs.sanitizar("Pressao Águas/01") == "Pressao_Aguas_01"

    tag, df = cs.ler_planilha(origem)

    assert tag == "PT-01"
    assert list(df.columns) == ["timestamp", "valor"]
    assert len(df) == 2
    assert df["timestamp"].is_monotonic_increasing
    assert df.iloc[0]["valor"] == 3.25
    assert df.iloc[1]["valor"] == 1.5
    assert str(df["valor"].dtype) == "float64"


def test_cabecalho_generico_usa_nome_do_arquivo(tmp_path):
    origem = tmp_path / "PT-99.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["timestamp", "valor"])
    ws.append(["01/01/2024 00:00:00", "12,5"])
    wb.save(origem)

    tag, df = cs.ler_planilha(origem)

    assert tag == "PT-99"
    assert len(df) == 1


def test_processar_csv_parquet_e_manifesto(tmp_path):
    entrada = tmp_path / "entrada"
    saida = tmp_path / "saida"
    entrada.mkdir()
    criar_planilha(entrada / "pt.xlsx")

    resultado = cs.processar(entrada / "pt.xlsx", saida, "ambos")

    assert resultado["status"] == "ok"
    assert resultado["tag"] == "PT-01"
    assert (saida / "PT-01.csv").exists()
    assert (saida / "PT-01.parquet").exists()

    parquet = pd.read_parquet(saida / "PT-01.parquet")
    csv = pd.read_csv(saida / "PT-01.csv")
    assert len(parquet) == len(csv) == 2
    assert list(parquet.columns) == ["timestamp", "valor"]
    assert list(csv.columns) == ["timestamp", "valor"]


def test_cli_converte_varios_arquivos_e_ignora_temporario(tmp_path, monkeypatch):
    entrada = tmp_path / "entrada"
    saida = tmp_path / "saida"
    entrada.mkdir()
    criar_planilha(entrada / "pt.xlsx")
    criar_planilha(entrada / "~$pt.xlsx")

    monkeypatch.setattr(
        "sys.argv",
        ["converter_scada.py", "--entrada", str(entrada),
         "--saida", str(saida), "--formato", "csv", "--jobs", "1"],
    )

    assert cs.main() == 0
    manifesto = pd.read_csv(saida / "_manifest.csv")
    assert len(manifesto) == 1
    assert manifesto.iloc[0]["tag"] == "PT-01"


def test_cli_rejeita_pasta_ausente(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["converter_scada.py", "--entrada", str(tmp_path / "nao_existe"),
         "--saida", str(tmp_path / "saida")],
    )
    assert cs.main() == 1


def test_dimensionar_jobs_respeita_quantidade_de_arquivos(tmp_path, monkeypatch):
    arquivos = []
    for indice in range(3):
        caminho = tmp_path / f"{indice}.xlsx"
        caminho.write_bytes(b"x")
        arquivos.append(caminho)

    monkeypatch.setattr(cs, "memoria_disponivel_bytes", lambda: 1024**3)
    monkeypatch.setattr(cs.os, "cpu_count", lambda: 8)

    assert 1 <= cs.dimensionar_jobs(arquivos, verbose=False) <= 3
