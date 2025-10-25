# tabs/current_game.py
import time
import streamlit as st
import plotly.graph_objects as go

from core import (
    get_current_gid, get_players, get_board_size, shots_df, get_started_at_ms,
    get_avg_duration_ms, now_ms, ms_to_mmss, player_summary, hit_streaks,
    hunt_to_target, board_heatmap, top_highscores, get_player_ranking_position, sql_df
)

def render(db_path: str, auto: bool, interval_s: int):
    # Compute current/ended state
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

    sel_is_current = st.session_state.get("active_pill") == "🟢 Partida Atual"

    gid = current_gid_now
    show_ended = st.session_state.get("_just_ended", False) and st.session_state.get("_last_ended_gid")

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

        p1_hits = int(s[s["attacker"]==1]["hit"].sum()) if not s.empty else 0
        p2_hits = int(s[s["attacker"]==2]["hit"].sum()) if not s.empty else 0

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

        started_ms = get_started_at_ms(db_path, gid)
        if started_ms:
            elapsed_ms = now_ms() - started_ms
            avg_ms = get_avg_duration_ms(db_path)
            st.caption(
                f"Tempo decorrido: **{ms_to_mmss(elapsed_ms)}**" +
                (f"  •  Média histórica: **{ms_to_mmss(avg_ms)}**" if avg_ms else "")
            )
            if avg_ms:
                elapsed_s = elapsed_ms / 1000.0
                avg_s = avg_ms / 1000.0
                x_max = max(elapsed_s, avg_s) * 1.15 if max(elapsed_s, avg_s) > 0 else 60.0
                bar_color = "limegreen" if elapsed_s <= avg_s else "gold"

                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=[elapsed_s], y=[""], orientation="h",
                    marker_color=bar_color, hovertemplate="Decorrido: %{x:.1f}s<extra></extra>"
                ))
                fig.add_shape(
                    type="line",
                    x0=avg_s, x1=avg_s, y0=-0.4, y1=0.4,
                    line=dict(color="red", width=3, dash="dash")
                )
                fig.add_annotation(
                    x=avg_s, y=0.5,
                    text=f"Média: {ms_to_mmss(avg_ms)}",
                    showarrow=False, yanchor="bottom",
                    font=dict(color="red", size=11)
                )
                fig.update_xaxes(range=[0, x_max], title_text="Segundos")
                fig.update_yaxes(showticklabels=False)
                fig.update_layout(height=110, margin=dict(l=10, r=10, t=10))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Ainda não há média histórica para comparar.")

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

        st.subheader("Mini boards")
        cL, cR = st.columns(2)
        figL = board_heatmap(s[s["attacker"]==1], W, H, f"Ataques do {p1 or 'P1'}")
        figR = board_heatmap(s[s["attacker"]==2], W, H, f"Ataques do {p2 or 'P2'}")

        cell_px = 30
        min_px, max_px = 200, 800
        height_px = int(max(min_px, min(max_px, cell_px * H + 80)))
        width_px  = int(max(min_px, min(max_px, cell_px * W + 80)))

        for fig in (figL, figR):
            fig.update_layout(
                height=height_px, width=width_px,
                yaxis=dict(scaleanchor="x", scaleratio=1, autorange="reversed"),
                margin=dict(l=10, r=10, t=40, b=10),
            )
        cL.plotly_chart(figL, use_container_width=False)
        cR.plotly_chart(figR, use_container_width=False)

    # --- Auto refresh ONLY if user is on this pill, and cancel if pill changes mid-sleep
    if auto and st.session_state.get("active_pill") == "🟢 Partida Atual":
        # bump an epoch; any new run will change this number
        epoch = st.session_state.get("_auto_epoch", 0) + 1
        st.session_state["_auto_epoch"] = epoch

        time.sleep(interval_s)

        # after sleeping, confirm we are STILL on current tab and epoch unchanged
        still_current = st.session_state.get("active_pill") == "🟢 Partida Atual"
        same_epoch = st.session_state.get("_auto_epoch") == epoch
        if still_current and same_epoch:
            st.rerun()
