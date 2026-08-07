# Atualização 2026-08-07

## Resumo Executivo

Início do projeto NETWORK: aplicação de análise de vínculos (estilo i2) para
correlacionar Emitente -> Produto -> Destinatário a partir dos CSVs de NF-e
localizados em `\\qliksense02\gecof2\PROJETOS\AGENTE_IA\NETWORK` (montado
localmente como `W:\PROJETOS\AGENTE_IA\NETWORK`). Objetivo: extrair os dados,
correlacionar as entidades e exibir os vínculos em um grafo interativo.

---

## Funcionalidades Implementadas

- **Descoberta dinâmica de CSVs por diretório** (`src/ingest.py::descobrir_csvs`):
  em vez de nomes de arquivo fixos, a aplicação varre um diretório
  informado pelo usuário, detecta automaticamente o delimitador (`|`, `;`
  ou `,`) e se os campos de documento (CNPJ/CPF) estão íntegros ou
  corrompidos por notação científica, e ignora (com aviso) arquivos cujo
  schema não é reconhecido em vez de derrubar a carga inteira.
- **Ingestão e normalização** (`src/ingest.py::carregar_notas`): concatena
  todos os CSVs reconhecidos do diretório em um único DataFrame com
  Emitente, Destinatário e Produto normalizados.
- **Correlação de vínculos Emitente -> Produto -> Destinatário**
  (`src/vinculos.py`): grafo tripartido construído como ego-network em
  torno de uma entidade pesquisada (evita tentar renderizar as ~640 mil
  notas de uma vez).
- **Interface Streamlit** (`src/app.py`, porta 8502): busca por nome/CNPJ/CPF,
  grafo interativo (pyvis/vis.js) com cores por tipo de nó, métricas gerais
  da base, e uma barra lateral para apontar/reprocessar qualquer diretório
  de CSVs sem precisar editar código.
- **Script de pré-processamento em lote** (`scripts/preprocessar.py`): gera
  o Parquet em cache (`data_processed/notas_normalizadas.parquet`) a partir
  da linha de comando, aceitando um diretório opcional como argumento.

## Validação Realizada

- Ingestão dos dois CSVs de teste (581.901 + 55.958 linhas de item):
  637.859 linhas carregadas em ~50s, sem erros.
- Base consolidada: 275.991 notas únicas, 1.010 emitentes, 4.072
  destinatários, 960 produtos distintos, R$ 2.552.868.859,14 em valor total
  de notas; 137 destinatários (dentre os do arquivo `_et_`) permanecem sem
  documento confiável (fallback por nome, ver Pendências).
- Busca por "JUSTINO" retornou 10 entidades (emitentes e destinatários);
  grafo ego-network gerado para a primeira delas: 56 nós / 124 arestas,
  renderizado sem erros no navegador via pyvis.
- App Streamlit validado subindo em `http://localhost:8502` (HTTP 200) e
  acessível na rede em `http://10.50.5.84:8502`, seguindo o mesmo padrão de
  endereço das apps irmãs (`ENDEREÇOS` em :5173, `DOSSIE` em :8501).

---

## Correções Realizadas

- N/A (primeira sessão do projeto)

---

## Melhorias Técnicas

- N/A

---

## Refatorações

- N/A

---

## Alterações de Arquitetura

- Definida estrutura inicial do projeto:
  ```
  NETWORK/
  ├── memoria/        # histórico e decisões (esta pasta)
  ├── src/            # código da aplicação (ingestão, grafo, app streamlit)
  ├── scripts/        # scripts auxiliares de execução
  ├── data_processed/ # saídas processadas (parquet) — não versionar dados sensíveis
  └── requirements.txt
  ```
- Stack escolhida: Python + Streamlit + pandas + networkx + pyvis, por
  consistência com a aplicação irmã "APP DOSSIE" (Streamlit, porta 8501) já
  em uso pelo usuário, evitando introduzir uma stack Node/Cytoscape paralela
  sem necessidade.

---

## Diagnóstico dos Dados-Fonte (CSVs de NF-e)

Dois arquivos CSV foram identificados na raiz do projeto:

| Arquivo | Linhas | Delimitador | Observação |
|---|---|---|---|
| `alexandre.rodrigues-grupo_justimo_20-23_ep-13-08-2024-095134.csv` | 581.902 | `\|` (pipe) | Campos numéricos (CNPJ/CPF) preservados como texto — íntegros. |
| `alexandre.rodrigues-grupo_justimo_20-23_et-13-08-2024-094949.csv` | 55.959 | `;` (ponto e vírgula) | **CNPJ/CPF de emitente e destinatário corrompidos**: exportados em notação científica do Excel (ex.: `4,59332E+12`), com perda de precisão. |

Ambos os arquivos têm o mesmo schema (65 colunas), oriundo de um layout de
NF-e (nota fiscal eletrônica). Colunas relevantes mapeadas para as entidades
do grafo:

- **Emitente**: `fatonfe_infnfe_emit_cnpj`, `fatonfe_infnfe_emit_cpf`,
  `fatonfe_infnfe_emit_xnome`, `..._emit_enderemit_xmun`, `..._emit_enderemit_uf`
- **Destinatário**: `fatonfe_infnfe_dest_cnpj`, `fatonfe_infnfe_dest_cpf`,
  `fatonfe_infnfe_dest_xnome`, `..._dest_enderdest_xmun`, `..._dest_enderdest_uf`
- **Produto**: `fatoitemnfe_infnfe_det_prod_xprod`, `..._prod_cprod`,
  `..._prod_ncm`, `..._prod_cfop`, `..._prod_vprod`, `..._prod_qcom`
- **Nota fiscal (contexto do vínculo)**: `fatonfe_infprot_chnfe` (chave de
  acesso, 44 dígitos), `fatonfe_infnfe_ide_dhemi_data` (data de emissão),
  `fatonfe_infnfe_total_icmstot_vnf` (valor total da nota)

### Decisão técnica: recuperação de CNPJ do emitente via chave de acesso

A chave de acesso da NF-e (`chnfe`) segue layout fixo de 44 dígitos:
`cUF(2) + AAMM(4) + CNPJ-emitente(14) + mod(2) + serie(3) + nNF(9) + tpEmis(1) + cNF(8) + cDV(1)`.
Por isso, quando `fatonfe_infnfe_emit_cnpj` está em notação científica
(arquivo `et`), o CNPJ do emitente é recuperado com precisão total extraindo
os caracteres nas posições 7–20 da chave, em vez de usar a coluna corrompida.

### Pendência conhecida: CNPJ/CPF do destinatário no arquivo `et`

O documento do **destinatário** não está presente na chave de acesso, então
não há como recuperar os dígitos perdidos na notação científica do arquivo
`et` (55.959 linhas). Estratégia adotada para o MVP: quando o campo de
documento do destinatário não bate com o padrão de 11 (CPF) ou 14 (CNPJ)
dígitos, o nó é identificado por nome + município (`dest_xnome` +
`dest_xmun`), marcado com uma flag de qualidade (`doc_aproximado`) para
deixar claro na interface que a identidade não é 100% confiável. Solução
definitiva recomendada: re-exportar o arquivo `et` da fonte original
garantindo que as colunas de documento sejam tratadas como texto.

---

## Alterações de Banco de Dados

- N/A (dados processados serão persistidos como Parquet em `data_processed/`,
  não há banco de dados relacional nesta fase).

---

## Alterações de Infraestrutura

- Instalado pacote Python `pyvis` (0.3.2) para renderização do grafo
  interativo estilo i2 dentro do Streamlit.

---

## Dependências Atualizadas

### Adicionadas

- `pyvis==0.3.2` (e dependência transitiva `jsonpickle`)

### Já disponíveis no ambiente (reaproveitadas)

- `pandas`, `networkx`, `streamlit`, `pyarrow`

### Removidas

- N/A

---

## Arquivos Criados

- `memoria/2026-08-07-setup-projeto-network.md` (este arquivo)
- `src/ingest.py` — descoberta e normalização dos CSVs
- `src/vinculos.py` — correlação de vínculos e construção do grafo
- `src/app.py` — aplicação Streamlit
- `scripts/preprocessar.py` — pré-processamento em lote (CLI)
- `requirements.txt`, `README.md`, `.gitignore`

---

## Arquivos Modificados

- N/A (todos os arquivos de código são novos nesta sessão)

---

## Arquivos Removidos

- N/A

---

## Problemas Encontrados

- CNPJ/CPF corrompidos por notação científica no arquivo `_et_` (ver seção
  de diagnóstico acima).
- `vinculos.py::preparar_ids` usava `DataFrame.apply(axis=1)` para calcular
  os IDs de emitente/destinatário/produto, o que além de lento (~640 mil
  linhas) quebrava com `AttributeError` quando `produto_nome` vinha `NaN`
  (float, sem `.strip()`).
- No ego-network, quando a mesma entidade pesquisada aparecia do outro lado
  de um vínculo (ex.: também consta como destinatária de si mesma em outra
  nota), `networkx.Graph.add_node` sobrescrevia os atributos do nó "foco"
  (cor vermelha / destaque), fazendo a entidade pesquisada perder o
  destaque visual no grafo.

---

## Soluções Aplicadas

- Recuperação do CNPJ do emitente a partir da chave de acesso da NF-e.
- Fallback por nome+município para destinatário quando o documento é
  inválido, com flag explícita de qualidade do dado.
- `preparar_ids` reescrito de forma vetorizada (`fillna`/`np.select` em vez
  de `apply(axis=1)`), mais rápido e tolerante a valores nulos.
- `construir_grafo_entidade` agora detecta quando a contraparte é a própria
  entidade pesquisada e apenas liga a aresta, sem re-registrar o nó,
  preservando o tipo `"foco"`.

---

## Pendências

- Confirmar com a fonte de dados a possibilidade de reexportar o arquivo
  `_et_` com os campos de documento como texto, eliminando a necessidade do
  fallback por nome.
- Definir critério de poda/filtro do grafo para volumes grandes (~580 mil
  notas), já que renderizar todos os vínculos de uma vez inviabiliza a
  visualização no navegador.

---

## Próximos Passos

- Confirmar com a fonte se novos CSVs terão sempre o mesmo schema, para
  eventualmente relaxar a lista fixa de `COLUNAS_USADAS`.
- Avaliar necessidade de paginação/filtro por período (data de emissão) na
  interface, já que a base tende a crescer a cada nova carga.
- Definir política de retenção/backup do Parquet em `data_processed/`.
- Confirmar com o usuário a visibilidade do repositório GitHub
  (`alexandredacostarodrigues2026/network`) antes do push, dado que os
  CSVs de origem e os textos com endereços internos foram propositalmente
  excluídos via `.gitignore`.
