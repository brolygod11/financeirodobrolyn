import streamlit as st
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
from google import genai
import firebase_admin
from firebase_admin import credentials, db

# Configuração 9:16 (Centered)
st.set_page_config(page_title="Financeiro Sayjins", layout="centered", initial_sidebar_state="collapsed")

# --- CUSTOM CSS (Laranja Sayjin, Fundo Preto, Texto de Botão Preto) ---
st.markdown("""
    <style>
    .stApp { background-color: #0e0e0e; color: #ffffff; }
    
    /* Botões: Fundo Laranja, Texto Preto */
    div.stButton > button {
        background-color: #ff6600 !important;
        color: #000000 !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: bold !important;
        width: 100%;
        height: 45px;
    }
    div.stButton > button:hover { background-color: #cc5200 !important; color: #000000 !important; }
    
    /* Inputs e Selects */
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
        border-radius: 5px; background-color: #1a1a1a !important; color: white !important;
    }
    
    /* Tabs */
    button[data-baseweb="tab"] { color: white !important; }
    button[data-baseweb="tab"][aria-selected="true"] { color: #ff6600 !important; border-bottom-color: #ff6600 !important; }
    </style>
""", unsafe_allow_html=True)

def custom_card(title, value, border_color, text_color):
    st.markdown(f"""
        <div style="background-color: #1a1a1a; padding: 15px; border-radius: 10px; border-left: 6px solid {border_color}; margin-bottom: 10px;">
            <p style="margin: 0; font-size: 13px; color: #a0a0a0; font-weight: bold;">{title}</p>
            <h3 style="margin: 0; font-size: 22px; color: {text_color};">{value}</h3>
        </div>
    """, unsafe_allow_html=True)

# --- Firebase Init ---
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(dict(st.secrets["firebase_key"]))
        firebase_admin.initialize_app(cred, {'databaseURL': st.secrets["database_url"]})
    except Exception as e:
        st.error("Erro no Firebase. Verifique os Secrets no Streamlit Cloud.")
        st.stop()

def load_db(): return db.reference('/').get() or {"users": {}}
def save_db(db_main): db.reference('/').set(db_main)
def format_brl(value): return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

if 'db_main' not in st.session_state: st.session_state.db_main = load_db()
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

db_main = st.session_state.db_main

# --- TELA DE ACESSO ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #ff6600;'>⚡ Financeiro Sayjins</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["Entrar", "Criar Conta"])
    with t1:
        with st.form("login_form"):
            u = st.text_input("Usuário"); p = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar no Sistema"):
                if u in db_main.get("users", {}) and db_main["users"][u]["password"] == p:
                    st.session_state.logged_in = True; st.session_state.username = u; st.rerun()
                else: st.error("Usuário ou senha incorretos.")
    with t2:
        with st.form("reg_form"):
            nu = st.text_input("Novo Usuário"); np = st.text_input("Senha", type="password")
            if st.form_submit_button("Criar Conta"):
                if nu and np:
                    if nu in db_main.get("users", {}): st.error("Usuário já existe.")
                    else:
                        db_main.setdefault("users", {})[nu] = {"password": np, "data": {"accounts": [], "transactions": [], "goals": [], "fixed_expenses": [], "settings": {"credit_limit": 5000.0}}}
                        save_db(db_main); st.success("Conta criada!"); st.rerun()
    st.stop()

# --- CARREGAMENTO DE DADOS DO USUÁRIO ---
u_name = st.session_state.username
u_data = db_main["users"][u_name]["data"]
u_data.setdefault("fixed_expenses", [])
u_data.setdefault("transactions", [])
u_data.setdefault("accounts", [])

# --- LÓGICA DE SALDO (CORRIGIDA) ---
def get_real_balance():
    # Saldo inicial das contas
    total = sum(a.get("initial_balance", 0) for a in u_data.get("accounts", []))
    # Apenas transações MANUAIS (não CSV) pagas alteram o saldo
    for t in u_data.get("transactions", []):
        if t.get("status") == "Paid" and not t.get("ignoreBalance", False):
            val = t.get("amount", 0)
            total += val if t.get("type") == "ENTRADA" else -val
    return total

global_balance = get_real_balance()
today = datetime.date.today()
str_month = today.strftime("%Y-%m")

# Cálculo de Totais (Painel)
paid_in_all = sum(t["amount"] for t in u_data["transactions"] if t["type"] == "ENTRADA" and t["status"] == "Paid")
paid_out_all = sum(t["amount"] for t in u_data["transactions"] if t["type"] == "SAIDA" and t["status"] == "Paid")
# Sobra média para metas
avg_savings = max(0, (paid_in_all - paid_out_all) / max(1, (today.year - 2024)*12 + today.month))

# --- INTERFACE ---
st.markdown(f"<p style='text-align:center;'>Perfil: <b>{u_name}</b></p>", unsafe_allow_html=True)
tabs = st.tabs(["📊 Painel", "💸 Histórico", "➕ Lançar", "🎯 Metas", "⚙️ Sair"])

# 1. PAINEL
with tabs[0]:
    f_mes = st.text_input("Mês de Referência (YYYY-MM)", value=str_month)
    # Soma TUDO que está Unpaid no mês filtrado
    aberto = sum(t["amount"] for t in u_data["transactions"] if t["status"] == "Unpaid" and t["type"] == "SAIDA" and t["date"].startswith(f_mes))
    
    c1, c2 = st.columns(2)
    with c1: custom_card("SALDO GLOBAL", format_brl(global_balance), "#007BFF", "#3399ff")
    with c2: custom_card(f"ABERTO EM {f_mes}", format_brl(aberto), "#ffc107", "#ffcd39")

    st.markdown("### 📅 Resumo de Pagamentos")
    pagos = [t for t in u_data["transactions"] if t["status"] == "Paid" and t["type"] == "SAIDA" and t["date"].startswith(f_mes)]
    if pagos:
        for t in pagos:
            st.markdown(f"<div style='background-color:#1a1a1a; padding:8px; border-radius:5px; border-left:4px solid #4dd26b; margin-bottom:5px;'>{t['date']} | {t['description']} | {format_brl(t['amount'])}</div>", unsafe_allow_html=True)
    else: st.caption("Nenhum pagamento registrado neste mês.")

# 2. HISTÓRICO
with tabs[1]:
    st.write("### Últimas Movimentações")
    for t in sorted(u_data["transactions"], key=lambda x: x['id'], reverse=True)[:50]:
        cor = "#4dd26b" if t["type"] == "ENTRADA" else "#ff6b7a"
        tag = "[CSV]" if t.get("ignoreBalance") else ""
        st.markdown(f"<div style='background-color:#1a1a1a; padding:10px; border-radius:5px; border-left:4px solid {cor}; margin-bottom:5px;'>{t['date']} - {tag} {t['description']} - <b>{format_brl(t['amount'])}</b></div>", unsafe_allow_html=True)

# 3. LANÇAR
with tabs[2]:
    m_man, m_fix, m_reem = st.tabs(["Manual", "Fixas/Pagar", "Reembolso"])
    
    with m_man:
        op = st.radio("Tipo", ["SAIDA", "ENTRADA"], horizontal=True)
        desc = st.text_input("O que é?")
        if desc:
            val = st.number_input("Valor R$", min_value=0.01)
            dat = st.date_input("Data do Lançamento")
            if st.button("Salvar Lançamento"):
                new_id = max([t['id'] for t in u_data["transactions"]], default=0) + 1
                u_data["transactions"].append({"id": new_id, "type": op, "account": u_data["accounts"][0]["name"], "description": desc, "amount": val, "date": dat.strftime("%Y-%m-%d"), "status": "Paid", "ignoreBalance": False})
                save_db(db_main); st.rerun()

    with m_fix:
        st.write("### Suas Contas a Pagar")
        for fixa in u_data["fixed_expenses"]:
            with st.expander(f"📁 {fixa['name']}"):
                fv = st.number_input("Valor da Fatura", key=f"v_{fixa['id']}")
                fd = st.date_input("Vencimento", key=f"d_{fixa['id']}")
                if st.button("Lançar Mês", key=f"b_{fixa['id']}"):
                    new_id = max([t['id'] for t in u_data["transactions"]], default=0) + 1
                    u_data["transactions"].append({
                        "id": new_id, "type": "SAIDA", "account": u_data["accounts"][0]["name"],
                        "description": f"[Fixo] {fixa['name']}", "amount": fv, "date": fd.strftime("%Y-%m-%d"), "status": "Unpaid", "ignoreBalance": False
                    })
                    save_db(db_main); st.success("Lançado em Aberto!"); st.rerun()
                
                # Baixa na conta
                hist = [t for t in u_data["transactions"] if t["description"] == f"[Fixo] {fixa['name']}"]
                for t in sorted(hist, key=lambda x: x['date'], reverse=True):
                    c_a, c_b = st.columns([3,1])
                    status_icon = "🔴" if t["status"] == "Unpaid" else "🟢"
                    c_a.write(f"{status_icon} {t['date']} | {format_brl(t['amount'])}")
                    if t["status"] == "Unpaid":
                        if c_b.button("Pagar", key=f"p_{t['id']}"):
                            t["status"] = "Paid"; save_db(db_main); st.rerun()
                
                if st.button("Deletar Categoria", key=f"del_{fixa['id']}"):
                    u_data["fixed_expenses"] = [f for f in u_data["fixed_expenses"] if f["id"] != fixa["id"]]
                    save_db(db_main); st.rerun()

        st.markdown("---")
        nf = st.text_input("Nova Categoria Fixa (Ex: ALUGUEL)")
        if st.button("Criar Categoria"):
            u_data["fixed_expenses"].append({"id": len(u_data["fixed_expenses"])+1, "name": nf.upper()})
            save_db(db_main); st.rerun()

    with m_reem:
        if u_data["transactions"]:
            tre = st.selectbox("Escolha a transação", sorted(u_data["transactions"], key=lambda x:x['id'], reverse=True), format_func=lambda x: f"{x['date']} - {x['description']}")
            if st.button("Processar Reembolso"):
                nt = "ENTRADA" if tre["type"] == "SAIDA" else "SAIDA"
                new_id = max([t['id'] for t in u_data["transactions"]], default=0) + 1
                u_data["transactions"].append({"id": new_id, "type": nt, "account": tre["account"], "description": f"[REEM] {tre['description']}", "amount": tre["amount"], "date": today.strftime("%Y-%m-%d"), "status": "Paid", "ignoreBalance": False})
                save_db(db_main); st.rerun()

# 4. METAS
with tabs[3]:
    st.write("### Suas Metas Sayjins")
    if st.button("➕ Nova Meta"): st.session_state.nm = True
    if st.session_state.get("nm"):
        with st.form("fm"):
            nn = st.text_input("Qual o objetivo?"); vv = st.number_input("Valor Final")
            if st.form_submit_button("Salvar Meta"):
                u_data.setdefault("goals", []).append({"name": nn, "target": vv, "status": "Active"})
                save_db(db_main); st.session_state.nm = False; st.rerun()
                
    for i, g in enumerate(u_data.get("goals", [])):
        if g.get("status", "Active") == "Active":
            progress = max(0.0, min(global_balance / g["target"], 1.0)) if g["target"] > 0 else 0.0
            st.write(f"**{g['name']}**")
            st.progress(progress)
            st.caption(f"{format_brl(global_balance)} / {format_brl(g['target'])}")
            if global_balance < g["target"] and avg_savings > 0:
                meses = int((g["target"] - global_balance) / avg_savings) + 1
                st.caption(f"⏱️ Previsão: ~{meses} meses")
            if st.button("✅ Concluir", key=f"m_{i}"):
                g["status"] = "Achieved"; save_db(db_main); st.rerun()

# 5. EXTRA
with tabs[4]:
    if st.button("🚪 Sair da Conta"):
        st.session_state.logged_in = False; st.rerun()
    st.markdown("---")
    if st.button("🚨 ZERAR MEUS DADOS"):
        u_data["transactions"] = []; u_data["goals"] = []; save_db(db_main); st.rerun()
