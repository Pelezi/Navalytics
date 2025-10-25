# tabs/ranking.py
import streamlit as st
from core import top_highscores, render_ranking_podium_plus_list

def render(db_path: str):
    rank = top_highscores(db_path, limit=10)
    if rank.empty:
        st.info("Sem dados de Ranking ainda — jogue algumas partidas!")
    else:
        render_ranking_podium_plus_list(rank, limit=10)