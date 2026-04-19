"""
Gerador de Dashboard CVM 2026 - Dashboard 2
Le o CSV consolidado e gera um HTML com graficos interativos
de rentabilidade real dos fundos Lagunna / Neblina.

Uso: python gerar_dashboard2.py
"""

import pandas as pd
import json
import os
import sys
from datetime import datetime, timezone, timedelta

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURACAO
# ──────────────────────────────────────────────────────────────────────────────

_BASE    = os.getcwd()
CSV_PATH = os.path.join(_BASE, "output", "cotas_fundos2_2026_consolidado.csv")

CNPJS = {
    "18189040000199": "Lagunna",
    "09188983000106": "Neblina_Equity",
    "08296871000106": "Neblina",
    "59196483000194": "Neblina_II",
}

CORES = {
    "18189040000199": "#1D9E75",
    "09188983000106": "#378ADD",
    "08296871000106": "#BA7517",
    "59196483000194": "#D85A30",
}

GRUPO_NEBLINA_CNPJS = ["09188983000106", "08296871000106", "59196483000194"]
GRUPO_NEBLINA_COR   = "#FFD700"

CDI_PERIODOS = [
    {"de": "2026-01-01", "ate": "2026-03-18", "anual": 14.90},
    {"de": "2026-03-19", "ate": "2099-12-31", "anual": 14.65},
]

def taxa_diaria_cdi(dt):
    for p in CDI_PERIODOS:
        if p["de"] <= dt <= p["ate"]:
            return (1 + p["anual"] / 100) ** (1 / 252) - 1
    return 0.0

# ──────────────────────────────────────────────────────────────────────────────
# AUXILIARES
# ──────────────────────────────────────────────────────────────────────────────

def norm(s):
    return "".join(c for c in (s or "") if c.isdigit())

def fmt_cnpj(s):
    s = s.zfill(14)
    return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"

# ──────────────────────────────────────────────────────────────────────────────
# LEITURA
# ──────────────────────────────────────────────────────────────────────────────

print("\n=== Gerador de Dashboard CVM 2026 — Dashboard 2 ===\n")

if not os.path.exists(CSV_PATH):
    print(f"ERRO: {CSV_PATH} nao encontrado.")
    print("Execute o coletar_cotas2.py primeiro.")
    sys.exit(1)

print(f"Lendo: {CSV_PATH}")
df = pd.read_csv(CSV_PATH, sep=";", encoding="utf-8-sig", dtype=str)
print(f"  {len(df):,} registros | colunas: {list(df.columns)}\n")

df["CNPJ_NORM"]   = df["CNPJ_NORM"].apply(norm)
df["VL_QUOTA_F"]  = pd.to_numeric(df["VL_QUOTA"].str.replace(",", "."),       errors="coerce")
df["VL_PATRIM_F"] = pd.to_numeric(df["VL_PATRIM_LIQ"].str.replace(",", "."), errors="coerce")
df["DT_COMPTC"]   = df["DT_COMPTC"].str.strip()
df = df.dropna(subset=["VL_QUOTA_F", "DT_COMPTC"]).sort_values("DT_COMPTC")

# ── ÚLTIMA DATA DA CVM ────────────────────────────────────────────────────────
ultima_cvm = df["DT_COMPTC"].max()
ultima_cvm_fmt = datetime.strptime(ultima_cvm, "%Y-%m-%d").strftime("%d/%m/%Y")

# ── COTA BASE DEZ/2025 ────────────────────────────────────────────────────────
dez25 = df[df["DT_COMPTC"] <= "2025-12-31"]
cota_base = {}
for cnpj in CNPJS:
    rows = dez25[dez25["CNPJ_NORM"] == cnpj].sort_values("DT_COMPTC")
    if not rows.empty:
        last = rows.iloc[-1]
        cota_base[cnpj] = {"dt": last["DT_COMPTC"], "cota": last["VL_QUOTA_F"]}
        print(f"  Base dez/2025  {CNPJS[cnpj]}: cota {last['VL_QUOTA_F']:.8f} em {last['DT_COMPTC']}")

# Filtra só 2026
df2026 = df[df["DT_COMPTC"] >= "2026-01-01"].copy()
datas_todas = sorted(df2026["DT_COMPTC"].unique())

# CDI index
cdi_idx = {}; acum = 1.0
for dt in datas_todas:
    acum *= (1 + taxa_diaria_cdi(dt))
    cdi_idx[dt] = acum

# ──────────────────────────────────────────────────────────────────────────────
# PROCESSA FUNDOS
# ──────────────────────────────────────────────────────────────────────────────

fundos = []

for cnpj_raw, nome in CNPJS.items():
    df_f = df2026[df2026["CNPJ_NORM"] == cnpj_raw].drop_duplicates("DT_COMPTC").sort_values("DT_COMPTC")
    if df_f.empty:
        print(f"  SEM DADOS: {fmt_cnpj(cnpj_raw)}"); continue

    cota_map   = dict(zip(df_f["DT_COMPTC"], df_f["VL_QUOTA_F"]))
    patrim_map = dict(zip(df_f["DT_COMPTC"], df_f["VL_PATRIM_F"]))

    if cnpj_raw in cota_base:
        cota_ini = cota_base[cnpj_raw]["cota"]
    else:
        cota_ini = df_f["VL_QUOTA_F"].iloc[0]

    hist = []

    if cnpj_raw in cota_base:
        patrim_dez = df[
            (df["CNPJ_NORM"] == cnpj_raw) & (df["DT_COMPTC"] == cota_base[cnpj_raw]["dt"])
        ]["VL_PATRIM_F"].values
        patrim_dez_val = float(patrim_dez[0]) if len(patrim_dez) > 0 else 0.0
        qt_dez = round(patrim_dez_val / (cota_ini * 1000), 6) if cota_ini else 0.0
        hist.append({
            "dt": "2025-12-31",
            "cota": round(cota_ini, 8),
            "cotas_qt": qt_dez,
            "patrimonio": round(qt_dez * cota_ini, 2),
            "rent_acum": 0.0,
            "var_diaria": 0.0,
        })

    for dt in datas_todas:
        if dt not in cota_map: continue
        c   = cota_map[dt]
        pat = patrim_map.get(dt, 0.0) or 0.0
        qt  = round(pat / (c * 1000), 6) if c else 0.0
        ra  = round((c / cota_ini - 1) * 100, 6) if cota_ini else 0.0
        vd  = round((c / hist[-1]["cota"] - 1) * 100, 6) if hist and hist[-1]["cota"] else 0.0
        hist.append({
            "dt": dt, "cota": round(c, 8),
            "cotas_qt": qt, "patrimonio": round(qt * c, 2),
            "rent_acum": ra, "var_diaria": vd,
        })

    if not hist: continue

    dt_fim     = hist[-1]["dt"]
    cota_fim   = hist[-1]["cota"]
    rent_final = round((cota_fim / cota_ini - 1) * 100, 6) if cota_ini else 0.0
    patrim_ini = hist[0]["patrimonio"]
    patrim_fim = hist[-1]["patrimonio"]
    ganho      = round(patrim_fim - patrim_ini, 2)

    fundos.append({
        "cnpj": fmt_cnpj(cnpj_raw), "cnpj_raw": cnpj_raw,
        "nome": nome, "nome_curto": nome,
        "color": CORES.get(cnpj_raw, "#aaa"),
        "cota_ini": cota_ini, "cota_fim": cota_fim,
        "rent": rent_final, "patrim_ini": patrim_ini, "patrim_fim": patrim_fim,
        "ganho": ganho, "dt_ini": hist[0]["dt"], "dt_fim": dt_fim,
        "n_dias": len(hist), "historico": hist,
    })

    print(f"  OK  {fmt_cnpj(cnpj_raw)}  {nome}")
    print(f"      Rent: {rent_final:+.4f}%  |  Patrim: R$ {patrim_ini:,.2f} -> R$ {patrim_fim:,.2f}  |  Resultado: R$ {ganho:+,.2f}\n")

if not fundos:
    print("ERRO: nenhum fundo processado.")
    sys.exit(1)

# Data comum = menor data final entre todos os fundos (para totais e carteira)
ultima_dt = min(f["dt_fim"] for f in fundos)
print(f"  Data limite comum: {ultima_dt}\n")

# Fundos individuais mantêm sua última data real (sem truncar)
# Para os totais, usamos o valor de cada fundo na ultima_dt

# ── TOTAIS (calculados na ultima_dt, data comum a todos) ──────────────────────
tot_ini = sum(f["patrim_ini"] for f in fundos)

def patrim_na_dt(f, dt):
    h = next((x for x in reversed(f["historico"]) if x["dt"] <= dt), None)
    return h["patrimonio"] if h else f["patrim_ini"]

tot_fim   = sum(patrim_na_dt(f, ultima_dt) for f in fundos)
tot_ganho = round(tot_fim - tot_ini, 2)
tot_rent  = round((tot_fim / tot_ini - 1) * 100, 6) if tot_ini else 0

print(f"  TOTAL  R$ {tot_ini:,.2f} -> R$ {tot_fim:,.2f}  |  {tot_rent:+.4f}%  |  R$ {tot_ganho:+,.2f}\n")

# ── CDI para comparação ───────────────────────────────────────────────────────
cdi_hist = [{"dt": "2025-12-31", "rent_acum": 0.0, "var_diaria": 0.0}]
for dt in datas_todas:
    if dt > ultima_dt: break
    cdi_hist.append({
        "dt": dt,
        "rent_acum":  round((cdi_idx[dt] - 1) * 100, 6),
        "var_diaria": round(taxa_diaria_cdi(dt) * 100, 6),
    })
cdi_rent = cdi_hist[-1]["rent_acum"] if cdi_hist else 0.0

# ── CARTEIRA CONSOLIDADA ──────────────────────────────────────────────────────
cart_hist = [{"dt": "2025-12-31", "patrimonio": round(tot_ini, 2), "rent_acum": 0.0, "var_diaria": 0.0}]
for dt in datas_todas:
    if dt > ultima_dt: break
    pat_tot = 0.0
    for f in fundos:
        h = next((x for x in f["historico"] if x["dt"] == dt), None)
        if h:
            pat_tot += h["patrimonio"]
        else:
            ant = [x for x in f["historico"] if x["dt"] <= dt]
            if ant: pat_tot += ant[-1]["patrimonio"]
    pat_tot = round(pat_tot, 2)
    ra = round((pat_tot / tot_ini - 1) * 100, 6) if tot_ini else 0.0
    vd = round((pat_tot / cart_hist[-1]["patrimonio"] - 1) * 100, 6) if cart_hist and cart_hist[-1]["patrimonio"] else 0.0
    cart_hist.append({"dt": dt, "patrimonio": pat_tot, "rent_acum": ra, "var_diaria": vd})

cart_rent = cart_hist[-1]["rent_acum"] if cart_hist else 0.0
print(f"  CARTEIRA  R$ {tot_ini:,.2f} -> R$ {tot_fim:,.2f}  |  Rent: {cart_rent:+.4f}%\n")

# ── GRUPO NEBLINA ─────────────────────────────────────────────────────────────
def get_fundo(cnpj_raw):
    return next((f for f in fundos if f["cnpj_raw"] == cnpj_raw), None)

def consolidar_grupo(nome, cor, cnpjs):
    dts = sorted(set(h["dt"] for c in cnpjs for f in [get_fundo(c)] if f for h in f["historico"] if h["dt"] <= ultima_dt))
    pat_ini_grupo = sum(get_fundo(c)["patrim_ini"] for c in cnpjs if get_fundo(c))
    hist_grupo = []
    for dt in dts:
        pat = 0.0
        for c in cnpjs:
            f = get_fundo(c)
            if not f: continue
            h = next((x for x in f["historico"] if x["dt"] == dt), None)
            if h: pat += h["patrimonio"]
        ra = round((pat / pat_ini_grupo - 1) * 100, 6) if pat_ini_grupo else 0.0
        vd = round((pat / hist_grupo[-1]["patrimonio"] - 1) * 100, 6) if hist_grupo and hist_grupo[-1]["patrimonio"] else 0.0
        hist_grupo.append({"dt": dt, "patrimonio": round(pat, 2), "rent_acum": ra, "var_diaria": vd})
    if not hist_grupo: return None
    pat_fim_grupo = hist_grupo[-1]["patrimonio"]
    return {
        "nome": nome, "nome_curto": nome, "cnpj": "Grupo virtual", "cnpj_raw": "",
        "color": cor, "virtual": True,
        "rent": hist_grupo[-1]["rent_acum"], "patrim_ini": pat_ini_grupo,
        "patrim_fim": pat_fim_grupo, "ganho": round(pat_fim_grupo - pat_ini_grupo, 2),
        "dt_ini": hist_grupo[0]["dt"], "dt_fim": hist_grupo[-1]["dt"],
        "n_dias": len(hist_grupo), "historico": hist_grupo,
    }

grupo_neblina = consolidar_grupo("Neblina (grupo)", GRUPO_NEBLINA_COR, GRUPO_NEBLINA_CNPJS)
grupos = [g for g in [grupo_neblina] if g]
if grupo_neblina:
    print(f"  Grupo Neblina:  R$ {grupo_neblina['patrim_ini']:,.2f} -> R$ {grupo_neblina['patrim_fim']:,.2f}  |  {grupo_neblina['rent']:+.4f}%\n")

# ──────────────────────────────────────────────────────────────────────────────
# GERA HTML
# ──────────────────────────────────────────────────────────────────────────────

dados_json  = json.dumps(fundos,    ensure_ascii=False)
grupos_json = json.dumps(grupos,    ensure_ascii=False)
cdi_json    = json.dumps(cdi_hist,  ensure_ascii=False)
cart_json   = json.dumps(cart_hist, ensure_ascii=False)
totais_json = json.dumps({
    "ini": tot_ini, "fim": tot_fim, "ganho": tot_ganho, "rent": tot_rent,
    "dt_ini": fundos[0]["dt_ini"], "dt_fim": ultima_dt,
    "cart_rent": cart_rent,
    "cdi_rent": cdi_rent,
    "cart_color": "#C084FC",
    "cdi_color": "#7F77DD",
    "lagunna_color": CORES["18189040000199"],
    "lagunna_cnpj": "18189040000199",
    "grupo_neblina_color": GRUPO_NEBLINA_COR,
}, ensure_ascii=False)

BRT = timezone(timedelta(hours=-3))
gerado_em = datetime.now(BRT).strftime("%d/%m/%Y %H:%M")


HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard CVM 2026 — II</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'IBM Plex Sans',sans-serif;background:#090d18;color:#dde2f0;min-height:100vh;font-size:14px}
header{background:#0c1020;border-bottom:1px solid #1a2035;padding:16px 28px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}
.logo{font-family:'IBM Plex Mono',monospace;font-size:12px;font-weight:700;letter-spacing:.1em;color:#1D9E75;text-transform:uppercase}
.sub{font-size:10px;color:#8892a8;margin-top:3px;font-family:'IBM Plex Mono',monospace}
.gerado{font-size:10px;color:#8892a8;font-family:'IBM Plex Mono',monospace;text-align:right;line-height:1.7}
main{padding:22px 28px;max-width:1300px;margin:0 auto}
.slbl{font-family:'IBM Plex Mono',monospace;font-size:10px;font-weight:700;color:#8892a8;text-transform:uppercase;letter-spacing:.12em;margin-bottom:12px;padding-bottom:7px;border-bottom:1px solid #1a2035;margin-top:24px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:8px}
.card{background:#0f1525;border:1px solid #1a2035;border-radius:8px;padding:16px 18px}
.card .lbl{font-size:10px;color:#8892a8;text-transform:uppercase;letter-spacing:.08em;font-family:'IBM Plex Mono',monospace;margin-bottom:6px}
.card .val{font-size:18px;font-weight:600;font-family:'IBM Plex Mono',monospace}
.card .sub{font-size:10px;color:#8892a8;margin-top:4px;font-family:'IBM Plex Mono',monospace}
.pos{color:#1D9E75} .neg{color:#D85A30}
.tab-row{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}
.tab{font-size:11px;padding:6px 14px;border-radius:6px;border:1px solid #1a2035;background:transparent;color:#8892a8;cursor:pointer;font-family:'IBM Plex Mono',monospace;transition:all .15s}
.tab.active{background:#1a2840;color:#378ADD;border-color:#378ADD}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:12px}
.legend-item{display:flex;align-items:center;gap:6px;font-size:11px;color:#888;font-family:'IBM Plex Mono',monospace}
.legend-sq{width:10px;height:10px;border-radius:2px;flex-shrink:0}
.cbox{background:#0f1525;border:1px solid #1a2035;border-radius:8px;padding:18px 20px;margin-bottom:8px}
.fgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;margin-bottom:8px}
.fc{background:#0f1525;border:1px solid #1a2035;border-radius:8px;padding:16px;cursor:pointer;transition:border-color .15s}
.fc:hover,.fc.active{border-color:#378ADD;background:#0d1828}
.fc-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}
.fc-nome{font-size:11px;font-weight:600;max-width:175px;line-height:1.5}
.fc-cnpj{font-size:9px;color:#8892a8;margin-top:2px;font-family:'IBM Plex Mono',monospace}
.badge{border-radius:4px;padding:4px 10px;font-size:12px;font-weight:700;font-family:'IBM Plex Mono',monospace;white-space:nowrap}
.fc-row{display:flex;justify-content:space-between;margin-top:5px;font-size:10px}
.fc-lbl{color:#8892a8} .fc-val{font-family:'IBM Plex Mono',monospace}
.dbox{background:#0f1525;border:1px solid #378ADD;border-radius:8px;padding:20px 24px;margin-bottom:8px;display:none}
.dbox.show{display:block}
.dh{display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-bottom:16px;align-items:flex-start}
.dt{font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:700;color:#1D9E75;text-transform:uppercase;letter-spacing:.1em}
.ds{font-size:10px;color:#8892a8;margin-top:3px;font-family:'IBM Plex Mono',monospace}
.mgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-top:16px}
.mbox{background:#090d18;border-radius:6px;padding:10px 12px}
.mlbl{font-size:9px;color:#8892a8;text-transform:uppercase;letter-spacing:.08em;font-family:'IBM Plex Mono',monospace}
.mval{font-size:11px;margin-top:4px;font-family:'IBM Plex Mono',monospace}
.pie-wrap{display:grid;grid-template-columns:220px 1fr;gap:20px;align-items:center}
.pie-info{display:flex;flex-direction:column;gap:10px}
.pie-row{display:flex;align-items:center;gap:10px;font-size:12px}
@media(max-width:600px){main{padding:14px}header{padding:12px 14px}.pie-wrap{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <div>
    <div class="logo">&#128202; Dashboard CVM &middot; Rentabilidade 2026 &middot; II</div>
    <div class="sub" id="headerSub"></div>
  </div>
  <div class="gerado">&#128197; CVM: """ + ultima_cvm_fmt + """<br>Gerado em """ + gerado_em + """</div>
</header>
<main>
  <div class="slbl">Resumo da carteira</div>
  <div class="cards" id="summaryCards"></div>

  <div class="slbl">Evolucao 2026</div>
  <div class="cbox">
    <div class="tab-row">
      <button class="tab active" onclick="setTab('acum')">Rent. acumulada %</button>
      <button class="tab"        onclick="setTab('patrim')">Patrimonio R$</button>
      <button class="tab"        onclick="setTab('diario')">Variacao diaria %</button>
    </div>
    <div class="legend" id="legend"></div>
    <div style="position:relative;width:100%;height:300px">
      <canvas id="mainChart"></canvas>
    </div>
  </div>

  <div class="slbl">Fundos individuais &mdash; clique para detalhar</div>
  <div class="fgrid" id="fundosGrid"></div>

  <div class="dbox" id="detailBox">
    <div class="dh">
      <div><div class="dt" id="detTitle"></div><div class="ds" id="detSub"></div></div>
      <div class="tab-row" style="margin-bottom:0">
        <button class="tab active" onclick="setDTab('cota')">Cota</button>
        <button class="tab"        onclick="setDTab('rent')">Rent. acum %</button>
        <button class="tab"        onclick="setDTab('patrim')">Patrimonio R$</button>
        <button class="tab"        onclick="setDTab('diario')">Var. diaria %</button>
      </div>
    </div>
    <div style="position:relative;width:100%;height:240px">
      <canvas id="detChart"></canvas>
    </div>
    <div class="mgrid" id="detMeta"></div>
  </div>

  <div class="slbl">Composicao da carteira &mdash; <span id="lblDataComp" style="color:#dde2f0;font-weight:400"></span></div>
  <div class="cbox">
    <div class="pie-wrap">
      <div style="position:relative;height:220px">
        <canvas id="pieChart"></canvas>
      </div>
      <div class="pie-info" id="pieInfo"></div>
    </div>
  </div>
</main>

<script>
const DADOS  = """ + dados_json  + """;
const GRUPOS = """ + grupos_json + """;
const CDI    = """ + cdi_json    + """;
const CART   = """ + cart_json   + """;
const TOTAIS = """ + totais_json + """;

const fmtBRL  = v => 'R$\u00a0' + Number(v).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});
const fmtPct  = v => (v>=0?'+':'')+Number(v).toFixed(4)+'%';
const fmtCota = v => Number(v).toFixed(8);
const fmtQtd  = v => Number(v).toLocaleString('pt-BR',{minimumFractionDigits:3,maximumFractionDigits:3});

document.getElementById('headerSub').textContent =
  'Informe Diario \u00b7 ' + TOTAIS.dt_ini + ' \u2192 ' + TOTAIS.dt_fim + ' \u00b7 4 fundos';

(function(){
  const T = TOTAIS;
  [
    {lbl:'Patrimonio inicial', val:fmtBRL(T.ini),      sub:'em '+T.dt_ini, cls:''},
    {lbl:'Patrimonio atual',   val:fmtBRL(T.fim),      sub:'em '+T.dt_fim, cls:''},
    {lbl:'Resultado R$', val:(T.ganho>=0?'+':'')+fmtBRL(T.ganho), sub:fmtPct(T.rent)+' no periodo', cls:T.ganho>=0?'pos':'neg'},
    {lbl:'Rent. carteira', val:fmtPct(T.cart_rent),   sub:'consolidado no periodo', cls:T.cart_rent>=0?'pos':'neg'},
    {lbl:'CDI acumulado',  val:fmtPct(T.cdi_rent),    sub:T.dt_fim, cls:'pos'},
  ].forEach(c=>{
    document.getElementById('summaryCards').innerHTML +=
      `<div class="card"><div class="lbl">${c.lbl}</div><div class="val ${c.cls}">${c.val}</div><div class="sub">${c.sub}</div></div>`;
  });
})();

const lagunna = DADOS.find(f => f.cnpj_raw === TOTAIS.lagunna_cnpj);
const legendItems = [
  {nome_curto: 'CDI',           color: TOTAIS.cdi_color,  virtual: false},
  {nome_curto: 'Carteira Total',color: TOTAIS.cart_color, virtual: false},
  ...(lagunna ? [{nome_curto: lagunna.nome_curto, color: lagunna.color, virtual: false}] : []),
  ...GRUPOS,
];
legendItems.forEach(f=>{
  document.getElementById('legend').innerHTML +=
    `<span class="legend-item"><span class="legend-sq" style="background:${f.color}${f.virtual?';opacity:0.7':''}"></span>${f.nome_curto}${f.virtual?' <span style="font-size:9px;color:#8892a8">(grupo)</span>':''}</span>`;
});

let mainChart;

function getDS(tab){
  const key = tab==='acum'?'rent_acum':tab==='patrim'?'patrimonio':'var_diaria';
  const dsCart = [{label:'Carteira Total',data:CART.map(h=>h[key]),borderColor:TOTAIS.cart_color,backgroundColor:tab==='patrim'?TOTAIS.cart_color+'18':'transparent',fill:tab==='patrim',borderWidth:3,pointRadius:0,tension:0.1}];
  if(tab==='patrim') return dsCart;
  const dsLagunna = lagunna ? [{label:lagunna.nome_curto,data:lagunna.historico.map(h=>h[key]),borderColor:lagunna.color,backgroundColor:'transparent',fill:false,borderWidth:2.5,pointRadius:0,tension:0.1}] : [];
  const dsGrupos = GRUPOS.map(g=>({label:g.nome_curto,data:g.historico.map(h=>h[key]),borderColor:g.color,backgroundColor:'transparent',fill:false,borderWidth:2.5,pointRadius:0,borderDash:[3,3],tension:0.1}));
  const dsCDI = [{label:'CDI',data:CDI.map(h=>h[key]),borderColor:TOTAIS.cdi_color,backgroundColor:'transparent',fill:false,borderWidth:2,pointRadius:0,borderDash:[6,3],tension:0.1}];
  return [...dsCDI,...dsCart,...dsLagunna,...dsGrupos];
}

function fmtY(tab,v){
  if(tab==='patrim'){
    if(Math.abs(v)>=1000000) return 'R$'+Number(v/1000000).toFixed(2)+'M';
    if(Math.abs(v)>=1000)    return 'R$'+Number(v/1000).toFixed(1)+'k';
    return 'R$'+Number(v).toFixed(0);
  }
  return Number(v).toFixed(tab==='diario'?4:2)+'%';
}

function renderMain(tab){
  const labels = CART.map(h=>h.dt.slice(5));
  if(mainChart) mainChart.destroy();
  mainChart = new Chart(document.getElementById('mainChart'),{
    type:'line', data:{labels,datasets:getDS(tab)},
    options:{responsive:true,maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>`  ${ctx.dataset.label}: ${fmtY(tab,ctx.parsed.y)}`}}},
      scales:{x:{ticks:{autoSkip:true,maxTicksLimit:10,color:'#8892a8',font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}},y:{ticks:{color:'#8892a8',font:{size:10},callback:v=>fmtY(tab,v)},grid:{color:'rgba(255,255,255,0.04)'}}},
    },
  });
}

function setTab(tab){
  document.querySelectorAll('.cbox .tab-row .tab').forEach((b,i)=>{b.classList.toggle('active',['acum','patrim','diario'][i]===tab);});
  renderMain(tab);
}
renderMain('acum');

let activeIdx=null, detChart=null;

DADOS.forEach((f,i)=>{
  const pc=f.rent>=0?'pos':'neg';
  const card=document.createElement('div');
  card.className='fc';
  card.innerHTML=`
    <div class="fc-top">
      <div><div class="fc-nome">${f.nome}</div><div class="fc-cnpj">${f.cnpj}</div></div>
      <div class="badge ${pc}" style="background:${f.color}22;color:${f.color}">${fmtPct(f.rent)}</div>
    </div>
    <div class="fc-row"><span class="fc-lbl">Cotas</span><span class="fc-val">${fmtQtd(f.historico[f.historico.length-1].cotas_qt)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Cota inicial</span><span class="fc-val">${fmtCota(f.cota_ini)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Cota atual</span><span class="fc-val">${fmtCota(f.cota_fim)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Patrimonio inicial</span><span class="fc-val">${fmtBRL(f.patrim_ini)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Patrimonio atual</span><span class="fc-val" style="color:${f.color}">${fmtBRL(f.patrim_fim)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Resultado</span><span class="fc-val ${pc}">${f.ganho>=0?'+':''}${fmtBRL(f.ganho)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Periodo</span><span class="fc-val">${f.dt_ini} \u2192 ${f.dt_fim}</span></div>`;
  card.onclick=()=>toggleDet(i,card);
  document.getElementById('fundosGrid').appendChild(card);
});

GRUPOS.forEach((g,gi)=>{
  const pc=g.rent>=0?'pos':'neg';
  const card=document.createElement('div');
  card.className='fc';
  card.style.borderColor=g.color+'88';
  card.style.borderStyle='dashed';
  card.innerHTML=`
    <div class="fc-top">
      <div>
        <div class="fc-nome">${g.nome} <span style="font-size:9px;background:${g.color}22;color:${g.color};border-radius:3px;padding:2px 6px">GRUPO</span></div>
        <div class="fc-cnpj">Consolidado · apenas visualizacao</div>
      </div>
      <div class="badge ${pc}" style="background:${g.color}22;color:${g.color}">${fmtPct(g.rent)}</div>
    </div>
    <div class="fc-row"><span class="fc-lbl">Patrimonio inicial</span><span class="fc-val">${fmtBRL(g.patrim_ini)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Patrimonio atual</span><span class="fc-val" style="color:${g.color}">${fmtBRL(g.patrim_fim)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Resultado</span><span class="fc-val ${pc}">${g.ganho>=0?'+':''}${fmtBRL(g.ganho)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Rentabilidade</span><span class="fc-val ${pc}">${fmtPct(g.rent)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Periodo</span><span class="fc-val">${g.dt_ini} \u2192 ${g.dt_fim}</span></div>`;
  card.onclick=()=>{
    document.querySelectorAll('.fc').forEach(c=>c.classList.remove('active'));
    const box=document.getElementById('detailBox');
    if(activeIdx==='g'+gi){activeIdx=null;box.classList.remove('show');return;}
    activeIdx='g'+gi; card.classList.add('active');
    renderGrupoDet(g); box.classList.add('show');
    box.scrollIntoView({behavior:'smooth',block:'nearest'});
  };
  document.getElementById('fundosGrid').appendChild(card);
});

(function(){
  const T=TOTAIS, pc=T.cart_rent>=0?'pos':'neg';
  const card=document.createElement('div');
  card.className='fc';
  card.style.borderColor=T.cart_color;
  card.innerHTML=`
    <div class="fc-top">
      <div><div class="fc-nome">Carteira Total</div><div class="fc-cnpj">Consolidado · todos os fundos</div></div>
      <div class="badge ${pc}" style="background:${T.cart_color}22;color:${T.cart_color}">${fmtPct(T.cart_rent)}</div>
    </div>
    <div class="fc-row"><span class="fc-lbl">Patrimonio inicial</span><span class="fc-val">${fmtBRL(T.ini)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Patrimonio atual</span><span class="fc-val" style="color:${T.cart_color}">${fmtBRL(T.fim)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Resultado</span><span class="fc-val ${pc}">${T.ganho>=0?'+':''}${fmtBRL(T.ganho)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Rentabilidade</span><span class="fc-val ${pc}">${fmtPct(T.cart_rent)}</span></div>
    <div class="fc-row"><span class="fc-lbl">CDI no periodo</span><span class="fc-val pos">${fmtPct(T.cdi_rent)}</span></div>
    <div class="fc-row"><span class="fc-lbl">Periodo</span><span class="fc-val">${T.dt_ini} \u2192 ${T.dt_fim}</span></div>`;
  card.onclick=()=>{
    document.querySelectorAll('.fc').forEach(c=>c.classList.remove('active'));
    const box=document.getElementById('detailBox');
    if(activeIdx==='cart'){activeIdx=null;box.classList.remove('show');return;}
    activeIdx='cart'; card.classList.add('active');
    renderCartDet(); box.classList.add('show');
    box.scrollIntoView({behavior:'smooth',block:'nearest'});
  };
  document.getElementById('fundosGrid').appendChild(card);
})();

function renderGrupoDet(g){
  document.getElementById('detTitle').innerHTML=g.nome+' <span style="font-size:9px;background:'+g.color+'22;color:'+g.color+';border-radius:3px;padding:2px 6px">GRUPO</span>';
  document.getElementById('detSub').textContent='Consolidado · '+g.dt_ini+' \u2192 '+g.dt_fim;
  if(detChart) detChart.destroy();
  detChart=new Chart(document.getElementById('detChart'),{type:'line',data:{labels:g.historico.map(h=>h.dt.slice(5)),datasets:[{label:g.nome,data:g.historico.map(h=>h.rent_acum),borderColor:g.color,backgroundColor:g.color+'18',fill:true,borderWidth:2,pointRadius:0,tension:0.1}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{autoSkip:true,maxTicksLimit:10,color:'#8892a8',font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}},y:{ticks:{color:'#8892a8',font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}}}}});
  const pc=g.rent>=0?'pos':'neg';
  document.getElementById('detMeta').innerHTML=[
    {lbl:'Composicao',val:'Neblina_Equity + Neblina + Neblina_II'},
    {lbl:'Patrimonio inicial',val:fmtBRL(g.patrim_ini)},
    {lbl:'Patrimonio atual',val:fmtBRL(g.patrim_fim)},
    {lbl:'Resultado R$',val:(g.ganho>=0?'+':'')+fmtBRL(g.ganho),cls:pc},
    {lbl:'Rentabilidade',val:fmtPct(g.rent),cls:pc},
    {lbl:'Periodo',val:g.dt_ini+' \u2192 '+g.dt_fim},
  ].map(m=>`<div class="mbox"><div class="mlbl">${m.lbl}</div><div class="mval ${m.cls||''}">${m.val}</div></div>`).join('');
}

function renderCartDet(){
  document.getElementById('detTitle').textContent='Carteira Total \u2014 Consolidado';
  document.getElementById('detSub').textContent='Todos os fundos \u00b7 '+TOTAIS.dt_ini+' \u2192 '+TOTAIS.dt_fim;
  if(detChart) detChart.destroy();
  detChart=new Chart(document.getElementById('detChart'),{type:'line',data:{labels:CART.map(h=>h.dt.slice(5)),datasets:[{label:'Carteira',data:CART.map(h=>h.rent_acum),borderColor:TOTAIS.cart_color,backgroundColor:TOTAIS.cart_color+'18',fill:true,borderWidth:2.5,pointRadius:0,tension:0.1}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{autoSkip:true,maxTicksLimit:10,color:'#8892a8',font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}},y:{ticks:{color:'#8892a8',font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}}}}});
  const T=TOTAIS,pc=T.cart_rent>=0?'pos':'neg';
  document.getElementById('detMeta').innerHTML=[
    {lbl:'Composicao',val:'4 fundos'},
    {lbl:'Patrimonio inicial',val:fmtBRL(T.ini)},
    {lbl:'Patrimonio atual',val:fmtBRL(T.fim)},
    {lbl:'Resultado R$',val:(T.ganho>=0?'+':'')+fmtBRL(T.ganho),cls:pc},
    {lbl:'Rentabilidade',val:fmtPct(T.cart_rent),cls:pc},
    {lbl:'CDI no periodo',val:fmtPct(T.cdi_rent),cls:'pos'},
    {lbl:'Periodo',val:T.dt_ini+' \u2192 '+T.dt_fim},
  ].map(m=>`<div class="mbox"><div class="mlbl">${m.lbl}</div><div class="mval ${m.cls||''}">${m.val}</div></div>`).join('');
}

function toggleDet(i,card){
  document.querySelectorAll('.fc').forEach(c=>c.classList.remove('active'));
  const box=document.getElementById('detailBox');
  if(activeIdx===i){activeIdx=null;box.classList.remove('show');return;}
  activeIdx=i; card.classList.add('active');
  renderDet(DADOS[i],'cota');
  box.classList.add('show');
  box.scrollIntoView({behavior:'smooth',block:'nearest'});
}

function renderDet(f,tab){
  document.getElementById('detTitle').textContent=f.nome;
  document.getElementById('detSub').textContent=f.cnpj+' \u00b7 '+f.n_dias+' dias uteis \u00b7 '+f.dt_ini+' \u2192 '+f.dt_fim;
  const km={cota:'cota',rent:'rent_acum',patrim:'patrimonio',diario:'var_diaria'};
  const key=km[tab];
  if(detChart) detChart.destroy();
  detChart=new Chart(document.getElementById('detChart'),{type:'line',data:{labels:f.historico.map(h=>h.dt.slice(5)),datasets:[{label:tab,data:f.historico.map(h=>h[key]),borderColor:f.color,backgroundColor:f.color+'18',fill:true,borderWidth:2,pointRadius:0,tension:0.1}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{autoSkip:true,maxTicksLimit:10,color:'#8892a8',font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}},y:{ticks:{color:'#8892a8',font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}}}}});
  const pc=f.rent>=0?'pos':'neg';
  document.getElementById('detMeta').innerHTML=[
    {lbl:'CNPJ',val:f.cnpj},
    {lbl:'Cotas',val:fmtQtd(f.historico[f.historico.length-1].cotas_qt)},
    {lbl:'Cota em '+f.dt_ini,val:fmtCota(f.cota_ini)},
    {lbl:'Cota em '+f.dt_fim,val:fmtCota(f.cota_fim)},
    {lbl:'Patrimonio inicial',val:fmtBRL(f.patrim_ini)},
    {lbl:'Patrimonio atual',val:fmtBRL(f.patrim_fim)},
    {lbl:'Resultado R$',val:(f.ganho>=0?'+':'')+fmtBRL(f.ganho),cls:pc},
    {lbl:'Rentabilidade',val:fmtPct(f.rent),cls:pc},
    {lbl:'Periodo',val:f.dt_ini+' \u2192 '+f.dt_fim},
  ].map(m=>`<div class="mbox"><div class="mlbl">${m.lbl}</div><div class="mval ${m.cls||''}">${m.val}</div></div>`).join('');
}

function setDTab(tab){
  document.querySelectorAll('#detailBox .tab-row .tab').forEach((b,i)=>{b.classList.toggle('active',['cota','rent','patrim','diario'][i]===tab);});
  if(activeIdx==='cart') renderCartDet();
  else if(typeof activeIdx==='number') renderDet(DADOS[activeIdx],tab);
}

(function(){
  const ultimaDt=TOTAIS.dt_fim;
  function patrimNaData(f,dt){const h=f.historico.slice().reverse().find(x=>x.dt<=dt);return h?h.patrimonio:0;}
  const labels=DADOS.map(f=>f.nome_curto);
  const vals=DADOS.map(f=>patrimNaData(f,ultimaDt));
  const cores=DADOS.map(f=>f.color);
  const total=vals.reduce((s,v)=>s+v,0);
  const rents=DADOS.map(f=>f.rent);
  document.getElementById('lblDataComp').textContent=ultimaDt;
  new Chart(document.getElementById('pieChart'),{type:'doughnut',data:{labels,datasets:[{data:vals.map(v=>+v.toFixed(2)),backgroundColor:cores,borderWidth:1,borderColor:'rgba(255,255,255,0.08)'}]},options:{responsive:true,maintainAspectRatio:false,cutout:'62%',plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>`  ${ctx.label}: ${fmtBRL(ctx.parsed)}`}}}}});
  document.getElementById('pieInfo').innerHTML=vals.map((v,i)=>{
    const pct=(v/total*100).toFixed(1);
    const cls=rents[i]>=0?'pos':'neg';
    return `<div class="pie-row"><span style="width:10px;height:10px;border-radius:2px;background:${cores[i]};flex-shrink:0"></span><div><div style="font-size:11px;color:#8892a8">${labels[i]}</div><div style="font-size:13px;font-weight:600">${fmtBRL(v)} <span style="font-size:10px;color:#8892a8">(${pct}%)</span></div><div class="${cls}" style="font-size:11px;font-family:'IBM Plex Mono',monospace">${fmtPct(rents[i])}</div></div></div>`;
  }).join('')+`
    <div style="border-top:1px solid #1a2035;margin-top:8px;padding-top:10px;display:flex;align-items:center;gap:10px">
      <span style="width:10px;height:10px;border-radius:50%;background:#dde2f0;flex-shrink:0"></span>
      <div><div style="font-size:11px;color:#8892a8">Total da Carteira</div><div style="font-size:15px;font-weight:700;color:#dde2f0">${fmtBRL(total)}</div><div style="font-size:10px;color:#8892a8;font-family:'IBM Plex Mono',monospace">em ${ultimaDt}</div></div>
    </div>
    <div style="border-top:1px solid #1a2035;margin-top:8px;padding-top:8px">
      <div style="font-size:10px;color:#8892a8;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;font-family:'IBM Plex Mono',monospace">Grupos · apenas visualizacao</div>
      ${GRUPOS.map(g=>{const pc=g.rent>=0?'pos':'neg';return`<div class="pie-row" style="margin-bottom:6px"><span style="width:10px;height:10px;border-radius:2px;background:${g.color};opacity:0.7;flex-shrink:0"></span><div><div style="font-size:11px;color:#8892a8">${g.nome}</div><div style="font-size:13px;font-weight:600">${fmtBRL(g.patrim_fim)}</div><div class="${pc}" style="font-size:11px;font-family:'IBM Plex Mono',monospace">${fmtPct(g.rent)}</div></div></div>`;}).join('')}
    </div>`;
})();
</script>
</body>
</html>"""

saida = os.path.join(os.getcwd(), "output", "index2.html")
with open(saida, "w", encoding="utf-8") as out:
    out.write(HTML)

print(f"\nDashboard gerado: {saida}")
print("HTML gerado com sucesso")
print("Concluido")
