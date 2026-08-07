# NETWORK — Análise de Vínculos (estilo i2)

Aplicação para correlacionar **Emitente -> Produto -> Destinatário** a partir
de notas fiscais eletrônicas (CSVs) e visualizar os vínculos em um grafo
interativo, no estilo de ferramentas de análise de vínculos (ex.: i2 Analyst's
Notebook).

## Estrutura

```
NETWORK/
├── memoria/            # histórico de desenvolvimento e decisões técnicas
├── src/
│   ├── ingest.py        # leitura e normalização dos CSVs de origem
│   ├── vinculos.py       # correlação de entidades e construção do grafo
│   └── app.py            # aplicação Streamlit (interface de visualização)
├── scripts/
│   └── preprocessar.py   # gera o Parquet em cache a partir dos CSVs
├── data_processed/       # saída do pré-processamento (gerado, não versionado)
└── requirements.txt
```

## Como rodar

```bash
pip install -r requirements.txt

# 1. Pré-processa os CSVs de origem (rodar de novo sempre que os CSVs mudarem)
python scripts/preprocessar.py

# 2. Sobe a interface
streamlit run src/app.py
```

Por padrão o Streamlit abre em `http://localhost:8501`. Caso a porta esteja
ocupada pelo app DOSSIE, use `streamlit run src/app.py --server.port 8502`.

## Fonte de dados

Os CSVs de origem ficam na raiz deste projeto (compartilhamento de rede
`\\qliksense02\gecof2\PROJETOS\AGENTE_IA\NETWORK`, montado localmente como
`W:\PROJETOS\AGENTE_IA\NETWORK`). Ver `memoria/2026-08-07-setup-projeto-network.md`
para o diagnóstico completo dos campos e das inconsistências encontradas
(notação científica corrompendo CNPJ/CPF em um dos arquivos).
