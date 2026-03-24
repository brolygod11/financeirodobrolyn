import streamlit as st
import json
import os
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
import google.generativeai as genai

st.set_page_config(page_title="Financeiro Sayjins", layout="wide", initial_sidebar_state="collapsed")

DATA_FILE = "finance_data.json"

# --- Sistema de Banco de Dados JSON ---
def load_db():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # Se não existir, cria a estrutura base para os usuários
    return {"users": {}}

def save_db(db_main):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db_main, f, indent=4)

def format_brl(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# Carrega o banco principal
if 'db_main' not in st.session_state:
    st.session_state.db_main = load_db()

# Variáveis de sessão para controle de login
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

db_main = st.session_state.db_main

# --- TELA DE LOGIN E REGISTRO ---
if not st.session_state.logged_in:
    st.title("⚡ Financeiro Sayjins")
    
    tab_login, tab_register = st.tabs(["Entrar", "Criar Conta"])
    
    with tab_login:
        st.subheader("Acesse sua conta")
        with st.form("login_form"):
            user_login = st.text_input("Usuário")
            pass_login = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                if user_login in db_main["users"] and db_main["users"][user_login]["password"] == pass_login:
                    st.session_state.logged_in = True
                    st.session_state.username = user_login
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos!")
                    
    with tab_register:
        st.subheader("Novo por aqui?")
        with st.form("register_form"):
            new_user = st.text_input("Escolha um Usuário")
            new_pass = st.text_input("Crie uma Senha", type="password")
            if st.form_submit_button("Criar Conta"):
                if not new_user or not new_pass:
                    st.warning("Preencha usuário e senha!")
                elif new_user in db_main["users"]:
                    st.error("Esse usuário já existe. Escolha outro!")
                else:
                    # Cria a estrutura de dados limpa para o novo usuário
                    db_main["users"][new_user] = {
                        "password": new_pass,
                        "data": {"accounts": [], "transactions": [], "goals": [], "settings": {"credit_limit": 5000.0}}
                    }
                    save_db(db_main)
                    st.success("Conta criada com sucesso! Vá na aba 'Entrar' para acessar.")
                    
    st.stop() # Bloqueia o carregamento do resto do app se não estiver logado

# --- CARREGA OS DADOS DO USUÁRIO LOGADO ---
# A partir daqui, a variável 'db' isola apenas os dados de quem está logado
username = st.session_state.username
db = db_main["users"][username]["data"]

# Botão de Logout na barra lateral
with st.sidebar:
    st.write(f"Logado como: **{username}**")
    if st.button("Sair"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

# --- Sistema de Onboarding (Bloqueio Inicial) ---
if not db["accounts"]:
    st.title(f"🚀 Bem-vindo, {username}!")
    st.info("Para começar, precisamos configurar sua conta principal e seu saldo atual REAL.")
    with st.form("onboarding_form"):
        acc_name = st.text_input("Nome da Conta (ex: Nubank, Carteira)")
        acc_balance = st.number_input("Saldo Atual Real (R$)", value=0.0, step=10.0)
        submitted = st.form_submit_button("Criar Conta e Entrar")
        if submitted and acc_name:
            db["accounts"].append({"id": 1, "name": acc_name, "initial_balance": acc_balance})
            save_db(db_main) # Salva no banco principal
            st.rerun()
    st.stop()

# --- Lógica de Negócios ---
def calculate_real_balance(account_name):
    acc = next((a for a in db["accounts"] if a["name"] == account_name), None)
    if not acc: return 0.0
    balance = acc["initial_balance"]
    for t in db["transactions"]:
        if t["account"] == account_name and t["status"] == "Paid" and not t.get("ignoreBalance", False):
            balance += t["amount"] if t["type"] == "Income" else -t["amount"]
    return balance

global_balance = sum(calculate_real_balance(a["name"]) for a in db["accounts"])
all_time_income = sum(t["amount"] for t in db["transactions"] if t["type"] == "Income" and t["status"] == "Paid" and not t.get("ignoreBalance", False))
all_time_expense = sum(t["amount"] for t in db["transactions"] if t["type"] == "Expense" and t["status"] == "Paid" and not t.get("ignoreBalance", False))
unpaid_credit = sum(t["amount"] for t in db["transactions"] if t["type"] == "Expense" and t["is_credit"] and t["status"] == "Unpaid")
available_credit = db["settings"]["credit_limit"] - unpaid_credit

# --- Abas (Tabs) ---
st.title("Financeiro Sayjins ⚡")
tabs = st.tabs(["Dashboard", "Transações", "Nova Transação", "Contas", "Metas", "Importar CSV", "AI Advisor", "Configurações"])

# 1. Dashboard
with tabs[0]:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Saldo Global Atual", format_brl(global_balance))
    col2.metric("Receita (All-Time)", format_brl(all_time_income))
    col3.metric("Despesas (All-Time)", format_brl(all_time_expense))
    col4.metric("Limite de Crédito Disponível", format_brl(available_credit))
    
    st.subheader("Últimas Transações")
    if db["transactions"]:
        df_recent = pd.DataFrame(db["transactions"]).tail(100)[["date", "description", "account", "type", "amount", "status"]]
        st.dataframe(df_recent, use_container_width=True)
    else:
        st.write("Nenhuma transação registrada.")

# 2. Transações
with tabs[1]:
    filter_month = st.text_input("Filtrar por Mês (YYYY-MM)", value=datetime.datetime.now().strftime("%Y-%m"))
    filtered_t = [t for t in db["transactions"] if t["date"].startswith(filter_month)]
    
    for i, t in enumerate(filtered_t):
        col_info, col_btn = st.columns([8, 2])
        col_info.write(f"**{t['date']}** | {t['description']} | {t['account']} | {format_brl(t['amount'])}")
        status_color = "🟢 Pago" if t["status"] == "Paid" else "🔴 Pendente"
        if col_btn.button(status_color, key=f"status_{t['id']}_{i}"):
            t["status"] = "Unpaid" if t["status"] == "Paid" else "Paid"
            save_db(db_main)
            st.rerun()

# 3. Nova Transação
with tabs[2]:
    with st.form("new_transaction"):
        t_type = st.radio("Tipo", ["Expense", "Income"], horizontal=True)
        t_acc = st.selectbox("Conta", [a["name"] for a in db["accounts"]])
        t_desc = st.text_input("Descrição")
        t_val = st.number_input("Valor (R$)", min_value=0.01, step=10.0)
        t_date = st.date_input("Data da 1ª Parcela")
        t_installments = st.number_input("Número de Parcelas", min_value=1, value=1)
        t_status = st.selectbox("Status", ["Paid", "Unpaid"])
        t_credit = st.checkbox("Compra no Cartão de Crédito") if t_type == "Expense" else False
        
        if st.form_submit_button("Salvar Transação"):
            base_date = t_date
            for i in range(t_installments):
                desc = f"{t_desc} ({i+1}/{t_installments})" if t_installments > 1 else t_desc
                new_t = {
                    "id": len(db["transactions"]) + 1,
                    "type": t_type, "account": t_acc, "description": desc,
                    "amount": t_val, "date": base_date.strftime("%Y-%m-%d"),
                    "status": t_status, "is_credit": t_credit, "ignoreBalance": False
                }
                db["transactions"].append(new_t)
                base_date += relativedelta(months=1)
            save_db(db_main)
            st.success("Transação salva!")
            st.rerun()

# 4. Contas
with tabs[3]:
    st.subheader("Suas Contas")
    for acc in db["accounts"]:
        st.write(f"**{acc['name']}** - Saldo Atual: {format_brl(calculate_real_balance(acc['name']))}")

# 5. Metas
with tabs[4]:
    with st.form("new_goal"):
        g_name = st.text_input("Nome da Meta")
        g_target = st.number_input("Valor Alvo (R$)", min_value=1.0)
        if st.form_submit_button("Criar Meta"):
            db["goals"].append({"name": g_name, "target": g_target})
            save_db(db_main)
            st.rerun()
            
    for g in db["goals"]:
        progress = min(global_balance / g["target"], 1.0) if global_balance > 0 else 0.0
        st.write(f"**{g['name']}**: {format_brl(global_balance)} / {format_brl(g['target'])}")
        st.progress(progress)

# 6. Importar CSV
with tabs[5]:
    st.info("Importa CSV padrão Banco Inter.")
    uploaded_files = st.file_uploader("Escolha os arquivos CSV", type="csv", accept_multiple_files=True)
    if uploaded_files and st.button("Processar Arquivos"):
        for file in uploaded_files:
            try:
                df = pd.read_csv(file, encoding='latin1', sep=';')
                for _, row in df.iterrows():
                    db["transactions"].append({
                        "id": len(db["transactions"]) + 1,
                        "type": "Expense",
                        "account": db["accounts"][0]["name"],
                        "description": str(row.get('Descrição', 'CSV Import')),
                        "amount": abs(float(str(row.get('Valor', '0')).replace(',', '.'))),
                        "date": str(row.get('Data', datetime.date.today())),
                        "status": "Paid", "is_credit": False, "ignoreBalance": True
                    })
                save_db(db_main)
                st.success("Arquivos processados com sucesso!")
            except Exception as e:
                st.error(f"Erro ao ler arquivo: {e}")

# 7. AI Advisor
with tabs[6]:
    st.markdown("### IA Conselheira Financeira")
    api_key = st.text_input("Sua Chave API do Google Gemini", type="password")
    if api_key and st.button("Pedir Plano de Ação"):
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-pro')
        prompt = f"Saldo: R$ {global_balance}. Receita: R$ {all_time_income}. Despesa: R$ {all_time_expense}. Metas: {db['goals']}. Crie um plano de ação."
        st.write(model.generate_content(prompt).text)

# 8. Configurações
with tabs[7]:
    new_limit = st.number_input("Limite Total de Crédito (R$)", value=db["settings"]["credit_limit"])
    if st.button("Salvar Configurações"):
        db["settings"]["credit_limit"] = new_limit
        save_db(db_main)
        st.success("Atualizado!")
        st.rerun()
