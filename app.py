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
    button[data-baseweb="tab"][aria-selected="true"] { color: #ff6600 !important; border-bottom: 3px solid #ff6600
