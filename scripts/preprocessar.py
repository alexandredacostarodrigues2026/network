"""Pré-processa os CSVs de origem uma única vez e grava o resultado em Parquet.

Executar sempre que os CSVs de origem forem atualizados:

    python scripts/preprocessar.py [diretorio_com_csvs]

Se `diretorio_com_csvs` não for informado, usa a raiz do projeto e descobre
automaticamente os CSVs presentes nela (mesmo mecanismo usado pelo app
Streamlit ao clicar em "Buscar CSVs no diretório").

O app Streamlit (`src/app.py`) lê o Parquet gerado aqui em vez de reprocessar
os CSVs a cada execução.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ingest import carregar_notas, descobrir_csvs
from vinculos import preparar_ids

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "data_processed" / "notas_normalizadas.parquet"


def main():
    diretorio = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ

    encontrados = descobrir_csvs(diretorio)
    print(f"Diretório: {diretorio}")
    print(f"CSVs encontrados: {len(encontrados)}")
    for arq in encontrados:
        print(f"  - {arq.name}")

    inicio = time.time()
    print("\nCarregando e normalizando CSVs de origem...")
    df = carregar_notas(diretorio)
    print(f"  {len(df):,} linhas carregadas em {time.time() - inicio:.1f}s")

    print("Calculando identidades de emitente/destinatário/produto...")
    df = preparar_ids(df)

    SAIDA.parent.mkdir(exist_ok=True)
    df.to_parquet(SAIDA, index=False)
    print(f"Parquet salvo em {SAIDA} ({SAIDA.stat().st_size / 1_048_576:.1f} MB)")
    print(f"Tempo total: {time.time() - inicio:.1f}s")


if __name__ == "__main__":
    main()
