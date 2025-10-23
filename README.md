## Navalytics – Dashboard

This repo includes a Streamlit dashboard to explore Battleship metrics stored in a local SQLite database.

### Quick start

1) Install dependencies

```bash
pip install -r requirements.txt
```

2) Start the dashboard

```bash
streamlit run streamlit_app.py
```

3) In the sidebar, set the path to your SQLite DB (default: `battleship.db`).

### What you get

- Global KPIs: average duration, shots, hits, and accuracy
- Games table with player names, winner, and basic stats
- Per-game charts:
	- Accuracy by player
	- Shot timeline
	- Remaining defender cells over time
	- Heatmaps (per-game and global) for count / hits / hit rate, filterable by attacker

### Notes

- The dashboard reuses the data helpers from `metrics.py` and builds matplotlib figures inline.
- If the DB updates while the app is open, click "Recarregar dados" in the sidebar to refresh caches.

