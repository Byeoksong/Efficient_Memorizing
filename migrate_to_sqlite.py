
import json
import sqlite3
import os

# Configuration
JSON_FILE = 'memory_data.json'
DB_FILE = 'memory.db'

def migrate():
    """
    Migrates data from memory_data.json to memory.db (SQLite).
    """
    if not os.path.exists(JSON_FILE):
        print(f"Error: {JSON_FILE} not found. Nothing to migrate.")
        return

    if os.path.exists(DB_FILE):
        print(f"Warning: {DB_FILE} already exists. Skipping migration to avoid overwriting.")
        return

    # Connect to SQLite database
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Create tables
    # Items table with flexible columns by storing data as JSON
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS items (
        item_id TEXT PRIMARY KEY,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        stage INTEGER DEFAULT 0,
        correct_streak INTEGER DEFAULT 0,
        next_review_date TEXT,
        last_processed_date TEXT,
        postponed INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT,
        status TEXT,
        history TEXT
    )
    """)

    # Daily stats table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_stats (
        date TEXT PRIMARY KEY,
        elapsed_today REAL DEFAULT 0
    )
    """)

    # Load data from JSON file
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        print(f"Could not read or decode {JSON_FILE}. Starting with an empty database structure.")
        data = {"items": {}, "daily_stats": {}}


    # Insert items
    if "items" in data and isinstance(data["items"], dict):
        for item_id, item_data in data["items"].items():
            # Ensure all keys exist to prevent KeyError
            item_data.setdefault('stage', 0)
            item_data.setdefault('correct_streak', 0)
            item_data.setdefault('next_review_date', None)
            item_data.setdefault('last_processed_date', None)
            item_data.setdefault('postponed', 0)
            item_data.setdefault('created_at', item_data.get('created_at'))
            item_data.setdefault('updated_at', item_data.get('updated_at'))
            item_data.setdefault('status', 'learning')
            item_data.setdefault('history', '[]') # Store history as a JSON string

            cursor.execute("""
            INSERT INTO items (item_id, question, answer, stage, correct_streak, next_review_date, last_processed_date, postponed, created_at, updated_at, status, history)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_id,
                item_data.get('question'),
                item_data.get('answer'),
                item_data.get('stage'),
                item_data.get('correct_streak'),
                item_data.get('next_review_date'),
                item_data.get('last_processed_date'),
                1 if item_data.get('postponed') else 0,
                item_data.get('created_at'),
                item_data.get('updated_at'),
                item_data.get('status'),
                json.dumps(item_data.get('history', [])) # Serialize list to string
            ))
        print(f"Successfully migrated {len(data['items'])} items.")

    # Insert daily stats
    if "daily_stats" in data and isinstance(data["daily_stats"], dict):
        for date, elapsed_today in data["daily_stats"].items():
            # The value is directly the elapsed time, not a dict
            if not isinstance(elapsed_today, (int, float)):
                # Handle cases where the structure might be {"elapsed_today": ...}
                if isinstance(elapsed_today, dict) and 'elapsed_today' in elapsed_today:
                    elapsed_today = elapsed_today.get('elapsed_today', 0)
                else:
                    elapsed_today = 0

            cursor.execute("""
            INSERT INTO daily_stats (date, elapsed_today)
            VALUES (?, ?)
            """, (
                date,
                elapsed_today
            ))
        print(f"Successfully migrated {len(data['daily_stats'])} daily_stats entries.")

    # Commit changes and close connection
    conn.commit()
    conn.close()
    print("Migration complete. Database is ready.")

if __name__ == '__main__':
    migrate()
