# app.py — Navalytics (Streamlit prototype)
# Run:  streamlit run app.py
import time
import sqlite3
from datetime import timedelta
from typing import Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DB_DEFAULT = "battleship.db"

# ----------------------- Streamlit Setup -----------------------
st.set_page_config(page_title="Navalytics", layout="wide")
st.title("🎯 Navalytics — Battleship Analytics")

with st.sidebar:
    st.header("Settings")
    db_path = st.text_input("SQLite DB path", value=DB_DEFAULT)
    auto = st.checkbox("Auto refresh", value=True)
    interval_s = st.number_input("Refresh interval (s)", min_value=1, max_value=10, value=1, step=1)
    st.caption("Tip: Leave this app in a browser on your game station for a live wallboard.")

# ----------------------- DB Helpers -----------------------
def _connect(db: str):
    conn = sqlite3.connect(db)
    # improve read/write concurrency
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    return conn

@st.cache_data(show_spinner=False, ttl=1)
def sql_df(db: str, query: str, params: Tuple = ()):
    with _connect(db) as c:
        return pd.read_sql_query(query, c, params=params)

def now_ms() -> int:
    return int(time.time() * 1000)

# ----------------------- Core Queries -----------------------
def get_current_gid(db: str) -> Optional[str]:
    q = """
    SELECT g.gid
    FROM games g
    LEFT JOIN game_end ge ON ge.gid = g.gid
    WHERE ge.gid IS NULL
    ORDER BY g.started_at_ms DESC
    LIMIT 1
    """
    df = sql_df(db, q)
    return None if df.empty else df.iloc[0]["gid"]

def get_players(db: str, gid: str) -> Tuple[Optional[str], Optional[str]]:
    q = """
    SELECT
      MAX(CASE WHEN player=1 THEN name END) AS p1,
      MAX(CASE WHEN player=2 THEN name END) AS p2
    FROM players WHERE gid=?
    """
    df = sql_df(db, q, (gid,))
    if df.empty: return None, None
    return df.iloc[0]["p1"], df.iloc[0]["p2"]

def get_board_size(db: str, gid: Optional[str]) -> Tuple[int,int]:
    if gid is None:
        q = "SELECT w,h FROM games LIMIT 1"
        df = sql_df(db, q)
    else:
        q = "SELECT w,h FROM games WHERE gid=?"
        df = sql_df(db, q, (gid,))
    if df.empty:
        return 8,8
    w = int(df.iloc[0]["w"] or 8)
    h = int(df.iloc[0]["h"] or 8)
    return w, h

def get_avg_duration_ms(db: str) -> Optional[float]:
    q = "SELECT AVG(duration_ms) AS avg_dur FROM game_end"
    df = sql_df(db, q)
    if df.empty or pd.isna(df.iloc[0]["avg_dur"]): return None
    return float(df.iloc[0]["avg_dur"])

def get_started_at_ms(db: str, gid: str) -> Optional[int]:
    q = "SELECT started_at_ms FROM games WHERE gid=?"
    df = sql_df(db, q, (gid,))
    if df.empty or pd.isna(df.iloc[0]["started_at_ms"]): return None
    return int(df.iloc[0]["started_at_ms"])

def shots_df(db: str, gid: Optional[str] = None) -> pd.DataFrame:
    if gid:
        return sql_df(db, "SELECT * FROM shots WHERE gid=? ORDER BY ts_ms", (gid,))
    return sql_df(db, "SELECT * FROM shots ORDER BY gid, ts_ms")

def games_list(db: str) -> pd.DataFrame:
    q = """
    WITH p AS (
      SELECT gid,
             MAX(CASE WHEN player=1 THEN name END) AS p1,
             MAX(CASE WHEN player=2 THEN name END) AS p2
      FROM players GROUP BY gid
    ),
    s AS (
      SELECT gid,
             SUM(CASE WHEN attacker=1 THEN 1 ELSE 0 END) AS p1_shots,
             SUM(CASE WHEN attacker=1 AND hit=1 THEN 1 ELSE 0 END) AS p1_hits,
             SUM(CASE WHEN attacker=2 THEN 1 ELSE 0 END) AS p2_shots,
             SUM(CASE WHEN attacker=2 AND hit=1 THEN 1 ELSE 0 END) AS p2_hits
      FROM shots GROUP BY gid
    )
    SELECT g.gid,
           COALESCE(p.p1,'?') AS p1,
           COALESCE(p.p2,'?') AS p2,
           ge.winner,
           ge.duration_ms,
           COALESCE(s.p1_shots,0) AS p1_shots,
           COALESCE(s.p1_hits,0)  AS p1_hits,
           COALESCE(s.p2_shots,0) AS p2_shots,
           COALESCE(s.p2_hits,0)  AS p2_hits
    FROM games g
    LEFT JOIN p  ON p.gid  = g.gid
    LEFT JOIN game_end ge  ON ge.gid = g.gid
    LEFT JOIN s  ON s.gid  = g.gid
    ORDER BY g.rowid DESC
    """
    return sql_df(db, q)

# ----------------------- KPI Helpers -----------------------
def ms_to_mmss(ms: float) -> str:
    if ms is None or pd.isna(ms): return "—"
    td = timedelta(milliseconds=float(ms))
    total_seconds = int(td.total_seconds())
    return f"{total_seconds//60:02d}:{total_seconds%60:02d}"

def accuracy_global(db: str) -> Optional[float]:
    df = sql_df(db, "SELECT SUM(hit)*1.0/COUNT(*) AS acc FROM shots")
    if df.empty or pd.isna(df.iloc[0]["acc"]): return None
    return float(df.iloc[0]["acc"])

def starter_win_rate(db: str) -> Optional[float]:
    q = """
    WITH first_shot AS (
      SELECT gid, MIN(ts_ms) AS first_ts FROM shots GROUP BY gid
    ),
    fs AS (
      SELECT s.gid, s.attacker AS starter
      FROM shots s
      JOIN first_shot f ON f.gid=s.gid AND f.first_ts=s.ts_ms
    )
    SELECT SUM(CASE WHEN ge.winner = fs.starter THEN 1 ELSE 0 END)*1.0/COUNT(*) AS wr
    FROM fs JOIN game_end ge USING(gid)
    """
    df = sql_df(db, q)
    if df.empty or pd.isna(df.iloc[0]["wr"]): return None
    return float(df.iloc[0]["wr"])

def avg_first_hit_seconds(db: str) -> Optional[float]:
    q = """
    WITH fh AS (
      SELECT g.gid, g.started_at_ms,
             MIN(CASE WHEN s.hit=1 THEN s.ts_ms END) AS first_hit_ts
      FROM games g
      LEFT JOIN shots s ON s.gid=g.gid
      GROUP BY g.gid
    )
    SELECT AVG((first_hit_ts - started_at_ms)/1000.0) AS avg_s
    FROM fh WHERE first_hit_ts IS NOT NULL AND started_at_ms IS NOT NULL
    """
    df = sql_df(db, q)
    if df.empty or pd.isna(df.iloc[0]["avg_s"]): return None
    return float(df.iloc[0]["avg_s"])

def hit_streaks(df: pd.DataFrame) -> dict:
    # df: shots for a single gid (ordered)
    out = {1: {"max":0, "avg":0.0}, 2: {"max":0, "avg":0.0}}
    for p in (1,2):
        grp = df[df["attacker"]==p]
        streaks = []
        s = 0
        for h in grp["hit"]:
            if h==1: s+=1
            else:
                if s>0: streaks.append(s)
                s=0
        if s>0: streaks.append(s)
        out[p]["max"] = max(streaks) if streaks else 0
        out[p]["avg"] = (sum(streaks)/len(streaks)) if streaks else 0.0
    return out

def hunt_to_target(df: pd.DataFrame) -> pd.DataFrame:
    # df: shots for a single gid (ordered)
    rows = []
    if df.empty: return pd.DataFrame(columns=["attacker","defender","shots_until_first_hit"])
    for (atk, dfd), grp in df.groupby(["attacker","defender"]):
        targeting = False
        counter = 0
        for _, r in grp.iterrows():
            if not targeting:
                counter += 1
                if r["hit"] == 1:
                    rows.append({"attacker": atk, "defender": dfd, "shots_until_first_hit": counter})
                    targeting = True
            if targeting and r["sunk"] == 1:
                targeting = False
                counter = 0
    return pd.DataFrame(rows)

# ----------------------- Visualization -----------------------
def board_heatmap(shots: pd.DataFrame, W: int, H: int, title: str) -> go.Figure:
    # 0: untouched, 1: miss, 2: hit
    Z = [[0 for _ in range(W)] for _ in range(H)]
    for _, r in shots.iterrows():
        x, y = int(r["x"]), int(r["y"])
        if 0 <= x < W and 0 <= y < H:
            Z[y][x] = 2 if int(r["hit"])==1 else max(Z[y][x], 1)
    fig = go.Figure(data=go.Heatmap(z=Z, showscale=False))
    fig.update_layout(title=title, xaxis=dict(dtick=1), yaxis=dict(dtick=1), margin=dict(l=10,r=10,t=40,b=10))
    return fig

def player_summary(shots: pd.DataFrame, defender_side: int) -> int:
    # latest remaining cells for that defender
    d = shots[shots["defender"]==defender_side]
    if d.empty: return None
    last = d.iloc[-1]["remaining_def"]
    try:
        return int(last)
    except Exception:
        return None

# ----------------------- Tabs -----------------------
tab_dash, tab_live, tab_games = st.tabs(["📊 Dashboard", "🟢 Current Game", "🗂 Games"])

# ----- Dashboard Tab -----
with tab_dash:
    colA, colB, colC, colD, colE, colF = st.columns(6)

    # # games
    df_games = sql_df(db_path, "SELECT COUNT(*) AS n_games FROM (SELECT DISTINCT gid FROM games)")
    n_games = int(df_games.iloc[0]["n_games"] or 0)
    colA.metric("Partidas", n_games)

    # avg duration
    avg_dur = get_avg_duration_ms(db_path)
    colB.metric("Tempo Médio", ms_to_mmss(avg_dur))

    # shots/game
    df_spg = sql_df(db_path, "SELECT AVG(cnt) AS spg FROM (SELECT gid, COUNT(*) AS cnt FROM shots GROUP BY gid)")
    spg = float(df_spg.iloc[0]["spg"]) if not df_spg.empty and not pd.isna(df_spg.iloc[0]["spg"]) else None
    colC.metric("Tiros / Partida", f"{spg:.2f}" if spg is not None else "—")

    # global accuracy
    acc = accuracy_global(db_path)
    colD.metric("Taxa de Acerto (global)", f"{acc*100:.1f}%" if acc is not None else "—")

    # starter win rate
    wr = starter_win_rate(db_path)
    colE.metric("Win Rate de quem começa", f"{wr*100:.1f}%" if wr is not None else "—")

    # avg first hit time
    af = avg_first_hit_seconds(db_path)
    colF.metric("Hunt→Target (1º acerto) — tempo médio", f"{af:.2f}s" if af is not None else "—")

    st.divider()

    st.subheader("Últimas partidas")
    tbl = games_list(db_path).copy()
    if tbl.empty:
        st.info("Ainda não há partidas registradas.")
    else:
        # pretty columns
        tbl["gid_short"] = tbl["gid"].str.slice(0,8) + "…"
        for p in (1,2):
            shots, hits = f"p{p}_shots", f"p{p}_hits"
            acc_col = f"p{p}_acc"
            if shots in tbl and hits in tbl:
                tbl[acc_col] = (tbl[hits] / tbl[shots]).fillna(0).round(3)
        view = tbl[["gid_short","p1","p2","winner","duration_ms","p1_shots","p1_hits","p1_acc","p2_shots","p2_hits","p2_acc"]]
        view = view.rename(columns={
            "gid_short":"GID",
            "winner":"Vencedor",
            "duration_ms":"Duração (ms)",
            "p1_shots":"P1 Tiros","p1_hits":"P1 Acertos","p1_acc":"P1 Acc",
            "p2_shots":"P2 Tiros","p2_hits":"P2 Acertos","p2_acc":"P2 Acc",
        })
        st.dataframe(view, use_container_width=True, height=300)

# ----- Current Game Tab -----
with tab_live:
    gid = get_current_gid(db_path)
    if auto:
        st.experimental_set_query_params(t=str(int(time.time())))
        time.sleep(interval_s)

    if not gid:
        st.info("Nenhuma partida ativa no momento.")
    else:
        p1, p2 = get_players(db_path, gid)
        W, H = get_board_size(db_path, gid)
        s = shots_df(db_path, gid)

        st.markdown(f"**GID:** `{gid}`  •  **Board:** {W}×{H}  •  **Players:** {p1 or 'P1'} × {p2 or 'P2'}")

        # elapsed vs avg duration
        started_ms = get_started_at_ms(db_path, gid)
        if started_ms:
            elapsed_ms = now_ms() - started_ms
            avg_ms = get_avg_duration_ms(db_path)
            if avg_ms:
                status = "abaixo da média" if elapsed_ms < avg_ms else "acima da média"
                st.caption(f"Tempo decorrido: **{ms_to_mmss(elapsed_ms)}** — {status} (média histórica: {ms_to_mmss(avg_ms)})")

        # per-player summaries
        cols = st.columns(4)
        for idx, player in enumerate((1,2)):
            sub = s[s["attacker"]==player]
            shots = len(sub)
            hits = int(sub["hit"].sum()) if not sub.empty else 0
            acc = (hits/shots)*100 if shots>0 else 0.0
            rem = player_summary(s, defender_side=3-player)
            cols[idx].metric(f"Jogador {player} — {p1 if player==1 else p2}",
                             f"{hits}/{shots} hits", f"{acc:.1f}% acc")
            cols[idx+2].metric(f"Defensor {3-player} — Células rest.",
                               rem if rem is not None else "—")

        # streaks + hunt→target
        st.subheader("Sequências e Hunt→Target")
        strk = hit_streaks(s)
        c1, c2 = st.columns(2)
        c1.write({
            "P1 max_streak": strk[1]["max"], "P1 avg_streak": round(strk[1]["avg"],2),
            "P2 max_streak": strk[2]["max"], "P2 avg_streak": round(strk[2]["avg"],2),
        })
        h2t = hunt_to_target(s)
        if h2t.empty:
            c2.info("Sem dados de Hunt→Target ainda.")
        else:
            c2.dataframe(h2t, use_container_width=True, height=160)

        # mini boards
        st.subheader("Mini boards")
        cL, cR = st.columns(2)
        cL.plotly_chart(board_heatmap(s[s["attacker"]==1], W, H, f"Ataques do {p1 or 'P1'}"), use_container_width=True)
        cR.plotly_chart(board_heatmap(s[s["attacker"]==2], W, H, f"Ataques do {p2 or 'P2'}"), use_container_width=True)

# ----- Games Tab -----
with tab_games:
    st.subheader("Todas as partidas")
    all_tbl = games_list(db_path)
    if all_tbl.empty:
        st.info("Sem partidas.")
    else:
        st.dataframe(all_tbl, use_container_width=True, height=380)
        st.caption("Dica: clique nas cabeçalhos para ordenar.")

st.markdown("---")
st.caption("Prototype • Streamlit • Uses your existing SQLite schema produced by ingest_serial.py")
