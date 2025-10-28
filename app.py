import streamlit as st

from core import DB_DEFAULT
from tabs import dashboard, current_game, games, ranking

st.set_page_config(page_title="GAS", page_icon="🛳️", layout="wide")
st.title("🎯 GAS — Game Analyst System")

db_path = DB_DEFAULT
auto = True
interval_s = 1

# --- Pills navigation
LABELS = ['📊 Dashboard', '🟢 Partida Atual', '🗂 Games', '🏆 Ranking']

PLOT_CONFIG = {"displayModeBar": False}

# Initialize once
if "active_pill" not in st.session_state:
    st.session_state["active_pill"] = LABELS[0]

# Use a key so Streamlit manages the state; no manual session_state writes
st.pills(
    "Navigation",
    LABELS,
    selection_mode='single',
    key='active_pill',
    label_visibility='hidden', 
)

choice = st.session_state["active_pill"]  # current selection

# --- Route to tab modules
if choice == '📊 Dashboard':
    dashboard.render(db_path)
elif choice == '🟢 Partida Atual':
    current_game.render(db_path, auto=auto, interval_s=interval_s)
elif choice == '🗂 Games':
    games.render(db_path)
elif choice == '🏆 Ranking':
    ranking.render(db_path)