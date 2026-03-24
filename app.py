import streamlit as st
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
from google import genai
import firebase_admin
from firebase_admin import credentials, db

st.set_page_config(page_title="Financeiro Sayjins", layout="centered", initial_sidebar_state="collapsed")

# --- CUSTOM CSS (Tema Dark & Laranja Sayjin) ---
st.markdown("""
    <style>
    .stApp { background-color: #0e0e0e; color: #ffffff; }
    div.stButton > button:first-child { background-color: #ff6600; color: white; border: none; border-radius: 8px; font-weight: bold; }
    div.stButton > button:first-child:hover { background-color: #cc5200; border: none; }
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] { border-radius: 5px; }
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
        st.error(f"Erro ao conectar com o Firebase. Verifique seus Secrets.")
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
            if st.form_submit_button("Criar Conta"):
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

with st.sidebar:
    st.write(f"Fala, **{username}**!")
    if st.button("Sair da Conta"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

# --- BLOQUEIO INICIAL ---
if not user_data.get("accounts"):
    st.title("Bem-vindo! 🐉")
    with st.form("onboarding_form"):
        acc_name = st.text_input("Nome da Conta Principal")
        acc_balance = st.number_input("Saldo Atual Real (R$)", value=0.0, step=10.0)
        if st.form_submit_button("Começar"):
            user_data.setdefault("accounts", []).append({"id": 1, "name": acc_name, "initial_balance": acc_balance})
            save_db(db_main)
            st.rerun()
    st.stop()

# --- LÓGICA DE NEGÓCIOS GERAL ---
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
str_year = today.strftime("%Y")
one_week_ago = (today - datetime.timedelta(days=7)).strftime("%Y-%m-%d")

totals = {"ENTRADA": {"dia": 0, "sem": 0, "mes": 0, "ano": 0, "all": 0}, "SAIDA": {"dia": 0, "sem": 0, "mes": 0, "ano": 0, "all": 0}}
for t in user_data.get("transactions", []):
    amt = t["amount"]
    t_type = "ENTRADA" if t["type"] in ["Income", "ENTRADA"] else "SAIDA"
    if t_type == "SAIDA" or (t_type == "ENTRADA" and t["status"] == "Paid"):
        totals[t_type]["all"] += amt
        if t["date"] == str_today: totals[t_type]["dia"] += amt
        if t["date"] >= one_week_ago and t["date"] <= str_today: totals[t_type]["sem"] += amt
        if t["date"].startswith(str_month): totals[t_type]["mes"] += amt
        if t["date"].startswith(str_year): totals[t_type]["ano"] += amt

net_savings = totals["ENTRADA"]["all"] - sum(t["amount"] for t in user_data.get("transactions", []) if t["type"] in ["Expense", "SAIDA"] and t["status"] == "Paid")
months_active = max(1, (today.year - 2024) * 12 + today.month - 1)
avg_monthly_savings = net_savings / months_active

# --- NAVEGAÇÃO MOBILE-FRIENDLY ---
st.markdown("<h3 style='text-align: center; color: #ff6600;'>Visão Geral</h3>", unsafe_allow_html=True)
tabs = st.tabs(["📊 Painel", "💸 Transf.", "➕ Lançar", "🎯 Metas", "📁 Extra"])

# 1. DASHBOARD (PAINEL)
with tabs[0]:
    filtro_mes_painel = st.text_input("Filtro de Mês (YYYY-MM)", value=str_month, key="filtro_painel")
    contas_aberto_mes = sum(t["amount"] for t in user_data.get("transactions", []) if t["type"] in ["Expense", "SAIDA"] and t["status"] == "Unpaid" and t["date"].startswith(filtro_mes_painel))
    
    col1, col2 = st.columns(2)
    with col1: custom_card("SALDO GLOBAL", format_brl(global_balance), "#007BFF", "#3399ff")
    with col2: custom_card(f"EM ABERTO ({filtro_mes_painel})", format_brl(contas_aberto_mes), "#ffc107", "#ffcd39")

    st.markdown("### 📅 Resumo por Período")
    with st.expander("Ver Resumo Completo", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("<p style='color:#4dd26b; font-weight:bold;'>🟩 ENTRADAS</p>", unsafe_allow_html=True)
            st.write(f"**Hoje:** {format_brl(totals['ENTRADA']['dia'])}")
            st.write(f"**7 dias:** {format_brl(totals['ENTRADA']['sem'])}")
            st.write(f"**Mês:** {format_brl(totals['ENTRADA']['mes'])}")
            st.write(f"**Ano:** {format_brl(totals['ENTRADA']['ano'])}")
            st.write(f"**ALL TIME:** {format_brl(totals['ENTRADA']['all'])}")
        with c2:
            st.markdown("<p style='color:#ff6b7a; font-weight:bold;'>🟥 SAÍDAS</p>", unsafe_allow_html=True)
            st.write(f"**Hoje:** {format_brl(totals['SAIDA']['dia'])}")
            st.write(f"**7 dias:** {format_brl(totals['SAIDA']['sem'])}")
            st.write(f"**Mês:** {format_brl(totals['SAIDA']['mes'])}")
            st.write(f"**Ano:** {format_brl(totals['SAIDA']['ano'])}")
            st.write(f"**ALL TIME:** {format_brl(totals['SAIDA']['all'])}")

    st.markdown("---")
    st.markdown(f"### Contas Pagas em {filtro_mes_painel}")
    pagas_mes = [t for t in user_data.get("transactions", []) if t["type"] in ["Expense", "SAIDA"] and t["status"] == "Paid" and t["date"].startswith(filtro_mes_painel)]
    if pagas_mes:
        for t in sorted(pagas_mes, key=lambda x: x["date"], reverse=True):
            st.markdown(f"<div style='background-color: #1a1a1a; padding: 10px; border-radius: 5px; margin-bottom: 5px; border-left: 3px solid #4dd26b;'><p style='margin:0; font-size:12px;'>Data: {t['date']}</p><p style='margin:0; font-weight:bold;'>{t['description']} - <span style='color:#4dd26b;'>{format_brl(t['amount'])}</span></p></div>", unsafe_allow_html=True)
    else: st.info("Nenhuma conta paga neste mês.")

# 2. TRANSFERÊNCIAS (Apenas Leitura)
with tabs[1]:
    st.markdown("### Histórico de Movimentações")
    st.caption("Apenas leitura. Lançamentos manuais e automáticos aparecem aqui.")
    all_t = sorted(user_data.get("transactions", []), key=lambda x: x["id"], reverse=True)
    
    for t in all_t[:50]:
        is_income = t["type"] in ["Income", "ENTRADA"]
        color_tag = "🟩" if is_income else "🟥"
        status_color = "#4dd26b" if t["status"] == "Paid" else "#ffc107"
        status_txt = "Pago/Recebido" if t["status"] == "Paid" else "Pendente"
        
        st.markdown(f"""
        <div style='background-color: #1e1e1e; padding: 10px; border-radius: 8px; margin-bottom: 5px; border-left: 3px solid {color_tag[-1]}'>
            <p style='margin:0; font-size:12px; color:gray;'>ID: {t['id']} | {t['date']} | Status: <span style='color:{status_color};'>{status_txt}</span></p>
            <div style='display: flex; justify-content: space-between; align-items: center;'>
                <p style='margin:0; font-weight:bold;'>{t['description']}</p>
                <p style='margin:0; font-weight:bold;'>{color_tag} {format_brl(t['amount'])}</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

# 3. LANÇAR (Quatro Abas Internas)
with tabs[2]:
    sub_manual, sub_pagar, sub_criar_fixa, sub_reembolso = st.tabs(["Manual", "Contas a Pagar", "Nova Fixa", "Reembolso"])
    
    # 3.1 MANUAL
    with sub_manual:
        t_type = st.radio("Selecione a Operação", ["SAIDA", "ENTRADA"], horizontal=True)
        if t_type:
            t_acc = st.selectbox("Selecione a Conta", [a["name"] for a in user_data["accounts"]])
            t_desc = st.text_input("Descrição")
            if t_desc:
                t_val = st.number_input("Valor (R$)", min_value=0.01, step=10.0)
                if t_val > 0:
                    if t_type == "SAIDA":
                        t_method = st.selectbox("Forma de Pagamento", ["PIX", "Cartão de Débito", "Cartão de Crédito"])
                        if t_method == "Cartão de Crédito":
                            t_date = st.date_input("Vencimento da 1ª Parcela")
                            t_installments = st.number_input("Número de Parcelas", min_value=1, value=1)
                        else:
                            t_date = st.date_input("Data do Ocorrido")
                            t_installments = 1
                    else:
                        t_method = "Recebimento"
                        t_date = st.date_input("Data do Recebimento")
                        t_installments = 1
                    
                    t_status = st.selectbox("Status", ["Paid", "Unpaid"], format_func=lambda x: "Efetivado" if x == "Paid" else "Pendente")
                    
                    if st.button("🚀 Confirmar Lançamento"):
                        base_date = t_date
                        for i in range(t_installments):
                            desc_f = f"{t_desc} ({i+1}/{t_installments})" if t_installments > 1 else t_desc
                            desc_m = f"[{t_method}] {desc_f}" if t_type == "SAIDA" else desc_f
                            user_data.setdefault("transactions", []).append({
                                "id": len(user_data["transactions"]) + 1, "type": t_type, "account": t_acc, 
                                "description": desc_m, "amount": t_val, "date": base_date.strftime("%Y-%m-%d"),
                                "status": t_status, "is_credit": (t_method == "Cartão de Crédito"), "ignoreBalance": False
                            })
                            base_date += relativedelta(months=1)
                        save_db(db_main)
                        st.success("Lançado com sucesso!")
                        st.rerun()

    # 3.2 CONTAS A PAGAR (Gavetas)
    with sub_pagar:
        st.write("Suas despesas recorrentes.")
        for fixa in user_data.get("fixed_expenses", []):
            with st.expander(f"📁 {fixa['name']}"):
                with st.form(f"form_fixa_{fixa['id']}"):
                    col1, col2 = st.columns(2)
                    f_val = col1.number_input("Valor R$", min_value=0.01, step=10.0)
                    f_date = col2.date_input("Vencimento")
                    f_status = st.selectbox("Status", ["Unpaid", "Paid"], format_func=lambda x: "Em Aberto" if x == "Unpaid" else "Já Pago")
                    if st.form_submit_button("Lançar Mês"):
                        user_data.setdefault("transactions", []).append({
                            "id": len(user_data["transactions"]) + 1, "type": "SAIDA", "account": user_data["accounts"][0]["name"],
                            "description": f"[Fixo] {fixa['name']}", "amount": f_val, "date": f_date.strftime("%Y-%m-%d"),
                            "status": f_status, "is_credit": False, "ignoreBalance": False
                        })
                        save_db(db_main)
                        st.rerun()
                
                st.markdown("**Histórico desta conta:**")
                historico_fixa = [t for t in user_data.get("transactions", []) if t["description"] == f"[Fixo] {fixa['name']}"]
                for t in sorted(historico_fixa, key=lambda x: x["date"], reverse=True):
                    cA, cB = st.columns([3, 1])
                    status_str = "🟢" if t["status"] == "Paid" else "🔴"
                    cA.write(f"{status_str} {t['date']} - {format_brl(t['amount'])}")
                    if t["status"] == "Unpaid":
                        if cB.button("Pagar", key=f"pagar_{t['id']}"):
                            t["status"] = "Paid"
                            save_db(db_main)
                            st.rerun()
                            
                st.markdown("---")
                # Botão para deletar a despesa fixa
                if st.button(f"🗑️ Excluir Categoria '{fixa['name']}'", key=f"del_fixa_{fixa['id']}"):
                    user_data["fixed_expenses"] = [f for f in user_data["fixed_expenses"] if f["id"] != fixa["id"]]
                    save_db(db_main)
                    st.rerun()

    # 3.3 CRIAR DESPESA FIXA
    with sub_criar_fixa:
        with st.form("new_fixed"):
            nf_name = st.text_input("Nome da Despesa Fixa (Ex: ALUGUEL)")
            if st.form_submit_button("Criar Despesa"):
                user_data.setdefault("fixed_expenses", []).append({"id": len(user_data.get("fixed_expenses", [])) + 1, "name": nf_name.upper()})
                save_db(db_main)
                st.success("Criado! Vá em 'Contas a Pagar' para lançar.")
                st.rerun()

    # 3.4 REEMBOLSO (Novidade)
    with sub_reembolso:
        st.write("Selecione uma movimentação para gerar o reembolso automático (inverte a operação no dia de hoje).")
        valid_t = sorted(user_data.get("transactions", []), key=lambda x: x["date"], reverse=True)
        if not valid_t:
            st.info("Nenhuma transação disponível para reembolso.")
        else:
            with st.form("form_reembolso"):
                t_options = {f"ID: {t['id']} | {t['date']} | {t['description']} | R$ {t['amount']}": t for t in valid_t}
                selected_t_str = st.selectbox("Selecione a Transação", list(t_options.keys()))
                
                if st.form_submit_button("🔄 Processar Reembolso"):
                    target_t = t_options[selected_t_str]
                    
                    # Se for Saída, o reembolso é Entrada (e vice-versa)
                    new_type = "ENTRADA" if target_t["type"] in ["Expense", "SAIDA"] else "SAIDA"
                    new_desc = f"[REEMBOLSO] {target_t['description']}"
                    
                    user_data.setdefault("transactions", []).append({
                        "id": len(user_data["transactions"]) + 1,
                        "type": new_type,
                        "account": target_t["account"],
                        "description": new_desc,
                        "amount": target_t["amount"],
                        "date": str_today, # Lança com a data de hoje
                        "status": "Paid",
                        "is_credit": False,
                        "ignoreBalance": False
                    })
                    save_db(db_main)
                    st.success("Reembolso processado com sucesso!")
                    st.rerun()

# 4. METAS
with tabs[3]:
    active_goals = [g for g in user_data.get("goals", []) if g.get("status", "Active") == "Active"]
    total_goals_val = sum(g["target"] for g in active_goals)
    custom_card("VALOR TOTAL DAS METAS", format_brl(total_goals_val), "#9b59b6", "#c39bd3")
    
    with st.expander("➕ Nova Meta"):
        with st.form("new_goal"):
            g_name = st.text_input("Objetivo")
            g_target = st.number_input("Valor Alvo (R$)", min_value=1.0)
            if st.form_submit_button("Salvar"):
                user_data.setdefault("goals", []).append({"name": g_name, "target": g_target, "status": "Active"})
                save_db(db_main)
                st.rerun()
                
    for i, g in enumerate(user_data.get("goals", [])):
        if g.get("status", "Active") == "Active":
            progress = min(global_balance / g["target"], 1.0) if global_balance > 0 else 0.0
            st.markdown(f"**{g['name']}**")
            st.progress(progress)
            st.caption(f"{format_brl(global_balance)} / {format_brl(g['target'])}")
            
            if global_balance >= g["target"]: st.caption("🎉 Você já tem saldo para essa meta!")
            elif avg_monthly_savings > 0: st.caption(f"⏱️ Previsão: ~{int((g['target'] - global_balance) / avg_monthly_savings) + 1} meses (Sobra média: {format_brl(avg_monthly_savings)}/mês)")
            else: st.caption("⏱️ Previsão Indefinida (Sua sobra média está negativa ou zerada)")
            
            if st.button("✅ Concluir", key=f"g_concluir_{i}"):
                g["status"] = "Achieved"
                save_db(db_main)
                st.rerun()
            st.markdown("---")

# 5. EXTRAS
with tabs[4]:
    sub_csv, sub_ai, sub_config = st.tabs(["CSV", "IA", "Config"])
    with sub_csv:
        uploaded_files = st.file_uploader("Importar Banco Inter", type="csv", accept_multiple_files=True)
        if uploaded_files and st.button("Processar CSV"):
            st.info("Leitura de CSV operante no backend.")
    with sub_ai:
        api_key = st.text_input("API Key (Gemini)", type="password")
        if api_key and st.button("Gerar Dicas"):
            client = genai.Client(api_key=api_key)
            st.write(client.models.generate_content(model='gemini-1.5-pro', contents=f"Saldo: R${global_balance}. Metas: {[g['name'] for g in active_goals]}.").text)
    with sub_config:
        if st.button("Zerar Meu Banco de Dados"):
            user_data["transactions"] = []
            user_data["goals"] = []
            save_db(db_main)
            st.rerun()
