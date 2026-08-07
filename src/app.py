"""APP NETWORK — análise de vínculos (estilo i2) entre Emitente, Produto e
Destinatário a partir das notas fiscais eletrônicas do projeto.

Executar com:

    streamlit run src/app.py

Requer que `scripts/preprocessar.py` já tenha sido executado ao menos uma
vez (gera `data_processed/notas_normalizadas.parquet`).
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest import carregar_notas, descobrir_csvs
from vinculos import (
    construir_grafo_selecao,
    estatisticas_gerais,
    listar_destinatarios,
    listar_emitentes,
    listar_produtos,
    preparar_ids,
)

RAIZ = Path(__file__).resolve().parent.parent
PARQUET = RAIZ / "data_processed" / "notas_normalizadas.parquet"

CORES = {"emitente": "#3498db", "destinatario": "#2ecc71", "produto": "#f39c12"}

st.set_page_config(page_title="NETWORK — Análise de Vínculos", layout="wide")


@st.cache_data
def carregar_dados() -> pd.DataFrame:
    return pd.read_parquet(PARQUET)


@st.cache_data(show_spinner=False)
def processar_csvs(caminhos: tuple[str, ...]) -> pd.DataFrame:
    df = carregar_notas(arquivos=[Path(c) for c in caminhos])
    return preparar_ids(df)


def renderizar_grafo(grafo) -> str:
    net = Network(height="720px", width="100%", bgcolor="#111111", font_color="white")
    net.barnes_hut(gravity=-4000, spring_length=150)
    for no, dados in grafo.nodes(data=True):
        selecionado = dados.get("selecionado", False)
        net.add_node(
            no,
            label=str(dados.get("label", no))[:40],
            title=dados.get("titulo", ""),
            color=CORES.get(dados.get("tipo"), "#95a5a6"),
            shape="dot",
            size=26 if selecionado else 15,
            borderWidth=4 if selecionado else 1,
            borderWidthSelected=4,
            font={"color": "white", "size": 16 if selecionado else 12},
        )
    for origem, destino, dados in grafo.edges(data=True):
        net.add_edge(origem, destino, value=dados.get("peso", 1), title=dados.get("titulo", ""))

    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
        net.write_html(tmp.name, notebook=False)
        return Path(tmp.name).read_text(encoding="utf-8")


def sidebar_fonte_dados() -> pd.DataFrame | None:
    """Permite escolher um diretório, buscar os CSVs nele e (re)processá-los."""
    st.sidebar.header("Fonte de dados")
    diretorio_str = st.sidebar.text_input("Diretório com os CSVs", value=str(RAIZ))
    recursivo = st.sidebar.checkbox("Buscar em subpastas", value=False)

    diretorio = Path(diretorio_str)
    if not diretorio.is_dir():
        st.sidebar.error("Diretório não encontrado.")
        return None

    encontrados = descobrir_csvs(diretorio, recursivo=recursivo)
    if not encontrados:
        st.sidebar.warning("Nenhum CSV encontrado nesse diretório.")
        return None

    rotulos = [f.name for f in encontrados]
    selecionados = st.sidebar.multiselect("CSVs a processar", rotulos, default=rotulos)
    caminhos_selecionados = tuple(str(f) for f in encontrados if f.name in selecionados)

    if not caminhos_selecionados:
        st.sidebar.info("Selecione ao menos um CSV.")
        return None

    if st.sidebar.button("Processar CSVs selecionados", type="primary"):
        with st.spinner(f"Processando {len(caminhos_selecionados)} arquivo(s)..."):
            df = processar_csvs(caminhos_selecionados)
        df.to_parquet(PARQUET, index=False)
        carregar_dados.clear()
        st.sidebar.success(f"{len(df):,} linhas processadas e salvas em cache.")

    return None


def main():
    st.title("NETWORK — Análise de Vínculos entre Emitentes, Produtos e Destinatários")

    sidebar_fonte_dados()

    if not PARQUET.exists():
        st.error(
            "Nenhum dado processado ainda. Use a barra lateral para escolher um "
            "diretório com CSVs e clicar em **Processar CSVs selecionados** "
            "(ou execute `python scripts/preprocessar.py` pela linha de comando)."
        )
        return

    df = carregar_dados()
    stats = estatisticas_gerais(df)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Notas", f"{stats['total_notas']:,}")
    col2.metric("Emitentes", f"{stats['total_emitentes']:,}")
    col3.metric("Destinatários", f"{stats['total_destinatarios']:,}")
    col4.metric("Produtos", f"{stats['total_produtos']:,}")
    col5.metric("Destinatários sem doc. confiável", f"{stats['destinatarios_doc_aproximado']:,}")

    st.divider()
    st.subheader("Selecionar entidades para investigar")
    st.caption(
        "Escolha um ou mais emitentes, destinatários e/ou produtos (digite para buscar). "
        "O grafo mostra as notas que envolvem qualquer um dos selecionados."
    )

    emitentes = listar_emitentes(df).assign(rotulo=lambda d: d["nome"].fillna("(sem nome)") + " — " + d["id"])
    destinatarios = listar_destinatarios(df).assign(rotulo=lambda d: d["nome"].fillna("(sem nome)") + " — " + d["id"])
    produtos = listar_produtos(df).assign(rotulo=lambda d: d["nome"].fillna("(sem nome)") + " — " + d["id"])

    col_e, col_d, col_p = st.columns(3)
    rotulos_emit = col_e.multiselect("Emitentes", emitentes["rotulo"], placeholder="Buscar emitente...")
    rotulos_dest = col_d.multiselect("Destinatários", destinatarios["rotulo"], placeholder="Buscar destinatário...")
    rotulos_prod = col_p.multiselect("Produtos", produtos["rotulo"], placeholder="Buscar produto...")

    emit_ids = emitentes.loc[emitentes["rotulo"].isin(rotulos_emit), "id"].tolist()
    dest_ids = destinatarios.loc[destinatarios["rotulo"].isin(rotulos_dest), "id"].tolist()
    produto_ids = produtos.loc[produtos["rotulo"].isin(rotulos_prod), "id"].tolist()

    if not (emit_ids or dest_ids or produto_ids):
        st.info("Selecione ao menos um emitente, destinatário ou produto para montar o grafo.")
        return

    with st.spinner("Construindo grafo de vínculos..."):
        grafo, total_encontradas, total_exibidas = construir_grafo_selecao(df, emit_ids, dest_ids, produto_ids)

    if grafo.number_of_nodes() == 0:
        st.warning("Nenhum vínculo encontrado para a seleção.")
        return

    if total_exibidas < total_encontradas:
        st.caption(
            f"Mostrando as {total_exibidas:,} notas de maior valor entre {total_encontradas:,} "
            "encontradas, para manter o grafo navegável."
        )
    else:
        st.caption(f"{total_exibidas:,} nota(s) encontradas.")
    st.caption(f"{grafo.number_of_nodes()} nós, {grafo.number_of_edges()} vínculos exibidos.")

    html = renderizar_grafo(grafo)
    components.html(html, height=740, scrolling=True)

    st.markdown(
        "🔵 Emitente &nbsp;&nbsp; 🟢 Destinatário &nbsp;&nbsp; 🟠 Produto "
        "&nbsp;&nbsp; contorno branco = selecionado por você"
    )


if __name__ == "__main__":
    main()
