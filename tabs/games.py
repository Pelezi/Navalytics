# tabs/games.py
import html
from datetime import datetime

import pandas as pd
import streamlit as st

from core import games_list, ms_to_mmss, sql_df


def _format_gid(gid) -> str:
    """GM-0001 style (cai para GM-<texto> se não for int)."""
    try:
        return f"Partida {gid}"
    except Exception:
        return f"Partida {gid}"

def _pct(n, d) -> float:
    n = 0 if n is None or pd.isna(n) else float(n)
    d = 0 if d is None or pd.isna(d) else float(d)
    return (n / d * 100.0) if d > 0 else 0.0


def render(db_path: str):
    df = games_list(db_path)

    if df.empty:
        st.info("Sem partidas.")
        return

    # Garante a data de início para cada jogo (sem precisar mexer no core)
    if "started_at_ms" not in df.columns:
        start_df = sql_df(db_path, "SELECT gid, started_at_ms FROM games")
        df = df.merge(start_df, on="gid", how="left")

    # ------- Filtros (Topo) -------
    st.markdown(
        """
        <style>
        .hist-wrap {max-width: 1200px; margin: 0 auto;}
        .hist-head {display:flex; align-items:center; justify-content:space-between; gap:16px; margin: 6px 2px 14px;}
        .hist-title {font-size: 22px; font-weight: 800; margin: 0;}
        .hist-sub {opacity:.75; font-size: 13px; margin-top: 2px;}
        .flt {display:flex; gap:10px; align-items:center;}
        .game-card {
            border:1px solid rgba(255,255,255,.09);
            background: rgba(255,255,255,.03);
            border-radius: 16px;
            padding: 14px 16px;
            margin: 10px 0 14px;
            box-shadow: 0 8px 26px rgba(0,0,0,.30);
        }
        .game-top {display:flex; align-items:center; justify-content:space-between; gap:10px;}
        .gid {font-weight: 800; letter-spacing:.02em;}
        .date {opacity:.75; font-size: 12px; margin-left: 8px;}
        .badge-win {
            display:inline-flex; align-items:center; gap:8px;
            border:1px solid #22c55e; color:#22c55e;
            background: #22c55e22; padding: 4px 10px; border-radius: 999px;
            font-weight: 800; white-space: nowrap;
        }
        .matchup {margin-top: 6px; font-size: 16px;}
        .matchup b {font-weight: 800;}
        .row {
            display:grid; grid-template-columns: 1fr 1fr 1fr; gap:24px;
            margin-top: 12px;
        }
        .stat {opacity:.85; font-size: 12px; margin-bottom: 6px;}
        .val {font-weight: 900; font-size: 22px;}
        .pill {
            display:inline-flex; align-items:center; justify-content:center;
            min-width:64px; padding: 4px 10px; border-radius: 999px;
            border:1px solid rgba(255,255,255,.14);
            background: rgba(255,255,255,.06);
            font-weight:800;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown("<div class='hist-wrap'>", unsafe_allow_html=True)
        # Cabeçalho + filtros
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown(
                "<div class='hist-head'><div>"
                "<div class='hist-title'>Game History</div>"
                "<div class='hist-sub'>Complete match archive and statistics</div>"
                "</div></div>",
                unsafe_allow_html=True,
            )

        # Constrói values para filtro por jogador
        players = sorted(
            set(
                p
                for p in pd.concat([df["p1"], df["p2"]], ignore_index=True)
                .dropna()
                .astype(str)
                .tolist()
            )
        )
        col_f1, col_f2, col_f3 = st.columns([1.1, 1.1, 1.2])
        with col_f1:
            player_filter = st.selectbox("Jogador", ["Todos"] + players, index=0)

        # Aplica filtros
        work = df.copy()

        if player_filter != "Todos":
            work = work[(work["p1"] == player_filter) | (work["p2"] == player_filter)]

        if work.empty:
            st.info("Nenhuma partida encontrada para os filtros atuais.")
            st.markdown("</div>", unsafe_allow_html=True)
            return

        # ------- Render dos cards -------
        for r in work.itertuples(index=False):
            gid = getattr(r, "gid")
            p1 = getattr(r, "p1") or "Jogador 1"
            p2 = getattr(r, "p2") or "Jogador 2"
            winner = int(getattr(r, "winner") or 0)
            dur_ms = getattr(r, "duration_ms")
            p1_shots = int(getattr(r, "p1_shots") or 0)
            p2_shots = int(getattr(r, "p2_shots") or 0)
            p1_hits = int(getattr(r, "p1_hits") or 0)
            p2_hits = int(getattr(r, "p2_hits") or 0)
            started_at_ms = getattr(r, "started_at_ms", None)

            # cálculos
            total_shots = p1_shots + p2_shots
            p1_acc = _pct(p1_hits, p1_shots)
            p2_acc = _pct(p2_hits, p2_shots)
            win_name = p1 if winner == 1 else (p2 if winner == 2 else "—")
            win_acc = p1_acc if winner == 1 else (p2_acc if winner == 2 else 0.0)

            gid_label = _format_gid(gid)
            p1_style = "color: #22c55e;" if winner == 1 else ""
            p2_style = "color: #22c55e;" if winner == 2 else ""
            matchup_html = (
                f"<div class='matchup'><b style='{p1_style}'>{html.escape(p1)}</b> <span style='opacity:.65'>vs</span> "
                f"<b style='{p2_style}'>{html.escape(p2)}</b></div>"
            )

            # card HTML
            card = f"""
            <div class="game-card">
              <div class="game-top">
                <div>
                  <span class="gid">{gid_label}</span>
                  {matchup_html}
                </div>
                <div class="badge-win">🏆 {html.escape(win_name)}</div>
              </div>

              <div class="row">
                <div>
                  <div class="stat">Duração</div>
                  <div class="val">⏱ {ms_to_mmss(dur_ms)}</div>
                </div>
                <div>
                  <div class="stat">Total de Disparos</div>
                  <div class="val">🎯 {total_shots}</div>
                </div>
                <div>
                  <div class="stat">Precisão</div>
                  <div class="val"><span class="pill">{win_acc:.1f}%</span></div>
                </div>
              </div>
            </div>
            """
            st.markdown(card, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)
