import streamlit as st
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
from google import genai
import firebase_admin
from firebase_admin import credentials, db

# Alterado para 'centered' para forçar o aspecto de celular (9:16)
st.set_page_config(page_title="Financeiro Sayjins", layout="centered", initial_sidebar_state="collapsed")

# --- CUSTOM CSS (Tema Dark & Laranja Sayjin + Cards) ---
st.markdown("""
    <style>
    /* Força fundo escuro e texto claro */
    .stApp {
        background-color: #0e0e0e;
        color: #ffffff;
    }
    /* Botões primários Laranja */
    div.stButton > button:first-child {
        background-color: #ff6600;
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: bold;
    }
    div.stButton > button:first-child:hover {
        background-color: #cc5200;
        border: none;
    }
    /* Inputs com borda laranja ao focar */
    .stTextInput input, .stNumberInput input {
        border-radius: 5px;
    }
    .stTextInput input:focus, .stNumberInput input:focus {
        border-color: #ff6600 !important;
        box-shadow: 0 0 0 1px #ff6600 !important;
    }
    </style>
""", unsafe_allow_html=True)

# Função para criar os Cards Coloridos do Dashboard
def custom_card(title, value, border_color, text_color):
    st.markdown(f"""
        <div style="background-color: #1a1a1a; padding: 15px; border-radius: 10px; border-left: 6px solid {border_color}; margin-bottom: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.5);">
            <p style="margin: 0; font-size: 14px; color: #a0a0a0; font-weight: bold;">{title}</p>
            <h3 style="margin: 0; font-size: 24px; color: {text_color};">{value}</h3>
        </div>
    """, unsafe_allow_html=True)

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
                else:
                    st.error("Usuário ou senha incorretos!")
                    
    with tab_register:
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
                        
                    # Pré-carrega os modelos rápidos pedidos para novas contas
                    default_templates = [
                        {"id": 1, "name": "COPASA (ÁGUA)", "type": "SAIDA", "method": "PIX", "amount": 0.0},
                        {"id": 2, "name": "CEMIG (LUZ)", "type": "SAIDA", "method": "PIX", "amount": 0.0},
                        {"id": 3, "name": "CRIAR SOFTWARE (SALÁRIO)", "type": "ENTRADA", "method": "Recebimento", "amount": 0.0},
                        {"id": 4, "name": "CLARO (CELULAR)", "type": "SAIDA", "method": "Cartão de Crédito", "amount": 0.0},
                        {"id": 5, "name": "NIO (INTERNET)", "type": "SAIDA", "method": "PIX", "amount": 0.0},
                        {"id": 6, "name": "LP CONNECT (INTERNET)", "type": "SAIDA", "method": "PIX", "amount": 0.0}
                    ]
                        
                    db_main["users"][new_user] = {
                        "password": new_pass,
                        "data": {
                            "accounts": [], "transactions": [], "goals": [], 
                            "templates": default_templates,
                            "settings": {"credit_limit": 5000.0}
                        }
                    }
                    save_db(db_main)
                    st.success("Conta criada! Vá na aba 'Entrar'.")
    st.stop()

# --- CARREGA DADOS DO USUÁRIO ---
username = st.session_state.username
user_data = db_main["users"][username]["data"]

# Verifica e cria a chave de templates se for um usuário antigo
if "templates" not in user_data:
    user_data["templates"] = []

with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/1/12/User_icon_2.svg/800px-User_icon_2.svg.png", width=50)
    st.write(f"Fala, **{username}**!")
    if st.button("Sair da Conta"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

# --- BLOQUEIO INICIAL (ONBOARDING) ---
if not user_data.get("accounts"):
    st.title("Bem-vindo ao campo de batalha! 🐉")
    st.info("Crie sua conta principal e informe o saldo real para iniciarmos as projeções.")
    with st.form("onboarding_form"):
        acc_name = st.text_input("Nome da Instituição (ex: Nubank, Inter)")
        acc_balance = st.number_input("Saldo Atual Real (R$)", value=0.0, step=10.0)
        if st.form_submit_button("Começar"):
            if "accounts" not in user_data:
                user_data["accounts"] = []
            user_data["accounts"].append({"id": 1, "name": acc_name, "initial_balance": acc_balance})
            save_db(db_main)
            st.rerun()
    st.stop()

# --- LÓGICA DE NEGÓCIOS & TEMPO ---
def calculate_real_balance(account_name):
    acc = next((a for a in user_data["accounts"] if a["name"] == account_name), None)
    if not acc: return 0.0
    balance = acc["initial_balance"]
    for t in user_data.get("transactions", []):
        if t["account"] == account_name and t["status"] == "Paid" and not t.get("ignoreBalance", False):
            balance += t["amount"] if t["type"] in ["Income", "ENTRADA"] else -t["amount"]
    return balance

global_balance = sum(calculate_real_balance(a["name"]) for a in user_data["accounts"])

today = datetime.date.today()
str_today = today.strftime("%Y-%m-%d")
str_month = today.strftime("%Y-%m")
str_year = today.strftime("%Y")
one_week_ago = (today - datetime.timedelta(days=7)).strftime("%Y-%m-%d")

# Dicionários para armazenar os totais de tempo
totals = {"ENTRADA": {"dia": 0, "sem": 0, "mes": 0, "ano": 0, "all": 0}, 
          "SAIDA":   {"dia": 0, "sem": 0, "mes": 0, "ano": 0, "all": 0}}

for t in user_data.get("transactions", []):
    amt = t["amount"]
    t_type = "ENTRADA" if t["type"] in ["Income", "ENTRADA"] else "SAIDA"
    
    # Soma ALL TIME (Soma TUDO na Saída. Na Entrada, soma só os Pagos)
    if t_type == "SAIDA" or (t_type == "ENTRADA" and t["status"] == "Paid"):
        totals[t_type]["all"] += amt
        
        # Recortes de tempo
        if t["date"] == str_today: totals[t_type]["dia"] += amt
        if t["date"] >= one_week_ago and t["date"] <= str_today: totals[t_type]["sem"] += amt
        if t["date"].startswith(str_month): totals[t_type]["mes"] += amt
        if t["date"].startswith(str_year): totals[t_type]["ano"] += amt

unpaid_credit = sum(t["amount"] for t in user_data.get("transactions", []) if t["type"] in ["Expense", "SAIDA"] and t.get("is_credit") and t["status"] == "Unpaid")
available_credit = user_data["settings"]["credit_limit"] - unpaid_credit

# --- NAVEGAÇÃO MOBILE-FRIENDLY ---
st.markdown("<h2 style='text-align: center; color: #ff6600;'>Visão Geral</h2>", unsafe_allow_html=True)
tabs = st.tabs(["📊 Painel", "💸 Transações", "➕ Lançar", "🎯 Metas", "📁 Extra"])

# 1. DASHBOARD
with tabs[0]:
    # Cards Globais Coloridos
    custom_card("SALDO GLOBAL ATUAL", format_brl(global_balance), "#007BFF", "#3399ff") # Azul
    
    col_e, col_s = st.columns(2)
    with col_e:
        custom_card("ENTROU (ALL TIME)", format_brl(totals["ENTRADA"]["all"]), "#28a745", "#4dd26b") # Verde
    with col_s:
        custom_card("SAIU (ALL TIME)", format_brl(totals["SAIDA"]["all"]), "#dc3545", "#ff6b7a") # Vermelho
        
    custom_card("LIMITE DE CRÉDITO DISP.", format_brl(available_credit), "#ffc107", "#ffcd39") # Amarelo/Laranja

    # Resumo Temporal
    st.markdown("### 📅 Resumo por Período")
    with st.expander("Ver Entradas e Saídas (Dia/Semana/Mês/Ano)", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("<p style='color:#4dd26b; font-weight:bold;'>🟩 ENTRADAS</p>", unsafe_allow_html=True)
            st.write(f"**Hoje:** {format_brl(totals['ENTRADA']['dia'])}")
            st.write(f"**Últimos 7 dias:** {format_brl(totals['ENTRADA']['sem'])}")
            st.write(f"**Neste Mês:** {format_brl(totals['ENTRADA']['mes'])}")
            st.write(f"**Neste Ano:** {format_brl(totals['ENTRADA']['ano'])}")
        with c2:
            st.markdown("<p style='color:#ff6b7a; font-weight:bold;'>🟥 SAÍDAS</p>", unsafe_allow_html=True)
            st.write(f"**Hoje:** {format_brl(totals['SAIDA']['dia'])}")
            st.write(f"**Últimos 7 dias:** {format_brl(totals['SAIDA']['sem'])}")
            st.write(f"**Neste Mês:** {format_brl(totals['SAIDA']['mes'])}")
            st.write(f"**Neste Ano:** {format_brl(totals['SAIDA']['ano'])}")

# 2. TRANSAÇÕES
with tabs[1]:
    st.markdown("### Histórico de Transações")
    search_term = st.text_input("🔍 Buscar por nome ou valor...").lower()
    
    # Filtra as transações (todas ou pela busca)
    all_t = user_data.get("transactions", [])
    if search_term:
        filtered_t = [t for t in all_t if search_term in t['description'].lower() or search_term in str(t['amount'])]
    else:
        # Pega as 50 últimas se não tiver buscando
        filtered_t = sorted(all_t, key=lambda x: x["id"], reverse=True)[:50]
        st.caption("Mostrando as 50 transações mais recentes. Use a busca para ver mais antigas.")
    
    if not filtered_t:
        st.info("Nenhuma transação encontrada.")
        
    for i, t in enumerate(filtered_t):
        is_income = t["type"] in ["Income", "ENTRADA"]
        color_tag = "🟩" if is_income else "🟥"
        status_txt = "Recebido" if is_income else "Pago"
        
        with st.container():
            st.markdown(f"""
            <div style='background-color: #1e1e1e; padding: 10px; border-radius: 8px; margin-bottom: 5px; border-left: 3px solid {"#4dd26b" if is_income else "#ff6b7a"}'>
                <p style='margin:0; font-size:12px; color:gray;'>ID: {t['id']} | {t['date']} | Conta: {t['account']}</p>
                <div style='display: flex; justify-content: space-between; align-items: center;'>
                    <p style='margin:0; font-weight:bold;'>{t['description']}</p>
                    <p style='margin:0; font-weight:bold; color: {"#4dd26b" if is_income else "#ff6b7a"};'>{color_tag} {format_brl(t['amount'])}</p>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Botões de controle limpos
            btn_col1, btn_col2 = st.columns([1, 1])
            is_paid = (t["status"] == "Paid")
            
            btn_label = f"Desmarcar ({status_txt})" if is_paid else f"Marcar como {status_txt}"
            if btn_col1.button(f"🔄 {btn_label}", key=f"tgl_{t['id']}_{i}"):
                # Atualiza o status na lista original
                for original_t in user_data["transactions"]:
                    if original_t["id"] == t["id"]:
                        original_t["status"] = "Unpaid" if is_paid else "Paid"
                save_db(db_main)
                st.rerun()

# 3. NOVA TRANSAÇÃO & MODELOS (TEMPLATES)
with tabs[2]:
    sub_lancar, sub_modelos = st.tabs(["Lançamento Manual", "Modelos Rápidos (Automático)"])
    
    with sub_lancar:
        t_type = st.radio("Tipo", ["SAIDA", "ENTRADA"], horizontal=True)
        with st.form("form_manual"):
            t_acc = st.selectbox("Conta", [a["name"] for a in user_data["accounts"]])
            if t_type == "SAIDA":
                t_desc = st.text_input("Descrição da Despesa")
                t_method = st.selectbox("Pagamento", ["PIX", "Cartão de Débito", "Cartão de Crédito"])
            else:
                t_desc = st.text_input("Origem (Quem pagou?)")
                t_method = "Recebimento"
                
            t_val = st.number_input("Valor (R$)", min_value=0.01, step=10.0)
            t_date = st.date_input("Data do Ocorrido/1ª Parcela")
            t_installments = st.number_input("Parcelas", min_value=1, value=1)
            t_status = st.selectbox("Status", ["Paid", "Unpaid"], format_func=lambda x: "Efetivado (Pago/Recebido)" if x == "Paid" else "Pendente")
            
            if st.form_submit_button("Salvar Transação"):
                base_date = t_date
                for i in range(t_installments):
                    desc_f = f"{t_desc} ({i+1}/{t_installments})" if t_installments > 1 else t_desc
                    desc_m = f"[{t_method}] {desc_f}" if t_type == "SAIDA" else desc_f
                    is_credit = True if (t_type == "SAIDA" and t_method == "Cartão de Crédito") else False
                    
                    user_data.setdefault("transactions", []).append({
                        "id": len(user_data["transactions"]) + 1,
                        "type": t_type, "account": t_acc, "description": desc_m,
                        "amount": t_val, "date": base_date.strftime("%Y-%m-%d"),
                        "status": t_status, "is_credit": is_credit, "ignoreBalance": False
                    })
                    base_date += relativedelta(months=1)
                save_db(db_main)
                st.success("Lançamento efetuado!")
                st.rerun()

    with sub_modelos:
        st.write("Crie atalhos para suas despesas e receitas frequentes.")
        
        # Botões para os templates existentes
        for tmpl in user_data.get("templates", []):
            with st.container():
                st.markdown(f"**{tmpl['name']}** ({tmpl['type']} via {tmpl['method']})")
                colA, colB = st.columns([3, 1])
                # Permite digitar o valor na hora
                valor_rapido = colA.number_input("Valor R$", min_value=0.0, step=10.0, key=f"val_{tmpl['id']}")
                if colB.button("Lançar", key=f"btn_{tmpl['id']}", use_container_width=True):
                    if valor_rapido > 0:
                        desc_m = f"[{tmpl['method']}] {tmpl['name']}" if tmpl['type'] == "SAIDA" else tmpl['name']
                        is_credit = True if (tmpl['type'] == "SAIDA" and tmpl['method'] == "Cartão de Crédito") else False
                        
                        user_data.setdefault("transactions", []).append({
                            "id": len(user_data.get("transactions", [])) + 1,
                            "type": tmpl['type'], 
                            "account": user_data["accounts"][0]["name"], # Lança na conta principal
                            "description": desc_m,
                            "amount": valor_rapido, 
                            "date": str_today,
                            "status": "Paid", 
                            "is_credit": is_credit, 
                            "ignoreBalance": False
                        })
                        save_db(db_main)
                        st.success(f"Lançado: {tmpl['name']}!")
                        st.rerun()
                    else:
                        st.warning("Insira um valor maior que zero.")
                st.divider()
                
        # Criar novo modelo
        with st.expander("➕ Criar Novo Modelo de Atalho"):
            with st.form("new_template"):
                m_name = st.text_input("Nome do Lançamento Frequente")
                m_type = st.radio("Tipo", ["SAIDA", "ENTRADA"], horizontal=True)
                m_method = st.selectbox("Método", ["PIX", "Cartão de Débito", "Cartão de Crédito", "Recebimento"])
                if st.form_submit_button("Salvar Modelo"):
                    novo_id = len(user_data["templates"]) + 1
                    user_data["templates"].append({
                        "id": novo_id, "name": m_name, "type": m_type, "method": m_method, "amount": 0.0
                    })
                    save_db(db_main)
                    st.rerun()

# 4. METAS
with tabs[3]:
    st.markdown("### Suas Metas Sayjins")
    
    active_goals = [g for g in user_data.get("goals", []) if g.get("status", "Active") == "Active"]
    total_goals_val = sum(g["target"] for g in active_goals)
    
    custom_card("VALOR TOTAL DAS METAS", format_brl(total_goals_val), "#9b59b6", "#c39bd3") # Roxo
    st.write(f"Você possui **{len(active_goals)}** metas pendentes.")
    
    with st.expander("➕ Criar Nova Meta"):
        with st.form("new_goal"):
            g_name = st.text_input("O que você quer conquistar?")
            g_target = st.number_input("Qual o valor alvo (R$)?", min_value=1.0)
            if st.form_submit_button("Adicionar"):
                user_data.setdefault("goals", []).append({"name": g_name, "target": g_target, "status": "Active"})
                save_db(db_main)
                st.rerun()
                
    for i, g in enumerate(user_data.get("goals", [])):
        if g.get("status", "Active") == "Active":
            progress = min(global_balance / g["target"], 1.0) if global_balance > 0 else 0.0
            
            st.markdown(f"**{g['name']}**")
            col_pb, col_bt = st.columns([7, 3])
            col_pb.progress(progress)
            col_pb.caption(f"{format_brl(global_balance)} de {format_brl(g['target'])}")
            
            if col_bt.button("✅ Bateu Meta!", key=f"g_concluir_{i}"):
                g["status"] = "Achieved"
                save_db(db_main)
                st.rerun()
            st.markdown("---")

# 5. EXTRAS (CSV, Config, IA)
with tabs[4]:
    sub_csv, sub_ai, sub_config = st.tabs(["📁 Importar CSV", "🧠 AI Advisor", "⚙️ Configurações"])
    
    with sub_csv:
        st.info("Importa CSV padrão Banco Inter. Atualiza resumos de tempo sem alterar o saldo global.")
        uploaded_files = st.file_uploader("Arquivos CSV", type="csv", accept_multiple_files=True)
        if uploaded_files and st.button("Processar Arquivos"):
            for file in uploaded_files:
                try:
                    df = pd.read_csv(file, encoding='utf-8', sep=';', skiprows=5)
                    df.columns = df.columns.str.strip()
                    for _, row in df.iterrows():
                        if pd.isna(row.get('Data Lançamento')): continue
                        val_str = str(row.get('Valor', '0')).replace('.', '').replace(',', '.')
                        try: amount_val = float(val_str)
                        except: amount_val = 0.0
                        
                        t_type = "SAIDA" if amount_val < 0 else "ENTRADA"
                        desc = str(row.get('Histórico', '')) + " " + str(row.get('Descrição', ''))
                        desc = desc.replace("nan", "").strip()
                        
                        raw_date = str(row.get('Data Lançamento', ''))
                        try: parsed_date = datetime.datetime.strptime(raw_date.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
                        except: parsed_date = raw_date
                            
                        user_data.setdefault("transactions", []).append({
                            "id": len(user_data["transactions"]) + 1, "type": t_type,
                            "account": "CSV Inter", "description": desc,
                            "amount": abs(amount_val), "date": parsed_date,
                            "status": "Paid", "is_credit": False, "ignoreBalance": True
                        })
                    save_db(db_main)
                    st.success(f"Arquivo '{file.name}' importado!")
                except Exception as e:
                    st.error(f"Erro: {e}")
                    
    with sub_ai:
        api_key = st.text_input("Chave API (Gemini)", type="password")
        if api_key and st.button("Gerar Plano"):
            try:
                client = genai.Client(api_key=api_key)
                prompt = f"Saldo: R${global_balance}. Metas pendentes: {[g['name'] for g in active_goals]}. Crie dicas curtas."
                response = client.models.generate_content(model='gemini-1.5-pro', contents=prompt)
                st.write(response.text)
            except Exception as e:
                st.error(f"Erro AI: {e}")
                
    with sub_config:
        st.write("⚙️ **Configurações Gerais**")
        new_limit = st.number_input("Limite Total Crédito (R$)", value=user_data.get("settings", {}).get("credit_limit", 5000.0))
        if st.button("Salvar Limite"):
            user_data.setdefault("settings", {})["credit_limit"] = new_limit
            save_db(db_main)
            st.success("Salvo!")
            st.rerun()
            
        st.warning("Isso apaga TUDO (Lançamentos e Metas) da sua conta.")
        if st.button("Zerar Meu Banco de Dados"):
            user_data["transactions"] = []
            user_data["goals"] = []
            save_db(db_main)
            st.rerun()
