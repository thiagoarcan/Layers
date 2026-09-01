# Layers

Conversor, visualizador e player de dados de sensores SCADA. O projeto transforma planilhas XLSX em arquivos CSV ou Parquet e oferece uma interface desktop para explorar sensores, comparar curvas e reproduzir dados no tempo.

## Recursos

- Conversao em lote de varios arquivos XLSX.
- Deteccao de TAG e descarte de metadados no inicio da planilha.
- Normalizacao de timestamps e valores numericos no padrao pt-BR.
- Remocao de timestamps duplicados, mantendo o ultimo valor.
- Exportacao para CSV, Parquet ou ambos.
- Manifesto `_manifest.csv` com indice dos sensores convertidos.
- Processamento paralelo dimensionado por CPU e memoria disponivel.
- Interface grafica desktop baseada em PySide6.
- Graficos com ate tres eixos Y, crosshair, tooltip, legenda interativa e anotacoes.
- Temas visuais importaveis e exportaveis em JSON.
- Recorte temporal por linhas de arraste e janela deslizante.
- Replay com pausa, busca, velocidade, marcadores e passos de tempo/amostra.
- Simulador de streaming SCADA para desenvolvimento e demonstracao.

## Requisitos

- Python 3.10 ou superior.
- `pandas`
- `openpyxl`
- `numpy`
- `PySide6`
- `pyqtgraph`
- `pyarrow` para exportacao Parquet.
- `psutil` e opcional; quando instalado, melhora o dimensionamento automatico dos processos.

Instale as dependencias com:

```bash
python -m pip install pandas openpyxl numpy PySide6 pyqtgraph pyarrow psutil
```

## Uso pela interface grafica

Execute:

```bash
python conversor_gui.py
```

Na janela do aplicativo:

1. Abra uma pasta ou selecione arquivos XLSX.
2. Confira os sensores carregados na aba `Dados`.
3. Use `Converter` para escolher a pasta de destino e o formato de exportacao.
4. Use `Graficos` para plotar um sensor ou todos os sensores.
5. Use `Streaming` para reproduzir os dados ou iniciar o simulador ao vivo.

## Conversao pela linha de comando

Converta todos os XLSX de uma pasta para Parquet:

```bash
python converter_scada.py --entrada ./xlsx --saida ./dados
```

Gere CSV e Parquet usando quatro processos:

```bash
python converter_scada.py --entrada ./xlsx --saida ./dados --formato ambos --jobs 4
```

Opcoes disponiveis:

| Opcao | Obrigatoria | Descricao |
| --- | --- | --- |
| `--entrada` | Sim | Pasta que contem os arquivos `.xlsx`. |
| `--saida` | Sim | Pasta onde os arquivos convertidos serao gravados. |
| `--formato` | Nao | `csv`, `parquet` ou `ambos`; padrao: `parquet`. |
| `--jobs` | Nao | `auto` ou quantidade de processos; padrao: `auto`. |

## Formato de entrada

Cada planilha deve conter uma serie temporal de um sensor:

- Coluna A: data e hora.
- Coluna B: valor do sensor.
- A TAG pode estar no cabecalho da coluna B.
- Metadados antes do cabecalho sao aceitos nas primeiras 20 linhas.
- A primeira aba da planilha e utilizada.

Quando nao ha TAG identificavel, o nome do arquivo e usado.

## Saidas

Para cada sensor, o conversor gera um arquivo com nome seguro baseado na TAG:

- CSV com `timestamp` em ISO 8601 e `valor` numerico.
- Parquet com `timestamp` como datetime e `valor` como `float64`.
- `_manifest.csv` com TAG, arquivo, quantidade de pontos, inicio, fim, minimo e maximo.

## Estrutura

```text
Layers/
|-- conversor_gui.py       # Aplicacao desktop
|-- converter_scada.py     # Conversor XLSX e interface CLI
|-- graficos.py            # Temas, curvas e widgets de plotagem
|-- streaming.py           # Replay, transporte e simulador ao vivo
|-- DESCRITIVO.md          # Escopo e arquitetura do projeto
|-- .gitignore
```

## Estado do projeto

O projeto esta em desenvolvimento. A proxima evolucao natural e separar configuracoes e dependencias em arquivos proprios, adicionar testes automatizados para a conversao e conectar uma fonte SCADA real ao contrato de `FonteAoVivo`.

## Licenca

Ainda nao definida.
