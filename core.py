# core.py — shared DB helpers, queries, and UI bits
import time
import sqlite3
from datetime import timedelta
from typing import Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DB_DEFAULT = "battleship.db"

# ----------------------- DB Helpers -----------------------
def _connect(db: str):
    conn = sqlite3.connect(db)
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

@st.cache_data(show_spinner=False, ttl=1)
def top_highscores(db: str, limit: int = 10) -> pd.DataFrame:
    q = f"""
    WITH scores AS (
        SELECT players.name AS Jogador, game_end.p1_score AS Highscore
        FROM game_end
        LEFT JOIN players ON players.gid = game_end.gid
        WHERE players.player = 1
        UNION ALL
        SELECT players.name AS Jogador, game_end.p2_score AS Highscore
        FROM game_end
        LEFT JOIN players ON players.gid = game_end.gid
        WHERE players.player = 2
    )
    SELECT Jogador, MAX(Highscore) AS Highscore
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
    q = """
    WITH scores AS (
        SELECT players.name AS Jogador, p1_score AS Highscore
        FROM game_end
        LEFT JOIN players ON players.gid = game_end.gid
        WHERE players.player = 1
        UNION ALL
        SELECT players.name AS Jogador, p2_score AS Highscore
        FROM game_end
        LEFT JOIN players ON players.gid = game_end.gid
        WHERE players.player = 2
    ), ranked AS (
        SELECT Jogador, MAX(Highscore) AS Highscore,
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

# ----------------------- KPI & Viz helpers -----------------------
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
    out = {1: {"max":0, "avg":0.0}, 2: {"max":0, "avg":0.0}}
    for p in (1,2):
        grp = df[df["attacker"]==p]
        streaks, s = [], 0
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

def board_heatmap(shots: pd.DataFrame, W: int, H: int, title: str) -> go.Figure:
    Z = [[0 for _ in range(W)] for _ in range(H)]
    for _, r in shots.iterrows():
        x, y = int(r["x"]), int(r["y"])
        if 0 <= x < W and 0 <= y < H:
            Z[y][x] = 2 if int(r["hit"])==1 else max(Z[y][x], 1)
    fig = go.Figure(data=go.Heatmap(z=Z, showscale=False))
    fig.update_layout(title=title, xaxis=dict(dtick=1), yaxis=dict(dtick=1),
                      margin=dict(l=10,r=10,t=40,b=10))
    return fig

def player_summary(shots: pd.DataFrame, defender_side: int) -> Optional[int]:
    d = shots[shots["defender"]==defender_side]
    if d.empty: return None
    last = d.iloc[-1]["remaining_def"]
    try:
        return int(last)
    except Exception:
        return None

# ----------------------- UI: Ranking Podium -----------------------
def render_ranking_podium_plus_list(rank_df: pd.DataFrame, limit: int = 10) -> None:
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
    df = df.sort_values(["score", "name"], ascending=[False, True], kind="stable")
    if limit is not None:
        df = df.head(int(limit))
    df["rank"] = df["score"].rank(method="min", ascending=False).astype(int)

    top3 = df.head(3)
    rest = df.iloc[3:]

    css = """
    <style>
    .rank-wrap { max-width: 1100px; margin: 0 auto; padding: 6px 10px; }
    .podium {
      display: grid; grid-template-columns: 1fr 1.2fr 1fr; gap: 16px;
      align-items: end; margin: 8px 0 18px;
    }
    @media (max-width: 980px) { .podium { grid-template-columns: 1fr; } }
    .pod-card { position: relative; border-radius: 22px;
      border: 1px solid rgba(255,255,255,0.10);
      background: rgba(255,255,255,0.03);
      box-shadow: 0 10px 32px rgba(0,0,0,0.35);
      height: 260px; display: flex; flex-direction: column;
      align-items: center; justify-content: center; overflow: hidden; }
    .pod-card.center { height: 300px; }
    .pod-card.gold   { border-color: rgba(255,215,0,.38);
      background: linear-gradient(135deg, rgba(255,215,0,.16), rgba(255,215,0,0) 62%); }
    .pod-card.silver { border-color: rgba(192,192,192,.38);
      background: linear-gradient(135deg, rgba(192,192,192,.16), rgba(192,192,192,0) 62%); }
    .pod-card.bronze { border-color: rgba(205,127,50,.40);
      background: linear-gradient(135deg, rgba(205,127,50,.18), rgba(205,127,50,0) 62%); }
    .medal { position: absolute; top: -22px; left: 50%; transform: translateX(-50%);
      width: 68px; height: 68px; border-radius: 50%;
      display:flex; align-items:center; justify-content:center;
      font-weight: 900; font-size: 22px; color: #111;
      border: 3px solid rgba(0,0,0,.25);
      box-shadow: 0 8px 18px rgba(0,0,0,.35), inset 0 0 0 2px rgba(255,255,255,.35); }
    .medal.gold   { background: radial-gradient(circle, #ffd700, #ffb300); }
    .medal.silver { background: radial-gradient(circle, #d9d9d9, #bfbfbf); }
    .medal.bronze { background: radial-gradient(circle, #e0a15e, #b8742a); }
    .place { position:absolute; top: 50px; font-size: 12px; opacity: .85; letter-spacing: .06em; }
    .place.center { top: 58px; }
    .pod-name { max-width: 90%; text-align: center; white-space: nowrap; overflow: hidden;
      text-overflow: ellipsis; font-weight: 800; font-size: 22px; margin-top: 10px; }
    .pod-name.center { font-size: 24px; }
    .pod-score { font-weight: 900; font-variant-numeric: tabular-nums; font-size: 48px; margin-top: 6px; }
    .pod-score.center { font-size: 56px; }
    .rank-list { max-width: 720px; margin: 6px auto 0; }
    .rank-row { width:100%; display:grid; grid-template-columns:44px 1fr auto; gap:10px; align-items:center;
      padding:10px 12px; margin:6px 0; border:1px solid rgba(255,255,255,0.08);
      border-radius:12px; background:rgba(255,255,255,0.03); }
    .rank-pos { text-align:center; font-weight:800; font-variant-numeric:tabular-nums; opacity:.95; }
    .rank-name { font-weight:650; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .rank-score { text-align:right; font-weight:700; font-variant-numeric:tabular-nums; opacity:.9; }
    </style>
    """

    def card_html(place: int, name: str, score: int, cls: str, center: bool = False) -> str:
        esc_name = html.escape(name or "—")
        center_cls = " center" if center else ""
        place_badge = {1:"gold",2:"silver",3:"bronze"}[place]
        label = "Campeão" if place == 1 else f"#{place}"
        return f"""
        <div class="pod-card {cls}{center_cls}">
          <div class="medal {place_badge}">{place}</div>
          <div class="place{center_cls}">{label}</div>
          <div class="pod-name{center_cls}">{esc_name}</div>
          <div class="pod-score{center_cls}">{score}</div>
        </div>
        """

    p = top3 = df.head(3).to_dict("records")
    while len(p) < 3:
        p.append({"rank": len(p)+1, "name": "—", "score": 0})
    left  = p[1] if len(p) > 1 else {"rank":2,"name":"—","score":0}
    center= p[0] if len(p) > 0 else {"rank":1,"name":"—","score":0}
    right = p[2] if len(p) > 2 else {"rank":3,"name":"—","score":0}

    podium_html = f"""
    <div class="rank-wrap">
      <div class="podium">
        <div>{card_html(2, left["name"],   int(left["score"]),   "silver")}</div>
        <div>{card_html(1, center["name"], int(center["score"]), "gold", center=True)}</div>
        <div>{card_html(3, right["name"],  int(right["score"]),  "bronze")}</div>
      </div>
    </div>
    """

    rows_html = []
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for r in df.iloc[3:].itertuples(index=False):
        rr = int(r.rank); nm = html.escape(str(r.name or "—")); sc = int(r.score)
        badge = medals.get(rr, f"{rr}.")
        rows_html.append(
            f'<div class="rank-row">'
            f'  <div class="rank-pos">{badge}</div>'
            f'  <div class="rank-name">{nm}</div>'
            f'  <div class="rank-score">{sc}</div>'
            f'</div>'
        )
    list_html = f'<div class="rank-list">{"".join(rows_html)}</div>'

    st.markdown(css + podium_html + list_html, unsafe_allow_html=True)