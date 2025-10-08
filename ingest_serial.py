# ingest_serial.py
import os
import sqlite3
import time
import uuid
from telemetry_parser import parse_line
import serial  # pyserial
from serial.tools import list_ports

DB_PATH = "battleship.db"
SCHEMA_PATH = "schema.sql"

# Porta/baud (leia do ambiente ou autodetecta)
PORT = os.getenv("PORT", "auto")
BAUD = int(os.getenv("BAUD", "115200"))
TIMEOUT = 1  # segundos

def _ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")

def log(level: str, msg: str):
    print(f"[{_ts()}] {level}: {msg}", flush=True)

def ensure_schema(conn: sqlite3.Connection):
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    log("DB", "Schema verificado/aplicado com sucesso.")

# ===== NOVO: gid atual da partida (gerado ao receber PN) =====
CURRENT_GID: str | None = None

def new_db_gid() -> str:
    return uuid.uuid4().hex  # 32 chars hex único

def ensure_current_gid(reason: str) -> str:
    """Garante que exista um CURRENT_GID (cria provisório se necessário)."""
    global CURRENT_GID
    if CURRENT_GID is None:
        CURRENT_GID = new_db_gid()
        log("WARN", f"Nenhum PN recebido antes de {reason}. Criando db_gid provisório: {CURRENT_GID}")
    return CURRENT_GID

def upsert_players(conn, db_gid: str, name1: str, name2: str):
    # cria placeholder de game se ainda não existir
    conn.execute(
        "INSERT OR IGNORE INTO games (gid, w, h, started_at_ms) VALUES (?, ?, ?, ?)",
        (db_gid, 0, 0, int(time.time() * 1000)),
    )
    conn.execute(
        "INSERT OR REPLACE INTO players (gid, player, name) VALUES (?, 1, ?)",
        (db_gid, name1),
    )
    conn.execute(
        "INSERT OR REPLACE INTO players (gid, player, name) VALUES (?, 2, ?)",
        (db_gid, name2),
    )

def handle_event(conn, ev) -> str:
    """Insere/atualiza no banco e retorna uma string de resumo para logging."""
    global CURRENT_GID
    k = ev.kind
    d = ev.data

    if k == "PN":
        # Gera um novo gid para cada nova partida
        CURRENT_GID = new_db_gid()
        upsert_players(conn, CURRENT_GID, d["name1"], d["name2"])
        conn.commit()
        return (f"PN salvo: db_gid={CURRENT_GID} "
                f"p1='{d['name1']}' p2='{d['name2']}'")

    elif k == "GS":
        db_gid = ensure_current_gid("GS")
        conn.execute(
            """
            INSERT INTO games (gid, w, h, started_at_ms)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(gid) DO UPDATE SET
              w=excluded.w, h=excluded.h, started_at_ms=excluded.started_at_ms
        """,
            (db_gid, d["w"], d["h"], d["started_at_ms"]),
        )
        conn.commit()
        return (f"GS salvo: db_gid={db_gid} w={d['w']} h={d['h']} started_at_ms={d['started_at_ms']}")

    elif k == "PS":
        db_gid = ensure_current_gid("PS")
        conn.execute(
            """
            INSERT INTO placements (gid, player, x, y, len, horiz, ts_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (db_gid, d["player"], d["x"], d["y"], d["len"], d["horiz"], d["ts_ms"]),
        )
        conn.commit()
        hv = "H" if d["horiz"] else "V"
        return (f"PS salvo: db_gid={db_gid} p={d['player']} "
                f"pos=({d['x']},{d['y']}) len={d['len']} dir={hv} ts={d['ts_ms']}")

    elif k == "SH":
        db_gid = ensure_current_gid("SH")
        conn.execute(
            """
            INSERT INTO shots (gid, attacker, defender, x, y, hit, sunk, remaining_def, ts_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                db_gid,
                d["attacker"],
                d["defender"],
                d["x"],
                d["y"],
                d["hit"],
                d["sunk"],
                d["remaining_def"],
                d["ts_ms"],
            ),
        )
        conn.commit()
        return (f"SH salvo: db_gid={db_gid} "
                f"{d['attacker']}→{d['defender']} ({d['x']},{d['y']}) "
                f"hit={d['hit']} sunk={d['sunk']} rem={d['remaining_def']} ts={d['ts_ms']}")

    elif k == "GE":
        db_gid = ensure_current_gid("GE")
        # garante players (caso PN tenha sido perdido)
        conn.execute(
            "INSERT OR IGNORE INTO players (gid, player, name) VALUES (?, 1, ?)",
            (db_gid, d["p1_name"]),
        )
        conn.execute(
            "INSERT OR IGNORE INTO players (gid, player, name) VALUES (?, 2, ?)",
            (db_gid, d["p2_name"]),
        )
        conn.execute(
            """
            INSERT INTO game_end
              (gid, winner, duration_ms,
               p1_shots, p1_hits, p1_sunk_cells, p1_score,
               p2_shots, p2_hits, p2_sunk_cells, p2_score,
               finished_at_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(gid) DO UPDATE SET
              winner=excluded.winner,
              duration_ms=excluded.duration_ms,
              p1_shots=excluded.p1_shots, p1_hits=excluded.p1_hits, p1_sunk_cells=excluded.p1_sunk_cells, p1_score=excluded.p1_score,
              p2_shots=excluded.p2_shots, p2_hits=excluded.p2_hits, p2_sunk_cells=excluded.p2_sunk_cells, p2_score=excluded.p2_score,
              finished_at_ms=excluded.finished_at_ms
        """,
            (
                db_gid,
                d["winner"],
                d["duration_ms"],
                d["p1_shots"],
                d["p1_hits"],
                d["p1_sunk_cells"],
                d["p1_score"],
                d["p2_shots"],
                d["p2_hits"],
                d["p2_sunk_cells"],
                d["p2_score"],
                d["finished_at_ms"],
            ),
        )
        conn.commit()
        return (f"GE salvo: db_gid={db_gid} winner={d['winner']} dur={d['duration_ms']}ms")

    else:
        return "Evento desconhecido (não salvo)"

# ===== Serial helpers (auto-port) =====
def pick_port(preferred: str | None):
    ports = list(list_ports.comports())
    if not ports:
        return None
    if preferred:
        for p in ports:
            if p.device.upper() == preferred.upper():
                return p.device
    keywords = ("arduino", "ch340", "wch", "cp210", "ftdi", "usb-serial")
    for p in ports:
        desc = f"{p.description} {p.manufacturer} {p.hwid}".lower()
        if any(k in desc for k in keywords):
            return p.device
    return ports[0].device

def resolve_port():
    if PORT and PORT.lower() != "auto":
        return PORT
    return pick_port(None)

def main():
    log("INFO", f"Tentando abrir Serial @ {BAUD}…")
    conn = sqlite3.connect(DB_PATH)
    ensure_schema(conn)

    while True:
        try:
            chosen = resolve_port()
            if not chosen:
                log("WARN", "Nenhuma porta serial encontrada. Tentando de novo em 2s…")
                time.sleep(2); continue

            log("INFO", f"Usando porta {chosen}")
            with serial.Serial(chosen, BAUD, timeout=TIMEOUT) as ser:
                log("INFO", "Conectado. Lendo eventos… (Ctrl+C para sair)")
                while True:
                    raw = ser.readline()
                    if not raw:
                        continue
                    line = raw.decode(errors="replace").strip()
                    if not line:
                        continue

                    log("RAW", line)
                    try:
                        ev = parse_line(line)
                        if not ev:
                            log("SKIP", "Linha ignorada (parser não reconheceu).")
                            continue
                        msg = handle_event(conn, ev)
                        log("OK", msg)
                    except Exception as e:
                        log("ERR", f"Falha ao processar linha: {e}")

        except serial.SerialException as e:
            log("WARN", f"Serial desconectado: {e}. Re-tentando em 2s…")
            time.sleep(2)
        except KeyboardInterrupt:
            log("INFO", "Encerrando…")
            break
        except Exception as e:
            log("ERR", f"{e}")
            time.sleep(1)

    conn.close()
    log("INFO", "Conexão com DB fechada.")

if __name__ == "__main__":
    main()
