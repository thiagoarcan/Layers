from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

import conversor_gui as gui
import converter_scada as cs


def criar_excel(caminho: Path, tag: str = "PIPE-XLSX"):
    wb = Workbook()
    ws = wb.active
    ws.append(["Data", tag])
    ws.append(["01/01/2024 00:00:02", "2,5"])
    ws.append(["01/01/2024 00:00:01", "1,5"])
    wb.save(caminho)


def dataframe_canonico():
    return pd.DataFrame({
        "timestamp": pd.to_datetime(
            ["2024-01-01", "2024-01-01 00:00:01"], format="mixed"
        ),
        "valor": pd.Series([10.0, 11.0], dtype="float64"),
    })


def validar_cache(conteudo: bytes):
    assert conteudo[:4] == b"PAR1"
    assert conteudo[-4:] == b"PAR1"
    df = cs.ler_parquet_memoria(conteudo)
    assert list(df.columns) == ["timestamp", "valor"]
    assert str(df["valor"].dtype) == "float64"
    assert df["timestamp"].is_monotonic_increasing
    return df


def test_excel_e_csv_sao_convertidos_para_parquet_em_memoria(tmp_path):
    excel = tmp_path / "entrada.xlsx"
    csv = tmp_path / "PIPE-CSV.csv"
    criar_excel(excel)
    csv.write_text(
        "timestamp,valor\n"
        "2024-01-01T00:00:01,1.5\n"
        "2024-01-01T00:00:02,2.5\n",
        encoding="utf-8",
    )

    tag_excel, cache_excel, convertido_excel = cs.preparar_cache_parquet(excel)
    tag_csv, cache_csv, convertido_csv = cs.preparar_cache_parquet(csv)

    assert (tag_excel, convertido_excel) == ("PIPE-XLSX", True)
    assert (tag_csv, convertido_csv) == ("PIPE-CSV", True)
    assert list(validar_cache(cache_excel)["valor"]) == [1.5, 2.5]
    assert list(validar_cache(cache_csv)["valor"]) == [1.5, 2.5]


def test_parquet_canonico_e_reutilizado_sem_reconversao(tmp_path):
    origem = tmp_path / "PIPE-PARQUET.parquet"
    conteudo_original = cs.serializar_parquet(dataframe_canonico())
    origem.write_bytes(conteudo_original)

    tag, cache, convertido = cs.preparar_cache_parquet(origem)

    assert tag == "PIPE-PARQUET"
    assert convertido is False
    assert cache == conteudo_original
    validar_cache(cache)


def test_parquet_nao_canonico_e_rejeitado_sem_conversao_silenciosa(tmp_path):
    origem = tmp_path / "INVALIDO.parquet"
    pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-02", "2024-01-01"]),
        "valor": [1, 2],
    }).to_parquet(origem, index=False)

    with pytest.raises(ValueError, match="Parquet não canônico"):
        cs.preparar_cache_parquet(origem)


def test_gui_carrega_tres_formatos_no_cache_e_curva_nasce_do_parquet(
    qtbot, tmp_path
):
    excel = tmp_path / "PIPE-GUI-X.xlsx"
    csv = tmp_path / "PIPE-GUI-C.csv"
    parquet = tmp_path / "PIPE-GUI-P.parquet"
    criar_excel(excel, "PIPE-GUI-X")
    csv.write_text(
        "timestamp,valor\n2024-01-01T00:00:00,3\n"
        "2024-01-01T00:00:01,4\n",
        encoding="utf-8",
    )
    parquet_original = cs.serializar_parquet(dataframe_canonico())
    parquet.write_bytes(parquet_original)

    janela = gui.Janela()
    qtbot.addWidget(janela)
    janela._carregar([excel, csv, parquet])
    qtbot.waitUntil(
        lambda: janela.worker is not None and not janela.worker.isRunning(),
        timeout=10000,
    )
    qtbot.waitUntil(lambda: len(janela.parquets) == 3, timeout=3000)

    assert janela.parquets["PIPE-GUI-P"] == parquet_original
    for cache in janela.parquets.values():
        validar_cache(cache)

    janela.dados["PIPE-GUI-X"] = pd.DataFrame({"valor": [999.0]})
    curva = janela._curva_de("PIPE-GUI-X")
    assert list(curva.buffer.dados()[1]) == [1.5, 2.5]
    janela.close()


def test_worker_exporta_parquet_por_copia_e_deriva_csv(qtbot, tmp_path):
    cache = cs.serializar_parquet(dataframe_canonico())
    destino = tmp_path / "saida"

    worker = gui.WorkerExportacao({"PIPE-OUT": cache}, destino, "ambos")
    worker.start()
    qtbot.waitUntil(lambda: not worker.isRunning(), timeout=5000)

    assert (destino / "PIPE-OUT.parquet").read_bytes() == cache
    csv = pd.read_csv(destino / "PIPE-OUT.csv")
    assert list(csv["valor"]) == [10.0, 11.0]
    manifesto = pd.read_csv(destino / "_manifest.csv")
    assert manifesto.loc[0, "tag"] == "PIPE-OUT"
