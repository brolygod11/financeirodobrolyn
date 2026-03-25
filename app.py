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

# --- CUSTOM CSS (Geometria, Espaçamentos e Dark Theme) ---
st.markdown("""
    <style>
    .stApp { background-color: #0e0e0e; color: #ffffff; }
    
    /* Botões: Simetria e Visibilidade */
    div.stButton > button {
        background-color: #ff6600 !important;
        color: #000000 !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: bold !important;
        width: 100%;
        height: 45px;
        margin-top: 5px;
        transition: 0.3s;
    }
    div.stButton > button:hover { background-color: #e65c00 !important; color: #ffffff !important; transform: scale(0.98); }
    
    /* Inputs, Selects e Expansores */
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
        border-radius: 8px; background-color: #1a1a1a !important; color: white !important; border: 1px solid #333;
    }
    
    /* Ajuste de Tabs para Mobile */
    button[data-baseweb="tab"] { color: #a0a0a0 !important; font-size: 14px; }
    button[data-baseweb="tab"][aria-selected="true"] { color: #ff6600 !important; border-bottom: 3px solid #ff6600 !important; font-weight: bold; }
    
    /* Ocultar elementos desnecessários do Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

def custom_card(title, value, border_color, text_color):
    st.markdown(f"""
        <div style="background-color: #161616; padding: 18px; border-radius: 12px; border-left: 6px solid {border_color}; margin-bottom: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
            <p style="margin: 0; font-size: 12px; color: #a0a0a0; font-weight: bold; text-transform: uppercase; letter-spacing: 1px;">{title}</p>
            <h3 style="margin: 5px 0 0 0; font-size: 24px; color: {text_color};">{value}</h3>
        </div>
    """, unsafe_allow_html=True)

# --- FIREBASE ---
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(dict(st.secrets["firebase_key"]))
        firebase_admin.initialize_app(cred, {'databaseURL': st.secrets["database_url"]})
    except Exception as e:
        st.error(f"Erro no Firebase. Verifique seus Secrets.")
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
    st.markdown("<h1 style='text-align: center; color: #ff6600; margin-bottom: 30px;'>⚡ Sayjins Finanças</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["Acessar", "Criar Conta"])
    with t1:
        with st.form("login_f"):
            u_in = st.text_input("Usuário")
            p_in = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                u = u_in.strip().lower()
                if u in db_main.get("users", {}) and db_main["users"][u]["password"] == p_in.strip():
                    st.session_state.logged_in = True; st.session_state.username = u; st.rerun()
                else: st.error("Dados incorretos. Verifique letras maiúsculas ou espaços.")
    with t2:
        with st.form("reg_f"):
            nu_in = st.text_input("Novo Usuário")
            np_in = st.text_input("Senha", type="password")
            if st.form_submit_button("Criar Conta"):
                nu = nu_in.strip().lower()
                if nu and np_in:
                    db_main.setdefault("users", {})[nu] = {"password": np_in.strip(), "data": {"accounts": [{"id":1, "name":"Principal", "initial_balance":0.0}], "transactions": [], "goals": [], "fixed_expenses": [], "cofre": 0.0}}
                    save_db(db_main); st.success("Criado com sucesso! Vá em Acessar."); st.rerun()
    st.stop()

# --- CARREGAR DADOS ---
u_name = st.session_state.username
u_data = db_main["users"][u_name]["data"]
u_data.setdefault("fixed_expenses", [])
u_data.setdefault("transactions", [])
u_data.setdefault("cofre", 0.0)

# --- CÁLCULO DE SALDO ---
def get_balance():
    b = sum(a.get("initial_balance", 0) for a in u_data.get("accounts", []))
    for t in u_data["transactions"]:
        if t.get("status") == "Paid" and not t.get("ignoreBalance"):
            b += t["amount"] if t["type"] == "ENTRADA" else -t["amount"]
    return b - u_data["cofre"] # O Cofre segura o dinheiro das metas

global_balance = get_balance()
hoje = datetime.date.today()
str_mes = hoje.strftime("%Y-%m")

# --- NAVEGAÇÃO ---
tabs = st.tabs(["📊 Painel", "💸 Histórico", "➕ Lançar", "🎯 Cofre/Metas", "⚙️ Extra"])

# ==========================================
# 1. PAINEL (DASHBOARD PRO - GRÁFICOS AJUSTADOS)
# ==========================================
with tabs[0]:
    f_mes = st.text_input("Mês Filtro (YYYY-MM)", value=str_mes)
    
    aberto = sum(t["amount"] for t in u_data["transactions"] if t.get("status") == "Unpaid" and t.get("type") == "SAIDA" and str(t.get("date", "")).startswith(f_mes))
    pago_mes = sum(t["amount"] for t in u_data["transactions"] if t.get("status") == "Paid" and t.get("type") == "SAIDA" and str(t.get("date", "")).startswith(f_mes))
    entrou_mes = sum(t["amount"] for t in u_data["transactions"] if t.get("status") == "Paid" and t.get("type") == "ENTRADA" and str(t.get("date", "")).startswith(f_mes))
    
    c1, c2 = st.columns(2)
    with c1: custom_card("SALDO LIVRE", format_brl(global_balance), "#007BFF", "#3399ff")
    with c2: custom_card(f"ABERTO ({f_mes})", format_brl(aberto), "#ffc107", "#ffcd39")

    # Gráficos Geométricos
    st.markdown("### 📈 Visão Gráfica")
    
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        if aberto > 0 or pago_mes > 0:
            fig_pie = go.Figure(data=[go.Pie(labels=['Já Pago', 'Em Aberto'], values=[pago_mes, aberto], hole=.6, marker_colors=['#4dd26b', '#ffc107'], textinfo='none')])
            fig_pie.update_layout(
                title=dict(text="Despesas", font=dict(size=14, color="white")),
                showlegend=True, legend=dict(orientation="h", yanchor="top", y=1.1, xanchor="center", x=0.5, font=dict(size=10, color="white")),
                paper_bgcolor='#161616', plot_bgcolor='#161616', margin=dict(t=50, b=10, l=10, r=10), height=280
            )
            st.plotly_chart(fig_pie, use_container_width=True, config={'displayModeBar': False})
        else:
            st.info("Sem despesas no mês.")
            
    with col_g2:
        if entrou_mes > 0 or (aberto + pago_mes) > 0:
            fig_bar = go.Figure(data=[
                go.Bar(name='Receitas', x=['Balanço'], y=[entrou_mes], marker_color='#4dd26b', textposition='none', width=0.4),
                go.Bar(name='Despesas', x=['Balanço'], y=[aberto + pago_mes], marker_color='#ff6b7a', textposition='none', width=0.4)
            ])
            fig_bar.update_layout(
                barmode='group',
                title=dict(text="Balanço", font=dict(size=14, color="white")),
                paper_bgcolor='#161616', plot_bgcolor='#161616', margin=dict(t=50, b=10, l=10, r=10), height=280,
                xaxis=dict(showgrid=False, showticklabels=False), yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
                showlegend=True, legend=dict(orientation="h", yanchor="top", y=1.1, xanchor="center", x=0.5, font=dict(size=10, color="white"))
            )
            st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False})
        else:
            st.info("Sem saldo no mês.")

    st.markdown("### 📅 Pagos no Mês")
    pagos = [t for t in u_data["transactions"] if t.get("status") == "Paid" and t.get("type") == "SAIDA" and str(t.get("date", "")).startswith(f_mes)]
    if pagos:
        for t in sorted(pagos, key=lambda x: x['date'], reverse=True):
            st.markdown(f"<div style='background-color:#161616; padding:12px; border-radius:8px; border-left:4px solid #4dd26b; margin-bottom:8px; font-size:13px;'>{t['date']} | {t['description']} | <b>{format_brl(t['amount'])}</b></div>", unsafe_allow_html=True)
    else: st.caption("Nenhum pagamento efetivado no filtro.")

# ==========================================
# 2. HISTÓRICO (COM EXCLUSÃO EM MASSA)
# ==========================================
with tabs[1]:
    st.write("### Últimas Movimentações")
    all_t = sorted(u_data["transactions"], key=lambda x: x.get('id', 0), reverse=True)
    
    for i, t in enumerate(all_t[:30]):
        is_in = t["type"] == "ENTRADA"
        cor = "#4dd26b" if is_in else "#ff6b7a"
        grp = t.get("group_id")
        
        with st.container():
            st.markdown(f"<div style='background-color:#161616; padding:12px; border-radius:8px; border-left:4px solid {cor}; margin-bottom:5px; font-size:13px;'>{t['date']} - {t['description']} - <b style='color:{cor}'>{format_brl(t['amount'])}</b></div>", unsafe_allow_html=True)
            
            c_del1, c_del2 = st.columns(2)
            if c_del1.button("🗑️ Excluir", key=f"d1_{t['id']}_{i}"):
                u_data["transactions"] = [tr for tr in u_data["transactions"] if tr.get('id') != t.get('id')]
                save_db(db_main); st.rerun()
            
            if grp:
                if c_del2.button("⚠️ Excluir Parcelamento", key=f"d2_{t['id']}_{i}"):
                    u_data["transactions"] = [tr for tr in u_data["transactions"] if tr.get('group_id') != grp]
                    save_db(db_main); st.rerun()
            st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# 3. LANÇAR (COM IFOOD VR)
# ==========================================
with tabs[2]:
    m_man, m_fix = st.tabs(["Lançamento Manual", "Contas Fixas"])
    
    with m_man:
        op = st.radio("Operação", ["SAIDA", "ENTRADA"], horizontal=True)
        desc = st.text_input("Descrição do Lançamento")
        if desc:
            v = st.number_input("Valor R$", min_value=0.01)
            
            if op == "SAIDA":
                metodo = st.selectbox("Método", ["PIX", "Cartão de Débito", "Cartão de Crédito", "Vale iFood (VR/VA)"])
                if metodo == "Cartão de Crédito":
                    d = st.date_input("Vencimento 1ª Parcela")
                    inst = st.number_input("Parcelas", min_value=1, value=1)
                else:
                    d = st.date_input("Data do Gasto")
                    inst = 1
                
                status_idx = 1 if metodo == "Cartão de Crédito" else 0
                st_sel = st.selectbox("Status", ["Paid", "Unpaid"], index=status_idx, format_func=lambda x: "Efetivado" if x=="Paid" else "Em Aberto")
            else:
                metodo = "Recebimento"
                d = st.date_input("Data")
                inst = 1
                st_sel = st.selectbox("Status", ["Paid", "Unpaid"], format_func=lambda x: "Recebido" if x=="Paid" else "Pendente")

            if st.button("🚀 Confirmar Lançamento"):
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
                save_db(db_main); st.success("Lançado!"); st.rerun()

    with m_fix:
        for fixa in u_data["fixed_expenses"]:
            with st.expander(f"📁 {fixa['name']}"):
                col1, col2 = st.columns(2)
                fv = col1.number_input("Valor", key=f"v_{fixa['id']}")
                fd = col2.date_input("Vencimento", key=f"d_{fixa['id']}")
                if st.button("Lançar no Mês", key=f"b_{fixa['id']}"):
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
                
                if st.button("🗑️ Deletar Categoria", key=f"del_cat_{fixa['id']}"):
                    u_data["fixed_expenses"] = [f for f in u_data["fixed_expenses"] if f["id"] != fixa["id"]]
                    save_db(db_main); st.rerun()

        st.markdown("---")
        nf = st.text_input("Nova Gaveta Fixa (Ex: LUZ)")
        if st.button("Criar Gaveta"):
            new_id_f = max([f.get('id', 0) for f in u_data["fixed_expenses"]], default=0) + 1
            u_data["fixed_expenses"].append({"id": new_id_f, "name": nf.upper()})
            save_db(db_main); st.rerun()

# ==========================================
# 4. METAS E COFRE
# ==========================================
with tabs[3]:
    st.write("### 🔒 Meu Cofre")
    custom_card("SALDO NO COFRE", format_brl(u_data["cofre"]), "#9b59b6", "#c39bd3")
    
    with st.expander("Movimentar Cofre"):
        c_op = st.radio("Operação", ["Guardar", "Resgatar (Devolver ao Saldo)"], horizontal=True)
        c_val = st.number_input("Valor R$", min_value=0.01)
        if st.button("Confirmar Movimentação"):
            if c_op == "Guardar":
                if c_val <= global_balance:
                    u_data["cofre"] += c_val
                    save_db(db_main); st.success("Guardado!"); st.rerun()
                else: st.error("Saldo Livre insuficiente.")
            else:
                if c_val <= u_data["cofre"]:
                    u_data["cofre"] -= c_val
                    save_db(db_main); st.success("Resgatado!"); st.rerun()
                else: st.error("Você não tem esse valor no cofre.")
                
    st.markdown("---")
    st.write("### 🎯 Minhas Metas")
    
    if st.button("➕ Nova Meta"): st.session_state.nm = True
    if st.session_state.get("nm"):
        with st.form("fm"):
            nn = st.text_input("Objetivo"); vv = st.number_input("Alvo R$")
            if st.form_submit_button("Salvar Meta"):
                u_data.setdefault("goals", []).append({"name": nn, "target": vv, "status": "Active"})
                save_db(db_main); st.session_state.nm = False; st.rerun()
                
    for i, g in enumerate(u_data.get("goals", [])):
        if g.get("status") == "Active":
            prog = max(0.0, min(u_data["cofre"] / g["target"], 1.0)) if g["target"] > 0 else 0.0
            st.write(f"**{g['name']}**")
            st.progress(prog)
            st.caption(f"{format_brl(u_data['cofre'])} / {format_brl(g['target'])}")
            if st.button("✅ Concluir Meta", key=f"m_{i}"):
                g["status"] = "Achieved"; save_db(db_main); st.rerun()

# ==========================================
# 5. EXTRA (IA À PROVA DE FALHAS & CSV)
# ==========================================
with tabs[4]:
    s_ai, s_csv, s_config = st.tabs(["🧠 IA", "📁 CSV", "⚙️ Sis"])
    with s_ai:
        st.write("Análise Financeira IA")
        ak = st.text_input("Chave API Gemini", type="password")
        if ak and st.button("Analisar"):
            try:
                c = genai.Client(api_key=ak)
                prompt_text = f"Meu saldo livre: R${global_balance}. Cofre: R${u_data['cofre']}. Metas: {[g['name'] for g in u_data.get('goals', [])]}. Analise curto e direto."
                
                # Sistema de Fallback da IA (Tenta o mais atual, se falhar tenta o pro, se falhar tenta o gemini-2.0-flash padrão)
                try:
                    res = c.models.generate_content(model='gemini-2.0-flash', contents=prompt_text)
                except:
                    try:
                        res = c.models.generate_content(model='gemini-1.5-pro-latest', contents=prompt_text)
                    except:
                        res = c.models.generate_content(model='gemini-pro', contents=prompt_text)
                        
                st.write(res.text)
            except Exception as e: 
                st.error(f"Sua chave de API pode estar inválida ou sem cota. Erro técnico: {e}")
            
    with s_csv:
        up = st.file_uploader("Subir CSV", type="csv", accept_multiple_files=True)
        if up and st.button("Processar"):
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
        if st.button("🚪 Sair da Conta"): st.session_state.logged_in = False; st.rerun()
        st.write("---")
        if st.button("🚨 ZERAR TUDO"): u_data["transactions"] = []; u_data["goals"] = []; u_data["cofre"] = 0; save_db(db_main); st.rerun()
