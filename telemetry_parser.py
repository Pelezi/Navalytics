# telemetry_parser.py
from dataclasses import dataclass
import csv
from typing import Optional, Dict

# Tamanho padrão quando GS não informa WxH
DEFAULT_W = 8
DEFAULT_H = 8

@dataclass
class ParsedEvent:
    kind: str
    data: Dict

def _split(line: str):
    # usa csv para lidar com eventuais vírgulas/escapes futuros
    return next(csv.reader([line], skipinitialspace=True))

def parse_line(line: str) -> Optional[ParsedEvent]:
    line = line.strip()
    if not line:
        return None
    try:
        parts = _split(line)
    except Exception:
        return None

    kind = parts[0]

    # ---------------- PN ----------------
    if kind == 'PN':
        # NOVO: PN,name1,name2
        # LEGADO: PN,gid,name1,name2
        if len(parts) == 3:
            _, name1, name2 = parts
            return ParsedEvent('PN', dict(name1=name1, name2=name2))
        elif len(parts) >= 4:
            # mantém compat se ainda vier gid
            _, _old_gid, name1, name2 = parts[:4]
            return ParsedEvent('PN', dict(name1=name1, name2=name2))
        else:
            return None

    # ---------------- GS ----------------
    if kind == 'GS':
        # NOVO: GS,matchStartMs
        # LEGADO: GS,gid,matchStartMs  OU  GS,gid,WxH,matchStartMs
        if len(parts) == 2:
            _, start_ms = parts
            return ParsedEvent('GS', dict(
                w=DEFAULT_W, h=DEFAULT_H, started_at_ms=int(start_ms)
            ))
        elif len(parts) == 3:
            # antigo sem WxH (tinha gid no meio) -> ignora gid
            _, _old_gid, start_ms = parts
            return ParsedEvent('GS', dict(
                w=DEFAULT_W, h=DEFAULT_H, started_at_ms=int(start_ms)
            ))
        elif len(parts) >= 4:
            # antigo com WxH
            _, _old_gid, wh, start_ms = parts[:4]
            if 'x' in wh:
                w_str, h_str = wh.split('x', 1)
                w, h = int(w_str), int(h_str)
            else:
                w, h = DEFAULT_W, DEFAULT_H
            return ParsedEvent('GS', dict(w=w, h=h, started_at_ms=int(start_ms)))
        else:
            return None

    # ---------------- PS ----------------
    if kind == 'PS':
        # NOVO: PS,player,x,y,len,horiz,ts
        # LEGADO: PS,gid,player,x,y,len,horiz,ts
        if len(parts) == 7:
            _, player, x, y, ln, hz, ts = parts
        elif len(parts) >= 8:
            _, _old_gid, player, x, y, ln, hz, ts = parts[:8]
        else:
            return None
        return ParsedEvent('PS', dict(
            player=int(player), x=int(x), y=int(y),
            len=int(ln), horiz=int(hz), ts_ms=int(ts)
        ))

    # ---------------- SH ----------------
    if kind == 'SH':
        # NOVO: SH,attacker,defender,x,y,hit,sunk,remaining_def,ts
        # LEGADO: SH,gid,attacker,defender,x,y,hit,sunk,remaining_def,ts
        if len(parts) == 9:
            _, atk, dfd, x, y, hit, sunk, rem, ts = parts
        elif len(parts) >= 10:
            _, _old_gid, atk, dfd, x, y, hit, sunk, rem, ts = parts[:10]
        else:
            return None
        return ParsedEvent('SH', dict(
            attacker=int(atk), defender=int(dfd),
            x=int(x), y=int(y), hit=int(hit), sunk=int(sunk),
            remaining_def=int(rem), ts_ms=int(ts)
        ))

    # ---------------- GE ----------------
    if kind == 'GE':
        # NOVO: GE,winner,dur,name1,shots1,hits1,sunkCells1,score1,name2,shots2,hits2,sunkCells2,score2,ts
        # LEGADO: GE,gid, ... (mesma sequência depois do gid)
        if len(parts) == 14:
            (_,
             winner, dur, name1, shots1, hits1, sunk1, score1,
             name2, shots2, hits2, sunk2, score2, ts) = parts
        elif len(parts) >= 15:
            (_,
             _old_gid, winner, dur, name1, shots1, hits1, sunk1, score1,
             name2, shots2, hits2, sunk2, score2, ts) = parts[:15]
        else:
            return None
        return ParsedEvent('GE', dict(
            winner=int(winner), duration_ms=int(dur),
            p1_name=name1, p1_shots=int(shots1), p1_hits=int(hits1),
            p1_sunk_cells=int(sunk1), p1_score=int(score1),
            p2_name=name2, p2_shots=int(shots2), p2_hits=int(hits2),
            p2_sunk_cells=int(sunk2), p2_score=int(score2),
            finished_at_ms=int(ts)
        ))

    return None
