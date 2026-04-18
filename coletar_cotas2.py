"""
Coletor de Cotas CVM 2026 - Dashboard 2
Baixa o Informe Diario da CVM para os 4 fundos Lagunna/Neblina
e gera o CSV consolidado em output/cotas_fundos2_2026_consolidado.csv
"""

import os
import io
import csv
import zipfile
import requests
import pandas as pd
from datetime import datetime, date

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURACAO
# ──────────────────────────────────────────────────────────────────────────────

CNPJS = {
    "18189040000199": "Lagunna",
    "09188983000106": "Neblina_Equity",
    "08296871000106": "Neblina",
    "59196483000194": "Neblina_II",
}

OUTPUT_DIR = os.path.join(os.getcwd(), "output")
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "cotas_fundos2_2026_consolidado.csv")
BASE_URL   = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{ano}{mes:02d}.zip"

# ──────────────────────────────────────────────────────────────────────────────
# AUXILIARES
# ──────────────────────────────────────────────────────────────────────────────

def norm(s):
    return "".join(c for c in (s or "") if c.isdigit())

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# DOWNLOAD
# ──────────────────────────────────────────────────────────────────────────────

def baixar_mes(ano, mes):
    url = BASE_URL.format(ano=ano, mes=mes)
    print(f"  Baixando {ano}-{mes:02d}... ", end="", flush=True)
    try:
        r = requests.get(url, timeout=120)
        if r.status_code != 200:
            print(f"HTTP {r.status_code} — pulando")
            return []
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            csvname = next(n for n in z.namelist() if n.endswith(".csv"))
            with z.open(csvname) as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"), delimiter=";")
                rows = list(reader)

        col_cnpj = "CNPJ_FUNDO_CLASSE" if rows and "CNPJ_FUNDO_CLASSE" in rows[0] else "CNPJ_FUNDO"
        filtrados = [r for r in rows if norm(r.get(col_cnpj, "")) in CNPJS]
        print(f"{len(filtrados)} registros dos fundos")
        return filtrados, col_cnpj
    except Exception as e:
        print(f"ERRO: {e}")
        return [], None

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

print("\n=== Coletor de Cotas CVM 2026 — Dashboard 2 ===\n")

hoje = date.today()
todos = []
col_cnpj_global = "CNPJ_FUNDO"

# Dezembro 2025 (cota base)
resultado = baixar_mes(2025, 12)
if resultado and resultado[0]:
    rows, col = resultado
    col_cnpj_global = col
    todos.extend(rows)

# Janeiro 2026 até mês atual
for mes in range(1, hoje.month + 1):
    resultado = baixar_mes(2026, mes)
    if resultado and resultado[0]:
        rows, col = resultado
        col_cnpj_global = col
        todos.extend(rows)

if not todos:
    print("ERRO: nenhum dado baixado.")
    raise SystemExit(1)

# ──────────────────────────────────────────────────────────────────────────────
# PROCESSA E SALVA
# ──────────────────────────────────────────────────────────────────────────────

df = pd.DataFrame(todos)
df["CNPJ_NORM"] = df[col_cnpj_global].apply(norm)
df["NOME_FUNDO"] = df["CNPJ_NORM"].map(CNPJS)
df["DT_COMPTC"]  = df["DT_COMPTC"].str.strip()
df["VL_QUOTA"]   = df["VL_QUOTA"].str.replace(",", ".")
df["VL_PATRIM_LIQ"] = df["VL_PATRIM_LIQ"].str.replace(",", ".")

# Filtra só 2026 e dez/2025
df = df[df["DT_COMPTC"] >= "2025-12-01"]
df = df.drop_duplicates(subset=["CNPJ_NORM", "DT_COMPTC"])
df = df.sort_values(["CNPJ_NORM", "DT_COMPTC"])

# Colunas de saída
colunas = ["DT_COMPTC", "CNPJ_NORM", "NOME_FUNDO", "VL_QUOTA", "VL_PATRIM_LIQ"]
colunas_existentes = [c for c in colunas if c in df.columns]
df_out = df[colunas_existentes]

df_out.to_csv(OUTPUT_CSV, sep=";", index=False, encoding="utf-8-sig")
print(f"\nCSV salvo: {OUTPUT_CSV}")
print(f"Total de registros: {len(df_out):,}")
print(f"Período: {df_out['DT_COMPTC'].min()} → {df_out['DT_COMPTC'].max()}")
print(f"Fundos: {df_out['NOME_FUNDO'].unique().tolist()}")
print("\nConcluido")
