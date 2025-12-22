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
FORM_URL = st.secrets["FORM_URL"]
ADMIN_SENHA = st.secrets["ADMIN_SENHA"]

ABA_RIOS = "rios"
ABA_MUNICIPIOS = "municipios"
ABA_LEITURAS = "leituras"

FORM_FIELDS = {
    "id_rio": "entry.2045951420",
    "id_municipio": "entry.143224654",
    "data": "entry.2019012807",
    "hora": "entry.795474044",
    "nivel": "entry.718891381",
}

# ==========================
# FUNÇÕES AUXILIARES
# ==========================
def carregar_aba(nome):
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={nome}"
    return pd.read_csv(url)

def calcular_situacao(nivel, cota):
    try:
        nivel = float(str(nivel).replace(",", "."))
        cota = float(str(cota).replace(",", ".")) if cota else None
    except:
        return "Leitura inválida", "gray", None, "Leitura inválida."

    if not cota or pd.isna(cota) or cota <= 0:
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
# RELATÓRIO GERAL
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
            "Cota": row.get("nivel_transbordo"),
            "Penúltima": penultima,
            "Última": ultima,
            "Fonte": row.get("fonte")
        })

    return pd.DataFrame(registros)

def cor_nivel(valor, cota):
    if pd.isna(valor) or pd.isna(cota):
        return "background-color: #f0f0f0"

    _, cor, _, _ = calcular_situacao(valor, cota)

    cores = {
        "green": "#d4edda",
        "orange": "#fff3cd",
        "red": "#f8d7da",
        "purple": "#e2d6f3"
    }

    return f"background-color: {cores.get(cor, '#f0f0f0')}"

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
            st.rerun()
        else:
            st.sidebar.error("Senha incorreta.")
else:
    if st.sidebar.button("Sair"):
        st.session_state.admin = False
        st.rerun()

# ==========================
# PAINEL ADMINISTRADOR
# ==========================
if st.session_state.admin:
    st.title("🛠️ Painel do Administrador")

    base = municipios.merge(rios, on="id_rio")

    registros, registros_vazios = [], []

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
            payload = {
                FORM_FIELDS["id_rio"]: r["id_rio"],
                FORM_FIELDS["id_municipio"]: r["id_municipio"],
                FORM_FIELDS["data"]: r["data"],
                FORM_FIELDS["hora"]: r["hora"],
                FORM_FIELDS["nivel"]: r["nivel"],
            }
            enviar_formulario(payload)
        st.success("Medições enviadas!")

    st.divider()

    st.subheader("📄 Relatório Geral de Monitoramento")

    relatorio = montar_relatorio(rios, municipios, leituras)

    styled = relatorio.style.apply(
        lambda row: [
            "", "", "",
            cor_nivel(row["Penúltima"], row["Cota"]),
            cor_nivel(row["Última"], row["Cota"]),
            ""
        ],
        axis=1
    )

    st.dataframe(styled, use_container_width=True)

    html = styled.to_html()
    st.download_button(
        "📥 Baixar relatório (HTML)",
        data=html,
        file_name="relatorio_monitoramento.html",
        mime="text/html"
    )

# ==========================
# PAINEL PÚBLICO
# ==========================
if not st.session_state.admin:
    st.title("🌊 Monitoramento de Rios")

    rio_sel = st.selectbox("Rio", rios["nome_rio"])
    id_rio = rios.loc[rios["nome_rio"] == rio_sel, "id_rio"].iloc[0]

    mun_df = municipios[municipios["id_rio"] == id_rio]
    mun_sel = st.selectbox("Município", mun_df["nome_municipio"])
    mun_row = mun_df[mun_df["nome_municipio"] == mun_sel].iloc[0]

    filtro = leituras[
        (leituras["id_rio"] == id_rio) &
        (leituras["id_municipio"] == mun_row["id_municipio"])
    ].sort_values(["data", "hora"])

    if filtro.empty:
        st.warning("Sem registros.")
    else:
        ultima = filtro.iloc[-1]
        situacao, cor, perc, texto = calcular_situacao(
            ultima["nivel"], mun_row.get("nivel_transbordo")
        )

        st.subheader("📌 Situação Atual")
        st.markdown(f"**{situacao}** — {texto}")
        st.markdown(f"**Nível:** {ultima['nivel']}")

        if perc:
            st.markdown(f"**Percentual da cota:** {perc:.1f}%")

        st.subheader("📋 Histórico")
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
