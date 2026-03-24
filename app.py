import streamlit as st
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
from google import genai
import firebase_admin
from firebase_admin import credentials, db

st.set_page_config(page_title="Financeiro Sayjins", layout="wide", initial_sidebar_state="collapsed")

# --- Sistema de Banco de Dados Cloud (Firebase) ---
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(dict(st.secrets["firebase_key"]))
        firebase_admin.initialize_app(cred, {
            'databaseURL': st.secrets["database_url"]
        })
    except Exception as e:
        st.error(f"Erro ao conectar com o Firebase. Verifique seus Secrets. Erro: {e}")
        st.stop()

def load_db():
    ref = db.reference('/')
    data = ref.get()
    if data:
        return data
    return {"users": {}}

def save_db(db_main):
    ref = db.reference('/')
    ref.set(db_main)

def format_brl(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

if 'db_main' not in st.session_state:
    st.session_state.db_main = load_db()

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
                if user_login in db_main.get("users", {}) and db_main["users"][user_login]["password"] == pass_login:
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
                elif new_user in db_main.get("users", {}):
                    st.error("Esse usuário já existe. Escolha outro!")
                else:
                    if "users" not in db_main:
                        db_main["users"] = {}
                        
                    db_main["users"][new_user] = {
                        "password": new_pass,
                        "data": {"accounts": [], "transactions": [], "goals": [], "settings": {"credit_limit": 5000.0}}
                    }
                    save_db(db_main)
                    st.success("Conta criada com sucesso! Vá na aba 'Entrar' para acessar.")
                    
    st.stop()

# --- CARREGA OS DADOS DO USUÁRIO LOGADO ---
username = st.session_state.username
user_data = db_main["users"][username]["data"]

with st.sidebar:
    st.write(f"Logado como: **{username}**")
    if st.button("Sair"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

# --- Sistema de Onboarding (Bloqueio Inicial) ---
if not user_data.get("accounts"):
    st.title(f"🚀 Bem-vindo, {username}!")
    st.info("Para começar, precisamos configurar sua conta principal e seu saldo atual REAL.")
    with st.form("onboarding_form"):
        acc_name = st.text_input("Nome da Conta (ex: Banco Inter, Carteira)")
        acc_balance = st.number_input("Saldo Atual Real (R$)", value=0.0, step=10.0)
        submitted = st.form_submit_button("Criar Conta e Entrar")
        if submitted and acc_name:
            if "accounts" not in user_data:
                user_data["accounts"] = []
            user_data["accounts"].append({"id": 1, "name": acc_name, "initial_balance": acc_balance})
            save_db(db_main)
            st.rerun()
    st.stop()

# --- Lógica de Negócios (Cálculos Globais) ---
def calculate_real_balance(account_name):
    acc = next((a for a in user_data["accounts"] if a["name"] == account_name), None)
    if not acc: return 0.0
    balance = acc["initial_balance"]
    for t in user_data.get("transactions", []):
        if t["account"] == account_name and t["status"] == "Paid" and not t.get("ignoreBalance", False):
            balance += t["amount"] if t["type"] in ["Income", "ENTRADA"] else -t["amount"]
    return balance

global_balance = sum(calculate_real_balance(a["name"]) for a in user_data["accounts"])

entrou_alltime = sum(t["amount"] for t in user_data.get("transactions", []) if t["type"] in ["Income", "ENTRADA"] and t["status"] == "Paid")
saiu_alltime = sum(t["amount"] for t in user_data.get("transactions", []) if t["type"] in ["Expense", "SAIDA"])

unpaid_credit = sum(t["amount"] for t in user_data.get("transactions", []) if t["type"] in ["Expense", "SAIDA"] and t.get("is_credit") and t["status"] == "Unpaid")
available_credit = user_data["settings"]["credit_limit"] - unpaid_credit

# Cálculos para previsão das metas (Média Mensal)
paid_income = sum(t["amount"] for t in user_data.get("transactions", []) if t["type"] in ["Income", "ENTRADA"] and t["status"] == "Paid")
paid_expense = sum(t["amount"] for t in user_data.get("transactions", []) if t["type"] in ["Expense", "SAIDA"] and t["status"] == "Paid")
net_savings = paid_income - paid_expense

if user_data.get("transactions"):
    df_t = pd.DataFrame(user_data["transactions"])
    df_t['date'] = pd.to_datetime(df_t['date'], errors='coerce')
    min_date = df_t['date'].min()
    max_date = df_t['date'].max()
    if pd.notna(min_date) and pd.notna(max_date):
        months_active = (max_date.year - min_date.year) * 12 + max_date.month - min_date.month
        months_active = max(1, months_active)
    else:
        months_active = 1
else:
    months_active = 1

avg_monthly_savings = net_savings / months_active

# Dados para o card de Metas
active_goals = [g for g in user_data.get("goals", []) if g.get("status", "Active") == "Active"]
total_goals_val = sum(g["target"] for g in active_goals)

# --- Abas (Tabs) ---
st.title("Financeiro Sayjins ⚡")
tabs = st.tabs(["Dashboard", "Transações", "Nova Transação", "Contas", "Metas", "Importar CSV", "AI Advisor", "Configurações"])

# 1. Dashboard
with tabs[0]:
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Saldo Global Atual", format_brl(global_balance))
    col2.metric("ENTROU ALLTIME", format_brl(entrou_alltime))
    col3.metric("SAIU ALLTIME", format_brl(saiu_alltime))
    col4.metric("Limite de Crédito Disp.", format_brl(available_credit))
    col5.metric("METAS ATIVAS", format_brl(total_goals_val), f"{len(active_goals)} pendentes", delta_color="off")
    
    st.subheader("Últimas Transações")
    if user_data.get("transactions"):
        df_recent = pd.DataFrame(user_data["transactions"])
        # Ordena pelo ID em ordem decrescente (mais recentes primeiro)
        df_recent = df_recent.sort_values(by="id", ascending=False).head(100)[["id", "date", "description", "account", "type", "amount", "status"]]
        st.dataframe(df_recent, width="stretch", hide_index=True)
    else:
        st.write("Nenhuma transação registrada.")

# 2. Transações
with tabs[1]:
    filter_month = st.text_input("Filtrar por Mês (YYYY-MM)", value=datetime.datetime.now().strftime("%Y-%m"))
    filtered_t = [t for t in user_data.get("transactions", []) if t["date"].startswith(filter_month)]
    
    # Exibe também os mais recentes no topo dentro da aba de transações filtradas
    filtered_t.sort(key=lambda x: x["id"], reverse=True)
    
    for i, t in enumerate(filtered_t):
        col_info, col_btn = st.columns([8, 2])
        col_info.write(f"**{t['date']}** | {t['description']} | {t['account']} | {format_brl(t['amount'])}")
        status_color = "🟢 Pago/Recebido" if t["status"] == "Paid" else "🔴 Pendente"
        if col_btn.button(status_color, key=f"status_{t['id']}_{i}"):
            t["status"] = "Unpaid" if t["status"] == "Paid" else "Paid"
            save_db(db_main)
            st.rerun()

# 3. Nova Transação
with tabs[2]:
    t_type = st.radio("Tipo de Lançamento", ["SAIDA", "ENTRADA"], horizontal=True)
    
    with st.form("new_transaction"):
        t_acc = st.selectbox("Conta", [a["name"] for a in user_data["accounts"]])
        
        if t_type == "SAIDA":
            t_desc = st.text_input("Descrição da Despesa")
            t_method = st.selectbox("Forma de Pagamento", ["PIX", "Cartão de Débito", "Cartão de Crédito"])
            t_val = st.number_input("Valor (R$)", min_value=0.01, step=10.0)
            t_date = st.date_input("Data da 1ª Parcela")
            t_installments = st.number_input("Número de Parcelas", min_value=1, value=1)
            t_status = st.selectbox("Status", ["Paid", "Unpaid"], format_func=lambda x: "Pago" if x == "Paid" else "Pendente")
        else:
            t_desc = st.text_input("Nome de quem enviou (Origem)")
            t_method = "Recebimento"
            t_val = st.number_input("Valor Recebido (R$)", min_value=0.01, step=10.0)
            t_date = st.date_input("Data do Recebimento")
            t_installments = 1
            t_status = st.selectbox("Status", ["Paid", "Unpaid"], format_func=lambda x: "Recebido" if x == "Paid" else "Pendente")
        
        if st.form_submit_button("Salvar Lançamento"):
            base_date = t_date
            for i in range(t_installments):
                desc_final = f"{t_desc} ({i+1}/{t_installments})" if t_installments > 1 else t_desc
                desc_with_method = f"[{t_method}] {desc_final}" if t_type == "SAIDA" else desc_final
                
                is_credit = True if (t_type == "SAIDA" and t_method == "Cartão de Crédito") else False
                
                new_t = {
                    "id": len(user_data.get("transactions", [])) + 1,
                    "type": t_type, 
                    "account": t_acc, 
                    "description": desc_with_method,
                    "amount": t_val, 
                    "date": base_date.strftime("%Y-%m-%d"),
                    "status": t_status, 
                    "is_credit": is_credit, 
                    "ignoreBalance": False
                }
                
                if "transactions" not in user_data:
                    user_data["transactions"] = []
                user_data["transactions"].append(new_t)
                base_date += relativedelta(months=1)
                
            save_db(db_main)
            st.success("Lançamento salvo com sucesso!")
            st.rerun()

# 4. Contas
with tabs[3]:
    st.subheader("Suas Contas")
    for acc in user_data["accounts"]:
        st.write(f"**{acc['name']}** - Saldo Atual: {format_brl(calculate_real_balance(acc['name']))}")

# 5. Metas
with tabs[4]:
    with st.form("new_goal"):
        g_name = st.text_input("Nome da Meta")
        g_target = st.number_input("Valor Alvo (R$)", min_value=1.0)
        if st.form_submit_button("Criar Meta"):
            if "goals" not in user_data:
                user_data["goals"] = []
            user_data["goals"].append({"name": g_name, "target": g_target, "status": "Active"})
            save_db(db_main)
            st.rerun()
            
    for i, g in enumerate(user_data.get("goals", [])):
        if g.get("status", "Active") == "Active":
            progress = min(global_balance / g["target"], 1.0) if global_balance > 0 else 0.0
            
            col_g1, col_g2 = st.columns([8, 2])
            col_g1.write(f"**{g['name']}**: {format_brl(global_balance)} / {format_brl(g['target'])}")
            
            if col_g2.button("✅ Concluir Meta", key=f"goal_btn_{i}"):
                g["status"] = "Achieved"
                save_db(db_main)
                st.rerun()
                
            st.progress(progress)
            
            if global_balance >= g["target"]:
                st.caption("🎉 Você já tem saldo para alcançar essa meta!")
            elif avg_monthly_savings > 0:
                months_left = (g["target"] - global_balance) / avg_monthly_savings
                st.caption(f"⏱️ Previsão: ~{int(months_left) + 1} meses (com base na sua sobra média mensal)")
            else:
                st.caption("⏱️ Previsão: Indefinida (Sua sobra média mensal está negativa ou zerada)")
                
            st.markdown("---")
        else:
            st.success(f"🎉 **{g['name']}** - Concluída! ({format_brl(g['target'])})")

# 6. Importar CSV
with tabs[5]:
    st.info("Importa CSV padrão Banco Inter. Atualizará o ENTROU/SAIU All-Time sem alterar seu saldo real.")
    uploaded_files = st.file_uploader("Escolha os arquivos CSV", type="csv", accept_multiple_files=True)
    if uploaded_files and st.button("Processar Arquivos"):
        for file in uploaded_files:
            try:
                df = pd.read_csv(file, encoding='utf-8', sep=';', skiprows=5)
                df.columns = df.columns.str.strip()
                
                count_imported = 0
                for _, row in df.iterrows():
                    if pd.isna(row.get('Data Lançamento')):
                        continue
                        
                    val_str = str(row.get('Valor', '0')).replace('.', '').replace(',', '.')
                    try:
                        amount_val = float(val_str)
                    except ValueError:
                        amount_val = 0.0
                        
                    t_type = "SAIDA" if amount_val < 0 else "ENTRADA"
                    
                    hist = str(row.get('Histórico', ''))
                    desc = str(row.get('Descrição', ''))
                    desc = "" if desc.lower() == "nan" else desc
                    full_desc = f"{hist} {desc}".strip()
                    
                    raw_date = str(row.get('Data Lançamento', ''))
                    try:
                        parsed_date = datetime.datetime.strptime(raw_date.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
                    except ValueError:
                        parsed_date = raw_date
                        
                    if "transactions" not in user_data:
                        user_data["transactions"] = []
                        
                    user_data["transactions"].append({
                        "id": len(user_data["transactions"]) + 1,
                        "type": t_type,
                        "account": user_data["accounts"][0]["name"] if user_data["accounts"] else "Importada",
                        "description": full_desc if full_desc else "CSV Import",
                        "amount": abs(amount_val),
                        "date": parsed_date if parsed_date else str(datetime.date.today()),
                        "status": "Paid", 
                        "is_credit": False, 
                        "ignoreBalance": True
                    })
                    count_imported += 1
                    
                save_db(db_main)
                st.success(f"Arquivo '{file.name}' processado! {count_imported} transações importadas.")
            except Exception as e:
                st.error(f"Erro ao ler arquivo '{file.name}': {e}")

# 7. AI Advisor
with tabs[6]:
    st.markdown("### IA Conselheira Financeira")
    api_key = st.text_input("Sua Chave API do Google Gemini", type="password")
    if api_key and st.button("Pedir Plano de Ação"):
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"Saldo: R$ {global_balance}. Entrou All-Time: R$ {entrou_alltime}. Saiu All-Time: R$ {saiu_alltime}. Metas ativas: {[g['name'] for g in active_goals]}. Crie um plano de ação."
            response = client.models.generate_content(model='gemini-1.5-pro', contents=prompt)
            st.write(response.text)
        except Exception as e:
            st.error(f"Erro ao consultar a IA: {e}")

# 8. Configurações
with tabs[7]:
    st.subheader("Configurações da Conta")
    new_limit = st.number_input("Limite Total de Crédito (R$)", value=user_data.get("settings", {}).get("credit_limit", 5000.0))
    if st.button("Salvar Configurações"):
        if "settings" not in user_data:
            user_data["settings"] = {}
        user_data["settings"]["credit_limit"] = new_limit
        save_db(db_main)
        st.success("Atualizado!")
        st.rerun()
        
    st.markdown("---")
    st.subheader("🚨 Zona de Perigo")
    st.warning("Isso apagará todas as transações e metas da SUA conta.")
    if st.button("Zerar Minhas Transações e Metas"):
        user_data["transactions"] = []
        user_data["goals"] = []
        save_db(db_main)
        st.success("Dados da sua conta zerados com sucesso!")
        st.rerun()
