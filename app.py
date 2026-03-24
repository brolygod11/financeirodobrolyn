import streamlit as st
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
from google import genai
import firebase_admin
from firebase_admin import credentials, db

st.set_page_config(page_title="Financeiro Sayjins", layout="centered", initial_sidebar_state="collapsed")

# --- CUSTOM CSS (Laranja Sayjin + Botões Texto Preto) ---
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
        height: 42px;
    }
    div.stButton > button:hover { background-color: #cc5200 !important; color: #000000 !important; }
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
        border-radius: 5px; background-color: #1a1a1a !important; color: white !important;
    }
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

# --- LOGIN (Mobile Fix) ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #ff6600;'>⚡ Financeiro Sayjins</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["Entrar", "Criar Conta"])
    with t1:
        with st.form("login_f"):
            u_in = st.text_input("Usuário")
            p_in = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                u = u_in.strip().lower()
                if u in db_main.get("users", {}) and db_main["users"][u]["password"] == p_in.strip():
                    st.session_state.logged_in = True; st.session_state.username = u; st.rerun()
                else: st.error("Usuário ou senha incorretos.")
    with t2:
        with st.form("reg_f"):
            nu_in = st.text_input("Novo Usuário")
            np_in = st.text_input("Nova Senha", type="password")
            if st.form_submit_button("Criar Conta"):
                nu = nu_in.strip().lower()
                if nu and np_in:
                    db_main.setdefault("users", {})[nu] = {"password": np_in.strip(), "data": {"accounts": [{"id":1, "name":"Principal", "initial_balance":0.0}], "transactions": [], "goals": [], "fixed_expenses": [], "settings": {"credit_limit": 5000.0}}}
                    save_db(db_main); st.success("Criado!"); st.rerun()
    st.stop()

u_name = st.session_state.username
u_data = db_main["users"][u_name]["data"]
u_data.setdefault("fixed_expenses", [])
u_data.setdefault("transactions", [])

# --- LÓGICA DE SALDO E TOTAIS ---
def get_balance():
    b = sum(a.get("initial_balance", 0) for a in u_data.get("accounts", []))
    for t in u_data["transactions"]:
        if t.get("status") == "Paid" and not t.get("ignoreBalance"):
            b += t["amount"] if t["type"] in ["Income", "ENTRADA"] else -t["amount"]
    return b

global_balance = get_balance()
today = datetime.date.today()
str_today = today.strftime("%Y-%m-%d")
str_month = today.strftime("%Y-%m")
str_year = today.strftime("%Y")
one_week_ago = (today - datetime.timedelta(days=7)).strftime("%Y-%m-%d")

# Processamento dos Totais de Tempo
totals = {
    "ENTRADA": {"dia": 0, "sem": 0, "mes": 0, "ano": 0, "all": 0},
    "SAIDA":   {"dia": 0, "sem": 0, "mes": 0, "ano": 0, "all": 0}
}

for t in u_data["transactions"]:
    amt = t["amount"]
    t_type = "ENTRADA" if t["type"] in ["Income", "ENTRADA"] else "SAIDA"
    
    # Regra: Entradas só se pagas. Saídas sempre contam nos totais (All Time).
    if t_type == "SAIDA" or (t_type == "ENTRADA" and t["status"] == "Paid"):
        totals[t_type]["all"] += amt
        if t["date"] == str_today: totals[t_type]["dia"] += amt
        if t["date"] >= one_week_ago and t["date"] <= str_today: totals[t_type]["sem"] += amt
        if t["date"].startswith(str_month): totals[t_type]["mes"] += amt
        if t["date"].startswith(str_year): totals[t_type]["ano"] += amt

# --- INTERFACE ---
st.markdown(f"<p style='text-align:center;'>Sayjin: <b>{u_name}</b></p>", unsafe_allow_html=True)
tabs = st.tabs(["📊 Painel", "💸 Histórico", "➕ Lançar", "🎯 Metas", "⚙️ Extra"])

# 1. PAINEL (TOTALMENTE RESTAURADO)
with tabs[0]:
    f_mes = st.text_input("Mês Filtro (YYYY-MM)", value=str_month)
    aberto = sum(t["amount"] for t in u_data["transactions"] if t.get("status") == "Unpaid" and t.get("type") == "SAIDA" and str(t.get("date", "")).startswith(f_mes))
    
    c1, c2 = st.columns(2)
    with c1: custom_card("SALDO GLOBAL", format_brl(global_balance), "#007BFF", "#3399ff")
    with c2: custom_card(f"ABERTO EM {f_mes}", format_brl(aberto), "#ffc107", "#ffcd39")

    # Resumo Temporal (Diário, Semanal, Mensal, Anual, All Time)
    with st.expander("📅 Resumo por Período (ENTRADA vs SAÍDA)", expanded=True):
        col_e, col_s = st.columns(2)
        with col_e:
            st.markdown("<p style='color:#4dd26b; font-weight:bold;'>🟩 ENTRADAS</p>", unsafe_allow_html=True)
            st.write(f"Hoje: {format_brl(totals['ENTRADA']['dia'])}")
            st.write(f"7 dias: {format_brl(totals['ENTRADA']['sem'])}")
            st.write(f"Mês: {format_brl(totals['ENTRADA']['mes'])}")
            st.write(f"Ano: {format_brl(totals['ENTRADA']['ano'])}")
            st.write(f"**ALL TIME: {format_brl(totals['ENTRADA']['all'])}**")
        with col_s:
            st.markdown("<p style='color:#ff6b7a; font-weight:bold;'>🟥 SAÍDAS</p>", unsafe_allow_html=True)
            st.write(f"Hoje: {format_brl(totals['SAIDA']['dia'])}")
            st.write(f"7 dias: {format_brl(totals['SAIDA']['sem'])}")
            st.write(f"Mês: {format_brl(totals['SAIDA']['mes'])}")
            st.write(f"Ano: {format_brl(totals['SAIDA']['ano'])}")
            st.write(f"**ALL TIME: {format_brl(totals['SAIDA']['all'])}**")

    st.markdown("### 📅 Pagos no Mês")
    pagos = [t for t in u_data["transactions"] if t.get("status") == "Paid" and t.get("type") == "SAIDA" and str(t.get("date", "")).startswith(f_mes)]
    for t in pagos:
        st.markdown(f"<div style='background-color:#1a1a1a; padding:8px; border-radius:5px; border-left:4px solid #4dd26b; margin-bottom:5px;'>{t['date']} | {t['description']} | {format_brl(t['amount'])}</div>", unsafe_allow_html=True)

# 2. HISTÓRICO
with tabs[1]:
    st.write("### Movimentações Recentes")
    all_t = sorted(u_data["transactions"], key=lambda x: x.get('id', 0), reverse=True)
    for i, t in enumerate(all_t[:30]):
        cor = "#4dd26b" if t["type"] in ["Income", "ENTRADA"] else "#ff6b7a"
        with st.container():
            st.markdown(f"<div style='background-color:#1a1a1a; padding:10px; border-radius:5px; border-left:4px solid {cor}; margin-bottom:2px;'>{t['date']} - {t['description']} - <b>{format_brl(t['amount'])}</b></div>", unsafe_allow_html=True)
            if st.button(f"🗑️ Excluir #{t['id']}", key=f"del_t_{t['id']}_{i}"):
                u_data["transactions"] = [tr for tr in u_data["transactions"] if tr.get('id') != t.get('id')]
                save_db(db_main); st.rerun()

# 3. LANÇAR (Com Fluxo Dinâmico)
with tabs[2]:
    m_man, m_fix, m_reem = st.tabs(["Manual", "Gavetas (Fixas)", "Reembolso"])
    
    with m_man:
        op = st.radio("Selecione a Operação", ["SAIDA", "ENTRADA"], horizontal=True)
        t_desc = st.text_input("Descrição do Lançamento")
        if t_desc:
            t_val = st.number_input("Valor R$", min_value=0.01, step=10.0)
            if t_val > 0:
                if op == "SAIDA":
                    t_method = st.selectbox("Forma de Pagamento", ["PIX", "Cartão de Débito", "Cartão de Crédito"])
                    if t_method == "Cartão de Crédito":
                        t_date = st.date_input("Vencimento 1ª Parcela")
                        t_inst = st.number_input("Parcelas", min_value=1, value=1)
                    else:
                        t_date = st.date_input("Data")
                        t_inst = 1
                    t_status = st.selectbox("Status", ["Paid", "Unpaid"], index=0 if t_method != "Cartão de Crédito" else 1, format_func=lambda x: "Efetivado (Pago)" if x == "Paid" else "Pendente (Em Aberto)")
                else:
                    t_method = "Recebimento"
                    t_date = st.date_input("Data do Recebimento")
                    t_inst = 1
                    t_status = st.selectbox("Status", ["Paid", "Unpaid"], format_func=lambda x: "Recebido" if x == "Paid" else "Pendente")

                if st.button("🚀 Confirmar Lançamento"):
                    base_date = t_date
                    for i in range(t_inst):
                        desc_f = f"{t_desc} ({i+1}/{t_inst})" if t_inst > 1 else t_desc
                        new_id = max([t.get('id', 0) for t in u_data["transactions"]], default=0) + 1
                        u_data["transactions"].append({"id": new_id, "type": op, "description": f"[{t_method}] {desc_f}", "amount": t_val, "date": base_date.strftime("%Y-%m-%d"), "status": t_status, "ignoreBalance": False})
                        base_date += relativedelta(months=1)
                    save_db(db_main); st.success("Sucesso!"); st.rerun()

    with m_fix:
        for fixa in u_data["fixed_expenses"]:
            with st.expander(f"📁 {fixa['name']}"):
                fv = st.number_input("Valor", key=f"v_{fixa['id']}")
                fd = st.date_input("Vencimento", key=f"d_{fixa['id']}")
                if st.button("Lançar Mês", key=f"b_{fixa['id']}"):
                    new_id = max([t.get('id', 0) for t in u_data["transactions"]], default=0) + 1
                    u_data["transactions"].append({"id": new_id, "type": "SAIDA", "description": f"[Fixo] {fixa['name']}", "amount": fv, "date": fd.strftime("%Y-%m-%d"), "status": "Unpaid", "ignoreBalance": False, "fixed_id": fixa['id']})
                    save_db(db_main); st.rerun()
                
                hist = [t for t in u_data["transactions"] if t.get("fixed_id") == fixa['id']]
                for t in sorted(hist, key=lambda x: x['date'], reverse=True):
                    cA, cB = st.columns([3,1])
                    st_icon = "🔴" if t["status"] == "Unpaid" else "🟢"
                    cA.write(f"{st_icon} {t['date']} | {format_brl(t['amount'])}")
                    if t["status"] == "Unpaid" and cB.button("Pagar", key=f"p_{t['id']}"):
                        t["status"] = "Paid"; save_db(db_main); st.rerun()
                if st.button("Deletar Categoria", key=f"del_{fixa['id']}"):
                    u_data["fixed_expenses"] = [f for f in u_data["fixed_expenses"] if f["id"] != fixa["id"]]
                    save_db(db_main); st.rerun()

        nf = st.text_input("Nova Categoria Fixa")
        if st.button("Criar Gaveta"):
            u_data["fixed_expenses"].append({"id": len(u_data["fixed_expenses"])+1, "name": nf.upper()})
            save_db(db_main); st.rerun()

    with m_reem:
        if u_data["transactions"]:
            tre = st.selectbox("Estornar transação", sorted(u_data["transactions"], key=lambda x:x.get('id', 0), reverse=True), format_func=lambda x: f"{x['date']} - {x['description']}")
            if st.button("🔄 Gerar Estorno"):
                nt = "ENTRADA" if tre["type"] == "SAIDA" else "SAIDA"
                new_id = max([t.get('id', 0) for t in u_data["transactions"]], default=0) + 1
                u_data["transactions"].append({"id": new_id, "type": nt, "description": f"[REEM] {tre['description']}", "amount": tre["amount"], "date": str_today, "status": "Paid", "ignoreBalance": False})
                save_db(db_main); st.rerun()

# 4. METAS
with tabs[3]:
    active_goals = [g for g in u_data.get("goals", []) if g.get("status", "Active") == "Active"]
    total_goals_val = sum(g["target"] for g in active_goals)
    custom_card("TOTAL DAS METAS ATIVAS", format_brl(total_goals_val), "#9b59b6", "#c39bd3")
    
    with st.expander("➕ Nova Meta"):
        with st.form("f_meta"):
            n_m = st.text_input("Objetivo"); v_m = st.number_input("Valor Alvo")
            if st.form_submit_button("Salvar Meta"):
                u_data.setdefault("goals", []).append({"name": n_m, "target": v_m, "status": "Active"})
                save_db(db_main); st.rerun()
                
    for i, g in enumerate(u_data.get("goals", [])):
        if g.get("status", "Active") == "Active":
            prog = max(0.0, min(global_balance / g["target"], 1.0)) if g["target"] > 0 else 0.0
            st.write(f"**{g['name']}**"); st.progress(prog)
            if st.button("✅ Concluir Meta", key=f"m_{i}"):
                g["status"] = "Achieved"; save_db(db_main); st.rerun()

# 5. EXTRA
with tabs[4]:
    sub_csv, sub_config = st.tabs(["📁 Importar CSV", "⚙️ Sistema"])
    with sub_csv:
        up = st.file_uploader("Subir CSV Inter", type="csv", accept_multiple_files=True)
        if up and st.button("Processar CSV"):
            for f in up:
                df = pd.read_csv(f, encoding='utf-8', sep=';', skiprows=5)
                df.columns = df.columns.str.strip()
                for _, row in df.iterrows():
                    if pd.isna(row.get('Data Lançamento')): continue
                    v_s = str(row.get('Valor', '0')).replace('.', '').replace(',', '.')
                    v_v = abs(float(v_s))
                    t_t = "SAIDA" if float(v_s) < 0 else "ENTRADA"
                    desc = (str(row.get('Histórico', '')) + " " + str(row.get('Descrição', ''))).replace("nan", "").strip()
                    try: p_date = datetime.datetime.strptime(str(row.get('Data Lançamento', '')).strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
                    except: p_date = str_today
                    new_id = max([t.get('id', 0) for t in u_data["transactions"]], default=0) + 1
                    u_data["transactions"].append({"id": new_id, "type": t_t, "description": desc, "amount": v_v, "date": p_date, "status": "Paid", "ignoreBalance": True})
                save_db(db_main); st.success(f"Arquivo {f.name} importado!")
            st.rerun()
    with sub_config:
        if st.button("🚪 Sair da Conta"): st.session_state.logged_in = False; st.rerun()
        if st.button("🚨 RESETAR MEUS DADOS"): u_data["transactions"] = []; u_data["goals"] = []; save_db(db_main); st.rerun()
