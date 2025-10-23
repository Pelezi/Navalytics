# metrics.py
import argparse
import os
import sqlite3

import pandas as pd
import matplotlib.pyplot as plt

DB_PATH = "battleship.db"

# -------- DataFrames base --------
def df_games(conn):
    return pd.read_sql_query("SELECT * FROM games", conn)

def df_players(conn):
    return pd.read_sql_query("SELECT * FROM players", conn)

def df_game_end(conn):
    return pd.read_sql_query("SELECT * FROM game_end", conn)

def df_shots(conn, gid=None):
    q = "SELECT * FROM shots"
    if gid:
        q += " WHERE gid = ?"
        return pd.read_sql_query(q, conn, params=[gid])
    return pd.read_sql_query(q, conn)

def df_placements(conn, gid=None):
    q = "SELECT * FROM placements"
    if gid:
        q += " WHERE gid = ?"
        return pd.read_sql_query(q, conn, params=[gid])
    return pd.read_sql_query(q, conn)

# -------- Resumos úteis --------
def list_games_table(conn):
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
    ORDER BY g.rowid ASC
    """
    return pd.read_sql_query(q, conn)

def accuracy_by_player(conn, gid):
    shots = df_shots(conn, gid)
    if shots.empty:
        return pd.DataFrame(columns=["player", "shots", "hits", "accuracy"])
    agg = shots.groupby("attacker").agg(shots=("id","count"),
                                        hits=("hit","sum")).reset_index()
    agg["accuracy"] = agg["hits"] / agg["shots"]
    agg.rename(columns={"attacker":"player"}, inplace=True)
    return agg

def timeline_hits(conn, gid):
    shots = df_shots(conn, gid)
    if shots.empty:
        return shots
    return shots.sort_values("ts_ms")[["ts_ms","attacker","defender","hit","sunk","remaining_def"]]

# -------- KPIs agregados --------
def per_game_metrics(conn):
    """Tabela por partida com KPIs básicos; serve de base para médias."""
    games = df_games(conn)
    ge = df_game_end(conn)
    shots = df_shots(conn)
    if games.empty:
        return pd.DataFrame()

    # agregados por partida
    ag = shots.groupby("gid").agg(
        total_shots=("id","count"),
        total_hits=("hit","sum"),
        p1_shots=("attacker", lambda s: (s==1).sum()),
        p1_hits=("hit", lambda h: int(h[shots.loc[h.index, "attacker"]==1].sum())),
        p2_shots=("attacker", lambda s: (s==2).sum()),
        p2_hits=("hit", lambda h: int(h[shots.loc[h.index, "attacker"]==2].sum())),
        first_hit_ts=("ts_ms", lambda s: shots.loc[s.index][shots.loc[s.index, "hit"]==1]["ts_ms"].min()
                      if (shots.loc[s.index, "hit"]==1).any() else pd.NA),
        first_shot_ts=("ts_ms","min")
    ).reset_index()

    # junta started_at para calcular tempo até o primeiro acerto
    m = games.merge(ag, on="gid", how="left").merge(ge, on="gid", how="left", suffixes=("","_ge"))
    # acurácias
    m["p1_acc"] = (m["p1_hits"] / m["p1_shots"]).fillna(0)
    m["p2_acc"] = (m["p2_hits"] / m["p2_shots"]).fillna(0)
    m["overall_acc"] = (m["total_hits"] / m["total_shots"]).fillna(0)
    # tempo até 1º acerto (se tivermos started_at_ms e first_hit_ts)
    m["first_hit_s"] = ((m["first_hit_ts"] - m["started_at_ms"]) / 1000.0).where(m["first_hit_ts"].notna())
    # limpa colunas auxiliares
    keep = ["gid","w","h","started_at_ms","duration_ms","winner",
            "total_shots","total_hits","overall_acc",
            "p1_shots","p1_hits","p1_acc","p2_shots","p2_hits","p2_acc",
            "first_hit_s"]
    return m[keep]

def sequential_hits_analysis(conn, gid):
    """
    Analisa sequências de acertos consecutivos (AS - Acertos em Sequência).
    Retorna estatísticas sobre streaks de hits no mesmo navio.
    """
    shots = df_shots(conn, gid)
    if shots.empty:
        return {}
    
    shots = shots.sort_values("ts_ms")
    streaks = []
    current_streak = 0
    
    for _, shot in shots.iterrows():
        if shot["hit"] == 1:
            current_streak += 1
        else:
            if current_streak > 0:
                streaks.append(current_streak)
            current_streak = 0
    
    if current_streak > 0:
        streaks.append(current_streak)
    
    if not streaks:
        return {
            "max_streak": 0,
            "avg_streak": 0.0,
            "total_streaks": 0,
            "efficiency": 0.0  # % de acertos que fazem parte de streaks >1
        }
    
    hits_in_streaks = sum(s for s in streaks if s > 1)
    total_hits = shots["hit"].sum()
    
    return {
        "max_streak": max(streaks),
        "avg_streak": sum(streaks) / len(streaks),
        "total_streaks": len(streaks),
        "efficiency": (hits_in_streaks / total_hits * 100) if total_hits > 0 else 0.0
    }

def hunt_to_target_metrics(conn, gid):
    """
    Calcula métricas Hunt→Target: tiros até o primeiro acerto de cada navio.
    Identifica novos navios pelo campo 'sunk' e 'remaining_def'.
    """
    shots = df_shots(conn, gid)
    if shots.empty:
        return {}
    
    shots = shots.sort_values("ts_ms")
    hunt_phases = []
    shots_since_last_hit = 0
    
    for _, shot in shots.iterrows():
        shots_since_last_hit += 1
        if shot["hit"] == 1:
            # Primeiro acerto em um navio (nova fase Hunt→Target)
            hunt_phases.append(shots_since_last_hit)
            shots_since_last_hit = 0
    
    if not hunt_phases:
        return {
            "avg_hunt_shots": 0.0,
            "min_hunt_shots": 0,
            "max_hunt_shots": 0,
            "total_hunts": 0
        }
    
    return {
        "avg_hunt_shots": sum(hunt_phases) / len(hunt_phases),
        "min_hunt_shots": min(hunt_phases),
        "max_hunt_shots": max(hunt_phases),
        "total_hunts": len(hunt_phases)
    }

def first_player_advantage(conn):
    """
    Calcula a vantagem estatística do primeiro jogador (Win Rate de quem começa).
    Identifica quem jogou primeiro pelo primeiro tiro em cada partida.
    """
    games = df_games(conn)
    ge = df_game_end(conn)
    shots = df_shots(conn)
    
    if games.empty or ge.empty or shots.empty:
        return {}
    
    # Para cada partida, determinar quem jogou primeiro
    first_players = {}
    for gid in games["gid"]:
        game_shots = shots[shots["gid"] == gid].sort_values("ts_ms")
        if not game_shots.empty:
            first_players[gid] = game_shots.iloc[0]["attacker"]
    
    # Contar vitórias
    first_won = 0
    second_won = 0
    
    for _, game in ge.iterrows():
        gid = game["gid"]
        winner = game["winner"]
        if gid in first_players:
            if first_players[gid] == winner:
                first_won += 1
            else:
                second_won += 1
    
    total = first_won + second_won
    if total == 0:
        return {}
    
    return {
        "first_player_wins": first_won,
        "second_player_wins": second_won,
        "first_player_win_rate": (first_won / total) * 100,
        "total_games": total
    }

def overall_averages(conn):
    """KPIs médios e globais (todas as partidas)."""
    pg = per_game_metrics(conn)
    shots = df_shots(conn)
    if pg.empty:
        return {}

    avg_duration_ms = pg["duration_ms"].dropna().mean() if "duration_ms" in pg else None
    avg_shots_per_game = pg["total_shots"].mean()
    avg_hits_per_game  = pg["total_hits"].mean()
    avg_overall_acc_per_game = pg["overall_acc"].mean()  # média de acurácia por partida
    # acurácia global (soma dos acertos dividido por soma dos tiros)
    if shots.empty:
        global_acc = None
    else:
        global_acc = shots["hit"].sum() / len(shots)
    avg_first_hit_s = pg["first_hit_s"].dropna().mean() if "first_hit_s" in pg else None

    # Agregar métricas avançadas
    first_player_stats = first_player_advantage(conn)
    
    # Médias de hunt-to-target e sequential hits por todas as partidas
    all_hunt_shots = []
    all_max_streaks = []
    all_avg_streaks = []
    all_efficiencies = []
    
    for gid in pg["gid"]:
        hunt = hunt_to_target_metrics(conn, gid)
        if hunt and hunt.get("total_hunts", 0) > 0:
            all_hunt_shots.append(hunt["avg_hunt_shots"])
        
        seq = sequential_hits_analysis(conn, gid)
        if seq and seq.get("total_streaks", 0) > 0:
            all_max_streaks.append(seq["max_streak"])
            all_avg_streaks.append(seq["avg_streak"])
            all_efficiencies.append(seq["efficiency"])
    
    return {
        "n_games": len(pg),
        "avg_duration_ms": avg_duration_ms,
        "avg_shots_per_game": avg_shots_per_game,
        "avg_hits_per_game": avg_hits_per_game,
        "avg_overall_acc_per_game": avg_overall_acc_per_game,
        "global_accuracy": global_acc,
        "avg_first_hit_s": avg_first_hit_s,
        # Novas métricas
        "first_player_win_rate": first_player_stats.get("first_player_win_rate"),
        "first_player_wins": first_player_stats.get("first_player_wins", 0),
        "second_player_wins": first_player_stats.get("second_player_wins", 0),
        "avg_hunt_to_target": sum(all_hunt_shots) / len(all_hunt_shots) if all_hunt_shots else None,
        "avg_max_streak": sum(all_max_streaks) / len(all_max_streaks) if all_max_streaks else None,
        "avg_streak_efficiency": sum(all_efficiencies) / len(all_efficiencies) if all_efficiencies else None,
    }

# -------- Gráficos --------
def _maybe_save(show_or_save, outdir, filename):
    if show_or_save is None:
        plt.show()
    else:
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, filename)
        plt.tight_layout()
        plt.savefig(path, dpi=120, bbox_inches="tight")
        print(f"[saved] {path}")
    plt.close()

def plot_accuracy_bar(conn, gid, show_or_save=None, outdir="figs"):
    acc = accuracy_by_player(conn, gid)
    if acc.empty:
        print("Sem dados de tiros para este gid.")
        return
    ax = acc.plot(kind="bar", x="player", y="accuracy", legend=False, rot=0)
    ax.set_title(f"Acurácia por Jogador (gid={gid[:8]}…)")
    ax.set_xlabel("Jogador")
    ax.set_ylabel("Acurácia")
    _maybe_save(show_or_save, outdir, f"{gid}_accuracy.png")

def plot_shots_over_time(conn, gid, show_or_save=None, outdir="figs"):
    tl = timeline_hits(conn, gid)
    if tl.empty:
        print("Sem timeline para este gid.")
        return
    tl = tl.copy()
    tl["t"] = (tl["ts_ms"] - tl["ts_ms"].min())/1000.0
    ax = tl.plot(x="t", y="hit", kind="line", legend=False)
    ax.set_title(f"Tiros (hit=1/miss=0) ao longo do tempo (gid={gid[:8]}…)")
    ax.set_xlabel("Segundos desde o início")
    ax.set_ylabel("Hit (1) / Miss (0)")
    _maybe_save(show_or_save, outdir, f"{gid}_timeline.png")

def _board_size(conn, default=(8,8)):
    g = df_games(conn)
    if g.empty:
        return default
    unique = g[["w","h"]].drop_duplicates()
    if len(unique) == 1:
        r = unique.iloc[0]
        return int(r["w"]), int(r["h"])
    # tamanhos diferentes: avisa e usa o primeiro
    r = unique.iloc[0]
    print(f"[warn] Tamanhos de tabuleiro variados. Usando {int(r['w'])}x{int(r['h'])} para o heatmap.")
    return int(r["w"]), int(r["h"])

def plot_shot_heatmap(conn, gid, metric="hit_rate", attacker=None, show_or_save=None, outdir="figs"):
    """
    Heatmap por partida.
    metric: 'count' (total de tiros), 'hits' (só acertos) ou 'hit_rate' (acertos/tiros)
    attacker: None = todos, 1 ou 2
    """
    shots = df_shots(conn, gid)
    if shots.empty:
        print("Sem tiros neste gid.")
        return
    if attacker in (1,2):
        shots = shots[shots["attacker"] == attacker]

    W, H = _board_size(conn, default=(8,8))
    grid_count = pd.DataFrame(0, index=range(H), columns=range(W))
    grid_hits  = pd.DataFrame(0, index=range(H), columns=range(W))

    for _, row in shots.iterrows():
        x, y = int(row["x"]), int(row["y"])
        if 0 <= x < W and 0 <= y < H:
            grid_count.loc[y, x] += 1
            if row["hit"]:
                grid_hits.loc[y, x] += 1

    if metric == "count":
        Z = grid_count.values
        title = "Heatmap de tiros (quantidade)"
    elif metric == "hits":
        Z = grid_hits.values
        title = "Heatmap de acertos"
    else:  # hit_rate
        rate = grid_hits / grid_count.where(grid_count != 0)
        rate = rate.fillna(0)
        Z = rate.values
        title = "Heatmap de taxa de acerto"

    plt.figure(figsize=(5,5))
    plt.imshow(Z, origin="upper", interpolation="nearest")
    plt.title(f"{title} (gid={gid[:8]}…"
              + (f", attacker={attacker}" if attacker in (1,2) else ", ambos")
              + ")")
    plt.xlabel("X")
    plt.ylabel("Y")
    plt.colorbar()
    _maybe_save(show_or_save, outdir, f"{gid}_heatmap_{metric}{'' if attacker is None else f'_p{attacker}'}{'.png'}")

def plot_global_heatmap(conn, metric="hit_rate", attacker=None, show_or_save=None, outdir="figs"):
    """
    Heatmap agregando todas as partidas.
    metric: 'count' | 'hits' | 'hit_rate'
    attacker: None (todos), 1, 2
    """
    shots = df_shots(conn)
    if shots.empty:
        print("Sem tiros no banco.")
        return
    if attacker in (1,2):
        shots = shots[shots["attacker"] == attacker]

    W, H = _board_size(conn, default=(8,8))
    grid_count = pd.DataFrame(0, index=range(H), columns=range(W))
    grid_hits  = pd.DataFrame(0, index=range(H), columns=range(W))

    for _, row in shots.iterrows():
        x, y = int(row["x"]), int(row["y"])
        if 0 <= x < W and 0 <= y < H:
            grid_count.loc[y, x] += 1
            if row["hit"]:
                grid_hits.loc[y, x] += 1

    if metric == "count":
        Z = grid_count.values
        title = "Heatmap global – quantidade de tiros"
        fname = f"ALL_heatmap_count"
    elif metric == "hits":
        Z = grid_hits.values
        title = "Heatmap global – acertos"
        fname = f"ALL_heatmap_hits"
    else:
        rate = grid_hits / grid_count.where(grid_count != 0)
        rate = rate.fillna(0)
        Z = rate.values
        title = "Heatmap global – taxa de acerto"
        fname = f"ALL_heatmap_hit_rate"

    plt.figure(figsize=(5,5))
    plt.imshow(Z, origin="upper", interpolation="nearest")
    plt.title(title + (f" (attacker={attacker})" if attacker in (1,2) else ""))
    plt.xlabel("X")
    plt.ylabel("Y")
    plt.colorbar()
    suffix = "" if attacker is None else f"_p{attacker}"
    _maybe_save(show_or_save, outdir, f"{fname}{suffix}.png")

def plot_remaining_over_time(conn, gid, show_or_save=None, outdir="figs"):
    tl = timeline_hits(conn, gid)
    if tl.empty:
        print("Sem dados de remaining_def.")
        return
    tl = tl.copy()
    tl["t"] = (tl["ts_ms"] - tl["ts_ms"].min())/1000.0

    # Série para quanto resta do defensor 1 e 2 ao longo do tempo
    d1 = tl[tl["defender"]==1][["t","remaining_def"]].rename(columns={"remaining_def":"def1_remaining"})
    d2 = tl[tl["defender"]==2][["t","remaining_def"]].rename(columns={"remaining_def":"def2_remaining"})

    plt.figure()
    if not d1.empty:
        plt.step(d1["t"], d1["def1_remaining"], where="post", label="Defensor 1")
    if not d2.empty:
        plt.step(d2["t"], d2["def2_remaining"], where="post", label="Defensor 2")
    plt.title("Células restantes por defensor")
    plt.xlabel("Segundos desde o início")
    plt.ylabel("Células restantes")
    plt.legend()
    _maybe_save(show_or_save, outdir, f"{gid}_remaining.png")

# -------- CLI --------
def main():
    ap = argparse.ArgumentParser(description="Navalytics – métricas e gráficos")
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--list", action="store_true", help="Lista partidas com resumo")
    ap.add_argument("--gid", help="GID específico (para gráficos por partida)")
    ap.add_argument("--latest", action="store_true", help="Usa a última partida")
    ap.add_argument("--aggregate", action="store_true", help="Mostra KPIs médios (todas as partidas)")
    ap.add_argument("--plot", nargs="*", choices=["accuracy","timeline","heatmap","remaining","heatmap_all"],
                    help="Quais gráficos gerar")
    ap.add_argument("--heatmap-metric", default="hit_rate",
                    choices=["hit_rate","count","hits"], help="Métrica do heatmap (por partida ou global)")
    ap.add_argument("--attacker", type=int, choices=[1,2], help="Filtra heatmap por atacante (1/2)")
    ap.add_argument("--save", metavar="DIR", help="Salva PNGs em DIR (não abre janela)")
    args = ap.parse_args()

    with sqlite3.connect(args.db) as conn:
        if args.list:
            tbl = list_games_table(conn)
            if tbl.empty:
                print("Sem partidas ainda.")
            else:
                pretty = tbl.copy()
                pretty["gid"] = pretty["gid"].apply(lambda s: s[:8]+"…")
                for p in (1,2):
                    shots, hits = f"p{p}_shots", f"p{p}_hits"
                    if shots in pretty and hits in pretty:
                        pretty[f"p{p}_acc"] = (pretty[hits] / pretty[shots]).fillna(0).round(3)
                cols = ["gid","p1","p2","winner","duration_ms","p1_shots","p1_hits","p1_acc","p2_shots","p2_hits","p2_acc"]
                cols = [c for c in cols if c in pretty.columns]
                print(pretty[cols].to_string(index=False))

        if args.aggregate:
            k = overall_averages(conn)
            if not k:
                print("Sem partidas para agregar.")
            else:
                print("\n=== KPIs médios (todas as partidas) ===")
                print(f"Partidas:                {k['n_games']}")
                if k["avg_duration_ms"] is not None:
                    print(f"Duração média (ms):      {k['avg_duration_ms']:.0f}")
                print(f"Tiros por partida (méd): {k['avg_shots_per_game']:.2f}")
                print(f"Acertos por partida (m): {k['avg_hits_per_game']:.2f}")
                if k["avg_overall_acc_per_game"] is not None:
                    print(f"Acurácia média por jogo: {k['avg_overall_acc_per_game']*100:.2f}%")
                if k["global_accuracy"] is not None:
                    print(f"Acurácia global:         {k['global_accuracy']*100:.2f}%")
                if k["avg_first_hit_s"] is not None:
                    print(f"Tempo médio até 1º hit:  {k['avg_first_hit_s']:.2f} s")
                
                # Novas métricas avançadas
                print("\n=== Métricas Avançadas ===")
                if k.get("first_player_win_rate") is not None:
                    print(f"Win Rate 1º jogador:     {k['first_player_win_rate']:.1f}% ({k['first_player_wins']}/{k['first_player_wins']+k['second_player_wins']} vitórias)")
                if k.get("avg_hunt_to_target") is not None:
                    print(f"Hunt→Target médio:       {k['avg_hunt_to_target']:.2f} tiros")
                if k.get("avg_max_streak") is not None:
                    print(f"Streak máximo médio:     {k['avg_max_streak']:.2f} acertos")
                if k.get("avg_streak_efficiency") is not None:
                    print(f"Eficiência de streaks:   {k['avg_streak_efficiency']:.1f}%")

        # escolher gid por conveniência
        gid = args.gid
        if args.latest and not gid:
            games = df_games(conn)
            if games.empty:
                print("Sem partidas para exibir.")
            else:
                gid = games.iloc[-1]["gid"]

        # gráficos
        if args.plot:
            show_or_save = args.save  # None -> abre janela; DIR -> salva PNGs
            if "heatmap_all" in args.plot:
                plot_global_heatmap(conn, metric=args.heatmap_metric,
                                    attacker=args.attacker,
                                    show_or_save=show_or_save, outdir=args.save or "figs")

            # Gráficos por partida precisam de gid
            need_gid = set(args.plot) & {"accuracy","timeline","heatmap","remaining"}
            if need_gid and not gid:
                print("Você pediu gráficos por partida mas não forneceu --gid nem --latest.")
            else:
                if "accuracy" in args.plot:
                    plot_accuracy_bar(conn, gid, show_or_save, args.save or "figs")
                if "timeline" in args.plot:
                    plot_shots_over_time(conn, gid, show_or_save, args.save or "figs")
                if "heatmap" in args.plot:
                    plot_shot_heatmap(conn, gid, metric=args.heatmap_metric,
                                      attacker=args.attacker,
                                      show_or_save=show_or_save, outdir=args.save or "figs")
                if "remaining" in args.plot:
                    plot_remaining_over_time(conn, gid, show_or_save, args.save or "figs")

        # sumário rápido se nada mais foi pedido
        if not args.list and not args.aggregate and not args.plot:
            tbl = list_games_table(conn)
            if tbl.empty:
                print("Sem partidas ainda.")
            else:
                last = tbl.iloc[-1]
                print("Última partida:")
                print(last.to_string())

if __name__ == "__main__":
    main()