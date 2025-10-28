PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS games (
  gid INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
  gid INTEGER NOT NULL,
  player INTEGER NOT NULL CHECK(player IN (1,2)),
  name TEXT NOT NULL,
  PRIMARY KEY (gid, player),
  FOREIGN KEY (gid) REFERENCES games(gid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS placements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  gid INTEGER NOT NULL,
  player INTEGER NOT NULL CHECK(player IN (1,2)),
  x INTEGER NOT NULL,
  y INTEGER NOT NULL,
  len INTEGER NOT NULL,
  horiz INTEGER NOT NULL,                     -- 0 = vertical, 1 = horizontal
  ts_ms INTEGER NOT NULL,
  FOREIGN KEY (gid) REFERENCES games(gid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS shots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  gid INTEGER NOT NULL,
  attacker INTEGER NOT NULL CHECK(attacker IN (1,2)),
  defender INTEGER NOT NULL CHECK(defender IN (1,2)),
  x INTEGER NOT NULL,
  y INTEGER NOT NULL,
  hit INTEGER NOT NULL,                       -- 0/1
  sunk INTEGER NOT NULL,                      -- 0/1
  remaining_def INTEGER NOT NULL,
  ts_ms INTEGER NOT NULL,
  FOREIGN KEY (gid) REFERENCES games(gid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS game_end (
  gid INTEGER PRIMARY KEY,
  winner INTEGER NOT NULL CHECK(winner IN (1,2)),
  duration_ms INTEGER NOT NULL,
  p1_shots INTEGER NOT NULL,
  p1_hits INTEGER NOT NULL,
  p1_sunk_cells INTEGER NOT NULL,
  p1_score INTEGER NOT NULL,
  p2_shots INTEGER NOT NULL,
  p2_hits INTEGER NOT NULL,
  p2_sunk_cells INTEGER NOT NULL,
  p2_score INTEGER NOT NULL,
  finished_at_ms INTEGER NOT NULL,
  FOREIGN KEY (gid) REFERENCES games(gid) ON DELETE CASCADE
);

-- Índices úteis
CREATE INDEX IF NOT EXISTS idx_shots_gid_ts ON shots(gid, ts_ms);
CREATE INDEX IF NOT EXISTS idx_placements_gid ON placements(gid);
