"""Correlação de vínculos Emitente -> Produto -> Destinatário.

Constrói um grafo tripartido (emitente / produto / destinatário) a partir do
DataFrame normalizado produzido por `ingest.py`. A visualização (estilo i2)
não tenta renderizar a base inteira de uma vez — o usuário seleciona quais
emitentes, destinatários e/ou produtos quer investigar, e o grafo é
construído apenas com as notas que envolvem essa seleção, o que mantém a
renderização navegável mesmo com ~640 mil linhas de origem.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import networkx as nx


def preparar_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona colunas de identidade (emit_id, dest_id, produto_id) ao DataFrame.

    Vetorizado (em vez de `.apply(axis=1)`) porque a base tem ~640 mil linhas
    e a versão por linha levava dezenas de segundos a mais sem necessidade.
    """
    df = df.copy()

    df["emit_id"] = df["emit_cnpj"].fillna(df["emit_cpf"])
    df["emit_id"] = df["emit_id"].fillna("EMIT_SEM_DOC::" + df["emit_nome"].fillna(""))

    df["dest_id"] = df["dest_cnpj"].fillna(df["dest_cpf"])
    df["dest_id"] = df["dest_id"].fillna(
        "DEST_SEM_DOC::" + df["dest_nome"].fillna("") + "::" + df["dest_municipio"].fillna("")
    )

    ncm = df["produto_ncm"].fillna("").str.strip()
    nome_prod = df["produto_nome"].fillna("").str.strip().str.upper()
    df["produto_id"] = np.select(
        condlist=[ncm != "", nome_prod != ""],
        choicelist=["NCM_" + ncm, "PROD_" + nome_prod],
        default="PROD_DESCONHECIDO",
    )

    return df


def listar_emitentes(df: pd.DataFrame) -> pd.DataFrame:
    """Lista emitentes distintos (id + nome), ordenados por nome."""
    e = df[["emit_id", "emit_nome"]].drop_duplicates("emit_id").rename(columns={"emit_id": "id", "emit_nome": "nome"})
    return e.sort_values("nome", na_position="last")


def listar_destinatarios(df: pd.DataFrame) -> pd.DataFrame:
    """Lista destinatários distintos (id + nome), ordenados por nome."""
    d = df[["dest_id", "dest_nome"]].drop_duplicates("dest_id").rename(columns={"dest_id": "id", "dest_nome": "nome"})
    return d.sort_values("nome", na_position="last")


def listar_produtos(df: pd.DataFrame) -> pd.DataFrame:
    """Lista produtos distintos (id + nome), ordenados por nome."""
    p = df[["produto_id", "produto_nome"]].drop_duplicates("produto_id").rename(
        columns={"produto_id": "id", "produto_nome": "nome"}
    )
    return p.sort_values("nome", na_position="last")


def construir_grafo_selecao(
    df: pd.DataFrame,
    emit_ids: list[str] | None = None,
    dest_ids: list[str] | None = None,
    produto_ids: list[str] | None = None,
    max_notas: int = 1200,
) -> tuple[nx.Graph, int, int]:
    """Constrói o grafo tripartido restrito às notas que envolvem a seleção.

    Uma nota entra no recorte se envolver QUALQUER um dos emitentes,
    destinatários ou produtos selecionados (OR entre os filtros). Quando o
    recorte resultante é maior que `max_notas`, mantém apenas as notas de
    maior valor para preservar a navegabilidade do grafo no navegador.

    Retorna `(grafo, total_notas_encontradas, total_notas_exibidas)`.
    """
    emit_ids = set(emit_ids or [])
    dest_ids = set(dest_ids or [])
    produto_ids = set(produto_ids or [])
    selecionados = emit_ids | dest_ids | produto_ids

    if not selecionados:
        return nx.Graph(), 0, 0

    mask = pd.Series(False, index=df.index)
    if emit_ids:
        mask |= df["emit_id"].isin(emit_ids)
    if dest_ids:
        mask |= df["dest_id"].isin(dest_ids)
    if produto_ids:
        mask |= df["produto_id"].isin(produto_ids)

    sub = df[mask]
    total_encontradas = sub["chave_nfe"].nunique()

    if total_encontradas > max_notas:
        chaves_top = sub.drop_duplicates("chave_nfe").nlargest(max_notas, "valor_nota")["chave_nfe"]
        sub = sub[sub["chave_nfe"].isin(chaves_top)]
    total_exibidas = sub["chave_nfe"].nunique()

    g = nx.Graph()

    def _add_no(id_, nome, tipo):
        if g.has_node(id_):
            return
        g.add_node(
            id_,
            label=nome or id_,
            tipo=tipo,
            selecionado=id_ in selecionados,
            titulo=f"{nome}\n{id_}" if nome else str(id_),
        )

    emit_prod = sub.groupby(["emit_id", "produto_id"]).agg(
        emit_nome=("emit_nome", "first"),
        produto_nome=("produto_nome", "first"),
        qtd_notas=("chave_nfe", "nunique"),
        valor=("produto_valor", "sum"),
    )
    for (emit_id, produto_id), r in emit_prod.iterrows():
        _add_no(emit_id, r["emit_nome"], "emitente")
        _add_no(produto_id, r["produto_nome"], "produto")
        g.add_edge(emit_id, produto_id, peso=r["qtd_notas"], titulo=f"{r['qtd_notas']} nota(s) - R$ {r['valor']:,.2f}")

    prod_dest = sub.groupby(["produto_id", "dest_id"]).agg(
        produto_nome=("produto_nome", "first"),
        dest_nome=("dest_nome", "first"),
        qtd_notas=("chave_nfe", "nunique"),
        valor=("produto_valor", "sum"),
    )
    for (produto_id, dest_id), r in prod_dest.iterrows():
        _add_no(produto_id, r["produto_nome"], "produto")
        _add_no(dest_id, r["dest_nome"], "destinatario")
        g.add_edge(produto_id, dest_id, peso=r["qtd_notas"], titulo=f"{r['qtd_notas']} nota(s) - R$ {r['valor']:,.2f}")

    return g, total_encontradas, total_exibidas


def estatisticas_gerais(df: pd.DataFrame) -> dict:
    notas_unicas = df.drop_duplicates("chave_nfe")
    return {
        "total_notas": len(notas_unicas),
        "total_itens": len(df),
        "total_emitentes": df["emit_id"].nunique(),
        "total_destinatarios": df["dest_id"].nunique(),
        "total_produtos": df["produto_id"].nunique(),
        "valor_total": notas_unicas["valor_nota"].sum(),
        "destinatarios_doc_aproximado": int(df.loc[df["doc_aproximado"], "dest_id"].nunique()),
    }
