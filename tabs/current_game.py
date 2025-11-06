# tabs/current_game.py
import time
import html
from app import PLOT_CONFIG
import streamlit as st
import plotly.graph_objects as go

from core import (
    get_current_gid, get_players, shots_df, get_started_at_ms, now_ms, ms_to_mmss, player_summary, hit_streaks,
    hunt_to_target, top_highscores, get_player_ranking_position, sql_df
)

TOTAL_SHIPS = 5      # ajuste se necessário
CELL_PX = 56        # tamanho do "quadradinho" do tabuleiro (px)
MIN_SIZE = 360      # tamanho mínimo do tabuleiro (px)
MAX_SIZE = 760      # tamanho máximo do tabuleiro (px)

# ---------- Helpers visuais ----------
def _letters(n: int) -> list[str]:
    return [chr(65 + i) for i in range(n)]

def _coord(x: int, y: int) -> str:
    return f"{chr(65 + int(x))}{int(y) + 1}"

def _fmt_ago(ts_ms: int) -> str:
    if ts_ms is None:
        return "—"
    delta = max(0, int((now_ms() - int(ts_ms)) / 1000))
    return f"{delta//60:02d}:{delta%60:02d}"

def board_figure(shots, W: int, H: int, title: str) -> go.Figure:
    """Grid quadrado, com X (acerto), círculo (erro) e destaque de navios afundados."""
    from collections import deque

    fig = go.Figure()

    # --- Split shots
    erro   = shots[shots["hit"] == 0] if not shots.empty else shots
    acerto = shots[shots["hit"] == 1] if not shots.empty else shots

    # --- Compute sunk ship components (per board = per attacker)
    sunk_cells = set()
    if not shots.empty and "sunk" in shots.columns:
        # all hit cells on this board
        hit_cells = {(int(r["x"]), int(r["y"])) for _, r in shots.iterrows() if int(r.get("hit", 0)) == 1}

        def neighbors(c):
            x, y = c
            return [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]

        def component(start):
            """Return 4-neighbor connected component of hits containing start."""
            seen, dq = set(), deque([start])
            while dq:
                c = dq.popleft()
                if c in seen or c not in hit_cells:
                    continue
                seen.add(c)
                for nb in neighbors(c):
                    if nb in hit_cells and nb not in seen:
                        dq.append(nb)
            return seen

        # for each finalizing hit (sunk==1), collect the whole ship component
        sunk_hits = shots[(shots["hit"] == 1) & (shots["sunk"] == 1)]
        for _, r in sunk_hits.iterrows():
            start = (int(r["x"]), int(r["y"]))
            sunk_cells |= component(start)

    # --- Draw sunk overlays (below traces)
    for (x, y) in sunk_cells:
        # plot coords are 1-based centers; cell bounds are ±0.5
        cx, cy = x + 1, y + 1
        fig.add_shape(
            type="rect",
            x0=cx - 0.5, x1=cx + 0.5, y0=cy - 0.5, y1=cy + 0.5,
            fillcolor="rgba(34,197,94,0.28)",  # green @ ~28%
            line=dict(color="#22c55e", width=2),
            layer="below",
        )

    # Legend chip for sunk overlay
    if sunk_cells:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(symbol="square", size=14,
                        color="rgba(34,197,94,0.28)",
                        line=dict(color="#22c55e", width=2)),
            name="Navio afundado",
            hoverinfo="skip", showlegend=True
        ))

    # --- Misses
    if not erro.empty:
        fig.add_trace(go.Scatter(
            x=erro["x"] + 1, y=erro["y"] + 1,
            mode="markers", name="Erro",
            marker=dict(symbol="circle-open", size=18, line=dict(width=2, color="#4aa3ff")),
            hovertemplate="Erro • %{text}<extra></extra>",
            text=[_coord(int(x), int(y)) for x, y in zip(erro["x"], erro["y"])]
        ))

    # --- Hits
    if not acerto.empty:
        fig.add_trace(go.Scatter(
            x=acerto["x"] + 1, y=acerto["y"] + 1,
            mode="markers", name="Acerto",
            marker=dict(symbol="x", size=18, line=dict(width=3, color="#ff6b6b")),
            hovertemplate="Acerto • %{text}<extra></extra>",
            text=[_coord(int(x), int(y)) for x, y in zip(acerto["x"], acerto["y"])]
        ))

    # --- Grid lines
    for x in range(W + 1):
        fig.add_shape(type="line", x0=x + 0.5, x1=x + 0.5, y0=0.5, y1=H + 0.5,
                      line=dict(color="rgba(255,255,255,.15)", width=1))
    for y in range(H + 1):
        fig.add_shape(type="line", x0=0.5, x1=W + 0.5, y0=y + 0.5, y1=y + 0.5,
                      line=dict(color="rgba(255,255,255,.15)", width=1))

    # --- Axes (square cells)
    fig.update_xaxes(
        range=[0.5, W + 0.5], dtick=1, tickmode="array",
        tickvals=list(range(1, W + 1)), ticktext=_letters(W),
        side="top", mirror=False, showgrid=False, fixedrange=True
    )
    fig.update_yaxes(
        range=[H + 0.5, 0.5], dtick=1, tickmode="array",
        tickvals=list(range(1, H + 1)), ticktext=[str(i) for i in range(1, H + 1)],
        autorange=False, mirror=False, showgrid=False, fixedrange=True,
        scaleanchor="x", scaleratio=1
    )

    # --- Square figure size
    side = int(min(MAX_SIZE, max(MIN_SIZE, CELL_PX * max(W, H))))
    fig.update_layout(
        title=title, title_x=0,
        width=side, height=side,
        margin=dict(l=10, r=10, t=66, b=64),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", x=0, xanchor="left", y=-0.12, yanchor="top")
    )
    return fig

def render(db_path: str, auto: bool, interval_s: int):
    # Estado de partida atual/encerrada
    current_gid_now = get_current_gid(db_path)
    prev_has_game = st.session_state.get("_has_game", False)
    has_game_now = current_gid_now is not None

    if prev_has_game and not has_game_now:
        st.session_state["_just_ended"] = True
        st.session_state["_last_ended_gid"] = st.session_state.get("_last_gid", None)
        st.session_state["_balloons_shown"] = False

    st.session_state["_has_game"] = has_game_now
    if has_game_now:
        st.session_state["_last_gid"] = current_gid_now

    gid = current_gid_now
    show_ended = st.session_state.get("_just_ended", False) and st.session_state.get("_last_ended_gid")

    # ---------------- Partida encerrada ----------------
    if show_ended:
        ended_gid = st.session_state["_last_ended_gid"]

        if not st.session_state.get("_balloons_shown", False):
            st.balloons()
            st.session_state["_balloons_shown"] = True

        st.success("🎉 Partida Encerrada!")

        p1, p2 = get_players(db_path, ended_gid)
        s = shots_df(db_path, ended_gid)

        winner_q = "SELECT winner FROM game_end WHERE gid=?"
        winner_df = sql_df(db_path, winner_q, (ended_gid,))
        winner = int(winner_df.iloc[0]["winner"]) if not winner_df.empty else None

        p1_hits = int(s[s["attacker"] == 1]["hit"].sum()) if not s.empty else 0
        p2_hits = int(s[s["attacker"] == 2]["hit"].sum()) if not s.empty else 0

        st.markdown("### 🏁 Resultado Final")
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
            from core import render_ranking_podium_plus_list
            render_ranking_podium_plus_list(rank, limit=10)

        st.info("💡 A próxima partida aparecerá aqui automaticamente quando iniciada.")

    # ---------------- Sem partida ativa ----------------
    elif not gid:
        st.info("Nenhuma partida ativa no momento.")

    # ---------------- Partida em andamento ----------------
    else:
        p1, p2 = get_players(db_path, gid)
        s = shots_df(db_path, gid)

        has_shots = not s.empty

        if not has_shots:
            st.info("⚓ Os jogadores estão posicionando seus navios no tabuleiro...")
            st.markdown(
                f"**Partida:** `{gid}` • **Jogadores:** {html.escape(p1 or 'P1')} × {html.escape(p2 or 'P2')}",
                unsafe_allow_html=True
            )

        # Estilo dos cards/feed
        st.markdown("""
        <style>
          .kpi {border:1px solid rgba(255,255,255,.08); background:rgba(255,255,255,.03);
            border-radius:16px; padding:14px 16px; box-shadow:0 6px 18px rgba(0,0,0,.25);}
          .kpi h3 {margin:0 0 6px 0; font-size:13px; opacity:.85; letter-spacing:.02em;}
          .kpi .v {font-weight:800; font-size:28px;}
          .live {display:inline-flex; align-items:center; gap:8px; font-weight:700; opacity:.9;}
          .dot {width:10px; height:10px; border-radius:50%; background:#22c55e; box-shadow:0 0 12px #22c55e;}
          .feed-card {border:1px solid rgba(255,255,255,.08); background:rgba(255,255,255,.03);
                  border-radius:16px; padding:12px; height:640px; overflow:auto;}
          .evt {border:1px solid rgba(255,255,255,.08); border-radius:12px; padding:10px 12px; margin:8px 0;}
          .pill {display:inline-block; font-weight:800; font-size:11px; padding:2px 8px; border-radius:999px; margin-right:8px;}
          .miss {background:#ff6b6b22; border:1px solid #ff6b6b; color:#ff6b6b;}
          .hit {background:#4aa3ff22; border:1px solid #4aa3ff; color:#4aa3ff;}
          .sunk {background:#22c55e22; border:1px solid #22c55e; color:#22c55e;}
          .evt small {opacity:.8;}
        </style>
        """, unsafe_allow_html=True)

        # Cabeçalho
        st.markdown(
            f"### Partida em andamento  "
            f"<span class='live'><span class='dot'></span>LIVE</span>  "
            f"<span style='opacity:.7'>• Partida: <code>{gid}</code> • Jogadores: <b>{html.escape(p1 or 'P1')}</b> × <b>{html.escape(p2 or 'P2')}</b></span>",
            unsafe_allow_html=True
        )

        # KPIs
        started_ms = get_started_at_ms(db_path, gid)
        elapsed_ms = (now_ms() - started_ms) if started_ms else None
        total_shots = len(s)
        total_hits = int(s["hit"].sum()) if not s.empty else 0
        acc = (total_hits / total_shots * 100.0) if total_shots else 0.0

        p1_sunk = int(s[(s["defender"] == 1) & (s["sunk"] == 1)].shape[0]) if not s.empty else 0
        p2_sunk = int(s[(s["defender"] == 2) & (s["sunk"] == 1)].shape[0]) if not s.empty else 0
        p1_left = max(0, TOTAL_SHIPS - p1_sunk)
        p2_left = max(0, TOTAL_SHIPS - p2_sunk)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown("<div class='kpi'><h3>Acurácia (geral)</h3>"
                        f"<div class='v'>{acc:.1f}%</div></div>", unsafe_allow_html=True)
        with c2:
            st.markdown("<div class='kpi'><h3>Tempo de Partida</h3>"
                        f"<div class='v'>{ms_to_mmss(elapsed_ms) if elapsed_ms else '—'}</div></div>", unsafe_allow_html=True)
        with c3:
            st.markdown("<div class='kpi'><h3>Tiros Disparados</h3>"
                        f"<div class='v'>{total_shots}</div></div>", unsafe_allow_html=True)
        with c4:
            st.markdown("<div class='kpi'><h3>Navios Restantes (P1/P2)</h3>"
                        f"<div class='v'>{p1_left}/{TOTAL_SHIPS} • {p2_left}/{TOTAL_SHIPS}</div></div>", unsafe_allow_html=True)

        # ---------- Linha principal: 2 tabuleiros lado a lado (esq) + feed (dir) ----------
        boards_area, feed_area = st.columns([8, 4], gap="large")

        with boards_area:
            b1, b2 = st.columns(2, gap="large")
            with b1:
                fig1 = board_figure(s[s["attacker"] == 1], 8, 8, f"Tabuleiro — Ataques de {p1 or 'P1'}")
                st.plotly_chart(fig1, config=PLOT_CONFIG)
            with b2:
                fig2 = board_figure(s[s["attacker"] == 2], 8, 8, f"Tabuleiro — Ataques de {p2 or 'P2'}")
                st.plotly_chart(fig2, config=PLOT_CONFIG)

        with feed_area:
            st.markdown("#### Event Feed")
            feed = s.sort_values("ts_ms", ascending=False).head(14)

            # Build all event rows as a single HTML string so they stay inside the card
            rows = []
            if feed.empty:
                rows.append("<div class='evt'><small>Sem eventos ainda.</small></div>")
            else:
                for _, r in feed.iterrows():
                    hit  = int(r.get("hit", 0)) == 1
                    sunk = int(r.get("sunk", 0)) == 1
                    atk  = int(r.get("attacker", 0))
                    who  = (p1 if atk == 1 else p2) or f"Player {atk}"
                    xy   = _coord(int(r.get("x", 0)), int(r.get("y", 0)))
                    ago  = _fmt_ago(int(r.get("ts_ms", now_ms())))
                    pill = f"<span class='pill {'hit' if hit else 'miss'}'>{'Acerto' if hit else 'Erro'}</span>"
                    sunk_pill = " <span class='pill sunk'>Afundou</span>" if sunk else ""
                    rows.append(
                        f"<div class='evt'>{pill}{sunk_pill}"
                        f"<b>{html.escape(who)}</b> • <code>{xy}</code>"
                        f"<br><small>{ago} atrás</small></div>"
                    )

            feed_html = "<div class='feed-card' style='width:100%; display:block;'>" + "".join(rows) + "</div>"
            st.markdown(feed_html, unsafe_allow_html=True)


    # -------- Auto refresh SOMENTE nesta aba --------
    if auto and st.session_state.get("active_pill") == "🟢 Partida Atual":
        epoch = st.session_state.get("_auto_epoch", 0) + 1
        st.session_state["_auto_epoch"] = epoch
        time.sleep(interval_s)
        still_current = st.session_state.get("active_pill") == "🟢 Partida Atual"
        same_epoch = st.session_state.get("_auto_epoch") == epoch
        if still_current and same_epoch:
            st.rerun()
