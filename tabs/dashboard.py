# tabs/dashboard.py
import streamlit as st
import pandas as pd
from core import (
    sql_df, games_list, get_avg_duration_ms, accuracy_global,
    starter_win_rate, avg_first_hit_seconds, ms_to_mmss
)

def render(db_path: str):
    colA, colB, colC, colD, colE, colF = st.columns(6)

    # total games
    df_games = sql_df(db_path, "SELECT COUNT(*) AS n_games FROM (SELECT DISTINCT gid FROM games)")
    n_games = int(df_games.iloc[0]["n_games"] or 0)
    colA.metric("Partidas", n_games)

    # avg duration
    avg_dur = get_avg_duration_ms(db_path)
    colB.metric("Tempo Médio", ms_to_mmss(avg_dur))

    # shots / game
    df_spg = sql_df(db_path, "SELECT AVG(cnt) AS spg FROM (SELECT gid, COUNT(*) AS cnt FROM shots GROUP BY gid)")
    spg = float(df_spg.iloc[0]["spg"]) if not df_spg.empty and not pd.isna(df_spg.iloc[0]["spg"]) else None
    colC.metric("Tiros / Partida", f"{spg:.2f}" if spg is not None else "—")

    # global accuracy
    acc = accuracy_global(db_path)
    colD.metric("Taxa de Acerto (global)", f"{acc*100:.1f}%" if acc is not None else "—")

    # starter win rate
    wr = starter_win_rate(db_path)
    colE.metric("Win Rate de quem começa", f"{wr*100:.1f}%" if wr is not None else "—")

    # avg time to first hit
    af = avg_first_hit_seconds(db_path)
    colF.metric("Hunt→Target (1º acerto) — tempo médio", f"{af:.2f}s" if af is not None else "—")

    st.divider()

    st.subheader("Últimas partidas")
    tbl = games_list(db_path).copy()
    if tbl.empty:
        st.info("Ainda não há partidas registradas.")
        return

    tbl["gid_short"] = tbl["gid"].str.slice(0,8) + "…"
    for p in (1,2):
        shots, hits = f"p{p}_shots", f"p{p}_hits"
        acc_col = f"p{p}_acc"
        if shots in tbl and hits in tbl:
            tbl[acc_col] = (tbl[hits] / tbl[shots]).fillna(0).round(3)
    view = tbl[["gid_short","p1","p2","winner","duration_ms","p1_shots","p1_hits","p1_acc","p2_shots","p2_hits","p2_acc"]]
    view = view.rename(columns={
        "gid_short":"GID", "winner":"Vencedor", "duration_ms":"Duração (ms)",
        "p1_shots":"P1 Tiros","p1_hits":"P1 Acertos","p1_acc":"P1 Acc",
        "p2_shots":"P2 Tiros","p2_hits":"P2 Acertos","p2_acc":"P2 Acc",
    })
    st.dataframe(view, width='stretch', height=300)