import streamlit.components.v1 as components
import streamlit as st
import pandas as pd
import requests
import altair as alt
import math
from datetime import date, time
from bs4 import BeautifulSoup

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

import urllib3
from io import StringIO

# Desativa avisos de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def buscar_inea(url_estacao):
    url_csv = url_estacao.replace(".html", ".csv")
    try:
        # Busca o conteúdo bruto do CSV
        response = requests.get(url_csv, verify=False, timeout=15)
        if response.status_code != 200:
            return None

        conteudo = response.text
        
        # Lógica para encontrar onde a tabela começa (evita o erro Out-of-bounds)
        linhas = conteudo.splitlines()
        linha_cabecalho = 0
        for i, linha in enumerate(linhas):
            if "Data" in linha and "Nivel" in linha:
                linha_cabecalho = i
                break
        
        # Lê o CSV a partir da linha correta encontrada
        df_inea = pd.read_csv(StringIO(conteudo), sep=';', encoding='latin-1', skiprows=linha_cabecalho)
        
        if df_inea.empty:
            return None
        
        # Limpa os nomes das colunas (remove espaços extras)
        df_inea.columns = [c.strip() for c in df_inea.columns]
        
        # Pega a primeira linha de dados
        ultima_leitura = df_inea.iloc[0]
        
        # Tenta pegar pelos nomes das colunas para ser mais preciso
        data_hora_texto = str(ultima_leitura["Data"])
        # Remove unidades como "(m)" se existirem e converte para float
        nivel_bruto = str(ultima_leitura.iloc[1]).split()[0]
        nivel = float(nivel_bruto.replace(',', '.'))
        
        dt_obj = pd.to_datetime(data_hora_texto, dayfirst=True)
        
        return {
            "nivel": nivel,
            "data": dt_obj.date(),
            "hora": dt_obj.time()
        }
    except Exception as e:
        st.error(f"Erro técnico na captura: {e}")
        return None
def calcular_situacao(nivel, cota):
    try:
        nivel = float(str(nivel).replace(",", "."))
        cota = float(str(cota).replace(",", "."))
    except:
        return "Sem cota definida", "gray", None, "Dados insuficientes."

    if pd.isna(cota) or cota <= 0:
        return "Sem cota definida", "gray", None, "Cota de transbordo não definida."

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
        filtro = leituras[(leituras["id_rio"] == row["id_rio"]) & (leituras["id_municipio"] == row["id_municipio"])].sort_values(["data", "hora"])
        if filtro.empty: 
            continue
        ultima = filtro.iloc[-1]
        penultima = filtro.iloc[-2] if len(filtro) > 1 else None
        situacao, cor, _, _ = calcular_situacao(ultima["nivel"], row.get("nivel_transbordo"))
        linhas.append({
            "Rio": row["nome_rio"],
            "Município": row["nome_municipio"],
            "Cota de Transbordo": row.get("nivel_transbordo"),
            "Penúltima Medição": f"{penultima['nivel']:.2f}" if penultima is not None else "-",
            "Última Medição": f"{ultima['nivel']:.2f}",
            "Datas": f"{penultima['data']} / {ultima['data']}" if penultima is not None else ultima["data"],
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
if "admin" not in st.session_state: st.session_state.admin = False
if "confirmar_envio" not in st.session_state: st.session_state.confirmar_envio = False
if "enviando" not in st.session_state: st.session_state.enviando = False

# ==========================
# SIDEBAR
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

    # CONTROLES E CAPTURA AUTOMÁTICA
    col_auto, col_man1, col_man2, col_man3 = st.columns([2, 1, 1, 1])
    
    with col_auto:
        st.write("🛰️ **Captura INEA**")
        c_btn1, c_btn2 = st.columns(2)
        
        with c_btn1:
            if st.button("🔄 Lagoa de Cima"):
                url = "https://alertadecheias.inea.rj.gov.br/alertadecheias/214110320.html"
                dados = buscar_inea(url)
                if dados:
                    achou = False
                    for i, row in base.iterrows():
                        if "lagoa de cima" in str(row["nome_rio"]).lower():
                            st.session_state[f"d{i}"] = dados["data"]
                            st.session_state[f"h{i}"] = dados["hora"]
                            st.session_state[f"n{i}"] = dados["nivel"]
                            achou = True
                    if achou: st.success("Lagoa de Cima atualizada!"); st.rerun()
                    else: st.warning("Rio 'Lagoa de Cima' não encontrado na lista.")
                else: st.error("Erro ao conectar (Lagoa de Cima).")

        with c_btn2:
            if st.button("🔄 Rio Pomba"):
                url = "https://alertadecheias.inea.rj.gov.br/alertadecheias/21304212020.html"
                dados = buscar_inea(url)
                if dados:
                    achou = False
                    for i, row in base.iterrows():
                        nome_rio = str(row["nome_rio"]).lower()
                        if "pomba" in nome_rio or "pádua" in nome_rio:
                            st.session_state[f"d{i}"] = dados["data"]
                            st.session_state[f"h{i}"] = dados["hora"]
                            st.session_state[f"n{i}"] = dados["nivel"]
                            achou = True
                    if achou: st.success("Rio Pomba atualizado!"); st.rerun()
                    else: st.warning("Rio Pomba não encontrado na lista.")
                else: st.error("Erro ao conectar (Rio Pomba).")

    with col_man1: 
        data_padrao = st.date_input("Data padrão", value=None)
    with col_man2: 
        hora_padrao = st.time_input("Hora padrão", value=None)
    with col_man3:
        if st.button("Replicar Manual"):
            for i in range(len(base)):
                st.session_state[f"d{i}"] = data_padrao
                st.session_state[f"h{i}"] = hora_padrao

    # FORMULÁRIO DE MEDIÇÕES
    registros = []
    registros_vazios = []

    for i, row in base.iterrows():
        c1, c2, c3, c4, c5 = st.columns([3, 3, 2, 2, 2])
        with c1: st.text(row["nome_rio"])
        with c2: st.text(row["nome_municipio"])
        with c3: 
            # Corrigido: label="Data" evita o erro de acessibilidade
            d = st.date_input("Data", value=st.session_state.get(f"d{i}"), key=f"d{i}", label_visibility="collapsed")
        with c4: 
            # Corrigido: label="Hora" evita o erro de acessibilidade
            h = st.time_input("Hora", value=st.session_state.get(f"h{i}"), key=f"h{i}", label_visibility="collapsed")
        with c5: 
            # Corrigido: label="Nível" evita o erro de acessibilidade
            n = st.number_input("Nível", key=f"n{i}", step=0.1, min_value=0.0, label_visibility="collapsed")

        registro = {
            "id_rio": row["id_rio"],
            "id_municipio": row["id_municipio"],
            "data": d.strftime("%Y-%m-%d") if d else "",
            "hora": h.strftime("%H:%M") if h else "",
            "nivel": n if n > 0 else ""
        }
        if n <= 0: registros_vazios.append(registro)
        else: registros.append(registro)

    st.divider()
    # (Restante do código de salvar...)
    if st.button("💾 Salvar medições", disabled=st.session_state.enviando):
        if registros_vazios and not st.session_state.confirmar_envio:
            st.session_state.confirmar_envio = True
            st.rerun()
        else:
            st.session_state.enviando = True
            st.rerun()

    if st.session_state.confirmar_envio and not st.session_state.enviando:
        st.warning(f"⚠️ Existem {len(registros_vazios)} medições vazias. Salvar assim mesmo?")
        c_conf, c_canc = st.columns(2)
        if c_conf.button("✅ Confirmar"):
            st.session_state.enviando = True
            st.session_state.confirmar_envio = False
            st.rerun()
        if c_canc.button("❌ Cancelar"):
            st.session_state.confirmar_envio = False
            st.rerun()

    if st.session_state.enviando:
        with st.spinner("Salvando..."):
            ok = True
            for r in registros + registros_vazios:
                if r["nivel"] == "": continue
                payload = {FORM_FIELDS["id_rio"]: r["id_rio"], FORM_FIELDS["id_municipio"]: r["id_municipio"], FORM_FIELDS["data"]: r["data"], FORM_FIELDS["hora"]: r["hora"], FORM_FIELDS["nivel"]: r["nivel"]}
                if not enviar_formulario(payload): ok = False
            st.session_state.enviando = False
            if ok: st.success("Sucesso!")
            else: st.error("Erro no envio.")
            st.rerun()
    st.stop()

# ==========================
# PAINEL PÚBLICO
# ==========================
st.title("🌊 Monitoramento de Rios")
col1, col2 = st.columns(2)
with col1:
    rio_sel = st.selectbox("Rio", rios["nome_rio"])
    id_rio = rios.loc[rios["nome_rio"] == rio_sel, "id_rio"].iloc[0]
with col2:
    mun_df = municipios[municipios["id_rio"] == id_rio]
    mun_sel = st.selectbox("Município", mun_df["nome_municipio"])
    mun_row = mun_df[mun_df["nome_municipio"] == mun_sel].iloc[0]

filtro = leituras[(leituras["id_rio"] == id_rio) & (leituras["id_municipio"] == mun_row["id_municipio"])]

if filtro.empty:
    st.warning("Sem registros para este filtro.")
else:
    filtro = filtro.sort_values(["data", "hora"])
    ultima = filtro.iloc[-1]
    situacao, cor, perc, texto = calcular_situacao(ultima["nivel"], mun_row.get("nivel_transbordo"))

    st.subheader("📌 Situação Atual")
    st.markdown(f'<div style="display:flex; align-items:center; gap:10px;"><div style="width:14px;height:14px;border-radius:50%;background:{cor};"></div><strong style="color:{cor}; font-size:18px;">{situacao}</strong></div>', unsafe_allow_html=True)
    st.markdown(texto)
    st.markdown(f"**Nível:** {ultima['nivel']}")
    if perc is not None and not math.isnan(perc):
        st.markdown(f"**Percentual da cota:** {perc:.1f}%")

    # Gráfico
    st.subheader("📊 Evolução do Nível do Rio")
    filtro["data_hora"] = pd.to_datetime(filtro["data"] + " " + filtro["hora"])
    grafico_nivel = alt.Chart(filtro).mark_line(color="#0B5ED7", strokeWidth=3).encode(x=alt.X("data_hora:T", title="Data / Hora"), y=alt.Y("nivel:Q", title="Nível do Rio"))
    
    layers = [grafico_nivel]
    try:
        cota = float(str(mun_row.get("nivel_transbordo")).replace(",", "."))
        if cota > 0:
            linha_cota = alt.Chart(pd.DataFrame({"cota": [cota]})).mark_rule(color="#DC3545", strokeDash=[6, 4]).encode(y="cota:Q")
            layers.append(linha_cota)
    except: pass
    st.altair_chart(alt.layer(*layers).resolve_scale(y="shared"), use_container_width=True)

    # Histórico e Relatório Geral (Omitidos aqui por brevidade, mas mantidos no seu original)
    st.subheader("📄 Relatório Geral de Monitoramento")
    rel = gerar_relatorio_usuario(rios, municipios, leituras)
    if not rel.empty:
        st.dataframe(rel.drop(columns=["cor"]), use_container_width=True)

# ==========================
# RODAPÉ
# ==========================
st.markdown("---")
c_logo, c_txt = st.columns([1, 4])
with c_logo: st.image("logo_redec10.png", width=90)
with c_txt: st.markdown('<div style="font-size:13px; color:#555;">Criado por: CB BM Gustavo Siqueira <strong>Gaia</strong><br>REDEC 10 – Norte</div>', unsafe_allow_html=True)
