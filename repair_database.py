import sqlite3
import os
import shutil

# --- Configuration ---
DB_FILE = 'memory.db'
BACKUP_FILE = 'memory.db.bak'

def repair_database():
    """
    Recovers the database by reading data from an old SQLite DB with an incorrect schema
    and migrating it to a new DB with the correct schema, including the 'error_ratios' column.
    """
    if not os.path.exists(DB_FILE):
        print(f"File '{DB_FILE}' not found. No database to repair.")
        return

    print("Starting database repair process...")

    try:
        conn_old = sqlite3.connect(DB_FILE)
        conn_old.row_factory = sqlite3.Row
        cursor_old = conn_old.cursor()

        # FIX: Correctly execute the query first, then fetch the results.
        cursor_old.execute("SELECT * FROM items")
        items_data = cursor_old.fetchall()

        cursor_old.execute("SELECT * FROM daily_stats")
        stats_data = cursor_old.fetchall()
        
        conn_old.close()
        print(f"✅ Read {len(items_data)} learning items and {len(stats_data)} stats entries.")

    except sqlite3.Error as e:
        print(f"❌ An error occurred while reading the old database: {e}")
        return

    try:
        shutil.copyfile(DB_FILE, BACKUP_FILE)
        print(f"👍 Safely backed up the old database to '{BACKUP_FILE}'.")
        os.remove(DB_FILE)
    except Exception as e:
        print(f"❌ An error occurred during database backup: {e}")
        return

    try:
        conn_new = sqlite3.connect(DB_FILE)
        cursor_new = conn_new.cursor()

        # Create the 'items' table with the 'error_ratios' column included
        cursor_new.execute("""
        CREATE TABLE items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            stage INTEGER,
            correct_streak INTEGER,
            next_review_date TEXT,
            last_processed_date TEXT,
            postponed INTEGER,
            created_at TEXT,
            updated_at TEXT,
            status TEXT,
            history TEXT,
            response_times TEXT,
            error_ratios TEXT,
            review_log TEXT
        )
        """)

        # Create the 'daily_stats' table
        cursor_new.execute("""
        CREATE TABLE daily_stats (
            date TEXT PRIMARY KEY,
            elapsed_today REAL DEFAULT 0
        )
        """)

        if items_data:
            for item in items_data:
                # Exclude 'item_id' for autoincrement but include all other columns found
                keys_to_insert = [k for k in item.keys() if k != 'item_id']
                values_to_insert = [item[key] for key in keys_to_insert]
                placeholders = ', '.join(['?'] * len(keys_to_insert))
                
                query = f"INSERT INTO items ({', '.join(keys_to_insert)}) VALUES ({placeholders})"
                cursor_new.execute(query, values_to_insert)
            
            conn_new.commit()
            print(f"🚀 Successfully migrated {len(items_data)} learning items to the new database.")

        if stats_data:
            cursor_new.executemany("INSERT INTO daily_stats (date, elapsed_today) VALUES (?, ?)", stats_data)
            conn_new.commit()
            print(f"🚀 Successfully migrated {len(stats_data)} stats entries.")
            
        conn_new.close()

        print("\n🎉 All done! The database has been successfully repaired with 'error_ratios' data intact.")

    except sqlite3.Error as e:
        print(f"❌ An error occurred while writing data to the new database: {e}")
        shutil.copyfile(BACKUP_FILE, DB_FILE)
        print("The process failed and the original database has been restored.")

if __name__ == '__main__':
    repair_database()