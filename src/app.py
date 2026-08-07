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
from vinculos import buscar_entidades, construir_grafo_entidade, estatisticas_gerais, preparar_ids

RAIZ = Path(__file__).resolve().parent.parent
PARQUET = RAIZ / "data_processed" / "notas_normalizadas.parquet"

CORES = {"foco": "#e74c3c", "emitente": "#3498db", "destinatario": "#2ecc71", "produto": "#f39c12"}

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
        net.add_node(
            no,
            label=str(dados.get("label", no))[:40],
            title=dados.get("titulo", ""),
            color=CORES.get(dados.get("tipo"), "#95a5a6"),
            shape="dot",
            size=25 if dados.get("tipo") == "foco" else 15,
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
    st.subheader("Buscar entidade (nome, CNPJ ou CPF)")
    termo = st.text_input("Termo de busca", placeholder="Ex.: JUSTINO, 41136094000299...")

    if not termo:
        st.info("Digite um nome ou documento para localizar uma entidade e explorar seus vínculos.")
        return

    resultados = buscar_entidades(df, termo)
    if resultados.empty:
        st.warning("Nenhuma entidade encontrada para esse termo.")
        return

    resultados = resultados.assign(
        rotulo=lambda d: d["tipo"] + " — " + d["nome"].fillna("") + " (" + d["id"] + ")"
    )
    escolha = st.selectbox("Selecione a entidade", resultados["rotulo"])
    entidade_id = resultados.loc[resultados["rotulo"] == escolha, "id"].iloc[0]

    with st.spinner("Construindo grafo de vínculos..."):
        grafo = construir_grafo_entidade(df, entidade_id)

    if grafo.number_of_nodes() <= 1:
        st.warning("Entidade encontrada, mas sem vínculos de produto/nota associados.")
        return

    st.caption(f"{grafo.number_of_nodes()} nós, {grafo.number_of_edges()} vínculos exibidos (recorte top valor).")
    html = renderizar_grafo(grafo)
    components.html(html, height=740, scrolling=True)

    st.markdown(
        "🔴 Entidade pesquisada &nbsp;&nbsp; 🔵 Emitente &nbsp;&nbsp; 🟢 Destinatário &nbsp;&nbsp; 🟠 Produto"
    )


if __name__ == "__main__":
    main()
