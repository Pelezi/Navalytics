# tabs/games.py
import streamlit as st
from core import games_list

def render(db_path: str):
    all_tbl = games_list(db_path)
    if all_tbl.empty:
        st.info("Sem partidas.")
    else:
        st.dataframe(all_tbl, use_container_width=True, height=380)