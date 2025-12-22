import streamlit.components.v1 as components
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

def gerar_relatorio_usuario(rios, municipios, leituras):
    base = municipios.merge(rios, on="id_rio")
    linhas = []

    for _, row in base.iterrows():
        filtro = leituras[
            (leituras["id_rio"] == row["id_rio"]) &
            (leituras["id_municipio"] == row["id_municipio"])
        ].sort_values(["data", "hora"])

        if filtro.empty:
            continue

        ultima = filtro.iloc[-1]
        penultima = filtro.iloc[-2] if len(filtro) > 1 else None

        situacao, cor, _, _ = calcular_situacao(
            ultima["nivel"], row.get("nivel_transbordo")
        )

        linhas.append({
            "Rio": row["nome_rio"],
            "Município": row["nome_municipio"],
            "Cota de Transbordo": row.get("nivel_transbordo"),
            "Penúltima Medição": f"{penultima['nivel']:.2f}" if penultima is not None else "-",
            "Última Medição": f"{ultima['nivel']:.2f}",
            "Datas": (
                f"{penultima['data']} / {ultima['data']}"
                if penultima is not None else ultima["data"]
            ),
            "Fonte": row.get("fonte"),
            "cor": cor
        })

    return pd.DataFrame(linhas)

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

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        data_padrao = st.date_input("Data padrão", value=None)
    with col2:
        hora_padrao = st.time_input("Hora padrão", value=None)
    with col3:
        if st.button("Replicar"):
            for i in range(len(base)):
                st.session_state[f"d{i}"] = data_padrao
                st.session_state[f"h{i}"] = hora_padrao

    registros = []
    registros_vazios = []

    for i, row in base.iterrows():
        c1, c2, c3, c4, c5 = st.columns([3, 3, 2, 2, 2])

        with c1:
            st.text(row["nome_rio"])
        with c2:
            st.text(row["nome_municipio"])
        with c3:
            d = st.date_input("", value=st.session_state.get(f"d{i}"), key=f"d{i}")
        with c4:
            h = st.time_input("", value=st.session_state.get(f"h{i}"), key=f"h{i}")
        with c5:
            n = st.number_input("", key=f"n{i}", step=0.1)

        registro = {
            "id_rio": row["id_rio"],
            "id_municipio": row["id_municipio"],
            "data": d.strftime("%Y-%m-%d") if d else "",
            "hora": h.strftime("%H:%M") if h else "",
            "nivel": n if n > 0 else ""
        }

        if n <= 0:
            registros_vazios.append(registro)
        else:
            registros.append(registro)

    if st.button("Salvar medições", disabled=st.session_state.enviando):
        if registros_vazios and not st.session_state.confirmar_envio:
            st.warning("Existem medições sem nível preenchido. Deseja salvar mesmo assim?")
            st.session_state.confirmar_envio = True
        else:
            st.session_state.enviando = True
            st.rerun()

    if st.session_state.enviando:
        with st.spinner("Salvando medições, aguarde..."):
            ok = True
            for r in registros + registros_vazios:
                if r["nivel"] == "":
                    continue

                payload = {
                    FORM_FIELDS["id_rio"]: r["id_rio"],
                    FORM_FIELDS["id_municipio"]: r["id_municipio"],
                    FORM_FIELDS["data"]: r["data"],
                    FORM_FIELDS["hora"]: r["hora"],
                    FORM_FIELDS["nivel"]: r["nivel"],
                }

                if not enviar_formulario(payload):
                    ok = False

            st.session_state.enviando = False
            st.session_state.confirmar_envio = False

            if ok:
                st.success("Medições enviadas com sucesso!")
            else:
                st.error("Erro ao enviar algumas medições.")

            st.rerun()

    st.divider()

# ==========================
# PAINEL PÚBLICO — USUÁRIO
# ==========================
if not st.session_state.admin:
    st.title("🌊 Monitoramento de Rios")

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

        # ==========================
        # 📊 GRÁFICO COM LINHA DE TRANBORDO
        # ==========================
        st.subheader("📊 Evolução do Nível do Rio")

        filtro["data_hora"] = pd.to_datetime(filtro["data"] + " " + filtro["hora"])
        filtro = filtro.sort_values("data_hora")

        grafico_nivel = alt.Chart(filtro).mark_line(
            color="#0B5ED7",
            strokeWidth=3
        ).encode(
            x=alt.X("data_hora:T", title="Data / Hora"),
            y=alt.Y("nivel:Q", title="Nível do Rio")
        )

        layers = [grafico_nivel]

        try:
            cota = float(str(mun_row.get("nivel_transbordo")).replace(",", "."))
            if pd.isna(cota):
                cota = None
        except:
            cota = None

        if cota and cota > 0:
            linha_cota = alt.Chart(
                pd.DataFrame({"cota": [cota]})
            ).mark_rule(
                color="#DC3545",
                strokeDash=[6, 4],
                strokeWidth=2
            ).encode(y="cota:Q")
            layers.append(linha_cota)

        st.altair_chart(
            alt.layer(*layers).resolve_scale(y="shared"),
            use_container_width=True
        )

        # ==========================
        # 📋 HISTÓRICO DE MEDIÇÕES
        # ==========================
        st.subheader("📋 Histórico de Medições")
        st.caption(f"Fonte: {mun_row.get('fonte', '—')}")

        historico = filtro.sort_values(["data", "hora"], ascending=False)

        historico_exibicao = historico[["data", "hora", "nivel"]].copy()
        historico_exibicao.columns = ["Data", "Hora", "Nível"]

        def cor_historico(row):
            try:
                nivel = float(row["Nível"])
                cota = float(str(mun_row.get("nivel_transbordo")).replace(",", "."))
            except:
                return ["background-color: #e9ecef"] * len(row)

            if pd.isna(cota) or cota <= 0:
                return ["background-color: #e9ecef"] * len(row)

            perc = (nivel / cota) * 100

            if perc < 85:
                cor = "#d4edda"
            elif perc < 100:
                cor = "#fff3cd"
            elif perc <= 120:
                cor = "#f8d7da"
            else:
                cor = "#e2d6f3"

            return [f"background-color: {cor}"] * len(row)

        styled_historico = (
            historico_exibicao
            .reset_index(drop=True)
            .style
            .apply(cor_historico, axis=1)
            .set_properties(**{
                "text-align": "center",
                "font-size": "13px"
            })
        )

        st.dataframe(
            styled_historico,
            use_container_width=True,
            height=320
        )

        # ==========================
        # 🎨 LEGENDA DE SITUAÇÃO HIDROLÓGICA
        # ==========================
        components.html(
            """
            <div style="
                display:flex;
                gap:18px;
                flex-wrap:wrap;
                align-items:center;
                margin-bottom:12px;
                font-size:13px;
                font-family: Arial, sans-serif;
            ">

                <div style="display:flex; align-items:center; gap:6px;">
                    <span style="width:14px; height:14px; background:#d4edda; border-radius:3px;"></span>
                    <strong>Normal</strong> (&lt; 85%)
                </div>

                <div style="display:flex; align-items:center; gap:6px;">
                    <span style="width:14px; height:14px; background:#fff3cd; border-radius:3px;"></span>
                    <strong>Alerta</strong> (85–99%)
                </div>

                <div style="display:flex; align-items:center; gap:6px;">
                    <span style="width:14px; height:14px; background:#f8d7da; border-radius:3px;"></span>
                    <strong>Transbordo</strong> (100–120%)
                </div>

                <div style="display:flex; align-items:center; gap:6px;">
                    <span style="width:14px; height:14px; background:#e2d6f3; border-radius:3px;"></span>
                    <strong>Risco Hidrológico Extremo</strong> (&gt; 120%)
                </div>

                <div style="display:flex; align-items:center; gap:6px;">
                    <span style="width:14px; height:14px; background:#e9ecef; border-radius:3px;"></span>
                    <strong>Sem cota definida</strong>
                </div>

            </div>
            """,
            height=70
        )


# ==========================
# 📄 RELATÓRIO GERAL
# ==========================
st.subheader("📄 Relatório Geral de Monitoramento")

rel = gerar_relatorio_usuario(rios, municipios, leituras)

if not rel.empty:
    rel_exibicao = rel.drop(columns=["cor"])

    # 🔧 AJUSTE 1 — OCULTAR REPETIÇÃO DO NOME DO RIO
    rel_exibicao["Rio"] = rel_exibicao["Rio"].where(
        rel_exibicao["Rio"].ne(rel_exibicao["Rio"].shift())
    )

    # 🔧 AJUSTE 1.1 — REMOVER 'nan' VISUAL
    rel_exibicao["Rio"] = rel_exibicao["Rio"].fillna("")

    # 🔧 AJUSTE 1.2 — COTA SEM 'nan'
    rel_exibicao["Cota de Transbordo"] = rel_exibicao["Cota de Transbordo"].fillna("-")

    def cor_linha_fix(row):
        cor = rel.loc[row.name, "cor"]
        cores = {
            "green": "#d4edda",
            "orange": "#fff3cd",
            "red": "#f8d7da",
            "purple": "#e2d6f3"
        }
        return [f"background-color: {cores.get(cor, '#ffffff')}"] * len(rel_exibicao.columns)

    # 🔧 AJUSTE 2 — ESTILO PROFISSIONAL
    styled = (
        rel_exibicao.style
        .apply(cor_linha_fix, axis=1)
        .set_properties(**{
            "text-align": "center",
            "font-size": "13px",
            "border": "1px solid #ccc",
            "padding": "6px"
        })
        .set_properties(subset=["Rio", "Município"], **{
            "text-align": "left",
            "font-weight": "600"
        })
        .set_table_styles([
            {
                "selector": "th",
                "props": [
                    ("background-color", "#0B5ED7"),
                    ("color", "white"),
                    ("font-size", "14px"),
                    ("text-align", "center"),
                    ("padding", "8px")
                ]
            },
            {
                "selector": "table",
                "props": [
                    ("border-collapse", "collapse"),
                    ("width", "100%")
                ]
            }
        ])
    )

    st.components.v1.html(
        styled.to_html(),
        height=420,
        scrolling=True
    )


# ==========================
# RODAPÉ (RESTAURADO)
# ==========================
st.markdown("---")

col_logo, col_texto = st.columns([1, 4])

with col_logo:
    st.image("logo_redec10.png", width=90)

with col_texto:
    st.markdown(
        """
        <div style="font-size:13px; color:#555; line-height:1.4;">
            Criado e desenvolvido por:<br>
            CB BM Gustavo Siqueira <strong>Gaia</strong><br>
            REDEC 10 – Norte
        </div>
        """,
        unsafe_allow_html=True
    )

