# Layers

Layers e uma ferramenta desktop para tratamento, visualizacao e reproducao de series temporais originadas em sistemas SCADA. O projeto aceita XLSX, CSV e Parquet, mantem um cache Parquet canonico em memoria e permite analisar os sensores em graficos interativos.

## Objetivo

Reduzir o trabalho manual entre a captura de dados industriais e a analise de sensores, tratando metadados, formatos de data, valores com virgula decimal e grandes volumes de linhas em um fluxo unico.

## Recursos

- Carregamento em lote de arquivos XLSX, CSV e Parquet.
- Conversao automatica de XLSX e CSV para Parquet em memoria.
- Reutilizacao sem reconversao de entradas Parquet canonicas.
- Deteccao de TAG e descarte de metadados no inicio da planilha.
- Normalizacao de timestamps e valores numericos no padrao pt-BR.
- Ordenacao temporal e remocao de timestamps duplicados, mantendo o ultimo valor.
- Exportacao para CSV, Parquet ou ambos.
- Manifesto `_manifest.csv` com indice dos sensores convertidos.
- Processamento paralelo dimensionado por CPU e memoria disponivel.
- Interface desktop baseada em PySide6, com leitura e exportacao em segundo plano.
- Graficos com ate tres eixos Y, crosshair, tooltip, legenda interativa e anotacoes.
- Temas visuais importaveis e exportaveis em JSON.
- Recorte temporal por linhas de arraste e janela deslizante.
- Replay com pausa, busca, velocidade, marcadores e passos de tempo/amostra.
- Simulador de streaming SCADA para desenvolvimento e demonstracao.

## Requisitos

- Python 3.10 ou superior.
- `pandas`, `openpyxl`, `numpy`, `PySide6` e `pyqtgraph`.
- `pyarrow` para exportacao Parquet.
- `psutil` e opcional e melhora o dimensionamento automatico dos processos.

Instale as dependencias com:

```bash
python -m pip install pandas openpyxl numpy PySide6 pyqtgraph pyarrow psutil
```

## Uso pela interface grafica

```bash
python conversor_gui.py
```

Fluxo recomendado:

1. Abra uma pasta ou selecione arquivos XLSX, CSV ou Parquet.
2. Aguarde a preparacao automatica do cache Parquet em memoria.
3. Confira os sensores na aba `Dados`.
4. Escolha destino e formato na aba `Converter`.
5. Plote um sensor ou todos na aba `Graficos`.
6. Use `Streaming` para replay ou para conectar uma fonte ao vivo.

## Conversao pela linha de comando

Prepare e exporte todos os XLSX, CSV e Parquet de uma pasta:

```bash
python converter_scada.py --entrada ./xlsx --saida ./dados
```

Gere CSV e Parquet usando quatro processos:

```bash
python converter_scada.py --entrada ./xlsx --saida ./dados --formato ambos --jobs 4
```

| Opcao | Obrigatoria | Descricao |
| --- | --- | --- |
| `--entrada` | Sim | Pasta com arquivos `.xlsx`, `.csv` ou `.parquet`. |
| `--saida` | Sim | Pasta de destino. |
| `--formato` | Nao | `csv`, `parquet` ou `ambos`; padrao: `parquet`. |
| `--jobs` | Nao | `auto` ou quantidade de processos; padrao: `auto`. |

## Formatos de entrada

Cada arquivo deve conter uma serie temporal de um sensor. Para XLSX:

- Coluna A: data e hora.
- Coluna B: valor do sensor.
- A TAG pode estar no cabecalho da coluna B.
- Metadados antes do cabecalho sao aceitos nas primeiras 20 linhas.
- A primeira aba da planilha e utilizada.

O timestamp pode ser datetime nativo do Excel ou texto no formato `dd/mm/aaaa hh:mm:ss`. O valor pode ser numerico ou texto com virgula decimal. Quando nao ha TAG identificavel, o nome do arquivo e usado.

CSV usa a primeira coluna como timestamp e a segunda como valor. O cabecalho da segunda coluna pode fornecer a TAG; nomes genericos como `valor` fazem o sistema usar o nome do arquivo.

Parquet canonico deve conter exatamente `timestamp` datetime, `valor` float64, timestamps ordenados e sem duplicatas. Seus bytes sao reutilizados sem reconversao.

## Saidas

- `<TAG>.csv`: serie temporal com timestamp em ISO 8601.
- `<TAG>.parquet`: serie temporal colunar com `timestamp` datetime e `valor` `float64`.
- `_manifest.csv`: TAG, arquivo, quantidade de pontos, inicio, fim, minimo e maximo.

## Arquitetura

```text
XLSX -> leitura e normalizacao --+
CSV  -> leitura e normalizacao --+-> cache Parquet em memoria
Parquet -> validacao e reuso -----+          |
                                             +-> tabela / graficos / replay
                                             +-> exportacao Parquet (copia)
                                             +-> exportacao CSV (conversao)

Fonte SCADA ao vivo ------------------------> buffers das curvas
```

| Modulo | Responsabilidade |
| --- | --- |
| `converter_scada.py` | Leitura de XLSX/CSV/Parquet, normalizacao, cache e manifesto. |
| `conversor_gui.py` | Janela principal, tabela, selecao de arquivos e comandos. |
| `graficos.py` | Temas, curvas, buffers e componentes de plotagem. |
| `streaming.py` | Motor de replay, transporte e fontes ao vivo. |

O conversor pode ser usado de forma independente pela CLI. A interface reutiliza o conversor, os graficos e o streaming; o streaming reutiliza as estruturas de curvas e plotagem.

## Integracao de streaming

O replay usa as curvas materializadas a partir do cache Parquet. O modo ao vivo e separado: depende de uma fonte que entregue novos lotes aos buffers. `SimuladorSCADA` serve apenas para demonstracao manual; ele nao substitui nem comprova uma integracao SCADA real. A classe `FonteAoVivo` e o ponto de extensao para OPC UA, driver SCADA ou socket.

## Estrutura

```text
Layers/
|-- conversor_gui.py
|-- converter_scada.py
|-- graficos.py
|-- streaming.py
|-- README.md
|-- DESCRITIVO.md
|-- .gitignore
```

## Roadmap

1. Adicionar testes unitarios para parsing, deduplicacao, sanitizacao e manifesto.
2. Criar `requirements.txt` ou `pyproject.toml`.
3. Adicionar exemplos pequenos de entrada e saida.
4. Implementar fontes SCADA reais atras de `FonteAoVivo`.
5. Adicionar exportacao de imagens e relatorios.
6. Definir licenca, contribuicao e convencao de versionamento.

## Estado e licenca

O projeto esta em desenvolvimento. A licenca ainda nao foi definida.
