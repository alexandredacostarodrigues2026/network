"""Correlação de vínculos Emitente -> Produto -> Destinatário.

Constrói um grafo tripartido (emitente / produto / destinatário) a partir do
DataFrame normalizado produzido por `ingest.py`. A visualização (estilo i2)
não tenta renderizar a base inteira de uma vez — o usuário busca uma
entidade (CNPJ, CPF ou nome) e o grafo é construído em torno dela (ego-network),
o que mantém a renderização navegável mesmo com ~640 mil linhas de origem.
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


def buscar_entidades(df: pd.DataFrame, termo: str, limite: int = 20) -> pd.DataFrame:
    """Procura emitentes/destinatários por nome ou documento (busca parcial)."""
    termo_norm = termo.strip().lower()
    if not termo_norm:
        return pd.DataFrame(columns=["id", "nome", "tipo", "municipio", "uf"])

    emit = df[["emit_id", "emit_nome", "emit_municipio", "emit_uf"]].drop_duplicates("emit_id")
    emit.columns = ["id", "nome", "municipio", "uf"]
    emit["tipo"] = "emitente"

    dest = df[["dest_id", "dest_nome", "dest_municipio", "dest_uf"]].drop_duplicates("dest_id")
    dest.columns = ["id", "nome", "municipio", "uf"]
    dest["tipo"] = "destinatario"

    todas = pd.concat([emit, dest], ignore_index=True)
    filtro = (
        todas["id"].str.lower().str.contains(termo_norm, na=False)
        | todas["nome"].str.lower().str.contains(termo_norm, na=False)
    )
    return todas[filtro].head(limite)


def construir_grafo_entidade(
    df: pd.DataFrame, entidade_id: str, max_produtos: int = 15, max_contrapartes_por_produto: int = 8
) -> nx.Graph:
    """Constrói o ego-network de uma entidade: entidade -> produtos -> contrapartes.

    `entidade_id` pode ser um emit_id ou um dest_id. Os produtos mais
    relevantes (por valor total transacionado) são priorizados, e para cada
    produto apenas as contrapartes mais relevantes são incluídas, mantendo o
    grafo em um tamanho navegável no navegador.
    """
    g = nx.Graph()

    linhas_emit = df[df["emit_id"] == entidade_id]
    linhas_dest = df[df["dest_id"] == entidade_id]

    if linhas_emit.empty and linhas_dest.empty:
        return g

    nome_entidade = (
        linhas_emit["emit_nome"].iloc[0] if not linhas_emit.empty else linhas_dest["dest_nome"].iloc[0]
    )
    g.add_node(entidade_id, label=nome_entidade, tipo="foco", titulo=f"{nome_entidade}\n{entidade_id}")

    def _processar(linhas: pd.DataFrame, papel: str):
        if linhas.empty:
            return
        contraparte_id_col = "dest_id" if papel == "emitente" else "emit_id"
        contraparte_nome_col = "dest_nome" if papel == "emitente" else "emit_nome"

        por_produto = (
            linhas.groupby("produto_id")
            .agg(produto_nome=("produto_nome", "first"), valor_total=("produto_valor", "sum"), qtd_notas=("chave_nfe", "nunique"))
            .sort_values("valor_total", ascending=False)
            .head(max_produtos)
        )

        for produto_id, prod_row in por_produto.iterrows():
            g.add_node(
                produto_id,
                label=prod_row["produto_nome"] or produto_id,
                tipo="produto",
                titulo=f"{prod_row['produto_nome']}\nValor total: R$ {prod_row['valor_total']:,.2f}",
            )
            g.add_edge(
                entidade_id,
                produto_id,
                peso=prod_row["qtd_notas"],
                titulo=f"{prod_row['qtd_notas']} nota(s)",
            )

            linhas_produto = linhas[linhas["produto_id"] == produto_id]
            contrapartes = (
                linhas_produto.groupby(contraparte_id_col)
                .agg(nome=(contraparte_nome_col, "first"), valor_total=("produto_valor", "sum"), qtd_notas=("chave_nfe", "nunique"))
                .sort_values("valor_total", ascending=False)
                .head(max_contrapartes_por_produto)
            )
            for contraparte_id, cp_row in contrapartes.iterrows():
                if contraparte_id == entidade_id:
                    # Mesma entidade pesquisada aparecendo do outro lado do
                    # vínculo (ex.: também é destinatária de si mesma em
                    # outra nota) — mantém o nó "foco" em vez de sobrescrever.
                    g.add_edge(produto_id, contraparte_id, peso=cp_row["qtd_notas"], titulo="")
                    continue
                tipo_contraparte = "destinatario" if papel == "emitente" else "emitente"
                g.add_node(
                    contraparte_id,
                    label=cp_row["nome"] or contraparte_id,
                    tipo=tipo_contraparte,
                    titulo=f"{cp_row['nome']}\n{contraparte_id}\nValor total: R$ {cp_row['valor_total']:,.2f}",
                )
                g.add_edge(
                    produto_id,
                    contraparte_id,
                    peso=cp_row["qtd_notas"],
                    titulo=f"{cp_row['qtd_notas']} nota(s) - R$ {cp_row['valor_total']:,.2f}",
                )

    _processar(linhas_emit, "emitente")
    _processar(linhas_dest, "destinatario")

    return g


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
