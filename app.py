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
st.set_page_config(page_title="Navalytics", page_icon="🛳️", layout="wide")
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

# --- NEW: Ranking ---
@st.cache_data(show_spinner=False, ttl=1)
def top_highscores(db: str, limit: int = 5) -> pd.DataFrame:
        """
        Highscore = maior score registrado para cada jogador (p1_score ou p2_score em game_end).
        """
        q = f"""
        WITH scores AS (
            SELECT
                players.name AS Jogador,
                game_end.p1_score AS Highscore
            FROM game_end
            LEFT JOIN players ON players.gid = game_end.gid
            where players.player = 1
            UNION ALL
            SELECT
                players.name AS Jogador,
                game_end.p2_score AS Highscore
            FROM game_end
            LEFT JOIN players ON players.gid = game_end.gid
            where players.player = 2
        )
        SELECT
            Jogador,
            MAX(Highscore) AS Highscore
        FROM scores
        WHERE Jogador IS NOT NULL
        GROUP BY Jogador
        ORDER BY Highscore DESC, Jogador ASC
        LIMIT {int(limit)}
        """
        df = sql_df(db, q)
        if df.empty:
                return pd.DataFrame(columns=["Jogador", "Highscore"])
        return df

def get_player_ranking_position(db: str, player_name: str) -> Optional[int]:
        """
        Get the ranking position (1-based) for a player based on their highscore (p1_score/p2_score).
        Returns None if player not found.
        """
        q = """
        WITH scores AS (
            SELECT 
                players.name AS Jogador, 
                p1_score AS Highscore 
            FROM game_end
            LEFT JOIN players ON players.gid = game_end.gid
            WHERE players.player = 1
            UNION ALL
            SELECT 
                players.name AS Jogador, 
                p2_score AS Highscore 
            FROM game_end
            LEFT JOIN players ON players.gid = game_end.gid
            WHERE players.player = 2
        ), ranked AS (
            SELECT
                Jogador,
                MAX(Highscore) AS Highscore,
                ROW_NUMBER() OVER (ORDER BY MAX(Highscore) DESC, Jogador ASC) AS position
            FROM scores
            WHERE Jogador IS NOT NULL
            GROUP BY Jogador
        )
        SELECT position FROM ranked WHERE Jogador = ?
        """
        df = sql_df(db, q, (player_name,))
        if df.empty:
                return None
        return int(df.iloc[0]["position"])

# ----------------------- UI Helpers -----------------------
def render_ranking_text(rank_df: pd.DataFrame, max_rows: Optional[int] = None) -> None:
    """
    Ranking estilizado, empates com mesma posição.
    Espera colunas: ["Jogador", "Highscore"].
    """
    import html

    if rank_df is None or rank_df.empty:
        st.info("Sem dados de Ranking ainda — jogue algumas partidas!")
        return

    df = (
        rank_df[["Jogador", "Highscore"]]
        .copy()
        .rename(columns={"Jogador": "name", "Highscore": "score"})
    )
    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0).astype(int)
    df = df.sort_values("score", ascending=False, kind="stable")
    if max_rows is not None:
        df = df.head(int(max_rows))

    # Empates: mesma posição
    df["rank"] = df["score"].rank(method="min", ascending=False).astype(int)

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    accents = {
        1: "border-color:rgba(255,215,0,.45);background:linear-gradient(90deg,rgba(255,215,0,.18),transparent 55%);",
        2: "border-color:rgba(192,192,192,.45);background:linear-gradient(90deg,rgba(192,192,192,.18),transparent 55%);",
        3: "border-color:rgba(205,127,50,.45);background:linear-gradient(90deg,rgba(205,127,50,.22),transparent 55%);",
    }

    rows_html = []
    for r in df.itertuples(index=False):
        rank = int(r.rank)
        name = html.escape(str(r.name or "—"))
        score = int(r.score)
        badge = medals.get(rank, f"{rank}.")
        accent = accents.get(rank, "")

        box_style = (
            "width:100%;"
            "display:grid;grid-template-columns:44px 1fr auto;gap:10px;align-items:center;"
            "padding:10px 12px;margin:6px 0;border:1px solid rgba(255,255,255,0.08);"
            "border-radius:12px;background:rgba(255,255,255,0.03);" + accent
        )
        pos_style = "text-align:center;font-weight:800;font-variant-numeric:tabular-nums;opacity:.95;"
        name_style = "font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
        score_style = "text-align:right;font-weight:700;font-variant-numeric:tabular-nums;opacity:.9;"

        rows_html.append(
            f'<div style="{box_style}">'
            f'  <div style="{pos_style}">{badge}</div>'
            f'  <div style="{name_style}">{name}</div>'
            f'  <div style="{score_style}">{score}</div>'
            f"</div>"
        )

    container_style = "max-width: 720px; margin: 0 auto; padding: 0 8px;"
    st.markdown(f'<div style="{container_style}">' + "".join(rows_html) + "</div>", unsafe_allow_html=True)

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

# ----------------------- Live-state & Auto-jump -----------------------
# Evaluate live game state ONCE up front
current_gid_now = get_current_gid(db_path)
prev_has_game = st.session_state.get("_has_game", False)
has_game_now = current_gid_now is not None

# Initialize active tab if not set
if "_active_tab" not in st.session_state:
    st.session_state["_active_tab"] = "📊 Dashboard"

# Detect when a game just ended
if prev_has_game and not has_game_now:
    st.session_state["_just_ended"] = True
    st.session_state["_last_ended_gid"] = st.session_state.get("_last_gid", None)
    st.session_state["_balloons_shown"] = False  # Reset balloon flag

# Update live-game flag and last gid
st.session_state["_has_game"] = has_game_now
if has_game_now:
    st.session_state["_last_gid"] = current_gid_now

# ----------------------- Tabs (with soft 'selected' control) -----------------------
# By default: Dashboard, Current Game, Games, Ranking
labels_default = ["📊 Dashboard", "🟢 Partida Atual", "🗂 Games", "🏆 Ranking"]

active_tab = st.session_state["_active_tab"]

# Reorder tabs to put active tab first (this makes it selected in Streamlit)
if active_tab in labels_default:
    labels = [active_tab] + [l for l in labels_default if l != active_tab]
else:
    labels = labels_default[:]

_tabs = st.tabs(labels)
tabs = {label: t for label, t in zip(labels, _tabs)}  # map label -> object

# ----- Dashboard Tab -----
with tabs["📊 Dashboard"]:
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
        st.dataframe(view, width='stretch', height=300)

# ----- Current Game Tab -----
with tabs["🟢 Partida Atual"]:
    gid = current_gid_now  # reuse computed state

    # Check if we should show the "just ended" message
    show_ended = st.session_state.get("_just_ended", False) and st.session_state.get("_last_ended_gid")
    
    if show_ended:
        # Game just ended - show results and ranking
        ended_gid = st.session_state["_last_ended_gid"]
        
        # Show balloons only once
        if not st.session_state.get("_balloons_shown", False):
            st.balloons()
            st.session_state["_balloons_shown"] = True
        
        st.success("🎉 Partida Encerrada!")
        
        # Get game info
        p1, p2 = get_players(db_path, ended_gid)
        s = shots_df(db_path, ended_gid)
        
        # Get winner
        winner_q = "SELECT winner FROM game_end WHERE gid=?"
        winner_df = sql_df(db_path, winner_q, (ended_gid,))
        winner = int(winner_df.iloc[0]["winner"]) if not winner_df.empty else None
        
        # Calculate scores for this game
        p1_hits = int(s[s["attacker"]==1]["hit"].sum()) if not s.empty else 0
        p2_hits = int(s[s["attacker"]==2]["hit"].sum()) if not s.empty else 0
        
        st.markdown(f"### 🏁 Resultado Final")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"#### {'🏆 ' if winner == 1 else ''}{p1 or 'Jogador 1'}")
            st.metric("Acertos nesta partida", p1_hits)
            if p1:
                pos = get_player_ranking_position(db_path, p1)
                if pos:
                    st.metric("Posição no Ranking", f"#{pos}")
        
        with col2:
            st.markdown(f"#### {'🏆 ' if winner == 2 else ''}{p2 or 'Jogador 2'}")
            st.metric("Acertos nesta partida", p2_hits)
            if p2:
                pos = get_player_ranking_position(db_path, p2)
                if pos:
                    st.metric("Posição no Ranking", f"#{pos}")
        
        st.divider()
        st.subheader("🏆 Top 10 Ranking Atual")
        rank = top_highscores(db_path, limit=10)
        if not rank.empty:
            render_ranking_text(rank, max_rows=10)
        
        # Clear the flag after showing once
        if st.button("✅ OK, entendi"):
            st.session_state["_just_ended"] = False
            st.rerun()
        
        st.info("💡 A próxima partida aparecerá aqui automaticamente quando iniciada.")
    
    elif not gid:
        st.info("Nenhuma partida ativa no momento.")
    else:
        p1, p2 = get_players(db_path, gid)
        W, H = get_board_size(db_path, gid)
        s = shots_df(db_path, gid)

        st.markdown(f"**GID:** `{gid}`  •  **Players:** {p1 or 'P1'} × {p2 or 'P2'}")

        # elapsed vs avg duration → progress bar with average marker
        started_ms = get_started_at_ms(db_path, gid)
        if started_ms:
            elapsed_ms = now_ms() - started_ms
            avg_ms = get_avg_duration_ms(db_path)
            # always show elapsed text
            st.caption(f"Tempo decorrido: **{ms_to_mmss(elapsed_ms)}**" + (f"  •  Média histórica: **{ms_to_mmss(avg_ms)}**" if avg_ms else ""))

            if avg_ms:
                # use a horizontal bar (seconds) and draw a vertical line for the average
                elapsed_s = elapsed_ms / 1000.0
                avg_s = avg_ms / 1000.0
                x_max = max(elapsed_s, avg_s) * 1.15 if max(elapsed_s, avg_s) > 0 else 60.0

                # color: green if elapsed < avg, yellow if elapsed > avg (equal -> green)
                bar_color = "limegreen" if elapsed_s <= avg_s else "gold"

                fig = go.Figure()
                # bar representing elapsed time
                fig.add_trace(go.Bar(
                    x=[elapsed_s],
                    y=[""],
                    orientation="h",
                    marker_color=bar_color,
                    hovertemplate="Decorrido: %{x:.1f}s<extra></extra>"
                ))
                # average marker line
                fig.add_shape(
                    type="line",
                    x0=avg_s, x1=avg_s, y0=-0.4, y1=0.4,
                    line=dict(color="red", width=3, dash="dash")
                )
                # label for the average
                fig.add_annotation(
                    x=avg_s, y=0.5,
                    text=f"Média: {ms_to_mmss(avg_ms)}",
                    showarrow=False,
                    yanchor="bottom",
                    font=dict(color="red", size=11)
                )

                fig.update_xaxes(range=[0, x_max], title_text="Segundos")
                fig.update_yaxes(showticklabels=False)
                fig.update_layout(height=110, margin=dict(l=10, r=10, t=10))
                st.plotly_chart(fig, use_container_width=True)
            else:
                # no historical average yet — show simple progress feedback
                st.info("Ainda não há média histórica para comparar.")

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
            c2.dataframe(h2t, width='stretch', height=160)

        # mini boards
        st.subheader("Mini boards")
        cL, cR = st.columns(2)
        figL = board_heatmap(s[s["attacker"]==1], W, H, f"Ataques do {p1 or 'P1'}")
        figR = board_heatmap(s[s["attacker"]==2], W, H, f"Ataques do {p2 or 'P2'}")

        # Make cells square: anchor y to x and set explicit figure size
        cell_px = 30
        min_px, max_px = 200, 800
        height_px = int(max(min_px, min(max_px, cell_px * H + 80)))
        width_px  = int(max(min_px, min(max_px, cell_px * W + 80)))

        for fig in (figL, figR):
            fig.update_layout(
            height=height_px,
            width=width_px,
            yaxis=dict(scaleanchor="x", scaleratio=1, autorange="reversed"),
            margin=dict(l=10, r=10, t=40, b=10),
            )

        cL.plotly_chart(figL, use_container_width=False)
        cR.plotly_chart(figR, use_container_width=False)

# ----- Games Tab -----
with tabs["🗂 Games"]:
    st.subheader("Todas as partidas")
    all_tbl = games_list(db_path)
    if all_tbl.empty:
        st.info("Sem partidas.")
    else:
        st.dataframe(all_tbl, width='stretch', height=380)

# ----- Ranking Tab (Top 10 Highscores) -----
with tabs["🏆 Ranking"]:
    st.subheader("Top 10 — Highscores por Jogador")
    rank = top_highscores(db_path, limit=10)
    if rank.empty:
        st.info("Sem dados de Ranking ainda — jogue algumas partidas!")
    else:
        # Text-first rendering (clean, compact)
        render_ranking_text(rank, max_rows=10)

# Auto-refresh logic (kept as-is)
if auto:
    time.sleep(interval_s)
    st.rerun()