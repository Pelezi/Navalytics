# tabs/dashboard.py
import streamlit as st
import pandas as pd
from core import (
    sql_df, games_list, get_avg_duration_ms, accuracy_global,
    starter_win_rate, avg_first_hit_seconds, avg_turns_per_game, ms_to_mmss,
    global_hit_rate_heatmap, global_hit_rate_heatmap_progressive, get_game_ids_chronological,
    get_first_last_sunk_ship_stats, create_sunk_ship_bar_chart,
    get_first_ship_vs_turns_winner, create_first_ship_vs_turns_chart
)

def render(db_path: str):
    # KPI card styling (matching current_game.py)
    st.markdown("""
    <style>
      .kpi {border:1px solid rgba(255,255,255,.08); background:rgba(255,255,255,.03);
        border-radius:16px; padding:7px 16px; box-shadow:0 6px 18px rgba(0,0,0,.25);}
      .kpi h3 {margin:0; font-size:13px; opacity:.85; letter-spacing:.02em; padding: 0.75rem 0px 0.5rem;}
      .kpi .v {font-weight:800; font-size:28px;}
    </style>
    """, unsafe_allow_html=True)

    colA, colB, colC, colD, colE, colF, colG = st.columns(7)

    # total games
    df_games = sql_df(db_path, "SELECT COUNT(*) AS n_games FROM (SELECT DISTINCT gid FROM games WHERE gid IN (SELECT gid FROM game_end))")
    n_games = int(df_games.iloc[0]["n_games"] or 0)
    with colA:
        st.markdown("<div class='kpi'><h3>Partidas</h3>"
                    f"<div class='v'>{n_games}</div></div>", unsafe_allow_html=True)

    # avg duration
    avg_dur = get_avg_duration_ms(db_path)
    with colB:
        st.markdown("<div class='kpi'><h3>Tempo Médio</h3>"
                    f"<div class='v'>{ms_to_mmss(avg_dur)}</div></div>", unsafe_allow_html=True)

    # shots / game
    df_spg = sql_df(db_path, "SELECT AVG(cnt) AS spg FROM (SELECT gid, COUNT(*) AS cnt FROM shots WHERE gid IN (SELECT gid FROM game_end) GROUP BY gid)")
    spg = float(df_spg.iloc[0]["spg"]) if not df_spg.empty and not pd.isna(df_spg.iloc[0]["spg"]) else None
    with colC:
        st.markdown("<div class='kpi'><h3>Tiros / Partida</h3>"
                    f"<div class='v'>{f'{spg:.2f}' if spg is not None else '—'}</div></div>", unsafe_allow_html=True)

    # avg turns per game
    avg_turns = avg_turns_per_game(db_path)
    with colD:
        st.markdown("<div class='kpi'><h3>Turnos / Partida</h3>"
                    f"<div class='v'>{f'{avg_turns:.1f}' if avg_turns is not None else '—'}</div></div>", unsafe_allow_html=True)

    # global accuracy
    acc = accuracy_global(db_path)
    with colE:
        st.markdown("<div class='kpi'><h3>Taxa de Acerto (global)</h3>"
                    f"<div class='v'>{f'{acc*100:.1f}%' if acc is not None else '—'}</div></div>", unsafe_allow_html=True)

    # starter win rate
    wr = starter_win_rate(db_path)
    with colF:
        st.markdown("<div class='kpi'><h3>Win Rate de quem começa</h3>"
                    f"<div class='v'>{f'{wr*100:.1f}%' if wr is not None else '—'}</div></div>", unsafe_allow_html=True)
    
    # avg time to first hit
    af = avg_first_hit_seconds(db_path)
    with colG:
        st.markdown("<div class='kpi'><h3>Tempo médio para o 1º acerto</h3>"
                    f"<div class='v'>{f'{af:.2f}s' if af is not None else '—'}</div></div>", unsafe_allow_html=True)

    st.divider()    
    
    # Create two columns: heatmap on left, metrics on right
    col_heat, col_metrics = st.columns([1, 1])
    
    with col_heat:
        game_ids = get_game_ids_chronological(db_path)
        
        if len(game_ids) > 0:

            if len(game_ids) > 1:
                
                # Slider to select up to which game to show
                selected_game_idx = st.slider(
                    "",
                    min_value=1,
                    max_value=len(game_ids),
                    value=len(game_ids),
                    format="%d partidas",
                    key="heatmap_slider"
                )
                
                selected_gid = game_ids[selected_game_idx - 1]
                heatmap_fig = global_hit_rate_heatmap_progressive(db_path, max_gid=selected_gid, compact=True)
            else:
                # Show all games
                heatmap_fig = global_hit_rate_heatmap(db_path, compact=True)
            
            if heatmap_fig is not None:
                st.plotly_chart(heatmap_fig, use_container_width=True)
            else:
                st.info("Ainda não há dados suficientes para gerar o heatmap.")
        else:
            st.info("Ainda não há dados suficientes para gerar o heatmap.")
    
    with col_metrics:
                
        # Get first and last sunk ship statistics
        first_df, last_df = get_first_last_sunk_ship_stats(db_path)
        
        if first_df is not None and last_df is not None:
            # First sunk ships bar chart
            st.markdown("**Tamanho médio do primeiro Navio Afundado**")
            first_chart = create_sunk_ship_bar_chart(first_df, "", "#FF6B6B")
            if first_chart:
                first_chart.update_layout(height=250)
                st.plotly_chart(first_chart, use_container_width=True)
                        
            # Last sunk ships bar chart
            st.markdown("**Tamanho médio do último Navio Afundado**")
            last_chart = create_sunk_ship_bar_chart(last_df, "", "#4ECDC4")
            if last_chart:
                last_chart.update_layout(height=250)
                st.plotly_chart(last_chart, use_container_width=True)
        else:
            st.info("Ainda não há dados suficientes sobre navios afundados.")
    
    st.divider()
    
    turns_data = get_first_ship_vs_turns_winner(db_path)
    if turns_data is not None:
        turns_chart = create_first_ship_vs_turns_chart(turns_data)
        if turns_chart:
            st.plotly_chart(turns_chart, use_container_width=True)
    else:
        st.info("Ainda não há dados suficientes para análise de estratégia.")
        
        