import streamlit as st
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
from google import genai
import firebase_admin
from firebase_admin import credentials, db
import plotly.graph_objects as go
import uuid

# --- CONFIGURAÇÃO DA PÁGINA (Mobile-First 9:16) ---
st.set_page_config(page_title="Financeiro Sayjins", layout="centered", initial_sidebar_state="collapsed")

# --- CUSTOM CSS (Design Premium e Geométrico) ---
st.markdown("""
    <style>
    /* Fundo Escuro Profundo */
    .stApp { background-color: #0c0c0c; color: #ffffff; }
    
    /* Botões: Fundo Laranja, Texto Preto, Animação de Clique */
    div.stButton > button {
        background-color: #ff6600 !important;
        color: #000000 !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: bold !important;
        width: 100%;
        height: 48px;
        margin-top: 5px;
        transition: all 0.2s ease-in-out;
        box-shadow: 0 4px 6px rgba(255, 102, 0, 0.2);
    }
    div.stButton > button:hover { 
        background-color: #e65c00 !important; 
        color: #ffffff !important; 
        transform: scale(0.98); 
    }
    
    /* Inputs, Selects com Bordas Arredondadas Modernas */
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
        border-radius: 8px; 
        background-color: #1a1a1a !important; 
        color: white !important; 
        border: 1px solid #333;
    }
    
    /* Abas Nativas do Streamlit Otimizadas para Toque */
    button[data-baseweb="tab"] { color: #888888 !important; font-size: 14px; padding: 10px 15px; }
    button[data-baseweb="tab"][aria-selected="true"] { 
        color: #ff6600 !important; 
        border-bottom: 3px solid #ff6600 !important; 
        font-weight: bold; 
    }
    
    /* Ocultar lixo visual do Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# Função para Cards Modulares (Estilo Fintech)
def custom_card(title, value, border_color, text_color):
    st.markdown(f"""
        <div style="background-color: #161616; padding: 20px; border-radius: 12px; border-left: 6px solid {border_color}; margin-bottom: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.5);">
            <p style="margin: 0; font-size: 11px; color: #888888; font-weight: bold; text-transform: uppercase; letter-spacing: 1px;">{title}</p>
            <h3 style="margin: 8px 0 0 0; font-size: 26px; font-weight: 800; color: {text_color};">{value}</h3>
        </div>
    """, unsafe_allow_html=True)

# --- FIREBASE ---
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(dict(st.secrets["firebase_key"]))
        firebase_admin.initialize_app(cred, {'databaseURL': st.secrets["database_url"]})
    except Exception as e:
        st.error(f"Falha de Comunicação com o Servidor de Dados.")
        st.stop()

def load_db(): return db.reference('/').get() or {"users": {}}
def save_db(db_main): db.reference('/').set(db_main)
def format_brl(value): return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

if 'db_main' not in st.session_state: st.session_state.db_main = load_db()
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

db_main = st.session_state.db_main

# --- TELA DE LOGIN BLINDADA ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #ff6600; margin-top: 40px; margin-bottom: 40px;'>⚡ Sayjins Finanças</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["Acessar Conta", "Criar Nova Conta"])
    with t1:
        with st.form("login_f"):
            u_in = st.text_input("Nome de Usuário")
            p_in = st.text_input("Senha de Acesso", type="password")
            if st.form_submit_button("Entrar no Sistema"):
                u = u_in.strip().lower() # Evita erros de teclado de celular
                if u in db_main.get("users", {}) and db_main["users"][u]["password"] == p_in.strip():
                    st.session_state.logged_in = True; st.session_state.username = u; st.rerun()
                else: st.error("Acesso Negado. Verifique os dados inseridos.")
    with t2:
        with st.form("reg_f"):
            nu_in = st.text_input("Novo Usuário")
            np_in = st.text_input("Criar Senha Segura", type="password")
            if st.form_submit_button("Registrar Conta"):
                nu = nu_in.strip().lower()
                if nu and np_in:
                    db_main.setdefault("users", {})[nu] = {"password": np_in.strip(), "data": {"accounts": [{"id":1, "name":"Principal", "initial_balance":0.0}], "transactions": [], "goals": [], "fixed_expenses": [], "cofre": 0.0}}
                    save_db(db_main); st.success("Conta Sayjin criada! Acesse pelo menu ao lado."); st.rerun()
    st.stop()

# --- CARREGAR DADOS DO USUÁRIO LOGADO ---
u_name = st.session_state.username
u_data = db_main["users"][u_name]["data"]
u_data.setdefault("fixed_expenses", [])
u_data.setdefault("transactions", [])
u_data.setdefault("cofre", 0.0)

# --- MATEMÁTICA CENTRAL (SALDO E COFRE) ---
def get_balance():
    b = sum(a.get("initial_balance", 0) for a in u_data.get("accounts", []))
    for t in u_data["transactions"]:
        if t.get("status") == "Paid" and not t.get("ignoreBalance"):
            b += t["amount"] if t["type"] == "ENTRADA" else -t["amount"]
    return b - u_data["cofre"] # Subtrai o dinheiro guardado no cofre

global_balance = get_balance()
hoje = datetime.date.today()
str_mes = hoje.strftime("%Y-%m")

# --- NAVEGAÇÃO PRINCIPAL ---
tabs = st.tabs(["📊 Painel", "💸 Histórico", "➕ Lançar", "🎯 Cofre/Metas", "⚙️ Sis/IA"])

# ==========================================
# 1. DASHBOARD PRO (GRÁFICOS AMPLIADOS)
# ==========================================
with tabs[0]:
    f_mes = st.text_input("Calendário (YYYY-MM)", value=str_mes)
    
    # Cálculos Dinâmicos
    aberto = sum(t["amount"] for t in u_data["transactions"] if t.get("status") == "Unpaid" and t.get("type") == "SAIDA" and str(t.get("date", "")).startswith(f_mes))
    pago_mes = sum(t["amount"] for t in u_data["transactions"] if t.get("status") == "Paid" and t.get("type") == "SAIDA" and str(t.get("date", "")).startswith(f_mes))
    entrou_mes = sum(t["amount"] for t in u_data["transactions"] if t.get("status") == "Paid" and t.get("type") == "ENTRADA" and str(t.get("date", "")).startswith(f_mes))
    
    # Resumo
    c1, c2 = st.columns(2)
    with c1: custom_card("SALDO LIVRE", format_brl(global_balance), "#007BFF", "#3399ff")
    with c2: custom_card(f"ABERTO ({f_mes})", format_brl(aberto), "#ffc107", "#ffcd39")

    # Área de Gráficos (Estilo App Nativo)
    st.markdown("### 📈 Inteligência Visual")
    
    if aberto > 0 or pago_mes > 0:
        fig_pie = go.Figure(data=[go.Pie(
            labels=['Já Pago', 'Em Aberto'], 
            values=[pago_mes, aberto], 
            hole=.75, 
            marker=dict(colors=['#4dd26b', '#ffc107'], line=dict(color='#0c0c0c', width=4)),
            textinfo='percent',
            textposition='outside',
            textfont=dict(color='white')
        )])
        fig_pie.update_layout(
            title=dict(text="Situação das Contas", font=dict(size=18, color="white")),
            showlegend=True, 
            legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5, font=dict(color="white")),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
            margin=dict(t=40, b=20, l=10, r=10), height=320
        )
        fig_pie.add_annotation(text="<b>Despesas</b>", x=0.5, y=0.5, font_size=16, font_color="white", showarrow=False)
        st.plotly_chart(fig_pie, use_container_width=True, config={'displayModeBar': False})
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    if entrou_mes > 0 or (aberto + pago_mes) > 0:
        fig_bar = go.Figure(data=[
            go.Bar(name='Receitas', x=['Movimentação'], y=[entrou_mes], marker_color='#4dd26b', text=[format_brl(entrou_mes)], textposition='auto', width=0.4),
            go.Bar(name='Despesas', x=['Movimentação'], y=[aberto + pago_mes], marker_color='#ff6b7a', text=[format_brl(aberto + pago_mes)], textposition='auto', width=0.4)
        ])
        fig_bar.update_layout(
            barmode='group',
            title=dict(text="Balanço do Mês", font=dict(size=18, color="white")),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
            margin=dict(t=40, b=20, l=10, r=10), height=320,
            xaxis=dict(showgrid=False, showticklabels=False), 
            yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
            showlegend=True, 
            legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5, font=dict(color="white"))
        )
        st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False})
        
    st.markdown("---")
    st.markdown("### 📅 Contas Pagas Recentes")
    pagos = [t for t in u_data["transactions"] if t.get("status") == "Paid" and t.get("type") == "SAIDA" and str(t.get("date", "")).startswith(f_mes)]
    if pagos:
        for t in sorted(pagos, key=lambda x: x['date'], reverse=True)[:10]:
            st.markdown(f"<div style='background-color:#161616; padding:15px; border-radius:10px; border-left:5px solid #4dd26b; margin-bottom:10px;'><p style='margin:0; font-size:12px; color:#888;'>{t['date']}</p><p style='margin:0; font-size:16px;'><b>{t['description']}</b> <span style='float:right; color:#4dd26b;'>{format_brl(t['amount'])}</span></p></div>", unsafe_allow_html=True)
    else: st.caption("Nenhum pagamento registrado no calendário.")

# ==========================================
# 2. HISTÓRICO (EXCLUSÃO EM MASSA)
# ==========================================
with tabs[1]:
    st.write("### Auditoria de Lançamentos")
    all_t = sorted(u_data["transactions"], key=lambda x: x.get('id', 0), reverse=True)
    
    for i, t in enumerate(all_t[:50]):
        cor = "#4dd26b" if t["type"] == "ENTRADA" else "#ff6b7a"
        grp = t.get("group_id")
        
        with st.container():
            st.markdown(f"<div style='background-color:#161616; padding:15px; border-radius:10px; border-left:5px solid {cor}; margin-bottom:5px;'><p style='margin:0; font-size:12px; color:#888;'>Data: {t['date']}</p><p style='margin:0; font-size:15px;'>{t['description']} <br><b style='color:{cor}'>{format_brl(t['amount'])}</b></p></div>", unsafe_allow_html=True)
            
            c_del1, c_del2 = st.columns(2)
            if c_del1.button("🗑️ Apagar Lançamento", key=f"d1_{t['id']}_{i}"):
                u_data["transactions"] = [tr for tr in u_data["transactions"] if tr.get('id') != t.get('id')]
                save_db(db_main); st.rerun()
            
            if grp:
                if c_del2.button("⚠️ Apagar Parcelamento", key=f"d2_{t['id']}_{i}"):
                    u_data["transactions"] = [tr for tr in u_data["transactions"] if tr.get('group_id') != grp]
                    save_db(db_main); st.rerun()
            st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# 3. MÓDULO DE LANÇAMENTO E IFOOD
# ==========================================
with tabs[2]:
    m_man, m_fix = st.tabs(["Nova Transação", "Despesas Fixas"])
    
    with m_man:
        op = st.radio("Selecione o Fluxo", ["SAIDA", "ENTRADA"], horizontal=True)
        desc = st.text_input("Qual o motivo do lançamento?")
        if desc:
            v = st.number_input("Valor R$", min_value=0.01)
            
            if op == "SAIDA":
                metodo = st.selectbox("Método de Pagamento", ["PIX", "Cartão de Débito", "Cartão de Crédito", "Vale Benefício (iFood/VA)"])
                if metodo == "Cartão de Crédito":
                    d = st.date_input("Vencimento da 1ª Parcela")
                    inst = st.number_input("Parcelas", min_value=1, value=1)
                else:
                    d = st.date_input("Data do Ocorrido")
                    inst = 1
                
                status_idx = 1 if metodo == "Cartão de Crédito" else 0
                st_sel = st.selectbox("Status Contábil", ["Paid", "Unpaid"], index=status_idx, format_func=lambda x: "Efetivado (Descontar Saldo)" if x=="Paid" else "Em Aberto (Pendente)")
            else:
                metodo = "Receita"
                d = st.date_input("Data")
                inst = 1
                st_sel = st.selectbox("Status", ["Paid", "Unpaid"], format_func=lambda x: "Já Recebi" if x=="Paid" else "Vou Receber")

            if st.button("🚀 Processar"):
                base_date = d
                g_id = str(uuid.uuid4()) if inst > 1 else None 
                
                for i in range(inst):
                    dfinal = f"{desc} ({i+1}/{inst})" if inst > 1 else desc
                    new_id = max([t.get('id', 0) for t in u_data["transactions"]], default=0) + 1
                    u_data["transactions"].append({
                        "id": new_id, "type": op, "description": f"[{metodo}] {dfinal}", 
                        "amount": v, "date": base_date.strftime("%Y-%m-%d"), 
                        "status": st_sel, "ignoreBalance": False, "group_id": g_id
                    })
                    base_date += relativedelta(months=1)
                save_db(db_main); st.success("Registrado com Sucesso!"); st.rerun()

    with m_fix:
        st.write("### Gavetas de Cobrança")
        for fixa in u_data["fixed_expenses"]:
            with st.expander(f"📁 {fixa['name']}"):
                col1, col2 = st.columns(2)
                fv = col1.number_input("Valor da Fatura", key=f"v_{fixa['id']}")
                fd = col2.date_input("Data Vencimento", key=f"d_{fixa['id']}")
                if st.button("Lançar Fatura", key=f"b_{fixa['id']}"):
                    new_id = max([t.get('id', 0) for t in u_data["transactions"]], default=0) + 1
                    u_data["transactions"].append({"id": new_id, "type": "SAIDA", "description": f"[Fixo] {fixa['name']}", "amount": fv, "date": fd.strftime("%Y-%m-%d"), "status": "Unpaid", "ignoreBalance": False, "fixed_id": fixa['id']})
                    save_db(db_main); st.rerun()
                
                hist = [t for t in u_data["transactions"] if t.get("fixed_id") == fixa['id']]
                for t in sorted(hist, key=lambda x: x['date'], reverse=True):
                    cA, cB = st.columns([3,1])
                    if t["status"] == "Unpaid":
                        cA.write(f"🔴 {t['date']} | {format_brl(t['amount'])}")
                        if cB.button("Pagar", key=f"p_{t['id']}"):
                            t["status"] = "Paid"; save_db(db_main); st.rerun()
                    else: cA.write(f"🟢 {t['date']} | {format_brl(t['amount'])}")
                
                st.markdown("---")
                if st.button("🗑️ Deletar Gaveta Definitivamente", key=f"del_cat_{fixa['id']}"):
                    u_data["fixed_expenses"] = [f for f in u_data["fixed_expenses"] if f["id"] != fixa["id"]]
                    save_db(db_main); st.rerun()

        st.markdown("---")
        nf = st.text_input("Nome da Nova Despesa Fixa")
        if st.button("Criar Nova Gaveta"):
            new_id_f = max([f.get('id', 0) for f in u_data["fixed_expenses"]], default=0) + 1
            u_data["fixed_expenses"].append({"id": new_id_f, "name": nf.upper()})
            save_db(db_main); st.rerun()

# ==========================================
# 4. GESTÃO DE PATRIMÔNIO (COFRE E METAS)
# ==========================================
with tabs[3]:
    st.write("### 🔒 Cofre Pessoal")
    custom_card("RESERVA NO COFRE", format_brl(u_data["cofre"]), "#9b59b6", "#c39bd3")
    
    with st.expander("Operar Cofre", expanded=False):
        c_op = st.radio("Ação", ["Guardar Dinheiro", "Resgatar Dinheiro"], horizontal=True)
        c_val = st.number_input("Valor da Operação", min_value=0.01)
        if st.button("Executar Operação"):
            if c_op == "Guardar Dinheiro":
                if c_val <= global_balance:
                    u_data["cofre"] += c_val
                    save_db(db_main); st.success("Dinheiro protegido no cofre!"); st.rerun()
                else: st.error("Você não tem esse Saldo Livre disponível.")
            else:
                if c_val <= u_data["cofre"]:
                    u_data["cofre"] -= c_val
                    save_db(db_main); st.success("Dinheiro voltou pro Saldo Livre!"); st.rerun()
                else: st.error("O Cofre não possui esse valor para resgate.")
                
    st.markdown("---")
    st.write("### 🎯 Objetivos de Vida")
    st.caption("O progresso das metas é alimentado exclusivamente pela sua Reserva no Cofre.")
    
    if st.button("➕ Adicionar Novo Objetivo"): st.session_state.nm = True
    if st.session_state.get("nm"):
        with st.form("fm"):
            nn = st.text_input("Qual o seu sonho?"); vv = st.number_input("Custo Estimado (R$)")
            if st.form_submit_button("Iniciar Missão"):
                u_data.setdefault("goals", []).append({"name": nn, "target": vv, "status": "Active"})
                save_db(db_main); st.session_state.nm = False; st.rerun()
                
    for i, g in enumerate(u_data.get("goals", [])):
        if g.get("status") == "Active":
            prog = max(0.0, min(u_data["cofre"] / g["target"], 1.0)) if g["target"] > 0 else 0.0
            st.markdown(f"**{g['name']}**")
            st.progress(prog)
            st.caption(f"Status: {format_brl(u_data['cofre'])} guardado de {format_brl(g['target'])}")
            if st.button("✅ Missão Cumprida", key=f"m_{i}"):
                g["status"] = "Achieved"; save_db(db_main); st.rerun()
            st.markdown("---")

# ==========================================
# 5. SISTEMA E INTELIGÊNCIA ARTIFICIAL
# ==========================================
with tabs[4]:
    s_ai, s_csv, s_config = st.tabs(["🧠 IA", "📁 Arquivos", "⚙️ Configurações"])
    
    with s_ai:
        st.write("### Auditoria por IA")
        st.caption("Insira sua chave do Google AI Studio. O sistema fará múltiplas tentativas para encontrar o modelo compatível.")
        ak = st.text_input("Chave API de Desenvolvedor", type="password")
        if ak and st.button("Iniciar Análise Financeira"):
            with st.spinner("Conectando ao núcleo do Google Gemini..."):
                try:
                    c = genai.Client(api_key=ak)
                    prompt_text = f"Resumo rápido: Saldo R${global_balance}. Cofre R${u_data['cofre']}. Analise isso como um gestor financeiro rigoroso."
                    
                    # SISTEMA DE FALLBACK (BLINDAGEM CONTRA O ERRO 404)
                    modelos_disponiveis = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-1.0-pro', 'gemini-2.0-flash']
                    resposta = None
                    
                    for modelo in modelos_disponiveis:
                        try:
                            resposta = c.models.generate_content(model=modelo, contents=prompt_text)
                            if resposta: break
                        except:
                            continue # Pula para o próximo modelo se der erro 404
                    
                    if resposta:
                        st.success("Análise Concluída.")
                        st.write(resposta.text)
                    else:
                        st.error("⚠️ Falha Crítica: Sua chave não autorizou o uso de nenhum modelo de texto. Acesse o AI Studio e gere uma nova chave de API.")
                except Exception as e: 
                    st.error(f"Erro do Sistema: {e}")
            
    with s_csv:
        st.write("### Migração de Dados")
        up = st.file_uploader("Subir Extrato Bancário (CSV)", type="csv", accept_multiple_files=True)
        if up and st.button("Sincronizar Dados"):
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
                    except: p_date = hoje.strftime("%Y-%m-%d")
                    new_id = max([t.get('id', 0) for t in u_data["transactions"]], default=0) + 1
                    u_data["transactions"].append({"id": new_id, "type": t_t, "description": desc, "amount": v_v, "date": p_date, "status": "Paid", "ignoreBalance": True})
                save_db(db_main)
            st.rerun()
            
    with s_config:
        st.write("### Painel de Controle")
        if st.button("🚪 Encerrar Sessão"): st.session_state.logged_in = False; st.rerun()
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.warning("Ação Irreversível:")
        if st.button("🚨 FORMATAR BANCO DE DADOS"): u_data["transactions"] = []; u_data["goals"] = []; u_data["cofre"] = 0; save_db(db_main); st.rerun()
