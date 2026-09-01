# Descritivo do projeto Layers

## 1. Visao geral

Layers e uma ferramenta desktop para tratamento e analise de series temporais originadas em sistemas SCADA. O projeto combina conversao de dados, visualizacao tecnica e replay temporal em uma mesma aplicacao.

Seu objetivo e reduzir o trabalho manual entre a captura de dados em planilhas Excel e a analise de sensores. A ferramenta aceita arquivos XLSX, identifica as series, organiza os dados em formatos adequados para consulta e permite observar o comportamento dos sensores em graficos interativos.

## 2. Problema que resolve

Dados exportados por sistemas industriais costumam chegar em planilhas com metadados, formatos de data variados, valores com virgula decimal e grande volume de linhas. O processamento manual desses arquivos gera risco de inconsistencias, dificulta comparacoes e torna a investigacao de eventos mais lenta.

Layers centraliza esse fluxo e automatiza:

- leitura tolerante de planilhas SCADA;
- limpeza e normalizacao de timestamps e valores;
- conversao em lote com controle de memoria;
- catalogacao dos sensores em um manifesto;
- visualizacao de uma ou varias series;
- replay controlado da linha do tempo;
- simulacao de dados ao vivo durante o desenvolvimento.

## 3. Escopo funcional

### Conversao

O modulo `converter_scada.py` processa todos os arquivos XLSX de uma pasta. A leitura usa o modo `read_only` do `openpyxl`, procura dados validos nas duas primeiras colunas, descarta linhas invalidas, ordena cronologicamente e remove timestamps repetidos mantendo o ultimo valor.

O processamento pode ocorrer em paralelo. No modo automatico, a quantidade de workers considera a quantidade de CPUs, a memoria livre e o maior arquivo de entrada estimado.

### Interface desktop

O modulo `conversor_gui.py` fornece uma interface baseada em PySide6 com abas para dados, conversao, graficos, streaming, exibicao e ajuda. A leitura e a exportacao ocorrem em workers para manter a interface responsiva.

### Visualizacao

O modulo `graficos.py` concentra o modelo de curvas e os componentes de plotagem. Cada curva pode manter seus dados em buffer circular e ser exibida com eixo, cor e espessura configuraveis. A area de plotagem suporta tres eixos Y, sincronizacao do eixo X, crosshair, tooltip multisserie, legenda interativa, anotacoes e recorte temporal.

### Replay e streaming

O modulo `streaming.py` implementa o motor de reproducao. Ele controla estados parado, reproduzindo, pausado e ao vivo, alem de velocidade, busca, marcadores, janela deslizante e passos de tempo ou amostra.

O `SimuladorSCADA` produz lotes de amostras para validar o fluxo de ingestao sem depender de um equipamento ou protocolo externo. O ponto de extensao `FonteAoVivo` foi preparado para futuras integracoes com OPC UA, driver SCADA ou socket.

## 4. Fluxo de dados

```text
XLSX por sensor
      |
      v
Leitura e normalizacao
      |
      +--> CSV / Parquet
      |
      +--> _manifest.csv
      |
      v
Curvas em memoria
      |
      +--> Graficos interativos
      |
      +--> Replay temporal
      |
      +--> Feed ao vivo / simulador
```

## 5. Arquitetura dos modulos

| Modulo | Responsabilidade |
| --- | --- |
| `converter_scada.py` | Leitura de XLSX, normalizacao, conversao e manifesto. |
| `conversor_gui.py` | Janela principal, selecao de arquivos, tabela e comandos do usuario. |
| `graficos.py` | Temas, curvas, buffers, areas de plotagem e interacoes visuais. |
| `streaming.py` | Motor de replay, barra de transporte e fontes de dados ao vivo. |

A dependencia entre os modulos segue uma direcao simples: a interface usa o conversor, os graficos e o streaming; o streaming reutiliza as estruturas de graficos; o conversor pode ser utilizado de forma independente pela linha de comando.

## 6. Contrato de entrada e saida

Entrada minima esperada:

```text
Coluna A: timestamp
Coluna B: valor
```

O timestamp pode ser um datetime nativo do Excel ou texto no formato `dd/mm/aaaa hh:mm:ss`. O valor pode ser numerico ou texto com virgula decimal.

Saidas principais:

- `<TAG>.csv`: serie temporal em texto, com timestamp ISO 8601.
- `<TAG>.parquet`: serie temporal colunar, com compressao Zstandard.
- `_manifest.csv`: indice consolidado de todos os sensores processados.

## 7. Requisitos nao funcionais

- Manter a interface responsiva durante leitura e exportacao.
- Evitar carregar planilhas inteiras desnecessariamente na memoria.
- Permitir processamento de arquivos grandes com paralelismo limitado por memoria.
- Manter uma fonte unica de verdade para a logica de conversao.
- Separar ingestao, modelo de dados, plotagem e controle temporal para facilitar novas integracoes.

## 8. Roadmap sugerido

1. Adicionar testes unitarios para parsing, deduplicacao, sanitizacao e manifesto.
2. Criar um arquivo de dependencias versionado, como `requirements.txt`.
3. Adicionar exemplos pequenos de entrada e saida para validacao rapida.
4. Implementar leitura de fontes SCADA reais atras de `FonteAoVivo`.
5. Adicionar exportacao de imagens e relatorios de analise.
6. Definir licenca, politica de contribuicao e convencao de versionamento.
