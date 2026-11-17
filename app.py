"""Vila Aurora — Q13. Streamlit dashboard (S&OE risk matrix)."""
from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Vila Aurora | Riscos S&OE", page_icon="📈", layout="wide")
st.markdown("""
<style>
.block-container {max-width: 1450px; padding-top: 1.5rem}
.hero {background:linear-gradient(115deg,#102d42,#155e71); padding: 26px 30px; border-radius:17px; color: white; margin-bottom:18px}
.hero h1 {color:white; font-size:2.2rem; margin-bottom: 5px}
.hero p {color:#dceff4; margin-bottom:0}
[data-testid="stMetric"] {border:1px solid #dce6eb; background:#f7fafb; border-radius:12px; padding:15px}
</style>
""", unsafe_allow_html=True)

PROB = {"Baixa": 1, "Média": 2, "Alta": 3}
IMPACT = {"Baixo": 1, "Médio": 2, "Alto": 3, "Crítico": 4}
RISKS = [
    {"ID":"R01", "Risco":"Ruptura crítica F1 — Perecíveis", "Probabilidade":"Média", "Impacto":"Crítico",
     "KPI":"Fill rate F1 / cobertura em semanas", "Gatilho":"Fill rate F1 < 97% ou cobertura < 1 semana",
     "Decisor":"Planejamento de demanda + Operações",
     "Ação operacional":"Reforecast; priorizar canais críticos; redistribuir estoque e aprovar pedido emergencial.",
     "Fundamentação":"Meta de fill rate de 97% no Dashboard; 1 semana de cobertura é um gatilho proposto."},
    {"ID":"R02", "Risco":"Atraso no fornecedor F2 — Premium", "Probabilidade":"Alta", "Impacto":"Alto",
     "KPI":"Lead time realizado / lead time contratado", "Gatilho":"Lead time ≥ 2× o previsto (sem. 30–31)",
     "Decisor":"Suprimentos + Planejamento",
     "Ação operacional":"Acionar alternativa homologada; negociar entrega parcial; ajustar parâmetro de estoque de segurança.",
     "Fundamentação":"Evento de duplicação do lead time por duas semanas consta no cenário do Grupo 02."},
    {"ID":"R03", "Risco":"Pico promocional F1 não planejado", "Probabilidade":"Alta", "Impacto":"Alto",
     "KPI":"Demanda real versus forecast", "Gatilho":"Promoção F1 +40% na semana 20; alerta se erro > 15%",
     "Decisor":"Comercial + Planejamento de demanda",
     "Ação operacional":"Atualizar previsão promocional; antecipar abastecimento e reservar capacidade logística.",
     "Fundamentação":"Promoção de +40% na sem. 20 consta no cenário; desvio de 15% é sugestão gerencial."},
    {"ID":"R04", "Risco":"Viagens emergenciais e custos elevados", "Probabilidade":"Média", "Impacto":"Alto",
     "KPI":"Viagens extras no pior mês / custo P95", "Gatilho":"≥ 4 viagens extras no mês ou custo P95 > orçamento",
     "Decisor":"Logística + Finanças",
     "Ação operacional":"Consolidar cargas; otimizar rotas; exigir aprovação para frete extraordinário.",
     "Fundamentação":"Q11/Q12 medem viagens extras e custo P95; limite de 4 viagens é proposto."},
    {"ID":"R05", "Risco":"Descarte de F1 acima da meta", "Probabilidade":"Média", "Impacto":"Alto",
     "KPI":"Percentual de descarte F1", "Gatilho":"Descarte > 2%",
     "Decisor":"Operações + Estoque",
     "Ação operacional":"Adotar FEFO; ajustar tamanho do lote; antecipar transferências entre pontos de venda.",
     "Fundamentação":"Meta de descarte de 2% consta em M_Dashboard_Input; Q11/Q12 mostram descarte."},
    {"ID":"R06", "Risco":"WMS indisponível", "Probabilidade":"Média", "Impacto":"Alto",
     "KPI":"Minutos de indisponibilidade / divergência de inventário", "Gatilho":"WMS offline > 15 minutos ou divergência > 2%",
     "Decisor":"TI + Operações",
     "Ação operacional":"Ativar contingência manual rastreável; limitar movimentos; reconciliar inventário após retorno.",
     "Fundamentação":"Risco complementar da Q13; ambos os limites são hipóteses a validar com TI."},
    {"ID":"R07", "Risco":"Limite ESG excedido", "Probabilidade":"Média", "Impacto":"Alto",
     "KPI":"Indicador de ESG / CO₂ por viagem", "Gatilho":"Indicador ESG > 15 (definição/unidade a confirmar)",
     "Decisor":"Sustentabilidade + Logística",
     "Ação operacional":"Consolidar entregas; rever rotas e reduzir fretes extraordinários.",
     "Fundamentação":"M_Dashboard_Input contém limite_ESG=15 e CO₂ por viagem=42 kgCO₂e; não confundir unidades."},
]


def risk_priority(prob: str, impact: str) -> tuple[int, str]:
    score = PROB.get(prob, 0) * IMPACT.get(impact, 0)
    if score >= 9:
        return score, "Crítica"
    if score >= 6:
        return score, "Alta"
    if score >= 3:
        return score, "Média"
    return score, "Baixa"


def load_excel(upload, sheet_name: str) -> pd.DataFrame | None:
    if upload is None:
        return None
    try:
        upload.seek(0)
        return pd.read_excel(upload, sheet_name=sheet_name)
    except Exception as exc:
        st.warning(f"Não foi possível ler a aba {sheet_name}: {exc}")
        return None


def fmt_brl(num: float) -> str:
    return "R$ " + f"{num:,.0f}".replace(",", "_").replace(".", ",").replace("_", ".")


st.markdown('<div class="hero"><h1>Vila Aurora · Matriz de Riscos S&OE</h1><p>ENG4550 · 3VA · Grupo 02 · Bloco 4 · Questão 13</p></div>', unsafe_allow_html=True)
st.write("O painel converte riscos operacionais em **gatilhos mensuráveis, responsáveis e respostas práticas** para a reunião de S&OE.")

with st.sidebar:
    st.header("⚙️ Painel de controle")
    st.caption("As alterações feitas no painel duram apenas nesta sessão. Exporte o Excel para guardar a versão final.")
    st.subheader("Filtrar riscos")
    probs = st.multiselect("Probabilidade", list(PROB), default=list(PROB))
    impacts = st.multiselect("Impacto", list(IMPACT), default=list(IMPACT))
    keyword = st.text_input("Buscar", placeholder="F1, fornecedor, ESG…")
    st.divider()
    st.subheader("📎 Importar bases do grupo")
    results = st.file_uploader("Resultados Q11/Q12 (XLSX)", type="xlsx", key="results")
    dashboard = st.file_uploader("Dashboard do Bloco 4 (XLSX)", type="xlsx", key="dashboard")
    st.caption("Uploads são usados nesta sessão e não são publicados no GitHub.")

if "matrix" not in st.session_state:
    st.session_state.matrix = pd.DataFrame(RISKS)

matrix = st.session_state.matrix.copy()
matrix[["Score", "Prioridade"]] = matrix.apply(
    lambda r: pd.Series(risk_priority(str(r["Probabilidade"]), str(r["Impacto"]))), axis=1
)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Riscos monitorados", len(matrix))
m2.metric("Prioridade crítica", int((matrix["Prioridade"] == "Crítica").sum()))
m3.metric("Prioridade alta", int((matrix["Prioridade"] == "Alta").sum()))
m4.metric("Gatilhos definidos", int(matrix["Gatilho"].notna().sum()))

view_tab, matrix_tab, scenarios_tab, data_tab, methods_tab = st.tabs(
    ["Visão executiva", "Matriz editável", "Gatilhos de cenário", "Bases Q11/Q12", "Metodologia"]
)

with view_tab:
    st.subheader("Mapa de calor — frequência de riscos")
    heat = pd.crosstab(matrix["Probabilidade"], matrix["Impacto"])
    heat = heat.reindex(index=["Alta", "Média", "Baixa"], columns=["Baixo", "Médio", "Alto", "Crítico"], fill_value=0)
    st.dataframe(heat.style.background_gradient(cmap="YlOrRd", axis=None).format("{:.0f}"), use_container_width=True)
    st.caption("A cor indica concentração de riscos em cada célula, não uma probabilidade estatística estimada.")
    st.subheader("Fila de atenção")
    show = matrix.sort_values(["Score", "ID"], ascending=[False, True])
    st.dataframe(show[["ID", "Risco", "Probabilidade", "Impacto", "Prioridade", "Gatilho", "Decisor"]],
                 use_container_width=True, hide_index=True)
    st.info("**Evento crítico do grupo:** F1 tem promoção de +40% na semana 20; F2 sofre aumento de lead time nas semanas 30–31.")

with matrix_tab:
    st.subheader("Edite a matriz para a entrega da Q13")
    filtered = matrix.copy()
    filtered = filtered[filtered["Probabilidade"].isin(probs) & filtered["Impacto"].isin(impacts)]
    if keyword:
        filtered = filtered[filtered.astype(str).apply(lambda c: c.str.contains(keyword, case=False, na=False)).any(axis=1)]
    editable_cols = [c for c in st.session_state.matrix.columns]
    changed = st.data_editor(
        filtered[editable_cols], hide_index=True, use_container_width=True, num_rows="fixed",
        column_config={
            "ID": st.column_config.TextColumn(disabled=True),
            "Probabilidade": st.column_config.SelectboxColumn(options=list(PROB), required=True),
            "Impacto": st.column_config.SelectboxColumn(options=list(IMPACT), required=True),
            "Risco": st.column_config.TextColumn(width="large"),
            "Gatilho": st.column_config.TextColumn(width="large"),
            "Ação operacional": st.column_config.TextColumn(width="large"),
            "Fundamentação": st.column_config.TextColumn(width="large"),
        }, key="editor"
    )
    a, b = st.columns(2)
    if a.button("Salvar edições na sessão", type="primary", use_container_width=True):
        base = st.session_state.matrix.set_index("ID")
        if len(changed):
            for _, row in changed.iterrows():
                rid = row["ID"]
                if rid in base.index:
                    for col in editable_cols:
                        if col != "ID":
                            base.at[rid, col] = row[col]
        st.session_state.matrix = base.reset_index()
        st.success("Alterações salvas nesta sessão. Exporte o Excel para manter o arquivo.")
    if b.button("Restaurar matriz original", use_container_width=True):
        st.session_state.matrix = pd.DataFrame(RISKS)
        st.rerun()

    matrix_export = st.session_state.matrix.copy()
    matrix_export[["Score", "Prioridade"]] = matrix_export.apply(
        lambda r: pd.Series(risk_priority(r["Probabilidade"], r["Impacto"])), axis=1
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        matrix_export.to_excel(writer, sheet_name="Q13_Matriz_de_Riscos", index=False)
        pd.DataFrame({"Regra": ["score = probabilidade (1,2,3) × impacto (1,2,3,4)",
                                 "Crítica ≥9; Alta ≥6; Média ≥3; Baixa <3",
                                 "Limiares gerenciais propostos devem ser validados"]}).to_excel(
            writer, sheet_name="Metodologia", index=False
        )
    st.download_button("📥 Exportar matriz Q13 (.xlsx)", data=buffer.getvalue(),
                       file_name="Vila_Aurora_Q13_Matriz_Riscos.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with scenarios_tab:
    st.subheader("Eventos do cenário do Grupo 02")
    s1, s2 = st.columns(2)
    with s1:
        st.markdown("### F1 · Promoção")
        st.metric("Semana de ocorrência", "20")
        st.metric("Choque na demanda", "+40%")
        st.write("**S&OE:** revisar previsão, disponibilidade por canal e programação de reposição antes da campanha.")
    with s2:
        st.markdown("### F2 · Fornecedor Premium")
        st.metric("Início do atraso", "Semana 30")
        st.metric("Duração do evento", "2 semanas")
        st.write("**S&OE:** simular cobertura no novo lead time e acionar Suprimentos para plano alternativo.")
    st.warning("O painel mostra **regras de acionamento**, não calcula automaticamente a probabilidade de ocorrência ou o impacto financeiro do evento.")

with data_tab:
    st.subheader("Dados das questões 11 e 12")
    if results is None and dashboard is None:
        st.info("Envie as planilhas na lateral para consultar as métricas e os cenários. O painel funciona sem os arquivos.")
        st.markdown("**Indicadores disponíveis nas bases do grupo:** fill rate, cobertura semanal, custo médio/P95, viagens extras, descarte, CO₂ e duração do atraso.")
    if results is not None:
        q11 = load_excel(results, "Q11")
        q12 = load_excel(results, "Q12_replanejamento")
        q12delay = load_excel(results, "Q12_duracao_atraso")
        tabq11, tabq12, tabdelay = st.tabs(["Q11", "Q12 Replanejamento", "Q12 Atraso"])
        with tabq11:
            if q11 is not None:
                st.dataframe(q11, use_container_width=True)
                if {"fill_rate", "cobertura_sem", "custo_p95"}.issubset(q11.columns) and len(q11):
                    r = q11.iloc[0]
                    a, b, c = st.columns(3)
                    a.metric("Fill rate — 1º cenário Q11", f"{r['fill_rate']:.2%}")
                    b.metric("Cobertura — 1º cenário Q11", f"{r['cobertura_sem']:.2f} sem.")
                    c.metric("Custo P95 — 1º cenário Q11", fmt_brl(r["custo_p95"]))
        with tabq12:
            if q12 is not None:
                st.dataframe(q12, use_container_width=True)
        with tabdelay:
            if q12delay is not None:
                st.dataframe(q12delay, use_container_width=True)
    if dashboard is not None:
        st.markdown("#### Metas e eventos — Dashboard")
        d = load_excel(dashboard, "M_Dashboard_Input")
        if d is not None:
            keep = [c for c in ["semana", "familia", "demanda_total", "evento", "limite_ESG", "meta_fill_rate_pct", "meta_WAPE_pct", "meta_descarte_pct", "CO2_viagem_kgCO2e"] if c in d.columns]
            st.dataframe(d[keep], use_container_width=True)

with methods_tab:
    st.subheader("Como interpretar a matriz")
    st.markdown("""
    1. **Identifique o risco operacional**: qual evento pode comprometer a execução semanal?
    2. **Defina probabilidade e impacto**: classificação inicial qualitativa, a validar com a equipe.
    3. **Estabeleça um gatilho**: KPI observável com limiar e período bem definidos.
    4. **Atribua o decisor**: função responsável por escolher a ação, não apenas por monitorar o KPI.
    5. **Indique a resposta**: ação executável (reforecast, remanejamento, fornecedor alternativo etc.).

    **Escala proposta:** probabilidade Baixa=1, Média=2, Alta=3; impacto Baixo=1, Médio=2,
    Alto=3, Crítico=4. Score = multiplicação; prioridades Crítica ≥9, Alta ≥6, Média ≥3, Baixa <3.

    **Limiares que vieram do caso:** promoção F1 +40% na semana 20; duplicação de lead time F2
    a partir da semana 30, durante duas semanas; meta de fill rate 97%; meta descarte 2%; campo
    limite_ESG=15 — significado/unidade a confirmar.

    **Limiares sugeridos pelo grupo:** cobertura <1 semana, erro de forecast >15%, ≥4 viagens extras,
    indisponibilidade do WMS >15 min, divergência de inventário >2%. Não apresentá-los como métricas
    efetivamente observadas.

    **Importante:** a Q13 requer **matriz de riscos e gatilhos de S&OE**, não apenas listar
    indicadores. Ações devem ser ligadas ao KPI que disparou o alerta.
    """)

st.caption("Vila Aurora · Ferramenta acadêmica de apoio à decisão · Indicadores de upload não persistidos")
