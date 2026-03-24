import streamlit as st
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
from google import genai
import firebase_admin
from firebase_admin import credentials, db

st.set_page_config(page_title="Financeiro Sayjins", layout="centered", initial_sidebar_state="collapsed")

# --- CSS (Botoes Laranja com Texto Preto) ---
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
    except:
        st.error("Erro no Firebase.")
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
                    db_main.setdefault("users", {})[nu] = {"password": np, "data": {"accounts": [{"id":1, "name":"Principal", "initial_balance":0.0}], "transactions": [], "goals": [], "fixed_expenses": [], "settings": {"credit_limit": 5000.0}}}
                    save_db(db_main); st.success("Criado!"); st.rerun()
    st.stop()

u_name = st.session_state.username
u_data = db_main["users"][u_name]["data"]
u_data.setdefault("fixed_expenses", [])
u_data.setdefault("transactions", [])

# --- SALDO REAL (Ignora CSV) ---
def get_balance():
    b = sum(a.get("initial_balance", 0) for a in u_data.get("accounts", []))
    for t in u_data["transactions"]:
        if t.get("status") == "Paid" and not t.get("ignoreBalance"):
            b += t["amount"] if t["type"] == "ENTRADA" else -t["amount"]
    return b

global_balance = get_balance()
today = datetime.date.today()
str_month = today.strftime("%Y-%m")

# --- NAVEGAÇÃO ---
tabs = st.tabs(["📊 Painel", "💸 Transf.", "➕ Lançar", "🎯 Metas", "⚙️ Sair"])

# 1. PAINEL
with tabs[0]:
    f_mes = st.text_input("Mês Filtro (YYYY-MM)", value=str_month)
    # Soma EM ABERTO: Qualquer SAIDA que esteja Unpaid e no mês do filtro
    aberto = sum(t["amount"] for t in u_data["transactions"] if t.get("status") == "Unpaid" and t.get("type") == "SAIDA" and t.get("date", "").startswith(f_mes))
    
    c1, c2 = st.columns(2)
    with c1: custom_card("SALDO GLOBAL", format_brl(global_balance), "#007BFF", "#3399ff")
    with c2: custom_card(f"ABERTO EM {f_mes}", format_brl(aberto), "#ffc107", "#ffcd39")

    st.markdown("### 📅 Pagos no Mês")
    pagos = [t for t in u_data["transactions"] if t.get("status") == "Paid" and t.get("type") == "SAIDA" and t.get("date", "").startswith(f_mes)]
    for t in pagos:
        st.markdown(f"<div style='background-color:#1a1a1a; padding:8px; border-radius:5px; border-left:4px solid #4dd26b; margin-bottom:5px;'>{t['date']} | {t['description']} | {format_brl(t['amount'])}</div>", unsafe_allow_html=True)

# 2. TRANSF.
with tabs[1]:
    for t in sorted(u_data["transactions"], key=lambda x: x.get('id', 0), reverse=True)[:30]:
        cor = "#4dd26b" if t["type"] == "ENTRADA" else "#ff6b7a"
        st.markdown(f"<div style='background-color:#1a1a1a; padding:8px; border-radius:5px; border-left:4px solid {cor}; margin-bottom:5px;'>{t['date']} | {t['description']} | {format_brl(t['amount'])}</div>", unsafe_allow_html=True)

# 3. LANÇAR
with tabs[2]:
    m_man, m_fix, m_reem = st.tabs(["Manual", "Gavetas (Fixas)", "Reembolso"])
    
    with m_man:
        op = st.radio("Tipo", ["SAIDA", "ENTRADA"], horizontal=True)
        desc = st.text_input("Descrição")
        if desc:
            v = st.number_input("Valor", min_value=0.01)
            d = st.date_input("Data")
            if st.button("Salvar Manual"):
                new_id = max([t.get('id', 0) for t in u_data["transactions"]], default=0) + 1
                u_data["transactions"].append({"id": new_id, "type": op, "description": desc, "amount": v, "date": d.strftime("%Y-%m-%d"), "status": "Paid", "ignoreBalance": False})
                save_db(db_main); st.rerun()

    with m_fix:
        for fixa in u_data["fixed_expenses"]:
            with st.expander(f"📁 {fixa['name']}"):
                colv, cold = st.columns(2)
                fv = colv.number_input("Valor R$", key=f"v_{fixa['id']}")
                fd = cold.date_input("Vencimento", key=f"d_{fixa['id']}")
                if st.button("Lançar Mês", key=f"b_{fixa['id']}"):
                    new_id = max([t.get('id', 0) for t in u_data["transactions"]], default=0) + 1
                    # A tag 'fixed_id' garante que a transação pertença a esta gaveta
                    u_data["transactions"].append({
                        "id": new_id, "type": "SAIDA", "description": f"[Fixo] {fixa['name']}", 
                        "amount": fv, "date": fd.strftime("%Y-%m-%d"), "status": "Unpaid", 
                        "ignoreBalance": False, "fixed_id": fixa['id']
                    })
                    save_db(db_main); st.success("Lançado em Aberto!"); st.rerun()
                
                # Histórico da Gaveta
                st.write("---")
                hist = [t for t in u_data["transactions"] if t.get("fixed_id") == fixa['id']]
                for t in sorted(hist, key=lambda x: x['date'], reverse=True):
                    col_a, col_b = st.columns([3,1])
                    status = "🔴" if t["status"] == "Unpaid" else "🟢"
                    col_a.write(f"{status} {t['date']} | {format_brl(t['amount'])}")
                    if t["status"] == "Unpaid":
                        if col_b.button("Pagar", key=f"p_{t['id']}"):
                            t["status"] = "Paid"; save_db(db_main); st.rerun()
                if st.button("Deletar Categoria", key=f"del_{fixa['id']}"):
                    u_data["fixed_expenses"] = [f for f in u_data["fixed_expenses"] if f["id"] != fixa["id"]]
                    save_db(db_main); st.rerun()

        nf = st.text_input("Nova Categoria (Ex: CEMIG)")
        if st.button("Criar Gaveta"):
            new_id_f = max([f.get('id', 0) for f in u_data["fixed_expenses"]], default=0) + 1
            u_data["fixed_expenses"].append({"id": new_id_f, "name": nf.upper()})
            save_db(db_main); st.rerun()

    with m_reem:
        if u_data["transactions"]:
            tre = st.selectbox("Transação", sorted(u_data["transactions"], key=lambda x:x.get('id', 0), reverse=True), format_func=lambda x: f"{x['date']} - {x['description']}")
            if st.button("Reembolsar"):
                nt = "ENTRADA" if tre["type"] == "SAIDA" else "SAIDA"
                new_id = max([t.get('id', 0) for t in u_data["transactions"]], default=0) + 1
                u_data["transactions"].append({"id": new_id, "type": nt, "description": f"[REEM] {tre['description']}", "amount": tre["amount"], "date": today.strftime("%Y-%m-%d"), "status": "Paid", "ignoreBalance": False})
                save_db(db_main); st.rerun()

# 4. METAS
with tabs[3]:
    if st.button("➕ Nova Meta"): st.session_state.nm = True
    if st.session_state.get("nm"):
        with st.form("fm"):
            nn = st.text_input("Nome"); vv = st.number_input("Alvo")
            if st.form_submit_button("Salvar"):
                u_data.setdefault("goals", []).append({"name": nn, "target": vv, "status": "Active"})
                save_db(db_main); st.session_state.nm = False; st.rerun()
    for i, g in enumerate(u_data.get("goals", [])):
        if g.get("status") == "Active":
            prog = max(0.0, min(global_balance / g["target"], 1.0)) if g["target"] > 0 else 0.0
            st.write(f"**{g['name']}**"); st.progress(prog)
            if st.button("✅ Concluir", key=f"m_{i}"):
                g["status"] = "Achieved"; save_db(db_main); st.rerun()

# 5. EXTRA
with tabs[4]:
    if st.button("Sair"): st.session_state.logged_in = False; st.rerun()
    if st.button("ZERAR DADOS"): u_data["transactions"] = []; u_data["goals"] = []; save_db(db_main); st.rerun()
