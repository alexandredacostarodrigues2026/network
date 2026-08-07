"""Ingestão dos CSVs de NF-e do projeto NETWORK.

Em vez de apontar para nomes de arquivo fixos, este módulo varre um
diretório em busca de CSVs, detecta automaticamente o delimitador e se os
campos de documento (CNPJ/CPF) estão íntegros, normaliza os campos de
Emitente, Destinatário e Produto, e devolve um único DataFrame pronto para a
etapa de correlação de vínculos (ver `vinculos.py`).

Isso permite apontar a aplicação para qualquer pasta com exportações no
mesmo layout (ex.: novas cargas depositadas no compartilhamento de rede do
projeto) sem alterar código.

Ver `memoria/2026-08-07-setup-projeto-network.md` para o diagnóstico dos
dados-fonte e as decisões técnicas por trás das regras de recuperação de
CNPJ abaixo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

COLUNAS_USADAS = {
    "fatonfe_infprot_chnfe": "chave_nfe",
    "fatonfe_infnfe_ide_dhemi_data": "data_emissao",
    "fatonfe_infnfe_emit_cnpj": "emit_cnpj",
    "fatonfe_infnfe_emit_cpf": "emit_cpf",
    "fatonfe_infnfe_emit_xnome": "emit_nome",
    "fatonfe_infnfe_emit_enderemit_xmun": "emit_municipio",
    "fatonfe_infnfe_emit_enderemit_uf": "emit_uf",
    "fatonfe_infnfe_dest_cnpj": "dest_cnpj",
    "fatonfe_infnfe_dest_cpf": "dest_cpf",
    "fatonfe_infnfe_dest_xnome": "dest_nome",
    "fatonfe_infnfe_dest_enderdest_xmun": "dest_municipio",
    "fatonfe_infnfe_dest_enderdest_uf": "dest_uf",
    "fatonfe_infnfe_total_icmstot_vnf": "valor_nota",
    "fatoitemnfe_infnfe_det_prod_xprod": "produto_nome",
    "fatoitemnfe_infnfe_det_prod_ncm": "produto_ncm",
    "fatoitemnfe_infnfe_det_prod_cfop": "produto_cfop",
    "fatoitemnfe_infnfe_det_prod_qcom": "produto_qtd",
    "fatoitemnfe_infnfe_det_prod_vprod": "produto_valor",
}

DELIMITADORES_CANDIDATOS = ["|", ";", ","]
PADRAO_NOTACAO_CIENTIFICA = re.compile(r"^\d[.,]\d+E\+\d+$", re.IGNORECASE)


def descobrir_csvs(diretorio: Path, recursivo: bool = False) -> list[Path]:
    """Lista os arquivos .csv de um diretório (a raiz do projeto por padrão)."""
    padrao = "**/*.csv" if recursivo else "*.csv"
    return sorted(diretorio.glob(padrao))


def _detectar_delimitador(cabecalho: str) -> str | None:
    """Escolhe, entre os delimitadores candidatos, o que reconhece as colunas esperadas."""
    for delim in DELIMITADORES_CANDIDATOS:
        campos = cabecalho.strip().split(delim)
        if any(col in campos for col in COLUNAS_USADAS):
            return delim
    return None


def _detectar_documentos_integros(caminho: Path, delimitador: str, encoding: str, n_amostras: int = 500) -> bool:
    """Assinala False se encontrar CNPJ/CPF em notação científica na amostra."""
    amostra = pd.read_csv(
        caminho,
        sep=delimitador,
        usecols=["fatonfe_infnfe_emit_cnpj", "fatonfe_infnfe_dest_cnpj"],
        dtype=str,
        encoding=encoding,
        nrows=n_amostras,
    )
    for col in ("fatonfe_infnfe_emit_cnpj", "fatonfe_infnfe_dest_cnpj"):
        if col in amostra and amostra[col].dropna().map(lambda v: bool(PADRAO_NOTACAO_CIENTIFICA.match(str(v)))).any():
            return False
    return True


def inspecionar_csv(caminho: Path, encoding: str = "latin1") -> dict | None:
    """Detecta delimitador e integridade de documentos de um CSV. None se schema não reconhecido."""
    with open(caminho, encoding=encoding, errors="replace") as f:
        cabecalho = f.readline()
    delimitador = _detectar_delimitador(cabecalho)
    if delimitador is None:
        return None
    documentos_integros = _detectar_documentos_integros(caminho, delimitador, encoding)
    return {"arquivo": caminho, "delimitador": delimitador, "documentos_integros": documentos_integros}


def _extrair_cnpj_da_chave(chave: str) -> str | None:
    """Extrai o CNPJ do emitente (posições 7-20) da chave de acesso NF-e."""
    if not isinstance(chave, str) or len(chave) != 44 or not chave.isdigit():
        return None
    return chave[6:20]


def _normalizar_documento(valor) -> str | None:
    """Normaliza CNPJ/CPF para dígitos puros; descarta valores corrompidos.

    Valores exportados em notação científica pelo Excel (ex.: '4,59332E+12')
    não têm precisão suficiente para reconstruir o documento e são
    descartados aqui (retornam None) em vez de propagar um número incorreto.
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto or texto.lower() == "nan":
        return None
    if "e" in texto.lower() or "," in texto:
        return None  # notação científica / separador decimal -> corrompido
    texto = texto.split(".")[0]
    if not texto.isdigit():
        return None
    return texto.zfill(11) if len(texto) <= 11 else texto.zfill(14)


def _ler_fonte(caminho: Path, delimitador: str, documentos_integros: bool, encoding: str = "latin1") -> pd.DataFrame:
    df = pd.read_csv(
        caminho,
        sep=delimitador,
        usecols=list(COLUNAS_USADAS.keys()),
        dtype=str,
        encoding=encoding,
        low_memory=False,
    )
    df = df.rename(columns=COLUNAS_USADAS)

    df["emit_cnpj"] = df["emit_cnpj"].map(_normalizar_documento)
    df["emit_cpf"] = df["emit_cpf"].map(_normalizar_documento)
    df["dest_cnpj"] = df["dest_cnpj"].map(_normalizar_documento)
    df["dest_cpf"] = df["dest_cpf"].map(_normalizar_documento)

    if not documentos_integros:
        # Recupera o CNPJ do emitente via chave de acesso quando a coluna
        # original veio corrompida por notação científica.
        precisa_recuperar = df["emit_cnpj"].isna()
        df.loc[precisa_recuperar, "emit_cnpj"] = df.loc[precisa_recuperar, "chave_nfe"].map(
            _extrair_cnpj_da_chave
        )

    df["doc_aproximado"] = False
    sem_doc_dest = df["dest_cnpj"].isna() & df["dest_cpf"].isna()
    df.loc[sem_doc_dest, "doc_aproximado"] = True

    for col in ("produto_qtd", "produto_valor", "valor_nota"):
        df[col] = pd.to_numeric(df[col].str.replace(",", "."), errors="coerce")

    df["arquivo_origem"] = caminho.name
    return df


def carregar_notas(
    diretorio: Path | None = None,
    arquivos: list[Path] | None = None,
    recursivo: bool = False,
) -> pd.DataFrame:
    """Descobre e carrega todos os CSVs reconhecidos de um diretório (ou lista explícita).

    Arquivos cujo cabeçalho não bate com nenhum delimitador/coluna esperada
    são ignorados (schema não reconhecido) em vez de derrubar a carga
    inteira — o objetivo é tolerar outros arquivos soltos na mesma pasta.
    """
    if arquivos is None:
        diretorio = diretorio or Path(__file__).resolve().parent.parent
        arquivos = descobrir_csvs(diretorio, recursivo=recursivo)

    partes = []
    ignorados = []
    for caminho in arquivos:
        info = inspecionar_csv(caminho)
        if info is None:
            ignorados.append(caminho)
            continue
        partes.append(_ler_fonte(info["arquivo"], info["delimitador"], info["documentos_integros"]))

    if ignorados:
        nomes = ", ".join(p.name for p in ignorados)
        print(f"Aviso: {len(ignorados)} arquivo(s) com schema não reconhecido, ignorado(s): {nomes}")

    if not partes:
        return pd.DataFrame(columns=list(COLUNAS_USADAS.values()) + ["doc_aproximado", "arquivo_origem"])

    return pd.concat(partes, ignore_index=True)


if __name__ == "__main__":
    df = carregar_notas()
    print(f"Notas carregadas: {len(df):,}")
    print(f"Sem documento de destinatário confiável: {df['doc_aproximado'].sum():,}")
    print(df.head())
