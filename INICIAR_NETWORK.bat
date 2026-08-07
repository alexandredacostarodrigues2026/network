@echo off
chcp 65001 >nul
title NETWORK - Analise de Vinculos
cd /d "%~dp0"

if not exist "data_processed\notas_normalizadas.parquet" (
    echo Primeira execucao: processando os CSVs de origem, isso leva cerca de 1 minuto...
    python scripts\preprocessar.py
)

echo.
echo Iniciando NETWORK em http://localhost:8502 ...
echo O navegador abrira automaticamente. Para encerrar, feche esta janela.
echo.

streamlit run src\app.py --server.port 8502

pause
