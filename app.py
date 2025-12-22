import streamlit as st
import pandas as pd
import requests
import altair as alt
import math
from datetime import date, time

# ==========================
# CONFIGURAÇÕES
# ==========================
st.set_page_config(page_title="Monitoramento de Rios", layout="wide")

SHEET_ID = st.secrets["SHEET_ID"]

ABA_RIOS = "rios"
ABA_MUNICIPIOS = "municipios"
ABA_LEITURAS = "leituras"

FORM_URL = st.secrets["FORM_URL"]

FORM_FIELDS = {
    "id_rio": "entry.2045951420",
    "id_municipio": "entry.143224654",
    "data": "entry.2019012807",
    "hora": "entry.795474044",
    "nivel": "entry.718891381",
}

ADMIN_SENHA = st.secrets["ADMIN_SENHA"]

# ==========================
# FUNÇÕES AUXILIARES
# ==========================
def carregar_aba(nome):
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={nome}"
    return pd.read_csv(url)

def calcular_situacao(nivel, cota):
    try:
        nivel = float(str(nivel).replace(",", "."))
    except:
        return "Leitura inválida", "gray", None, "Leitura inválida."

    try:
        cota = float(str(cota).replace(",", "."))
    except:
        return "Sem cota definida", "gray", None, "Município sem cota de transbordo."

    if pd.isna(cota) or cota <= 0:
        return "Sem cota definida", "gray", None, "Município sem cota de transbordo."

    perc = (nivel / cota) * 100

    if perc < 85:
        return "Normal", "green", perc, "Nível dentro da normalidade."
    elif perc < 100:
        return "Alerta", "orange", perc, "Atenção: nível elevado."
    elif perc <= 120:
        return "Transbordo", "red", perc, "Rio acima da cota de transbordo."
    else:
        return "Risco Hidrológico Extremo", "purple", perc, "Nível extremamente crítico."

def enviar_formulario(payload):
    r = requests.post(FORM_URL, data=payload)
    return r.status_code == 200

# ==========================
# FUNÇÕES DO RELATÓRIO (USUÁRIO)
# ==========================
def montar_relatorio(rios, municipios, leituras):
    base = municipios.merge(rios, on="id_rio")
    registros = []

    for _, row in base.iterrows():
        filtro = leituras[
            (leituras["id_rio"] == row["id_rio"]) &
            (leituras["id_municipio"] == row["id_municipio"])
        ].sort_values(["data", "hora"])

        ultima = filtro.iloc[-1]["nivel"] if len(filtro) >= 1 else None
        penultima = filtro.iloc[-2]["nivel"] if len(filtro) >= 2 else None

        registros.append({
            "Rio": row["nome_rio"],
            "Município": row["nome_municipio"],
            "Cota de Transbordo": row.get("nivel_transbordo"),
            "Penúltima Medição": penultima,
            "Última Medição": ultima,
            "Fonte": row.get("fonte")
        })

    return pd.DataFrame(registros)

def cor_medido(valor, cota):
    if pd.isna(valor) or pd.isna(cota):
        return "background-color: #f2f2f2"

    _, cor, _, _ = calcular_situacao(valor, cota)

    mapa = {
        "green": "#d4edda",
        "orange": "#fff3cd",
        "red": "#f8d7da",
        "purple": "#e2d6f3"
    }
    return f"background-color: {mapa.get(cor, '#f2f2f2')}"

# ==========================
# CARREGAMENTO DE DADOS
# ==========================
rios = carregar_aba(ABA_RIOS)
municipios = carregar_aba(ABA_MUNICIPIOS)
leituras = carregar_aba(ABA_LEITURAS)

leituras.columns = [c.strip() for c in leituras.columns]
leituras["nivel"] = pd.to_numeric(leituras["nivel"], errors="coerce")

# ==========================
# ESTADOS
# ==========================
if "admin" not in st.session_state:
    st.session_state.admin = False
if "confirmar_envio" not in st.session_state:
    st.session_state.confirmar_envio = False
if "enviando" not in st.session_state:
    st.session_state.enviando = False

# ==========================
# SIDEBAR — LOGIN ADMIN
# ==========================
st.sidebar.title("🔐 Administrador")

if not st.session_state.admin:
    senha = st.sidebar.text_input("Senha", type="password")
    if st.sidebar.button("Entrar"):
        if senha == ADMIN_SENHA:
            st.session_state.admin = True
            st.session_state.confirmar_envio = False
            st.rerun()
        else:
            st.sidebar.error("Senha incorreta.")
else:
    if st.sidebar.button("Sair"):
        st.session_state.admin = False
        st.session_state.confirmar_envio = False
        st.rerun()

# ==========================
# PAINEL ADMINISTRADOR
# ==========================
if st.session_state.admin:
    st.title("🛠️ Painel do Administrador")
    base = municipios.merge(rios, on="id_rio")

    registros = []
    registros_vazios = []

    for i, row in base.iterrows():
        c1, c2, c3, c4, c5 = st.columns([3, 3, 2, 2, 2])
        c1.text(row["nome_rio"])
        c2.text(row["nome_municipio"])

        d = c3.date_input("", key=f"d{i}")
        h = c4.time_input("", key=f"h{i}")
        n = c5.number_input("", step=0.1, key=f"n{i}")

        registro = {
            "id_rio": row["id_rio"],
            "id_municipio": row["id_municipio"],
            "data": d.strftime("%Y-%m-%d") if d else "",
            "hora": h.strftime("%H:%M") if h else "",
            "nivel": n if n > 0 else ""
        }

        (registros if n > 0 else registros_vazios).append(registro)

    if st.button("Salvar medições"):
        for r in registros:
            enviar_formulario({
                FORM_FIELDS["id_rio"]: r["id_rio"],
                FORM_FIELDS["id_municipio"]: r["id_municipio"],
                FORM_FIELDS["data"]: r["data"],
                FORM_FIELDS["hora"]: r["hora"],
                FORM_FIELDS["nivel"]: r["nivel"],
            })
        st.success("Medições enviadas!")

    st.divider()

# ==========================
# PAINEL PÚBLICO — USUÁRIO
# ==========================
if not st.session_state.admin:
    st.title("🌊 Monitoramento de Rios")

    # 🔹 RELATÓRIO GERAL
    st.subheader("📄 Relatório Geral de Monitoramento")

    relatorio = montar_relatorio(rios, municipios, leituras)

    styled = relatorio.style.apply(
        lambda row: [
            "", "",
            "",
            cor_medido(row["Penúltima Medição"], row["Cota de Transbordo"]),
            cor_medido(row["Última Medição"], row["Cota de Transbordo"]),
            ""
        ],
        axis=1
    )

    st.dataframe(styled, use_container_width=True)

    st.download_button(
        "📥 Baixar relatório (HTML)",
        data=styled.to_html(),
        file_name="relatorio_monitoramento.html",
        mime="text/html"
    )

    st.markdown("---")

    # 🔹 VISUALIZAÇÃO INDIVIDUAL
    col1, col2 = st.columns(2)
    with col1:
        rio_sel = st.selectbox("Rio", rios["nome_rio"])
        id_rio = rios.loc[rios["nome_rio"] == rio_sel, "id_rio"].iloc[0]

    with col2:
        mun_df = municipios[municipios["id_rio"] == id_rio]
        mun_sel = st.selectbox("Município", mun_df["nome_municipio"])
        mun_row = mun_df[mun_df["nome_municipio"] == mun_sel].iloc[0]

    filtro = leituras[
        (leituras["id_rio"] == id_rio) &
        (leituras["id_municipio"] == mun_row["id_municipio"])
    ]

    if filtro.empty:
        st.warning("Sem registros para este filtro.")
    else:
        filtro = filtro.sort_values(["data", "hora"])
        ultima = filtro.iloc[-1]

        situacao, cor, perc, texto = calcular_situacao(
            ultima["nivel"], mun_row.get("nivel_transbordo")
        )

        st.subheader("📌 Situação Atual")
        st.markdown(
            f"""
            <div style="display:flex; align-items:center; gap:10px;">
                <div style="width:14px;height:14px;border-radius:50%;background:{cor};"></div>
                <strong style="color:{cor}; font-size:18px;">{situacao}</strong>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown(texto)
        st.markdown(f"**Nível:** {ultima['nivel']}")

        if perc is not None and not math.isnan(perc):
            st.markdown(f"**Percentual da cota:** {perc:.1f}%")

        st.subheader("📋 Histórico de Medições")

        fonte = mun_row.get("fonte")
        if isinstance(fonte, str) and fonte.strip():
            st.markdown(f"*Fonte: {fonte}*")

        st.dataframe(
            filtro[["data", "hora", "nivel"]].sort_values(
                ["data", "hora"], ascending=False
            ),
            use_container_width=True
        )

        st.image("logo_redec10.png", width=90)
