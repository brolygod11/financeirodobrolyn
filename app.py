import streamlit as st
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
from google import genai
import firebase_admin
from firebase_admin import credentials, db

st.set_page_config(page_title="Financeiro Sayjins", layout="centered", initial_sidebar_state="collapsed")

# --- CUSTOM CSS (Tema Dark & Botões Laranja com Texto Preto) ---
st.markdown("""
    <style>
    .stApp { background-color: #0e0e0e; color: #ffffff; }
    
    /* Estilização Global de Botões - Texto Preto Garantido */
    div.stButton > button {
        background-color: #ff6600 !important;
        color: #000000 !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: bold !important;
        width: 100%;
        height: 45px;
    }
    
    div.stButton > button:hover {
        background-color: #cc5200 !important;
        color: #000000 !important;
    }

    /* Ajuste para inputs e selects */
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
        border-radius: 5px;
        background-color: #1a1a1a !important;
        color: white !important;
    }
    
    /* Cor das Tabs */
    button[data-baseweb="tab"] { color: white !important; }
    button[data-baseweb="tab"][aria-selected="true"] { color: #ff6600 !important; border-bottom-color: #ff6600 !important; }
    </style>
""", unsafe_allow_html=True)

def custom_card(title, value, border_color, text_color):
    st.markdown(f"""
        <div style="background-color: #1a1a1a; padding: 15px; border-radius: 10px; border-left: 6px solid {border_color}; margin-bottom: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.5);">
            <p style="margin: 0; font-size: 13px; color: #a0a0a0; font-weight: bold;">{title}</p>
            <h3 style="margin: 0; font-size: 22px; color: {text_color};">{value}</h3>
        </div>
    """, unsafe_allow_html=True)

# --- Sistema de Banco de Dados Cloud (Firebase) ---
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(dict(st.secrets["firebase_key"]))
        firebase_admin.initialize_app(cred, {'databaseURL': st.secrets["database_url"]})
    except Exception as e:
        st.error("Erro ao conectar com o Firebase. Verifique seus Secrets.")
        st.stop()

def load_db(): return db.reference('/').get() or {"users": {}}
def save_db(db_main): db.reference('/').set(db_main)
def format_brl(value): return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

if 'db_main' not in st.session_state: st.session_state.db_main = load_db()
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

db_main = st.session_state.db_main

# --- TELA DE LOGIN ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #ff6600;'>⚡ Financeiro Sayjins</h1>", unsafe_allow_html=True)
    tab_login, tab_register = st.tabs(["Entrar", "Criar Conta"])
    with tab_login:
        with st.form("login_form"):
            user_login = st.text_input("Usuário")
            pass_login = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar no Sistema"):
                if user_login in db_main.get("users", {}) and db_main["users"][user_login]["password"] == pass_login:
                    st.session_state.logged_in = True
                    st.session_state.username = user_login
                    st.rerun()
                else: st.error("Usuário ou senha incorretos!")
    with tab_register:
        with st.form("register_form"):
            new_user = st.text_input("Escolha um Usuário")
            new_pass = st.text_input("Crie uma Senha", type="password")
            if st.form_submit_button("Criar Minha Conta"):
                if not new_user or not new_pass: st.warning("Preencha usuário e senha!")
                elif new_user in db_main.get("users", {}): st.error("Usuário já existe!")
                else:
                    if "users" not in db_main: db_main["users"] = {}
                    db_main["users"][new_user] = {
                        "password": new_pass,
                        "data": {"accounts": [], "transactions": [], "goals": [], "fixed_expenses": [], "settings": {"credit_limit": 5000.0}}
                    }
                    save_db(db_main)
                    st.success("Conta criada! Vá na aba 'Entrar'.")
    st.stop()

# --- CARREGA DADOS DO USUÁRIO ---
username = st.session_state.username
user_data = db_main["users"][username]["data"]
if "fixed_expenses" not in user_data: user_data["fixed_expenses"] = []

# --- LÓGICA DE NEGÓCIOS ---
def calculate_real_balance():
    balance = sum(a["initial_balance"] for a in user_data["accounts"])
    for t in user_data.get("transactions", []):
        if t["status"] == "Paid" and not t.get("ignoreBalance", False):
            balance += t["amount"] if t["type"] in ["Income", "ENTRADA"] else -t["amount"]
    return balance

global_balance = calculate_real_balance()
today = datetime.date.today()
str_today = today.strftime("%Y-%m-%d")
str_month = today.strftime("%Y-%m")

# Totais para Painel
totals = {"ENTRADA": {"dia": 0, "sem": 0, "mes": 0, "ano": 0, "all": 0}, "SAIDA": {"dia": 0, "sem": 0, "mes": 0, "ano": 0, "all": 0}}
for t in user_data.get("transactions", []):
    amt = t["amount"]
    t_type = "ENTRADA" if t["type"] in ["Income", "ENTRADA"] else "SAIDA"
    if t_type == "SAIDA" or (t_type == "ENTRADA" and t["status"] == "Paid"):
        totals[t_type]["all"] += amt
        if t["date"] == str_today: totals[t_type]["dia"] += amt
        if t["date"].startswith(str_month): totals[t_type]["mes"] += amt

# Sobra média para previsão de metas
net_savings = totals["ENTRADA"]["all"] - sum(t["amount"] for t in user_data.get("transactions", []) if t["type"] == "SAIDA" and t["status"] == "Paid")
avg_monthly_savings = max(0, net_savings / max(1, (today.year - 2024)*12 + today.month))

# --- NAVEGAÇÃO ---
st.markdown("<h3 style='text-align: center; color: #ff6600;'>Financeiro Sayjins</h3>", unsafe_allow_html=True)
tabs = st.tabs(["📊 Painel", "💸 Transf.", "➕ Lançar", "🎯 Metas", "⚙️ Extra"])

# 1. PAINEL
with tabs[0]:
    filtro_mes = st.text_input("Mês de Referência (YYYY-MM)", value=str_month)
    contas_aberto = sum(t["amount"] for t in user_data.get("transactions", []) if t["type"] == "SAIDA" and t["status"] == "Unpaid" and t["date"].startswith(filtro_mes))
    
    c1, c2 = st.columns(2)
    with c1: custom_card("SALDO GLOBAL", format_brl(global_balance), "#007BFF", "#3399ff")
    with c2: custom_card(f"ABERTO ({filtro_mes})", format_brl(contas_aberto), "#ffc107", "#ffcd39")

    with st.expander("📅 Resumo por Período", expanded=True):
        col_e, col_s = st.columns(2)
        col_e.markdown("<p style='color:#4dd26b; font-weight:bold;'>🟩 ENTRADAS</p>", unsafe_allow_html=True)
        col_e.write(f"Hoje: {format_brl(totals['ENTRADA']['dia'])}")
        col_e.write(f"Mês: {format_brl(totals['ENTRADA']['mes'])}")
        col_e.write(f"Total: {format_brl(totals['ENTRADA']['all'])}")
        
        col_s.markdown("<p style='color:#ff6b7a; font-weight:bold;'>🟥 SAÍDAS</p>", unsafe_allow_html=True)
        col_s.write(f"Hoje: {format_brl(totals['SAIDA']['dia'])}")
        col_s.write(f"Mês: {format_brl(totals['SAIDA']['mes'])}")
        col_s.write(f"Total: {format_brl(totals['SAIDA']['all'])}")

# 2. HISTÓRICO (APENAS LEITURA)
with tabs[1]:
    st.markdown("### Histórico de Movimentações")
    all_t = sorted(user_data.get("transactions", []), key=lambda x: x["id"], reverse=True)
    for t in all_t[:50]:
        is_income = t["type"] in ["Income", "ENTRADA"]
        color = "#4dd26b" if is_income else "#ff6b7a"
        st.markdown(f"<div style='background-color:#1a1a1a; padding:10px; border-radius:8px; border-left:4px solid {color}; margin-bottom:5px;'><p style='margin:0; font-size:11px; color:gray;'>{t['date']} | ID: {t['id']}</p><div style='display:flex; justify-content:space-between;'><b>{t['description']}</b><b style='color:{color};'>{format_brl(t['amount'])}</b></div></div>", unsafe_allow_html=True)

# 3. LANÇAR
with tabs[2]:
    m_manual, m_pagar, m_fixa, m_reembolso = st.tabs(["Manual", "Contas a Pagar", "Nova Fixa", "Reembolso"])
    
    with m_manual:
        t_op = st.radio("Operação", ["SAIDA", "ENTRADA"], horizontal=True)
        t_acc = st.selectbox("Conta", [a["name"] for a in user_data["accounts"]])
        t_desc = st.text_input("Descrição ")
        if t_desc:
            t_val = st.number_input("Valor R$", min_value=0.01)
            t_method = st.selectbox("Método", ["PIX", "Débito", "Crédito"] if t_op == "SAIDA" else ["Recebimento"])
            
            if t_method == "Crédito":
                t_date = st.date_input("Vencimento 1ª Parcela")
                t_inst = st.number_input("Parcelas", min_value=1, value=1)
            else:
                t_date = st.date_input("Data")
                t_inst = 1
            
            t_status = st.selectbox("Status ", ["Paid", "Unpaid"], format_func=lambda x: "Efetivado" if x == "Paid" else "Pendente")
            
            if st.button("🚀 Confirmar Lançamento"):
                base_date = t_date
                for i in range(t_inst):
                    desc_f = f"{t_desc} ({i+1}/{t_inst})" if t_inst > 1 else t_desc
                    user_data.setdefault("transactions", []).append({
                        "id": len(user_data["transactions"]) + 1, "type": t_op, "account": t_acc, 
                        "description": f"[{t_method}] {desc_f}", "amount": t_val, "date": base_date.strftime("%Y-%m-%d"), "status": t_status
                    })
                    base_date += relativedelta(months=1)
                save_db(db_main); st.success("Lançado!"); st.rerun()

    with m_pagar:
        for fixa in user_data.get("fixed_expenses", []):
            with st.expander(f"📁 {fixa['name']}"):
                f_v = st.number_input("Valor", key=f"v_{fixa['id']}")
                f_d = st.date_input("Vencimento", key=f"d_{fixa['id']}")
                if st.button("Lançar Mês", key=f"b_{fixa['id']}"):
                    user_data.setdefault("transactions", []).append({
                        "id": len(user_data["transactions"]) + 1, "type": "SAIDA", "account": user_data["accounts"][0]["name"],
                        "description": f"[Fixo] {fixa['name']}", "amount": f_v, "date": f_d.strftime("%Y-%m-%d"), "status": "Unpaid"
                    })
                    save_db(db_main); st.rerun()
                if st.button("🗑️ Deletar Categoria", key=f"del_{fixa['id']}"):
                    user_data["fixed_expenses"] = [f for f in user_data["fixed_expenses"] if f["id"] != fixa["id"]]
                    save_db(db_main); st.rerun()

    with m_fixa:
        new_f = st.text_input("Nome da Nova Despesa Fixa")
        if st.button("Criar Categoria"):
            user_data.setdefault("fixed_expenses", []).append({"id": len(user_data.get("fixed_expenses", []))+1, "name": new_f.upper()})
            save_db(db_main); st.rerun()

    with m_reembolso:
        if user_data.get("transactions"):
            t_re = st.selectbox("Selecione para Reembolsar", sorted(user_data["transactions"], key=lambda x: x['id'], reverse=True), format_func=lambda x: f"{x['date']} - {x['description']}")
            if st.button("🔄 Gerar Reembolso"):
                new_type = "ENTRADA" if t_re["type"] == "SAIDA" else "SAIDA"
                user_data["transactions"].append({
                    "id": len(user_data["transactions"]) + 1, "type": new_type, "account": t_re["account"],
                    "description": f"[REEMBOLSO] {t_re['description']}", "amount": t_re["amount"], "date": str_today, "status": "Paid"
                })
                save_db(db_main); st.rerun()

# 4. METAS
with tabs[3]:
    st.markdown("### Metas")
    active_goals = [g for g in user_data.get("goals", []) if g.get("status", "Active") == "Active"]
    total_val = sum(g["target"] for g in active_goals)
    custom_card("TOTAL DAS METAS", format_brl(total_val), "#9b59b6", "#c39bd3")

    with st.expander("➕ Nova Meta"):
        n_m = st.text_input("Objetivo"); v_m = st.number_input("Valor Alvo")
        if st.button("Salvar Meta"):
            user_data.setdefault("goals", []).append({"name": n_m, "target": v_m, "status": "Active"})
            save_db(db_main); st.rerun()
                
    for i, g in enumerate(user_data.get("goals", [])):
        # O .get("status", "Active") resolve o erro de chave antiga
        if g.get("status", "Active") == "Active":
            progress = min(global_balance/g["target"], 1.0) if g["target"] > 0 else 0
            st.write(f"**{g['name']}**")
            st.progress(progress)
            st.caption(f"{format_brl(global_balance)} / {format_brl(g['target'])}")
            if avg_monthly_savings > 0 and global_balance < g["target"]:
                st.caption(f"⏱️ Previsão: ~{int((g['target']-global_balance)/avg_monthly_savings)+1} meses")
            if st.button("✅ Concluir", key=f"meta_{i}"):
                g["status"] = "Achieved"; save_db(db_main); st.rerun()
            st.markdown("---")

# 5. EXTRA
with tabs[4]:
    sub_ai, sub_config = st.tabs(["🧠 IA Advisor", "⚙️ Config"])
    with sub_ai:
        api_key = st.text_input("Chave Gemini", type="password")
        if api_key and st.button("Pedir Conselhos"):
            client = genai.Client(api_key=api_key)
            st.write(client.models.generate_content(model='gemini-1.5-pro', contents=f"Saldo: {global_balance}. Metas: {[g['name'] for g in active_goals]}").text)
    with sub_config:
        st.warning("Zona de Perigo")
        if st.button("Zerar Meu Banco de Dados"):
            user_data["transactions"] = []; user_data["goals"] = []; save_db(db_main); st.rerun()
