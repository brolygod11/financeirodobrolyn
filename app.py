import streamlit as st
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
from google import genai
import firebase_admin
from firebase_admin import credentials, db

st.set_page_config(page_title="Financeiro Sayjins", layout="centered", initial_sidebar_state="collapsed")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0e0e0e; color: #ffffff; }
    div.stButton > button {
        background-color: #ff6600 !important;
        color: #000000 !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: bold !important;
        width: 100%;
        height: 45px;
    }
    div.stButton > button:hover { background-color: #cc5200 !important; }
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
        border-radius: 5px; background-color: #1a1a1a !important; color: white !important;
    }
    </style>
""", unsafe_allow_html=True)

def custom_card(title, value, border_color, text_color):
    st.markdown(f"""
        <div style="background-color: #1a1a1a; padding: 15px; border-radius: 10px; border-left: 6px solid {border_color}; margin-bottom: 10px;">
            <p style="margin: 0; font-size: 13px; color: #a0a0a0; font-weight: bold;">{title}</p>
            <h3 style="margin: 0; font-size: 22px; color: {text_color};">{value}</h3>
        </div>
    """, unsafe_allow_html=True)

# --- Firebase ---
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(dict(st.secrets["firebase_key"]))
        firebase_admin.initialize_app(cred, {'databaseURL': st.secrets["database_url"]})
    except Exception as e:
        st.error("Erro no Firebase. Verifique Secrets.")
        st.stop()

def load_db(): return db.reference('/').get() or {"users": {}}
def save_db(db_main): db.reference('/').set(db_main)
def format_brl(value): return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

if 'db_main' not in st.session_state: st.session_state.db_main = load_db()
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

db_main = st.session_state.db_main

# --- LOGIN ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #ff6600;'>⚡ Financeiro Sayjins</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["Entrar", "Criar Conta"])
    with t1:
        with st.form("l"):
            u = st.text_input("Usuário"); p = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                if u in db_main.get("users", {}) and db_main["users"][u]["password"] == p:
                    st.session_state.logged_in = True; st.session_state.username = u; st.rerun()
                else: st.error("Erro!")
    with t2:
        with st.form("r"):
            nu = st.text_input("Novo Usuário"); np = st.text_input("Nova Senha", type="password")
            if st.form_submit_button("Criar"):
                if nu and np:
                    db_main.setdefault("users", {})[nu] = {"password": np, "data": {"accounts": [], "transactions": [], "goals": [], "fixed_expenses": [], "settings": {"credit_limit": 5000.0}}}
                    save_db(db_main); st.success("Criado!"); st.rerun()
    st.stop()

# --- DADOS ---
u_name = st.session_state.username
u_data = db_main["users"][u_name]["data"]
u_data.setdefault("fixed_expenses", [])
u_data.setdefault("transactions", [])

def get_balance():
    b = sum(a["initial_balance"] for a in u_data.get("accounts", []))
    for t in u_data.get("transactions", []):
        if t.get("status") == "Paid":
            b += t["amount"] if t["type"] == "ENTRADA" else -t["amount"]
    return b

global_balance = get_balance()
today = datetime.date.today()
str_month = today.strftime("%Y-%m")

# --- NAVEGAÇÃO ---
st.markdown(f"<p style='text-align:center;'>Sayjin: <b>{u_name}</b></p>", unsafe_allow_html=True)
tabs = st.tabs(["📊 Painel", "💸 Transf.", "➕ Lançar", "🎯 Metas", "⚙️ Extra"])

# 1. PAINEL
with tabs[0]:
    f_mes = st.text_input("Mês Filtro (YYYY-MM)", value=str_month)
    # Soma "Em Aberto" apenas do mês filtrado
    aberto = sum(t["amount"] for t in u_data["transactions"] if t["type"] == "SAIDA" and t["status"] == "Unpaid" and t["date"].startswith(f_mes))
    
    c1, c2 = st.columns(2)
    with c1: custom_card("SALDO GLOBAL", format_brl(global_balance), "#007BFF", "#3399ff")
    with c2: custom_card(f"ABERTO EM {f_mes}", format_brl(aberto), "#ffc107", "#ffcd39")

    st.markdown("### 📅 Pagos no Mês")
    pagos = [t for t in u_data["transactions"] if t["status"] == "Paid" and t["type"] == "SAIDA" and t["date"].startswith(f_mes)]
    if pagos:
        for t in pagos:
            st.markdown(f"<div style='background-color:#1a1a1a; padding:8px; border-radius:5px; border-left:4px solid #4dd26b; margin-bottom:5px;'>{t['date']} | {t['description']} | {format_brl(t['amount'])}</div>", unsafe_allow_html=True)
    else: st.caption("Nada pago ainda.")

# 2. TRANSF.
with tabs[1]:
    st.write("### Histórico (Leitura)")
    for t in sorted(u_data["transactions"], key=lambda x: x['id'], reverse=True)[:30]:
        cor = "#4dd26b" if t["type"] == "ENTRADA" else "#ff6b7a"
        st.markdown(f"<div style='background-color:#1a1a1a; padding:10px; border-radius:5px; border-left:4px solid {cor}; margin-bottom:5px;'>{t['date']} - {t['description']} - {format_brl(t['amount'])}</div>", unsafe_allow_html=True)

# 3. LANÇAR
with tabs[2]:
    m_man, m_pag, m_fix, m_reem = st.tabs(["Manual", "Contas a Pagar", "Nova Fixa", "Reembolso"])
    
    with m_man:
        op = st.radio("Tipo", ["SAIDA", "ENTRADA"], horizontal=True)
        desc = st.text_input("Descrição ")
        if desc:
            val = st.number_input("Valor", min_value=0.01)
            dat = st.date_input("Data ")
            if st.button("Lançar"):
                u_data["transactions"].append({"id": len(u_data["transactions"])+1, "type": op, "account": u_data["accounts"][0]["name"], "description": desc, "amount": val, "date": dat.strftime("%Y-%m-%d"), "status": "Paid"})
                save_db(db_main); st.rerun()

    with m_pag:
        if not u_data["fixed_expenses"]: st.info("Crie uma categoria em 'Nova Fixa'")
        for fixa in u_data["fixed_expenses"]:
            with st.expander(f"📁 {fixa['name']}"):
                fv = st.number_input("Valor R$", key=f"v_{fixa['id']}")
                fd = st.date_input("Vencimento", key=f"d_{fixa['id']}")
                if st.button("Lançar Mês", key=f"b_{fixa['id']}"):
                    u_data["transactions"].append({
                        "id": len(u_data["transactions"])+1, "type": "SAIDA", "account": u_data["accounts"][0]["name"],
                        "description": f"[Fixo] {fixa['name']}", "amount": fv, "date": fd.strftime("%Y-%m-%d"), "status": "Unpaid"
                    })
                    save_db(db_main); st.success("Lançado em Aberto!"); st.rerun()
                
                # Histórico interno da gaveta
                st.write("---")
                hist = [t for t in u_data["transactions"] if t["description"] == f"[Fixo] {fixa['name']}"]
                for t in sorted(hist, key=lambda x: x['date'], reverse=True):
                    col_a, col_b = st.columns([3,1])
                    status_icon = "🔴" if t["status"] == "Unpaid" else "🟢"
                    col_a.write(f"{status_icon} {t['date']} | {format_brl(t['amount'])}")
                    if t["status"] == "Unpaid":
                        if col_b.button("Pagar", key=f"p_{t['id']}"):
                            t["status"] = "Paid"; save_db(db_main); st.rerun()
                
                if st.button("Deletar Categoria", key=f"del_{fixa['id']}"):
                    u_data["fixed_expenses"] = [f for f in u_data["fixed_expenses"] if f["id"] != fixa["id"]]
                    save_db(db_main); st.rerun()

    with m_fix:
        nf = st.text_input("Nome (Ex: COPASA)")
        if st.button("Criar"):
            u_data["fixed_expenses"].append({"id": len(u_data["fixed_expenses"])+1, "name": nf.upper()})
            save_db(db_main); st.rerun()

    with m_reem:
        if u_data["transactions"]:
            tre = st.selectbox("Selecione", sorted(u_data["transactions"], key=lambda x:x['id'], reverse=True), format_func=lambda x: f"{x['date']} - {x['description']}")
            if st.button("Gerar Reembolso"):
                nt = "ENTRADA" if tre["type"] == "SAIDA" else "SAIDA"
                u_data["transactions"].append({"id": len(u_data["transactions"])+1, "type": nt, "account": tre["account"], "description": f"[REEM] {tre['description']}", "amount": tre["amount"], "date": today.strftime("%Y-%m-%d"), "status": "Paid"})
                save_db(db_main); st.rerun()

# 4. METAS
with tabs[3]:
    st.write("### Metas")
    if st.button("➕ Nova Meta"): st.session_state.nm = True
    if st.session_state.get("nm"):
        with st.form("fm"):
            nn = st.text_input("Nome"); vv = st.number_input("Alvo")
            if st.form_submit_button("Salvar"):
                u_data.setdefault("goals", []).append({"name": nn, "target": vv, "status": "Active"})
                save_db(db_main); st.session_state.nm = False; st.rerun()
    for i, g in enumerate(u_data.get("goals", [])):
        if g.get("status", "Active") == "Active":
            st.write(f"**{g['name']}**")
            st.progress(min(global_balance/g["target"], 1.0) if g["target"] > 0 else 0)
            if st.button("✅ Bateu!", key=f"m_{i}"):
                g["status"] = "Achieved"; save_db(db_main); st.rerun()

# 5. EXTRA
with tabs[4]:
    if st.button("Sair"):
        st.session_state.logged_in = False; st.rerun()
    if st.button("ZERAR TUDO"):
        u_data["transactions"] = []; u_data["goals"] = []; save_db(db_main); st.rerun()
