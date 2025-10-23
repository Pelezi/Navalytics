import os
import sqlite3
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

import metrics as mx


# ------------- Helpers -------------
def _get_board_size(db_path: str, default: Tuple[int, int] = (8, 8)) -> Tuple[int, int]:
    with sqlite3.connect(db_path) as conn:
        g = mx.df_games(conn)
    if g.empty:
        return default
    unique = g[["w", "h"]].drop_duplicates()
    if len(unique) == 1:
        r = unique.iloc[0]
        return int(r["w"]), int(r["h"])
    r = unique.iloc[0]
    st.warning(
        f"Tamanhos de tabuleiro variados. Usando {int(r['w'])}x{int(r['h'])} para os heatmaps."
    )
    return int(r["w"]), int(r["h"])


def _mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


@st.cache_data(show_spinner=False)
def load_list_games_table(db_path: str, mtime: float) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return mx.list_games_table(conn)


@st.cache_data(show_spinner=False)
def load_overall_averages(db_path: str, mtime: float) -> dict:
    with sqlite3.connect(db_path) as conn:
        return mx.overall_averages(conn)


@st.cache_data(show_spinner=False)
def load_accuracy_by_player(db_path: str, gid: str, mtime: float) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return mx.accuracy_by_player(conn, gid)


@st.cache_data(show_spinner=False)
def load_timeline(db_path: str, gid: str, mtime: float) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return mx.timeline_hits(conn, gid)


@st.cache_data(show_spinner=False)
def load_shots(db_path: str, gid: Optional[str], mtime: float) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return mx.df_shots(conn, gid)


@st.cache_data(show_spinner=False)
def load_games(db_path: str, mtime: float) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return mx.df_games(conn)


@st.cache_data(show_spinner=False)
def load_sequential_hits(db_path: str, gid: str, mtime: float) -> dict:
    with sqlite3.connect(db_path) as conn:
        return mx.sequential_hits_analysis(conn, gid)


@st.cache_data(show_spinner=False)
def load_hunt_to_target(db_path: str, gid: str, mtime: float) -> dict:
    with sqlite3.connect(db_path) as conn:
        return mx.hunt_to_target_metrics(conn, gid)


@st.cache_data(show_spinner=False)
def load_first_player_advantage(db_path: str, mtime: float) -> dict:
    with sqlite3.connect(db_path) as conn:
        return mx.first_player_advantage(conn)


# ------------- Plot builders (return matplotlib Figure) -------------
def fig_accuracy(acc: pd.DataFrame, gid: str) -> Optional[plt.Figure]:
    if acc.empty:
        return None
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar(acc["player"].astype(str), acc["accuracy"], color=["#1f77b4", "#ff7f0e"])
    ax.set_title(f"Acurácia por Jogador (gid={gid[:8]}…)")
    ax.set_xlabel("Jogador")
    ax.set_ylabel("Acurácia")
    ax.set_ylim(0, 1)
    for i, v in enumerate(acc["accuracy" ].values):
        ax.text(i, v + 0.02, f"{v*100:.1f}%", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    return fig


def fig_timeline(tl: pd.DataFrame, gid: str) -> Optional[plt.Figure]:
    if tl.empty:
        return None
    tl = tl.copy()
    tl["t"] = (tl["ts_ms"] - tl["ts_ms"].min()) / 1000.0
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot(tl["t"], tl["hit"], drawstyle="steps-post", alpha=0.6)
    ax.set_title(f"Tiros (hit=1/miss=0) ao longo do tempo (gid={gid[:8]}…)")
    ax.set_xlabel("Segundos desde o início")
    ax.set_ylabel("Hit (1) / Miss (0)")
    ax.set_yticks([0, 1])
    fig.tight_layout()
    return fig


def _grid_from_shots(shots: pd.DataFrame, W: int, H: int) -> Tuple[np.ndarray, np.ndarray]:
    grid_count = np.zeros((H, W), dtype=int)
    grid_hits = np.zeros((H, W), dtype=int)
    for _, row in shots.iterrows():
        x, y = int(row["x"]), int(row["y"])
        if 0 <= x < W and 0 <= y < H:
            grid_count[y, x] += 1
            if int(row["hit"]) == 1:
                grid_hits[y, x] += 1
    return grid_count, grid_hits


def fig_heatmap(shots: pd.DataFrame, W: int, H: int, *, metric: str, title_prefix: str) -> Optional[plt.Figure]:
    if shots.empty:
        return None
    count, hits = _grid_from_shots(shots, W, H)
    if metric == "count":
        Z = count
        title = f"{title_prefix} – quantidade de tiros"
    elif metric == "hits":
        Z = hits
        title = f"{title_prefix} – acertos"
    else:
        with np.errstate(invalid="ignore", divide="ignore"):
            rate = np.divide(hits, np.where(count == 0, np.nan, count))
        Z = np.nan_to_num(rate)
        title = f"{title_prefix} – taxa de acerto"

    fig, ax = plt.subplots(figsize=(5, 5))
    im = ax.imshow(Z, origin="upper", interpolation="nearest")
    ax.set_title(title)
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    return fig


def fig_remaining_over_time(tl: pd.DataFrame) -> Optional[plt.Figure]:
    if tl.empty or "remaining_def" not in tl.columns:
        return None
    tl = tl.copy()
    tl["t"] = (tl["ts_ms"] - tl["ts_ms"].min()) / 1000.0
    d1 = tl[tl["defender"] == 1][["t", "remaining_def"]].rename(columns={"remaining_def": "def1"})
    d2 = tl[tl["defender"] == 2][["t", "remaining_def"]].rename(columns={"remaining_def": "def2"})
    if d1.empty and d2.empty:
        return None
    fig, ax = plt.subplots(figsize=(6, 3))
    if not d1.empty:
        ax.step(d1["t"], d1["def1"], where="post", label="Defensor 1")
    if not d2.empty:
        ax.step(d2["t"], d2["def2"], where="post", label="Defensor 2")
    ax.set_title("Células restantes por defensor")
    ax.set_xlabel("Segundos desde o início")
    ax.set_ylabel("Células restantes")
    ax.legend()
    fig.tight_layout()
    return fig


# ------------- UI -------------
st.set_page_config(page_title="Navalytics Dashboard", page_icon="🛳️", layout="wide")
st.title("Navalytics – Dashboard de Métricas")

with st.sidebar:
    st.header("Configuração")
    db_path = st.text_input("Caminho do banco (SQLite)", value=mx.DB_PATH)
    db_exists = os.path.exists(db_path)
    if not db_exists:
        st.warning("Banco não encontrado. Ajuste o caminho ou gere dados primeiro.")
    refresh = st.button("Recarregar dados")

mtime = _mtime(db_path) if db_exists else 0.0
if refresh:
    # Bust caches explicitly when the user clicks refresh
    load_list_games_table.clear()
    load_overall_averages.clear()
    load_accuracy_by_player.clear()
    load_timeline.clear()
    load_shots.clear()
    load_games.clear()
    load_sequential_hits.clear()
    load_hunt_to_target.clear()
    load_first_player_advantage.clear()


col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("KPIs Globais")
    if db_exists:
        kpis = load_overall_averages(db_path, mtime)
    else:
        kpis = {}
    if not kpis:
        st.info("Sem partidas para agregar.")
    else:
        # Métricas básicas
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Partidas", f"{kpis['n_games']}")
        if kpis.get("avg_duration_ms") is not None:
            c2.metric("Duração média (ms)", f"{kpis['avg_duration_ms']:.0f}")
        c3.metric("Tiros/partida (méd)", f"{kpis['avg_shots_per_game']:.2f}")
        c4.metric("Acertos/partida (m)", f"{kpis['avg_hits_per_game']:.2f}")
        
        # Taxa de acerto
        c5, c6 = st.columns(2)
        if kpis.get("avg_overall_acc_per_game") is not None:
            c5.metric("Taxa de Acerto (média)", f"{kpis['avg_overall_acc_per_game']*100:.2f}%")
        if kpis.get("global_accuracy") is not None:
            c6.metric("Taxa de Acerto (global)", f"{kpis['global_accuracy']*100:.2f}%")
        
        if kpis.get("avg_first_hit_s") is not None:
            st.caption(f"⏱️ Tempo médio até 1º acerto: {kpis['avg_first_hit_s']:.2f} s")
        
        # Métricas avançadas em expander
        with st.expander("📊 Métricas Avançadas", expanded=True):
            adv1, adv2, adv3 = st.columns(3)
            
            # Win Rate de quem começa
            if kpis.get("first_player_win_rate") is not None:
                adv1.metric(
                    "Win Rate 1º Jogador", 
                    f"{kpis['first_player_win_rate']:.1f}%",
                    delta=f"{kpis['first_player_win_rate'] - 50:.1f}% vs 50%"
                )
                adv1.caption(f"🏆 {kpis['first_player_wins']}W - {kpis['second_player_wins']}L")
            
            # Hunt→Target
            if kpis.get("avg_hunt_to_target") is not None:
                adv2.metric("Hunt→Target médio", f"{kpis['avg_hunt_to_target']:.1f} tiros")
                adv2.caption("🎯 Tiros até 1º acerto/navio")
            
            # AS - Acertos em Sequência
            if kpis.get("avg_max_streak") is not None:
                adv3.metric("AS médio (max)", f"{kpis['avg_max_streak']:.1f} hits")
                if kpis.get("avg_streak_efficiency") is not None:
                    adv3.caption(f"⚡ Eficiência: {kpis['avg_streak_efficiency']:.1f}%")

with col2:
    st.subheader("Partidas")
    if db_exists:
        tbl = load_list_games_table(db_path, mtime)
    else:
        tbl = pd.DataFrame()
    if tbl.empty:
        st.info("Sem partidas ainda.")
        gid_choice = None
    else:
        pretty = tbl.copy()
        pretty["label"] = (
            pretty["gid"].apply(lambda s: s[:8] + "…")
            + " – "
            + pretty["p1"].fillna("?")
            + " vs "
            + pretty["p2"].fillna("?")
            + pretty.apply(lambda r: f" (W:{int(r['winner'])})" if pd.notna(r.get("winner")) else "", axis=1)
        )
        # Most recent first
        pretty = pretty.iloc[::-1].reset_index(drop=True)
        labels = pretty["label"].tolist()
        gids = pretty["gid"].tolist()
        idx_default = 0
        sel = st.selectbox("Selecione a partida", options=list(range(len(labels))), format_func=lambda i: labels[i], index=idx_default)
        gid_choice = gids[sel]


st.markdown("---")
left, right = st.columns([3, 2])

with left:
    st.subheader("Métricas por Partida")
    if gid_choice:
        # Métricas avançadas da partida
        seq_stats = load_sequential_hits(db_path, gid_choice, mtime)
        hunt_stats = load_hunt_to_target(db_path, gid_choice, mtime)
        
        if seq_stats or hunt_stats:
            m1, m2, m3, m4 = st.columns(4)
            if hunt_stats and hunt_stats.get("total_hunts", 0) > 0:
                m1.metric("Hunt→Target", f"{hunt_stats['avg_hunt_shots']:.1f}")
                m1.caption(f"Min: {hunt_stats['min_hunt_shots']} | Max: {hunt_stats['max_hunt_shots']}")
            
            if seq_stats and seq_stats.get("total_streaks", 0) > 0:
                m2.metric("AS (max)", f"{seq_stats['max_streak']}")
                m2.caption(f"Streak médio: {seq_stats['avg_streak']:.1f}")
                m3.metric("AS Eficiência", f"{seq_stats['efficiency']:.1f}%")
                m3.caption(f"{seq_stats['total_streaks']} streaks")
        
        st.markdown("---")
        
        # Controls
        c1, c2, c3 = st.columns(3)
        show_accuracy = c1.checkbox("Acurácia", value=True)
        show_timeline = c2.checkbox("Timeline", value=True)
        show_remaining = c3.checkbox("Restante", value=True)

        # Accuracy
        if show_accuracy:
            acc = load_accuracy_by_player(db_path, gid_choice, mtime)
            fig = fig_accuracy(acc, gid_choice)
            if fig is None:
                st.info("Sem dados de tiros para esta partida.")
            else:
                st.pyplot(fig, clear_figure=True)

        # Timeline
        if show_timeline:
            tl = load_timeline(db_path, gid_choice, mtime)
            fig = fig_timeline(tl, gid_choice)
            if fig is None:
                st.info("Sem timeline para esta partida.")
            else:
                st.pyplot(fig, clear_figure=True)

        # Remaining over time
        if show_remaining:
            tl = load_timeline(db_path, gid_choice, mtime)
            fig = fig_remaining_over_time(tl)
            if fig is None:
                st.info("Sem dados de remaining_def.")
            else:
                st.pyplot(fig, clear_figure=True)
    else:
        st.info("Selecione uma partida para ver métricas detalhadas.")


with right:
    st.subheader("Heatmaps")
    metric = st.selectbox("Métrica", options=["hit_rate", "count", "hits"], index=0, help="Por partida ou global")
    attacker = st.selectbox("Atacante", options=["Todos", 1, 2], index=0)
    attacker_val = None if attacker == "Todos" else int(attacker)
    W, H = _get_board_size(db_path) if db_exists else (8, 8)

    # Global heatmap
    st.caption("Global (todas as partidas)")
    shots_all = load_shots(db_path, None, mtime) if db_exists else pd.DataFrame()
    if attacker_val in (1, 2):
        shots_all = shots_all[shots_all["attacker"] == attacker_val]
    fig = fig_heatmap(shots_all, W, H, metric=metric, title_prefix="Heatmap global") if not shots_all.empty else None
    if fig is None:
        st.info("Sem tiros no banco.")
    else:
        st.pyplot(fig, clear_figure=True)

    # Per-game heatmap
    st.caption("Por partida selecionada")
    if gid_choice:
        shots_g = load_shots(db_path, gid_choice, mtime)
        if attacker_val in (1, 2):
            shots_g = shots_g[shots_g["attacker"] == attacker_val]
        fig_g = fig_heatmap(shots_g, W, H, metric=metric, title_prefix=f"Heatmap da partida {gid_choice[:8]}…") if not shots_g.empty else None
        if fig_g is None:
            st.info("Sem tiros nesta partida.")
        else:
            st.pyplot(fig_g, clear_figure=True)
    else:
        st.info("Selecione uma partida para ver o heatmap por jogo.")


st.markdown("---")
st.caption("Feito com 💙 usando Streamlit • Dados de battleship coletados pelo Navalytics")
