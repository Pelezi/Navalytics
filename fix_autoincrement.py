"""
Script to reset the auto-increment counter for the games table.
This will make the next game use ID 4 instead of 5.
"""
import sqlite3

DB_PATH = "battleship.db"

def fix_autoincrement():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Check current state
    print("Current state:")
    cur.execute("SELECT name, seq FROM sqlite_sequence WHERE name='games'")
    result = cur.fetchone()
    if result:
        print(f"  Table: {result[0]}, Next ID will be: {result[1] + 1}")
    else:
        print("  No sequence found for 'games' table")
    
    # Check existing game IDs
    cur.execute("SELECT gid FROM games ORDER BY gid")
    existing_ids = [row[0] for row in cur.fetchall()]
    print(f"  Existing game IDs: {existing_ids}")
    
    if existing_ids:
        max_id = max(existing_ids)
        print(f"  Maximum existing ID: {max_id}")
        
        # Reset the counter to the maximum existing ID
        cur.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'games'", (max_id,))
        conn.commit()
        
        print(f"\n✓ Auto-increment counter reset to {max_id}")
        print(f"  Next game will use ID: {max_id + 1}")
    else:
        # No games exist, reset to 0
        cur.execute("DELETE FROM sqlite_sequence WHERE name = 'games'")
        conn.commit()
        print("\n✓ No games exist. Counter will start at 1 for the next game.")
    
    conn.close()

if __name__ == "__main__":
    fix_autoincrement()
