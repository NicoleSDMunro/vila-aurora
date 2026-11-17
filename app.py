"""
Vila Aurora - 3VA G02 - Bloco 4 (Q13-Q15) - Torre de Controle S&OE em Streamlit

Como rodar:
    pip install streamlit plotly pandas numpy openpyxl
    streamlit run app_vila_aurora.py

Coloque o .xlsx do Bloco 4 na mesma pasta (ou envie pela barra lateral).
"""
# ======================================================================
# MOTOR ANALITICO - Vila Aurora (3VA G02 - Bloco 4)
# Previsao por familia -> politica de estoque -> simulacao -> KPIs/semaforos
# ======================================================================
import math
import numpy as np
import pandas as pd

# ---------------------------- PREMISSAS -------------------------------
# Premissas operacionais nao fornecidas na base (ajustaveis no dashboard).
PREMISSAS = {
    #                LT(sem) validade(sem) cap. viagem(un)  rota
    "F1 - Pereciveis": dict(lt=1, validade=2,  cap=1000, rota="Refrigerado"),
    "F2 - Premium":    dict(lt=2, validade=26, cap=2000, rota="Seco"),
    "F3 - Mercearia":  dict(lt=2, validade=52, cap=2000, rota="Seco"),
    "F4 - Congelados": dict(lt=1, validade=12, cap=600,  rota="Congelado"),
    "F5 - Bebidas":    dict(lt=1, validade=26, cap=2000, rota="Seco"),
}
SEMANA_PROMO_F1 = 20          # promocao F1 (+40%)
UPLIFT_PROMO_F1 = 0.40
SEMANAS_ATRASO_F2 = (30, 31)  # pedidos de F2 colocados nessas semanas tem LT dobrado
LT_ALT_F2 = 1                 # fornecedor alternativo F2 (LT 1 semana)
INICIO_SIM = 9                # 8 semanas de aquecimento
# Nivel de servico de ciclo diferenciado por perfil ABC/XYZ (politica S&OE)
NIVEL_SERVICO = {"F1 - Pereciveis": 0.98,   # BX: alto giro, mas validade curta limita estoque
                 "F2 - Premium":    0.98,   # CY: margem alta + risco de fornecedor
                 "F3 - Mercearia":  0.99,   # AX: 50% do volume, demanda estavel -> ES barato
                 "F4 - Congelados": 0.97,   # BY
                 "F5 - Bebidas":    0.95}   # CZ: erratica, ES caro; meta de fill 88%

FAMILIAS = list(PREMISSAS)
CURTO = {f: f.split(" - ")[0] for f in FAMILIAS}


def carregar(path):
    d = pd.read_excel(path, sheet_name="M_Dashboard_Input")
    roi = pd.read_excel(path, sheet_name="N_ROI_Roadmap")
    metas = d.groupby("familia")[["meta_fill_rate_pct", "meta_WAPE_pct", "meta_descarte_pct",
                                  "limite_ESG", "custo_viagem_R$", "CO2_viagem_kgCO2e"]].first()
    dem = d.pivot(index="semana", columns="familia", values="demanda_total")[FAMILIAS].astype(float)
    return d, dem, metas, roi


# ----------------------- LIMPEZA (demanda censurada) ------------------
def limpar_demanda(dem):
    """Semanas 30-31 de F2 registram VENDA reprimida pela ruptura do fornecedor
    (44 e 234 un. vs ~360 de mediana). Para treinar previsao, substitui pela
    mediana movel de 8 semanas. A simulacao usa a demanda original."""
    limpa = dem.astype(float).copy()
    med = dem["F2 - Premium"].rolling(8, min_periods=4).median().shift(1)
    for s in SEMANAS_ATRASO_F2:
        limpa.loc[s, "F2 - Premium"] = med.loc[s]
    return limpa


# ----------------------------- MODELOS --------------------------------
def prever_1passo(hist, modelo):
    """Previsao para a proxima semana dado um vetor historico (np.array)."""
    n = len(hist)
    if modelo == "Naive":
        return hist[-1]
    if modelo == "MM4":
        return hist[-4:].mean()
    if modelo == "MM8":
        return hist[-8:].mean()
    if modelo.startswith("SES_"):
        a = float(modelo.split("_")[1])
        lvl = hist[:4].mean()
        for x in hist:
            lvl = a * x + (1 - a) * lvl
        return lvl
    if modelo == "Sazonal52":
        return hist[-52] if n >= 52 else hist[-4:].mean()
    if modelo == "SES+Sazonal":
        # nivel SES(0.2) x indice sazonal do ano anterior (suavizado em 3 semanas)
        base = prever_1passo(hist, "SES_0.2")
        if n < 56:
            return base
        ano_ant = hist[-53:-50].mean()           # vizinhanca da mesma semana no ano anterior
        nivel_ant = hist[-60:-46].mean()
        idx = np.clip(ano_ant / nivel_ant, 0.6, 1.8) if nivel_ant > 0 else 1.0
        return base * (0.5 + 0.5 * idx)
    if modelo == "Mediana8":
        return np.median(hist[-8:])
    raise ValueError(modelo)


MODELOS = ["Naive", "MM4", "MM8", "Mediana8", "SES_0.1", "SES_0.2", "SES_0.3", "SES_0.5",
           "Sazonal52", "SES+Sazonal"]


def wape(real, prev):
    real, prev = np.asarray(real, float), np.asarray(prev, float)
    return np.abs(real - prev).sum() / real.sum() * 100


def backtest(dem_limpa, inicio=53, fim=104):
    """WAPE 1-passo a frente nas semanas inicio..fim (ano 2 = holdout)."""
    linhas = []
    for f in FAMILIAS:
        s = dem_limpa[f].values
        for m in MODELOS:
            prev = [prever_1passo(s[: t - 1], m) for t in range(inicio, fim + 1)]
            real = s[inicio - 1: fim]
            vies = (np.sum(prev) - np.sum(real)) / np.sum(real) * 100
            linhas.append(dict(familia=f, modelo=m, WAPE=wape(real, prev), vies_pct=vies))
    return pd.DataFrame(linhas)


def perfil_familias(dem, metas):
    cv = dem.std() / dem.mean()
    vol = dem.sum()
    share = vol / vol.sum()
    abc = share.sort_values(ascending=False).cumsum().apply(lambda x: "A" if x <= 0.80 else ("B" if x <= 0.95 else "C"))
    # o primeiro item sempre A
    abc.iloc[0] = "A"
    xyz = cv.apply(lambda c: "X" if c < 0.2 else ("Y" if c < 0.5 else "Z"))
    p = pd.DataFrame({"media_sem": dem.mean().round(0), "desvio": dem.std().round(0),
                      "CV": cv.round(2), "share_vol_pct": (share * 100).round(1),
                      "ABC": abc.reindex(dem.columns), "XYZ": xyz})
    p["perfil"] = p["ABC"] + p["XYZ"]
    p["meta_fill_rate_pct"] = metas["meta_fill_rate_pct"]
    p["meta_WAPE_pct"] = metas["meta_WAPE_pct"]
    p["meta_descarte_pct"] = metas["meta_descarte_pct"]
    for f in FAMILIAS:
        p.loc[f, "lead_time_sem"] = PREMISSAS[f]["lt"]
        p.loc[f, "validade_sem"] = PREMISSAS[f]["validade"]
    return p


# --------------------------- POLITICA ---------------------------------
def z_de(nivel):
    from statistics import NormalDist
    return NormalDist().inv_cdf(min(max(nivel, 0.5), 0.999))


def sigma_erro(dem_limpa, f, modelo, inicio=53, fim=104):
    s = dem_limpa[f].values
    prev = np.array([prever_1passo(s[: t - 1], modelo) for t in range(inicio, fim + 1)])
    return float(np.std(s[inicio - 1: fim] - prev, ddof=1))


# --------------------------- SIMULACAO --------------------------------
def simular(dem, dem_limpa, metas, politica, modelos_escolhidos=None, nivel_servico=None,
            inicio=INICIO_SIM, fim=104, uplift=UPLIFT_PROMO_F1, cap_esg=None):
    """Simulacao semanal (revisao periodica R=1, order-up-to).

    politica = 'Atual'  : MM4 p/ todas, estoque de seguranca = 1 semana de demanda media,
                          sem tratamento de promocao nem do atraso F2 (reativo).
    politica = 'S&OE'   : modelo vencedor por familia, ES = z*sigma_erro*sqrt(LT+R) com
                          nivel de servico = meta da familia, uplift de promocao planejado,
                          gatilho de atraso F2 -> fornecedor alternativo (LT 1) e consolidacao
                          de cargas secas quando viagens projetadas >= 80% do limite ESG.
    Retorna DataFrame semanal por familia.
    """
    registros = []
    estado = {}
    for f in FAMILIAS:
        estado[f] = dict(lotes=[], pipeline={}, )   # lotes: [qtd, semana_chegada]
    # sigma do erro para politica S&OE
    sig = {}
    if politica == "S&OE":
        for f in FAMILIAS:
            sig[f] = sigma_erro(dem_limpa, f, modelos_escolhidos[f])

    # estoque inicial = 2 semanas de demanda media inicial
    for f in FAMILIAS:
        ini = dem[f].iloc[: inicio - 1].mean() * PREMISSAS[f]["lt"]
        estado[f]["lotes"] = [[ini, inicio - 1]]

    for t in range(inicio, fim + 1):
        chegadas_sem = {}
        for f in FAMILIAS:
            p = PREMISSAS[f]
            st = estado[f]
            # 1) recebimentos
            receb = st["pipeline"].pop(t, 0.0)
            receb_emerg = st["pipeline"].pop(("E", t), 0.0)
            if receb + receb_emerg > 0:
                st["lotes"].append([receb + receb_emerg, t])
            chegadas_sem[f] = (receb, receb_emerg)
            # 2) atende demanda FIFO
            d = float(dem.loc[t, f])
            restante = d
            for lote in st["lotes"]:
                usa = min(lote[0], restante)
                lote[0] -= usa
                restante -= usa
                if restante <= 0:
                    break
            atendido = d - restante
            # 3) descarte por validade
            descarte = sum(l[0] for l in st["lotes"] if t - l[1] + 1 >= p["validade"])
            st["lotes"] = [l for l in st["lotes"] if l[0] > 1e-9 and t - l[1] + 1 < p["validade"]]
            estoque = sum(l[0] for l in st["lotes"])
            # 4) previsao para proximas semanas
            hist = dem_limpa[f].values[: t]
            if politica == "Atual":
                fc = prever_1passo(hist, "MM4")
            else:
                fc = prever_1passo(hist, modelos_escolhidos[f])
            # lead time efetivo do pedido colocado agora
            lt = p["lt"]
            atraso = f == "F2 - Premium" and t in SEMANAS_ATRASO_F2
            lt_real = lt * 2 if atraso else lt
            # demanda de protecao (LT+R) e estoque de seguranca
            # pedido colocado no fim de t chega no inicio de t+LT -> exposicao = LT semanas
            cobertura = [fc] * lt
            if politica == "S&OE" and f == "F1 - Pereciveis":
                for k in range(1, lt + 1):
                    if t + k == SEMANA_PROMO_F1:
                        cobertura[k - 1] = fc * (1 + uplift)
            prot = sum(cobertura)
            if politica == "Atual":
                es = 0.5 * dem_limpa[f].values[max(0, t - 8): t].mean()  # regra de bolso: meia semana de demanda
                nivel = None
            else:
                nivel = (nivel_servico or NIVEL_SERVICO)[f]
                es = z_de(nivel) * sig[f] * math.sqrt(lt)
            S = prot + es
            pos = estoque + sum(v for k, v in st["pipeline"].items())
            pedido = max(0.0, S - pos)
            emerg = 0.0
            if atraso and politica == "S&OE":
                # gatilho: LT confirmado 2x -> fornecedor alternativo cobre o gap ate o pedido atrasado chegar
                emerg = fc * (lt_real - lt)
                emerg = max(0.0, min(emerg, pedido))
                pedido -= emerg
                st["pipeline"][("E", t + LT_ALT_F2)] = st["pipeline"].get(("E", t + LT_ALT_F2), 0) + emerg
            if pedido > 0:
                st["pipeline"][t + lt_real] = st["pipeline"].get(t + lt_real, 0) + pedido
            registros.append(dict(semana=t, familia=f, demanda=d, atendido=atendido,
                                  ruptura=restante, descarte=descarte, estoque_final=estoque,
                                  recebido=receb, recebido_emerg=receb_emerg, previsao=fc,
                                  pedido=pedido, pedido_emerg=emerg, lt_efetivo=lt_real,
                                  estoque_seg=es, nivel_alvo=S))
    sim = pd.DataFrame(registros)
    sim["cobertura_sem"] = sim["estoque_final"] / sim["previsao"].replace(0, np.nan)
    sim["viagens"] = 0.0
    # viagens por rota (consolidacao por temperatura)
    rota = sim["familia"].map(lambda f: PREMISSAS[f]["rota"])
    cap = {"Refrigerado": 1000, "Congelado": 600, "Seco": 2000}
    sim["rota"] = rota
    v = (sim.groupby(["semana", "rota"])[["recebido", "recebido_emerg"]].sum().reset_index())
    v["viagens"] = v.apply(lambda r: math.ceil(r["recebido"] / cap[r["rota"]]) +
                           math.ceil(r["recebido_emerg"] / cap[r["rota"]]), axis=1)
    return sim, v


def kpis(sim, v, metas, janela=None):
    s = sim if janela is None else sim[sim.semana.between(*janela)]
    vv = v if janela is None else v[v.semana.between(*janela)]
    g = s.groupby("familia").agg(demanda=("demanda", "sum"), atendido=("atendido", "sum"),
                                 descarte=("descarte", "sum"), recebido=("recebido", "sum"),
                                 receb_e=("recebido_emerg", "sum"),
                                 estoque_medio=("estoque_final", "mean"),
                                 semanas_ruptura=("ruptura", lambda x: (x > 0.5).sum()))
    g["fill_rate_pct"] = g.atendido / g.demanda * 100
    g["descarte_pct"] = g.descarte / (g.recebido + g.receb_e).replace(0, np.nan) * 100
    g["meta_fill"] = metas["meta_fill_rate_pct"]
    g["meta_desc"] = metas["meta_descarte_pct"]
    viag = vv.groupby("semana").viagens.sum()
    tot = dict(viagens_total=int(viag.sum()), viagens_media=viag.mean(), viagens_max=int(viag.max()),
               semanas_acima_ESG=int((viag > metas["limite_ESG"].iloc[0]).sum()),
               custo_frete=viag.sum() * metas["custo_viagem_R$"].iloc[0],
               co2_t=viag.sum() * metas["CO2_viagem_kgCO2e"].iloc[0] / 1000,
               fill_global=g.atendido.sum() / g.demanda.sum() * 100,
               vendas_perdidas=g.demanda.sum() - g.atendido.sum(),
               descarte_total=g.descarte.sum())
    return g, tot


# ------------------------ SEMAFOROS / RISCOS ---------------------------
def cor(valor, amarelo, vermelho, maior_pior=True):
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "CINZA"
    if maior_pior:
        return "VERMELHO" if valor >= vermelho else ("AMARELO" if valor >= amarelo else "VERDE")
    return "VERMELHO" if valor <= vermelho else ("AMARELO" if valor <= amarelo else "VERDE")


def indicadores_semana(sim, v, metas, t, wms_horas=0.0):
    """Calcula os KPIs-gatilho da matriz de riscos na semana t (janela movel de 4 sem)."""
    j = sim[sim.semana.between(t - 3, t)]
    f1 = j[j.familia == "F1 - Pereciveis"]
    f2 = sim[(sim.familia == "F2 - Premium") & (sim.semana == t)].iloc[0]
    f1t = sim[(sim.familia == "F1 - Pereciveis") & (sim.semana == t)].iloc[0]
    fill_f1 = f1.atendido.sum() / f1.demanda.sum() * 100
    fill_f1_sem = f1t.atendido / max(f1t.demanda, 1) * 100
    # pico nao planejado: erro positivo da semana em desvios-padrao do erro historico (26 sem)
    zs = []
    for f in FAMILIAS:
        x = sim[(sim.familia == f) & (sim.semana.between(t - 26, t))]
        e = (x.demanda - x.previsao).values
        sd = np.std(e[:-1], ddof=1) if len(e) > 5 else np.nan
        zs.append(((e[-1] / sd) if sd and sd > 0 else 0.0, f))
    pico, fam_pico = max(zs)
    lt_ratio = f2.lt_efetivo / PREMISSAS["F2 - Premium"]["lt"]
    cob_f2_sem = f2.estoque_final / max(f2.previsao, 1)
    viag = v[v.semana == t].viagens.sum()
    desc_f1 = f1.descarte.sum() / max((f1.recebido + f1.recebido_emerg).sum(), 1) * 100
    # vies acumulado 8 semanas = soma(real - previsto) / soma(real) - pior familia
    vs = []
    for f in ["F1 - Pereciveis", "F3 - Mercearia", "F4 - Congelados"]:   # familias A/B (X/Y); F2/F5 via WAPE mensal
        x = sim[(sim.familia == f) & (sim.semana.between(t - 7, t))]
        b = (x.demanda - x.previsao).sum() / max(x.demanda.sum(), 1) * 100
        vs.append((abs(b), f, b))
    ts_abs, fam_ts, ts_val = max(vs)
    return {
        "R1": (fill_f1, fill_f1_sem),
        "R2": (pico, fam_pico),
        "R3": (lt_ratio, cob_f2_sem),
        "R4": (wms_horas,),
        "R5": (viag,),
        "R6": (desc_f1,),
        "R7": (ts_abs, fam_ts, ts_val),
    }


MATRIZ_RISCOS = [
    dict(id="R1", risco="Ruptura crítica F1 (perecíveis)", kpi="Fill rate F1 móvel 4 sem e fill rate da semana",
         amarelo="Fill 4 sem < 97% (meta) OU qualquer ruptura na semana", vermelho="Fill 4 sem < 94% OU fill da semana < 94%",
         decisor="Amarelo: Coord. Planejamento | Vermelho: Gerente S&OE",
         acao="Pedido emergencial ao fornecedor F1 (D+1), transferência entre lojas, priorizar loja física e restringir oferta no marketplace",
         impacto="Crítico"),
    dict(id="R2", risco="Pico promocional não planejado", kpi="Erro da semana em desvios-padrão (z = (real - previsto)/sigma)",
         amarelo="z >= 2 (qualquer família)", vermelho="z >= 3",
         decisor="Analista de Demanda + Comercial (amarelo) | Gerente S&OE (vermelho)",
         acao="Reforecast imediato, pedido extra no proximo ciclo, cota por cliente no e-commerce; Comercial deve registrar promoções com 3 sem de antecedência",
         impacto="Alto"),
    dict(id="R3", risco="Atraso de fornecedor F2 (Premium)", kpi="LT observado / LT padrão e cobertura F2 (sem)",
         amarelo="LT >= 1,25x OU estoque F2 < 0,75 sem", vermelho="LT >= 2x OU estoque F2 < 0,25 sem",
         decisor="Gerente de Compras (com Gerente S&OE)",
         acao="Acionar fornecedor alternativo (LT 1 sem), antecipar pedidos, alocar estoque F2 para canais de maior margem e avisar marketplace",
         impacto="Alto"),
    dict(id="R4", risco="WMS offline", kpi="Horas de indisponibilidade do WMS",
         amarelo="> 2 h", vermelho="> 8 h ou backlog > 1 dia",
         decisor="Gerente do CD + TI (plantão)",
         acao="Plano de contingência: picking por lista impressa, priorizar F1/F4 (cadeia fria), pausar janelas de entrega do e-commerce",
         impacto="Crítico"),
    dict(id="R5", risco="Limite ESG de viagens excedido", kpi="Viagens/semana vs limite (15 = 630 kgCO2e)",
         amarelo=">= 12 viagens (80%)", vermelho="> 15 viagens",
         decisor="Gerente de Logística + Comitê ESG",
         acao="Consolidar cargas secas (F2/F3/F5), antecipar não perecíveis para semanas leves, renegociar janelas de entrega",
         impacto="Médio"),
    dict(id="R6", risco="Descarte de perecíveis acima da meta", kpi="Descarte F1 % do recebido (4 sem)",
         amarelo="> 2% (meta)", vermelho="> 3%",
         decisor="Coord. Planejamento + Comercial",
         acao="Reduzir pedido F1, markdown/promocao relampago, doação; revisar estoque de segurança",
         impacto="Médio"),
    dict(id="R7", risco="Viés persistente da previsão (modelo degradado)", kpi="Viés acumulado 8 sem = soma(real - prev) / soma(real), pior família A/B (F1, F3, F4)",
         amarelo="|viés| > 10%", vermelho="|viés| > 20%",
         decisor="Analista de Demanda (dono do modelo)",
         acao="Revisar modelo/parâmetros, checar eventos não cadastrados, aplicar override justificado no S&OE",
         impacto="Médio"),
]


def avaliar_riscos(ind):
    st = {}
    fill4, fill1 = ind["R1"]
    st["R1"] = max(cor(fill4, 97, 94, maior_pior=False), cor(fill1, 99.99, 94, maior_pior=False), key=_rank)
    st["R2"] = cor(ind["R2"][0], 2.0, 3.0)
    ltr, cobf2 = ind["R3"]
    st["R3"] = max(cor(ltr, 1.25, 2.0), cor(cobf2, 0.75, 0.25, maior_pior=False), key=_rank)
    st["R4"] = cor(ind["R4"][0], 2.0001, 8.0001)
    st["R5"] = "VERMELHO" if ind["R5"][0] > 15 else ("AMARELO" if ind["R5"][0] >= 12 else "VERDE")
    st["R6"] = "VERMELHO" if ind["R6"][0] > 3 else ("AMARELO" if ind["R6"][0] > 2 else "VERDE")
    st["R7"] = "VERMELHO" if ind["R7"][0] > 20 else ("AMARELO" if ind["R7"][0] > 10 else "VERDE")
    return st


def _rank(c):
    return {"CINZA": -1, "VERDE": 0, "AMARELO": 1, "VERMELHO": 2}[c]


def probabilidades(sim, v, metas, inicio=INICIO_SIM + 4, fim=104):
    """% de semanas em que cada gatilho ficou amarelo/vermelho (baseia a Probabilidade)."""
    cont = {r["id"]: [0, 0] for r in MATRIZ_RISCOS}
    n = 0
    for t in range(inicio, fim + 1):
        st = avaliar_riscos(indicadores_semana(sim, v, metas, t))
        n += 1
        for k, c in st.items():
            if c == "AMARELO":
                cont[k][0] += 1
            elif c == "VERMELHO":
                cont[k][1] += 1
    out = {}
    for k, (a, r) in cont.items():
        freq = (a + r) / n * 100
        if k == "R4":
            out[k] = (None, None, "Baixa")     # sem dados historicos: avaliacao qualitativa
            continue
        out[k] = (a / n * 100, r / n * 100, "Alta" if freq > 15 else ("Média" if freq >= 5 else "Baixa"))
    return out


# ------------------------------ ROI ------------------------------------
def roi_tabela(roi):
    r = roi.copy()
    for c in ["low", "base", "high"]:
        r[f"payback_{c}"] = r[f"custo_{c}_R$"] / r[f"beneficio_mensal_{c}_R$"]
    r["payback_pessimista"] = r["custo_high_R$"] / r["beneficio_mensal_low_R$"]   # custo alto + beneficio baixo
    r["ROI_12m_base_pct"] = (r["beneficio_mensal_base_R$"] * 12 - r["custo_base_R$"]) / r["custo_base_R$"] * 100
    return r


def escolher_modelos(bt, peso_vies=0.5):
    """Criterio de escolha: score = WAPE + peso * |vies|. Penaliza modelos lentos
    (ex.: SES alfa=0,1) que minimizam WAPE mas acumulam vies sistematico."""
    b = bt.copy()
    b["score"] = b["WAPE"] + peso_vies * b["vies_pct"].abs()
    best = b.loc[b.groupby("familia").score.idxmin()].set_index("familia")
    return best.modelo.to_dict(), b

# ======================================================================
# INTERFACE STREAMLIT
# ======================================================================
import os
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="Vila Aurora | S&OE Control Tower", layout="wide", page_icon="📦")

# ------------------------------ paleta ---------------------------------
COR_FAM = {"F1 - Pereciveis": "#2a78d6", "F2 - Premium": "#eb6834", "F3 - Mercearia": "#1baf7a",
           "F4 - Congelados": "#eda100", "F5 - Bebidas": "#e87ba4"}
COR_POL = {"Atual": "#898781", "S&OE": "#2a78d6"}
STATUS = {"VERDE": ("#0ca30c", "#ffffff", "●", "OK"), "AMARELO": ("#fab219", "#0b0b0b", "▲", "ATENÇÃO"),
          "VERMELHO": ("#d03b3b", "#ffffff", "✖", "AGIR"), "CINZA": ("#c3c2b7", "#0b0b0b", "–", "s/ dado")}
GRID = "#e1e0d9"

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 1rem;}
.kpi {background:#fcfcfb;border:1px solid #e1e0d9;border-radius:10px;padding:12px 14px;height:100%;}
.kpi .lab {font-size:.78rem;color:#52514e;text-transform:uppercase;letter-spacing:.03em;}
.kpi .val {font-size:1.6rem;font-weight:700;color:#0b0b0b;line-height:1.2;}
.kpi .sub {font-size:.8rem;color:#52514e;}
.sem {border-radius:10px;padding:10px 12px;margin-bottom:8px;border:1px solid #e1e0d9;background:#fcfcfb;}
.sem .tag {display:inline-block;border-radius:6px;padding:2px 8px;font-weight:700;font-size:.78rem;}
.sem .tit {font-weight:700;font-size:.95rem;color:#0b0b0b;margin:4px 0 2px 0;}
.sem .txt {font-size:.8rem;color:#52514e;}
</style>""", unsafe_allow_html=True)


def kpi_card(col, label, valor, sub=""):
    col.markdown(f'<div class="kpi"><div class="lab">{label}</div><div class="val">{valor}</div>'
                 f'<div class="sub">{sub}</div></div>', unsafe_allow_html=True)


def tag(status):
    bg, fg, ic, txt = STATUS[status]
    return f'<span class="tag" style="background:{bg};color:{fg}">{ic} {txt}</span>'


def estilo_fig(fig, h=340):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=78, b=10), plot_bgcolor="#fcfcfb",
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#0b0b0b"),
                      title=dict(y=0.98, yanchor="top", x=0, xanchor="left", font=dict(size=15)),
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, font=dict(size=11)), hovermode="x unified")
    fig.update_xaxes(gridcolor=GRID, linecolor="#c3c2b7")
    fig.update_yaxes(gridcolor=GRID, linecolor="#c3c2b7", zeroline=False)
    return fig


# ------------------------------ dados ----------------------------------
st.sidebar.title("⚙️ Controles")
up = st.sidebar.file_uploader("Base .xlsx do Bloco 4", type=["xlsx"])
padrao = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "ENG4550_3VA_G02_BLOCO4_Dashboard_IA_Roadmap_2026.2_v01.xlsx")
fonte = up if up is not None else padrao
if up is None and not os.path.exists(padrao):
    st.warning("Envie o arquivo .xlsx na barra lateral (ou coloque-o na mesma pasta do app).")
    st.stop()

politica = st.sidebar.radio("Política simulada", ["S&OE", "Atual"], horizontal=True,
                            help="Atual = reativa (MM4, ES fixo). S&OE = modelo por família, ES estatístico, gatilhos.")
semana = st.sidebar.slider("Semana de análise ('hoje')", 13, 104, 30)
wms = st.sidebar.number_input("WMS: horas offline na semana (input manual)", 0.0, 72.0, 0.0, 0.5)
uplift = st.sidebar.slider("Uplift planejado promoção F1 (sem 20)", 0.0, 0.8, UPLIFT_PROMO_F1, 0.05)
with st.sidebar.expander("Nível de serviço de ciclo por família (S&OE)"):
    ns = {f: st.slider(CURTO[f], 0.80, 0.995, NIVEL_SERVICO[f], 0.005, key=f) for f in FAMILIAS}


@st.cache_data(show_spinner="Rodando backtest e simulação...")
def rodar(fonte, uplift, ns_items):
    d, dem, metas, roi = carregar(fonte)
    dl = limpar_demanda(dem)
    bt = backtest(dl)
    esc, bts = escolher_modelos(bt)
    simA, vA = simular(dem, dl, metas, "Atual", esc)
    simB, vB = simular(dem, dl, metas, "S&OE", esc, nivel_servico=dict(ns_items), uplift=uplift)
    return d, dem, dl, metas, roi, bts, esc, simA, vA, simB, vB


d, dem, dl, metas, roi, bts, esc, simA, vA, simB, vB = rodar(fonte, uplift, tuple(ns.items()))
sim, v = (simB, vB) if politica == "S&OE" else (simA, vA)
g, tot = kpis(sim, v, metas)
gA, tA = kpis(simA, vA, metas)
gB, tB = kpis(simB, vB, metas)
data_sem = d[d.semana == semana].data.iloc[0].strftime("%d/%m/%Y")

st.markdown(f"## 📦 Vila Aurora — Torre de Controle S&OE")
st.caption(f"3VA · G02 · Cenário **Atraso de Fornecedor Premium** (LT de F2 dobra nas sem. 30–31; promoção F1 +40% na sem. 20) · "
           f"Política: **{politica}** · Semana {semana} ({data_sem})")

abas = st.tabs(["🚦 Painel S&OE", "⚠️ Matriz de riscos (Q13)", "📈 Previsão e política", "🧪 Simulação",
                "🤖 Automatizar × Humano (Q14)", "🗺️ Desenho e roadmap 90 dias (Q15)"])

# =========================== ABA 1: PAINEL ==============================
with abas[0]:
    ind = indicadores_semana(sim, v, metas, semana, wms_horas=wms)
    status = avaliar_riscos(ind)
    j4 = sim[sim.semana.between(semana - 3, semana)]
    fill4 = j4.atendido.sum() / j4.demanda.sum() * 100
    viag = int(v[v.semana == semana].viagens.sum())
    perdas4 = j4.ruptura.sum()
    c = st.columns(5)
    kpi_card(c[0], "Fill rate global (4 sem)", f"{fill4:.1f}%", "todas as famílias")
    kpi_card(c[1], "Vendas perdidas (4 sem)", f"{perdas4:,.0f} un".replace(",", "."), "demanda não atendida")
    kpi_card(c[2], "Estoque em mãos", f"{sim[sim.semana == semana].estoque_final.sum():,.0f} un".replace(",", "."), "fim da semana")
    kpi_card(c[3], "Viagens na semana", f"{viag} / 15", f"{viag * 42} kgCO2e · limite ESG 630")
    nv = sum(1 for s in status.values() if s == "VERMELHO"); na = sum(1 for s in status.values() if s == "AMARELO")
    kpi_card(c[4], "Alertas ativos", f"{nv} 🔴 · {na} 🟡", "riscos R1–R7")

    st.markdown("#### Semáforos de risco — semana selecionada")
    det = {
        "R1": f"Fill F1 4 sem {ind['R1'][0]:.1f}% · semana {ind['R1'][1]:.1f}%",
        "R2": f"z máx = {ind['R2'][0]:.1f} ({CURTO[ind['R2'][1]]})",
        "R3": f"LT F2 = {ind['R3'][0]:.0f}x padrão · estoque F2 = {ind['R3'][1]:.2f} sem",
        "R4": f"WMS offline {ind['R4'][0]:.1f} h",
        "R5": f"{ind['R5'][0]} viagens (limite 15)",
        "R6": f"Descarte F1 {ind['R6'][0]:.1f}% (meta 2%)",
        "R7": f"Viés 8 sem {ind['R7'][2]:+.1f}% ({CURTO[ind['R7'][1]]})",
    }
    cols = st.columns(4)
    for i, r in enumerate(MATRIZ_RISCOS):
        s = status[r["id"]]
        acao = r["acao"] if s != "VERDE" else "Monitorar — nenhuma ação necessária."
        cols[i % 4].markdown(
            f'<div class="sem" style="border-left:6px solid {STATUS[s][0]}">{tag(s)}'
            f'<div class="tit">{r["id"]} · {r["risco"]}</div><div class="txt"><b>{det[r["id"]]}</b></div>'
            f'<div class="txt">Decisor: {r["decisor"]}</div><div class="txt">➜ {acao}</div></div>',
            unsafe_allow_html=True)

    st.markdown("#### KPIs por família vs meta (acumulado da simulação)")
    t = g[["fill_rate_pct", "meta_fill", "semanas_ruptura", "estoque_medio", "descarte_pct", "meta_desc"]].copy()
    w = bts[bts.apply(lambda r: esc[r.familia] == r.modelo, axis=1)].set_index("familia")
    t["WAPE_pct"] = w["WAPE"]; t["meta_WAPE"] = metas["meta_WAPE_pct"]; t["modelo"] = pd.Series(esc)
    t["Status fill"] = ["🟢 OK" if a >= b else ("🟡 perto" if a >= b - 2 else "🔴 abaixo") for a, b in zip(t.fill_rate_pct, t.meta_fill)]
    t["Status WAPE"] = ["🟢 OK" if a <= b else ("🟡 perto" if a <= b * 1.15 else "🔴 acima") for a, b in zip(t.WAPE_pct, t.meta_WAPE)]
    t["Status descarte"] = ["🟢 OK" if a <= b else "🔴 acima" for a, b in zip(t.descarte_pct.fillna(0), t.meta_desc)]
    t = t.rename(columns={"fill_rate_pct": "Fill %", "meta_fill": "Meta fill", "semanas_ruptura": "Sem. c/ ruptura",
                          "estoque_medio": "Estoque médio", "descarte_pct": "Descarte %", "meta_desc": "Meta desc.",
                          "WAPE_pct": "WAPE %", "meta_WAPE": "Meta WAPE", "modelo": "Modelo"})
    st.dataframe(t.round(1), use_container_width=True)

    fam = st.selectbox("Família para acompanhar", FAMILIAS, index=1)
    x = sim[sim.familia == fam]
    fig = go.Figure()
    fig.add_bar(x=x.semana, y=x.ruptura, name="Ruptura (un)", marker_color="#d03b3b", opacity=.8)
    fig.add_scatter(x=x.semana, y=x.demanda, name="Demanda", line=dict(color="#52514e", width=2))
    fig.add_scatter(x=x.semana, y=x.previsao, name="Previsão", line=dict(color=COR_FAM[fam], width=2, dash="dot"))
    fig.add_scatter(x=x.semana, y=x.estoque_final, name="Estoque final", line=dict(color=COR_FAM[fam], width=2))
    fig.add_vline(x=semana, line_dash="dash", line_color="#898781")
    fig.update_layout(title=f"{fam} — demanda, previsão, estoque e ruptura")
    st.plotly_chart(estilo_fig(fig, 360), use_container_width=True)

# ======================== ABA 2: MATRIZ DE RISCOS =======================
with abas[1]:
    probA, probB = probabilidades(simA, vA, metas), probabilidades(simB, vB, metas)
    prob = probB if politica == "S&OE" else probA
    st.markdown("Probabilidade estimada pela **frequência de semanas em alerta** na simulação (sem. 13–104): "
                "Baixa < 5% · Média 5–15% · Alta > 15%. R4 (WMS) não tem histórico, então foi avaliado de forma qualitativa.")
    c1, c2 = st.columns([1, 1.35])
    imp_ord = ["Baixo", "Médio", "Alto", "Crítico"]; prob_ord = ["Baixa", "Média", "Alta"]
    z = np.array([[(pi + 1) * (ii + 1) for ii in range(4)] for pi in range(3)])
    zc = np.select([z <= 2, z <= 4, z <= 6], [0, 1, 2], 3)   # 0 baixo · 1 moderado · 2 alto · 3 crítico
    fig = go.Figure(go.Heatmap(z=zc, x=imp_ord, y=prob_ord, zmin=0, zmax=3, showscale=False, hoverinfo="skip", xgap=4, ygap=4,
                               colorscale=[[0, "#0ca30c"], [.25, "#0ca30c"], [.25, "#fab219"], [.5, "#fab219"],
                                           [.5, "#ec835a"], [.75, "#ec835a"], [.75, "#d03b3b"], [1, "#d03b3b"]]))
    cel = {}
    for r in MATRIZ_RISCOS:
        cel.setdefault((prob[r["id"]][2], r["impacto"]), []).append(r["id"])
    for (p, im), ids in cel.items():
        fig.add_annotation(x=im, y=p,
                           text="<b>" + " · ".join(ids) + "</b>", showarrow=False, font=dict(size=15, color="#0b0b0b"),
                           bgcolor="rgba(255,255,255,.85)")
    fig.update_layout(title=f"Probabilidade × Impacto — política {politica}", xaxis_title="Impacto", yaxis_title="Probabilidade")
    c1.plotly_chart(estilo_fig(fig, 380), use_container_width=True)

    mapa = {"VERDE": 0, "AMARELO": 1, "VERMELHO": 2, "CINZA": 0}
    sems = list(range(13, 105))
    M = np.array([[mapa[avaliar_riscos(indicadores_semana(sim, v, metas, t))[r["id"]]] for t in sems] for r in MATRIZ_RISCOS])
    fig2 = go.Figure(go.Heatmap(z=M, x=sems, y=[r["id"] for r in MATRIZ_RISCOS], zmin=0, zmax=2, showscale=False, xgap=1, ygap=2,
                                colorscale=[[0, "#0ca30c"], [0.33, "#0ca30c"], [0.34, "#fab219"], [0.66, "#fab219"], [0.67, "#d03b3b"], [1, "#d03b3b"]],
                                hovertemplate="Semana %{x} · %{y}<extra></extra>"))
    fig2.add_vline(x=semana, line_color="#0b0b0b", line_width=2)
    fig2.update_layout(title="Linha do tempo dos semáforos (verde / amarelo / vermelho)", hovermode="closest")
    fig2.update_yaxes(autorange="reversed")
    c2.plotly_chart(estilo_fig(fig2, 380), use_container_width=True)

    tab = pd.DataFrame(MATRIZ_RISCOS)
    tab["Prob. (Atual)"] = [probA[k][2] for k in tab.id]
    tab["Prob. (S&OE)"] = [probB[k][2] for k in tab.id]
    tab["% sem. alerta Atual"] = [None if probA[k][0] is None else round(probA[k][0] + probA[k][1], 1) for k in tab.id]
    tab["% sem. alerta S&OE"] = [None if probB[k][0] is None else round(probB[k][0] + probB[k][1], 1) for k in tab.id]
    tab["Status hoje"] = [STATUS[s][2] + " " + s for s in [avaliar_riscos(indicadores_semana(sim, v, metas, semana, wms))[k] for k in tab.id]]
    tab = tab[["id", "risco", "Status hoje", "Prob. (Atual)", "Prob. (S&OE)", "impacto", "kpi", "amarelo", "vermelho", "decisor", "acao",
               "% sem. alerta Atual", "% sem. alerta S&OE"]]
    st.dataframe(tab.rename(columns={"id": "ID", "risco": "Risco", "impacto": "Impacto", "kpi": "KPI-gatilho", "amarelo": "Gatilho 🟡",
                                     "vermelho": "Gatilho 🔴", "decisor": "Decisor", "acao": "Ação operacional"}),
                 use_container_width=True, hide_index=True, height=300)

# ===================== ABA 3: PREVISAO E POLITICA =======================
with abas[2]:
    c1, c2 = st.columns(2)
    w = bts.copy(); w["fam"] = w.familia.map(CURTO)
    esc_df = w[w.apply(lambda r: esc[r.familia] == r.modelo, axis=1)]
    fig = go.Figure()
    fig.add_bar(x=esc_df.fam, y=esc_df.WAPE, name="WAPE do modelo escolhido", marker_color=[COR_FAM[f] for f in esc_df.familia],
                text=[f"{m}<br>{x:.1f}%" for m, x in zip(esc_df.modelo, esc_df.WAPE)], textposition="outside")
    fig.add_scatter(x=esc_df.fam, y=metas.loc[esc_df.familia, "meta_WAPE_pct"].values, mode="markers", name="Meta WAPE",
                    marker=dict(symbol="line-ew", size=40, line=dict(width=3, color="#0b0b0b")))
    fig.update_layout(title="WAPE do backtest (holdout ano 2) × meta", yaxis_title="%", hovermode="closest")
    c1.plotly_chart(estilo_fig(fig, 380), use_container_width=True)
    piv = w.pivot(index="modelo", columns="fam", values="WAPE").round(1)
    fig = px.imshow(piv, text_auto=True, color_continuous_scale=["#cde2fb", "#2a78d6", "#0d366b"], aspect="auto")
    fig.update_layout(title="WAPE (%) por modelo × família — menor é melhor", coloraxis_showscale=False)
    c2.plotly_chart(estilo_fig(fig, 380), use_container_width=True)
    st.info("**F2 (Premium) não atinge a meta de WAPE (25%) com nenhum modelo estatístico**: a demanda é ruidosa (CV 0,44) e puxada por datas. "
            "Recomendação: previsão mensal/agregada com input comercial (calendário de datas comemorativas). "
            "As semanas 30–31 de F2 (44 e 234 un) foram tratadas como **demanda censurada** pela ruptura e substituídas no treino.")
    perfil = perfil_familias(dem, metas)
    pol = perfil[["perfil", "CV", "share_vol_pct", "lead_time_sem", "validade_sem", "meta_fill_rate_pct"]].copy()
    pol["Modelo"] = pd.Series(esc)
    pol["NS ciclo %"] = pd.Series(ns) * 100
    pol["σ erro"] = [round(sigma_erro(dl, f, esc[f])) for f in pol.index]
    pol["ES (un)"] = [round(z_de(ns[f]) * pol.loc[f, "σ erro"] * math.sqrt(PREMISSAS[f]["lt"])) for f in pol.index]
    pol["ES (sem)"] = (pol["ES (un)"] / perfil.media_sem).round(2)
    pol["Regra"] = ["Order-up-to semanal; D+1 em gatilho R1", "Order-up-to + monitor OTIF; fornecedor alternativo",
                    "Pedido automático (order-up-to)", "Order-up-to semanal com índice sazonal", "Min/máx semanal"]
    st.markdown("#### Política de estoque diferenciada por perfil ABC/XYZ")
    st.dataframe(pol, use_container_width=True)

# ============================ ABA 4: SIMULACAO ==========================
with abas[3]:
    c = st.columns(4)
    def delta(a, b): return f"{(b / a - 1) * 100:+.0f}% vs Atual" if a else ""
    kpi_card(c[0], "Vendas perdidas (sem 9–104)", f"{tB['vendas_perdidas']:,.0f}".replace(",", "."), f"Atual {tA['vendas_perdidas']:,.0f} · {delta(tA['vendas_perdidas'], tB['vendas_perdidas'])}".replace(",", "."))
    kpi_card(c[1], "Estoque médio total", f"{gB.estoque_medio.sum():,.0f} un".replace(",", "."), f"Atual {gA.estoque_medio.sum():,.0f} · {delta(gA.estoque_medio.sum(), gB.estoque_medio.sum())}".replace(",", "."))
    kpi_card(c[2], "Descarte total", f"{tB['descarte_total']:,.0f} un".replace(",", "."), f"Atual {tA['descarte_total']:,.0f} · {delta(tA['descarte_total'], tB['descarte_total'])}".replace(",", "."))
    kpi_card(c[3], "Viagens / CO2", f"{tB['viagens_total']} · {tB['co2_t']:.1f} t", f"Atual {tA['viagens_total']} · {tA['co2_t']:.1f} t · pico {tB['viagens_max']}/15")
    st.write("")
    c1, c2 = st.columns(2)
    for col, fam, ini, fim, titulo, marca in [(c1, "F2 - Premium", 24, 40, "F2 — atraso do fornecedor (pedidos das sem. 30–31 com LT 4)", (29.5, 31.5)),
                                              (c2, "F1 - Pereciveis", 14, 26, "F1 — promoção sem. 20 (+40%)", (19.5, 20.5))]:
        fig = go.Figure()
        fig.add_vrect(x0=marca[0], x1=marca[1], fillcolor="#d03b3b", opacity=.08, line_width=0)
        for nome, s in [("Atual", simA), ("S&OE", simB)]:
            x = s[(s.familia == fam) & s.semana.between(ini, fim)]
            fig.add_scatter(x=x.semana, y=x.estoque_final, name=f"Estoque {nome}", line=dict(color=COR_POL[nome], width=2, dash="dash" if nome == "Atual" else "solid"))
            fig.add_bar(x=x.semana, y=x.ruptura, name=f"Ruptura {nome}", marker_color=COR_POL[nome], opacity=.55)
        fig.update_layout(title=titulo, barmode="group")
        col.plotly_chart(estilo_fig(fig, 340), use_container_width=True)
    vv = pd.DataFrame({"Atual": vA.groupby("semana").viagens.sum(), "S&OE": vB.groupby("semana").viagens.sum()})
    fig = go.Figure()
    for nome in ["Atual", "S&OE"]:
        fig.add_scatter(x=vv.index, y=vv[nome], name=nome, line=dict(color=COR_POL[nome], width=2, dash="dash" if nome == "Atual" else "solid"))
    fig.add_hline(y=15, line_color="#d03b3b", annotation_text="Limite ESG 15 viagens", annotation_position="top left")
    fig.add_hline(y=12, line_color="#fab219", line_dash="dot", annotation_text="Gatilho amarelo 12", annotation_position="bottom left")
    fig.update_layout(title="Viagens por semana × limite ESG", yaxis_range=[0, 17])
    st.plotly_chart(estilo_fig(fig, 300), use_container_width=True)
    comp = pd.concat({"Atual": gA[["fill_rate_pct", "semanas_ruptura", "estoque_medio"]], "S&OE": gB[["fill_rate_pct", "semanas_ruptura", "estoque_medio"]]}, axis=1).round(1)
    st.dataframe(comp, use_container_width=True)
    st.caption("Premissas (não fornecidas na base): LT F1/F4/F5 = 1 sem, F2/F3 = 2 sem; validade F1 = 2 sem, F4 = 12, F2/F5 = 26, F3 = 52; "
               "capacidade por viagem: refrigerado 1.000 un, congelado 600, seco 2.000 (F2+F3+F5 consolidados). Revisão semanal, order-up-to, FIFO.")

# ========================= ABA 5: AUTOMATIZAR ===========================
with abas[4]:
    q14 = pd.DataFrame([
        ["Pedido de reposição F3", 1, 4, 1, "Automatizar", "AX: demanda estável (CV 0,11), WAPE 7,8%, validade longa; erro barato e corrigível no ciclo seguinte"],
        ["Alerta de estoque baixo / ruptura", 1, 5, 1, "Automatizar", "Regra objetiva (KPI × limiar); a máquina é mais rápida e consistente; o alerta só informa, não executa"],
        ["Atualização semanal da previsão", 2, 4, 2, "Automatizar + revisar exceções", "Recalcular 5 famílias toda semana é repetitivo; o humano revisa só quando R7 (viés) acende"],
        ["Pedido F1/F4 (perecível/frio)", 2, 5, 2, "Automatizar c/ aprovação de exceção", "Alta frequência, mas o erro gera descarte; sistema sugere e o humano aprova só fora da banda ±20%"],
        ["Consolidação de cargas (ESG)", 2, 4, 2, "Sugestão automática, humano aprova", "Otimização é computável; trade-off nível de serviço × CO2 exige julgamento"],
        ["Pedido F2 (Premium)", 3, 4, 3, "Sugestão automática + aprovação", "WAPE 42%, fornecedor instável e margem alta; o erro custa caro em ruptura"],
        ["Uplift de promoção/evento", 4, 2, 3, "Human-centric", "Depende de informação comercial que não está no histórico (mecânica, mídia, preço)"],
        ["Choque de oferta (fornecedor alternativo)", 5, 1, 4, "Human-centric", "Rara, sem histórico, envolve custo extra, contrato e relação com fornecedor"],
        ["Alocação entre canais na Black Friday", 5, 1, 4, "Human-centric", "Trade-off de margem, SLA, cancelamento e imagem entre loja, e-commerce e marketplace"],
        ["Contingência WMS offline", 4, 1, 4, "Human-centric (playbook)", "Crise operacional; exige coordenação de pessoas e priorização em tempo real"],
    ], columns=["Decisão", "Complexidade (1-5)", "Frequência (1-5)", "Consequência do erro (1-4)", "Recomendação", "Justificativa"])
    cor_rec = {"Automatizar": "#1baf7a", "Automatizar + revisar exceções": "#2a78d6", "Automatizar c/ aprovação de exceção": "#2a78d6",
               "Sugestão automática, humano aprova": "#eda100", "Sugestão automática + aprovação": "#eda100",
               "Human-centric": "#eb6834", "Human-centric (playbook)": "#eb6834"}
    grupo = {"Automatizar": "Automatizar", "Automatizar + revisar exceções": "Automatizar c/ exceções", "Automatizar c/ aprovação de exceção": "Automatizar c/ exceções",
             "Sugestão automática, humano aprova": "Humano aprova sugestão", "Sugestão automática + aprovação": "Humano aprova sugestão",
             "Human-centric": "Human-centric", "Human-centric (playbook)": "Human-centric"}
    q14["Grupo"] = q14["Recomendação"].map(grupo)
    cg = {"Automatizar": "#1baf7a", "Automatizar c/ exceções": "#2a78d6", "Humano aprova sugestão": "#eda100", "Human-centric": "#eb6834"}
    q14.insert(0, "#", range(1, len(q14) + 1))
    off = {1: (0, 0), 2: (0, 0), 3: (-.15, .12), 4: (0, 0), 5: (.15, -.12), 6: (0, 0), 7: (0, 0), 8: (-.28, 0), 9: (.28, 0), 10: (0, 0)}
    fig = go.Figure()
    for gname, gcolor in cg.items():
        x = q14[q14.Grupo == gname]
        fig.add_scatter(x=x["Frequência (1-5)"] + x["#"].map(lambda k: off[k][0]), y=x["Complexidade (1-5)"] + x["#"].map(lambda k: off[k][1]),
                        mode="markers+text", name=gname, text=x["#"].astype(str), textposition="middle center",
                        textfont=dict(size=11, color="#ffffff" if gname != "Humano aprova sugestão" else "#0b0b0b"),
                        customdata=x["Decisão"], marker=dict(size=16 + 7 * x["Consequência do erro (1-4)"], color=gcolor, line=dict(color="#fcfcfb", width=2)),
                        hovertemplate="#%{text} %{customdata}<extra></extra>")
    fig.add_annotation(x=4.5, y=0.55, text="Automatizar ⟶", showarrow=False, font=dict(color="#1baf7a", size=13))
    fig.add_annotation(x=1.5, y=5.65, text="⟵ Human-centric", showarrow=False, font=dict(color="#eb6834", size=13))
    fig.update_layout(title="Frequência × complexidade · tamanho = custo do erro", xaxis_title="Frequência da decisão",
                      yaxis_title="Complexidade", hovermode="closest", xaxis_range=[0.4, 5.6], yaxis_range=[0.3, 5.9])
    c1, c2 = st.columns([1, 1.25])
    c1.plotly_chart(estilo_fig(fig, 470), use_container_width=True)
    c2.dataframe(q14[["#", "Decisão", "Recomendação", "Consequência do erro (1-4)"]], use_container_width=True, hide_index=True, height=400)
    st.dataframe(q14[["#", "Decisão", "Justificativa"]], use_container_width=True, hide_index=True)
    st.markdown("**Regra de bolso:** automatizar o que é *frequente, padronizável e com erro barato e reversível*; manter human-centric o que é *raro, ambíguo, "
                "multiobjetivo e com erro caro ou irreversível*. Toda automação tem dono, banda de tolerância e botão de override registrado.")

# ========================== ABA 6: ROADMAP ==============================
with abas[5]:
    st.markdown("#### Desenho integrado")
    etapas = [("1 · Previsão", "#2a78d6", "Modelo por família<br>F1 SES α0,5 · F2 SES α0,1 + comercial<br>F3 SES α0,1 · F4 SES+sazonal · F5 MM8<br>Atualização semanal (seg)"),
              ("2 · Política de estoque", "#1baf7a", "ES = z·σ·√LT por perfil<br>NS: F3 99% · F1/F2 98%<br>F4 97% · F5 95%<br>Order-up-to semanal"),
              ("3 · Simulação", "#eda100", "Cenários: base, promo, atraso F2,<br>Black Friday, WMS off<br>KPIs: fill, ruptura, estoque,<br>descarte, viagens, CO2"),
              ("4 · Dashboard", "#eb6834", "7 semáforos R1–R7<br>KPIs × meta por família<br>Atualização diária (D-1)<br>Alertas push no amarelo"),
              ("5 · Rotina S&OE", "#e87ba4", "Diária 15 min (alertas)<br>Semanal 60 min (seg)<br>Escalonamento 🔴 em 24 h<br>Mensal: S&OP")]
    cols = st.columns(5)
    for c_, (t_, cor_, txt) in zip(cols, etapas):
        c_.markdown(f'<div class="kpi" style="border-top:5px solid {cor_}"><div class="tit" style="font-weight:700">{t_}</div>'
                    f'<div class="sub" style="margin-top:6px">{txt}</div></div>', unsafe_allow_html=True)
    r = roi_tabela(roi)
    ordem = {"Semanas 1-4": 0, "Semanas 5-8": 1, "Semanas 9-12": 2}
    cfase = {"Semanas 1-4": "#1baf7a", "Semanas 5-8": "#2a78d6", "Semanas 9-12": "#eb6834"}
    st.write("")
    c1, c2 = st.columns([1.2, 1])
    fig = go.Figure()
    for _, x in r.iloc[::-1].iterrows():
        i0 = ordem[x.fase] * 4 + 1
        fig.add_bar(y=[x.acao], x=[4], base=[i0 - 0.5], orientation="h", marker_color=cfase[x.fase], name=x.fase, showlegend=False,
                    hovertemplate=f"{x.acao}<br>{x.fase}<br>Custo base R$ {x['custo_base_R$']:,.0f}<br>Payback {x.payback_base:.1f} meses<extra></extra>")
    for f_, c_ in cfase.items():
        fig.add_bar(y=[None], x=[None], marker_color=c_, name=f_)
    fig.update_layout(title="Roadmap 90 dias (Gantt)", xaxis_title="Semana", barmode="overlay", hovermode="closest", xaxis=dict(range=[0.5, 12.5], dtick=1))
    c1.plotly_chart(estilo_fig(fig, 380), use_container_width=True)
    meses = np.arange(0, 13)
    fig = go.Figure()
    for cen, cor_ in [("low", "#898781"), ("base", "#2a78d6"), ("high", "#1baf7a")]:
        fc = np.zeros(len(meses))
        for _, x in r.iterrows():
            m0 = ordem[x.fase]; fc[m0] -= x[f"custo_{cen}_R$"]; fc[m0 + 1:] += x[f"beneficio_mensal_{cen}_R$"]
        fig.add_scatter(x=meses, y=fc.cumsum() / 1000, name=cen, line=dict(color=cor_, width=2), mode="lines+markers")
    fig.add_hline(y=0, line_color="#c3c2b7")
    fig.update_layout(title="Fluxo de caixa acumulado (R$ mil)", xaxis_title="Mês")
    c2.plotly_chart(estilo_fig(fig, 380), use_container_width=True)
    rt = r[["acao", "fase", "responsavel", "custo_base_R$", "beneficio_mensal_base_R$", "payback_base", "payback_pessimista", "ROI_12m_base_pct", "KPI", "dependencia"]].copy()
    st.dataframe(rt.rename(columns={"acao": "Ação", "fase": "Fase", "responsavel": "Responsável", "custo_base_R$": "Custo base R$",
                                    "beneficio_mensal_base_R$": "Benefício/mês R$", "payback_base": "Payback base (m)",
                                    "payback_pessimista": "Payback pessimista (m)", "ROI_12m_base_pct": "ROI 12m %", "dependencia": "Dependência"}).round(1),
                 use_container_width=True, hide_index=True)