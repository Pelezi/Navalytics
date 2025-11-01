import streamlit as st

from core import DB_DEFAULT
from tabs import dashboard, current_game, games, ranking

st.set_page_config(page_title="GAS - Game Analyst System", page_icon="🛳️", layout="wide")

# Reduce title margins
st.markdown("""
    <style>
        .stMainBlockContainer {
            padding-top: 1.5rem !important;
        }
    </style>
""", unsafe_allow_html=True)

db_path = DB_DEFAULT
auto = True
interval_s = 1

# --- Pills navigation
LABELS = ['📊 Dashboard', '🟢 Partida Atual', '🗂 Histórico', '🏆 Ranking']

PLOT_CONFIG = {"displayModeBar": False}

# Use a key so Streamlit manages the state automatically
st.pills(
    "Navigation",
    LABELS,
    selection_mode='single',
    key='active_pill',
    default=LABELS[0],
    label_visibility='hidden', 
)

choice = st.session_state["active_pill"]  # current selection

# --- Route to tab modules
if choice == '📊 Dashboard':
    dashboard.render(db_path)
elif choice == '🟢 Partida Atual':
    current_game.render(db_path, auto=auto, interval_s=interval_s)
elif choice == '🗂 Histórico':
    games.render(db_path)
elif choice == '🏆 Ranking':
    ranking.render(db_path)