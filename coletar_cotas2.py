"""
Coletor de Cotas CVM 2026 - Dashboard 2
Baixa o Informe Diario da CVM para os 4 fundos Lagunna/Neblina
e gera o CSV consolidado em output/cotas_fundos2_2026_consolidado.csv

Resiliencia:
- Retry com backoff exponencial (falhas de conexao e 5xx).
- Dezembro/2025 fica em cache local (mes fechado, nao muda mais).
- Se algum mes falhar, o CSV anterior e MESCLADO em vez de sobrescrito,
  para que uma queda de rede nao encurte o historico do dashboard.
"""

import os
import io
import csv
import zipfile
import requests
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import date

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

# Dezembro/2025 e um mes fechado: o ZIP nao muda mais. Guardamos os registros
# ja filtrados aqui para nao depender da CVM em todo run. Comite este arquivo
# no repo para que o cache sobreviva entre execucoes do Actions.
CACHE_DIR = os.path.join(os.getcwd(), "cache")
CACHE_DEZ = os.path.join(CACHE_DIR, "inf_diario_2025-12_fundos.csv")

# RESG_DIA e CAPTC_DIA vem do informe diario e sao os fluxos do FUNDO INTEIRO
# (todos os cotistas). Sem eles no CSV, o dashboard mostra "n.d.".
COLUNAS_SAIDA = [
    "DT_COMPTC", "CNPJ_NORM", "NOME_FUNDO",
    "VL_QUOTA", "VL_PATRIM_LIQ",
    "RESG_DIA", "CAPTC_DIA",
]

TIMEOUT    = 120
TENTATIVAS = 4      # 1 inicial + 4 retries
BACKOFF    = 3      # 3s, 6s, 12s, 24s

# ──────────────────────────────────────────────────────────────────────────────
# AUXILIARES
# ──────────────────────────────────────────────────────────────────────────────

def norm(s):
    return "".join(c for c in (s or "") if c.isdigit())

def detecta_col_cnpj(rows):
    """Pos-RCVM 175 o informe usa CNPJ_FUNDO_CLASSE; antes, CNPJ_FUNDO."""
    if rows and "CNPJ_FUNDO_CLASSE" in rows[0]:
        return "CNPJ_FUNDO_CLASSE"
    return "CNPJ_FUNDO"

def nova_sessao():
    s = requests.Session()
    retry = Retry(
        total=TENTATIVAS,
        connect=TENTATIVAS,      # cobre o [Errno 101] Network is unreachable
        read=TENTATIVAS,
        status=TENTATIVAS,
        backoff_factor=BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": "cvm-dashboard2 (+github.com/rhv78)"})
    return s

SESSAO = nova_sessao()

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# DOWNLOAD
# ──────────────────────────────────────────────────────────────────────────────

def baixar_mes(ano, mes):
    """
    Retorna (rows, status). status:
      'ok'         -> baixou e filtrou
      'vazio'      -> baixou, mas nenhum registro dos nossos fundos
      'nao_publicado' -> 404 (mes ainda nao existe no portal) — nao e falha
      'erro'       -> falha de rede/HTTP mesmo apos os retries
    """
    url = BASE_URL.format(ano=ano, mes=mes)
    print(f"  Baixando {ano}-{mes:02d}... ", end="", flush=True)
    try:
        r = SESSAO.get(url, timeout=TIMEOUT)
    except Exception as e:
        print(f"ERRO apos {TENTATIVAS} tentativas: {type(e).__name__}: {e}")
        return [], "erro"

    if r.status_code == 404:
        print("404 — mes ainda nao publicado")
        return [], "nao_publicado"
    if r.status_code != 200:
        print(f"HTTP {r.status_code} — falhou")
        return [], "erro"

    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            csvname = next(n for n in z.namelist() if n.endswith(".csv"))
            with z.open(csvname) as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"), delimiter=";")
                rows = list(reader)
    except Exception as e:
        print(f"ERRO ao abrir o ZIP: {type(e).__name__}: {e}")
        return [], "erro"

    col = detecta_col_cnpj(rows)
    filtrados = [r_ for r_ in rows if norm(r_.get(col, "")) in CNPJS]
    if not filtrados:
        print("0 registros dos fundos")
        return [], "vazio"

    print(f"{len(filtrados)} registros dos fundos")
    return filtrados, "ok"

def carregar_dez2025():
    """Dezembro/2025 vem do cache local se existir; senao baixa e cacheia."""
    if os.path.exists(CACHE_DEZ):
        with open(CACHE_DEZ, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        if rows:
            print(f"  2025-12 (cache): {len(rows)} registros")
            return rows, "ok"

    rows, status = baixar_mes(2025, 12)
    if rows:
        with open(CACHE_DEZ, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=";")
            w.writeheader()
            w.writerows(rows)
        print(f"  2025-12 salvo em cache: {CACHE_DEZ}")
    return rows, status

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

print("\n=== Coletor de Cotas CVM 2026 — Dashboard 2 ===\n")

hoje   = date.today()
todos  = []
falhas = []

rows, status = carregar_dez2025()
if rows:
    todos.extend(rows)
elif status == "erro":
    falhas.append("2025-12")

for mes in range(1, hoje.month + 1):
    rows, status = baixar_mes(2026, mes)
    if rows:
        todos.extend(rows)
    elif status == "erro":
        falhas.append(f"2026-{mes:02d}")

if falhas:
    print(f"\n  AVISO: falha ao baixar {len(falhas)} mes(es): {', '.join(falhas)}")
    print("         O CSV anterior sera mesclado para nao perder historico.\n")

# ──────────────────────────────────────────────────────────────────────────────
# PROCESSA
# ──────────────────────────────────────────────────────────────────────────────

df_novo = pd.DataFrame()

if todos:
    df_novo = pd.DataFrame(todos)
    col_cnpj = detecta_col_cnpj(todos)
    df_novo["CNPJ_NORM"]  = df_novo[col_cnpj].apply(norm)
    df_novo["NOME_FUNDO"] = df_novo["CNPJ_NORM"].map(CNPJS)
    df_novo["DT_COMPTC"]  = df_novo["DT_COMPTC"].str.strip()

    for c in ("VL_QUOTA", "VL_PATRIM_LIQ", "RESG_DIA", "CAPTC_DIA"):
        if c in df_novo.columns:
            df_novo[c] = df_novo[c].astype(str).str.replace(",", ".")
        else:
            print(f"  AVISO: coluna {c} ausente no informe da CVM.")

    df_novo = df_novo[df_novo["DT_COMPTC"] >= "2025-12-01"]
    df_novo = df_novo[[c for c in COLUNAS_SAIDA if c in df_novo.columns]]

# Mescla com o consolidado anterior: os registros novos tem prioridade,
# os antigos preenchem o que nao veio nesta execucao.
df_antigo = pd.DataFrame()
if os.path.exists(OUTPUT_CSV):
    try:
        df_antigo = pd.read_csv(OUTPUT_CSV, sep=";", dtype=str, encoding="utf-8-sig")
        print(f"  CSV anterior: {len(df_antigo):,} registros")
    except Exception as e:
        print(f"  AVISO: nao foi possivel ler o CSV anterior ({e}).")

if df_novo.empty and df_antigo.empty:
    print("\nERRO: nenhum dado baixado e nenhum CSV anterior disponivel.")
    raise SystemExit(1)

if df_novo.empty:
    print("\n  AVISO: nada baixado nesta execucao — mantendo o CSV anterior.")
    print("         O dashboard sera gerado com dados defasados.")
    raise SystemExit(0)

df = pd.concat([df_novo, df_antigo], ignore_index=True) if not df_antigo.empty else df_novo
df = df.drop_duplicates(subset=["CNPJ_NORM", "DT_COMPTC"], keep="first")
df = df.sort_values(["CNPJ_NORM", "DT_COMPTC"])

df_out = df[[c for c in COLUNAS_SAIDA if c in df.columns]]
df_out.to_csv(OUTPUT_CSV, sep=";", index=False, encoding="utf-8-sig")

print(f"\nCSV salvo: {OUTPUT_CSV}")
print(f"Total de registros: {len(df_out):,}")
print(f"Período: {df_out['DT_COMPTC'].min()} → {df_out['DT_COMPTC'].max()}")
print(f"Fundos: {df_out['NOME_FUNDO'].unique().tolist()}")
print(f"Colunas: {list(df_out.columns)}")
if falhas:
    print(f"ATENCAO: meses nao atualizados nesta execucao: {', '.join(falhas)}")
print("\nConcluido")
