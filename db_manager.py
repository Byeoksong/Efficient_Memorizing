import sqlite3
import json
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

class DBManager:
    """
    Manages all database interactions for the Spaced Repetition application.
    This class encapsulates the connection, queries, and modifications to the SQLite database.
    """
    def __init__(self, db_path: str = "memory.db"):
        """
        Initializes the DBManager instance.

        Args:
            db_path (str): The path to the database file.
        """
        self.db_path = Path(db_path)
        self.conn = None
        self.cursor = None

    def connect(self):
        """Connects to the database and creates a cursor."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # Allows accessing results like a dictionary
            self.cursor = self.conn.cursor()
            print("✅ Successfully connected to the database.")
        except sqlite3.Error as e:
            print(f"❌ Database connection error: {e}")
            raise

    def close(self):
        """Safely closes the database connection."""
        if self.conn:
            self.conn.commit()
            self.conn.close()
            self.conn = None
            self.cursor = None
            print("⚪️ Database connection closed.")

    def __enter__(self):
        """Calls the connect method for use with 'with' statements."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Calls the close method when exiting a 'with' statement."""
        self.close()

    def initialize_database(self):
        """
        Initializes the database by creating the 'items' and 'daily_stats' tables if they don't exist.
        """
        try:
            # items table
            self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                stage INTEGER DEFAULT 0,
                correct_streak INTEGER DEFAULT 0,
                next_review_date TEXT,
                last_processed_date TEXT,
                postponed INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                status TEXT DEFAULT 'learning' NOT NULL,
                history TEXT DEFAULT '[]' NOT NULL,
                response_times TEXT DEFAULT '[]' NOT NULL,
                error_ratios TEXT DEFAULT '[]' NOT NULL,
                review_log TEXT DEFAULT '[]' NOT NULL
            )
            """)
            # daily_stats table
            self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                elapsed_today REAL DEFAULT 0
            )
            """)
            self.conn.commit()
            print("👍 Database tables are ready.")
        except sqlite3.Error as e:
            print(f"❌ Table creation error: {e}")
            raise

    def add_items(self, items: List[Tuple[str, str]], today_date: str) -> int:
        """
        Adds a list of new question-answer pairs to the database.

        Args:
            items (List[Tuple[str, str]]): A list of (question, answer) tuples.
            today_date (str): The date the items were created (format YYYY-MM-DD).

        Returns:
            int: The number of items successfully added.
        """
        try:
            self.cursor.executemany("""
            INSERT INTO items (question, answer, next_review_date, created_at, last_processed_date, status, history, response_times, review_log)
            VALUES (?, ?, ?, ?, ?, 'learning', '[]', '[]', '[]')
            """, [(q, a, today_date, today_date, today_date) for q, a in items])
            self.conn.commit()
            return self.cursor.rowcount
        except sqlite3.Error as e:
            print(f"❌ Error adding items: {e}")
            return 0

    def edit_item(self, item_id: int, new_question: Optional[str] = None, new_answer: Optional[str] = None) -> bool:
        """
        Edits the question or answer of a specific item.

        Args:
            item_id (int): The ID of the item to edit.
            new_question (Optional[str]): The new question. If None, it's not modified.
            new_answer (Optional[str]): The new answer. If None, it's not modified.

        Returns:
            bool: True if the edit was successful, False otherwise.
        """
        try:
            if new_question:
                self.cursor.execute("UPDATE items SET question = ? WHERE item_id = ?", (new_question, item_id))
            if new_answer:
                self.cursor.execute("UPDATE items SET answer = ? WHERE item_id = ?", (new_answer, item_id))
            self.conn.commit()
            return self.cursor.rowcount > 0
        except sqlite3.Error as e:
            print(f"❌ Error editing item: {e}")
            return False

    def get_item(self, item_id: int) -> Optional[sqlite3.Row]:
        """Fetches information for a specific item."""
        self.cursor.execute("SELECT * FROM items WHERE item_id = ?", (item_id,))
        return self.cursor.fetchone()

    def get_due_item_ids(self, today_date: str) -> Tuple[List[int], List[int]]:
        """
        Gets the list of IDs for items to be learned and reviewed today.

        Args:
            today_date (str): Today's date (YYYY-MM-DD).

        Returns:
            Tuple[List[int], List[int]]: A tuple containing (list of learning item IDs, list of review item IDs).
        """
        self.cursor.execute("SELECT item_id FROM items WHERE status = 'learning' AND postponed = 0 ORDER BY created_at")
        learning_ids = [row['item_id'] for row in self.cursor.fetchall()]

        self.cursor.execute("SELECT item_id FROM items WHERE status = 'review' AND next_review_date <= ? AND postponed = 0", (today_date,))
        review_ids = [row['item_id'] for row in self.cursor.fetchall()]
        
        return learning_ids, review_ids

    def update_item_after_session(self, item_id: int, updates: Dict[str, Any]):
        """
        Updates the state of an item after a learning or review session.

        Args:
            item_id (int): The ID of the item to update.
            updates (Dict[str, Any]): A dictionary of fields and values to update.
        """
        # Convert JSON fields to strings
        for key in ['history', 'response_times', 'error_ratios', 'review_log']:
            if key in updates and isinstance(updates[key], list):
                updates[key] = json.dumps(updates[key])

        query = f"UPDATE items SET {', '.join([f'{k} = ?' for k in updates.keys()])} WHERE item_id = ?"
        params = list(updates.values()) + [item_id]
        
        try:
            self.cursor.execute(query, params)
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"❌ Error updating item ({item_id}): {e}")


    def get_all_items_for_stats(self) -> List[sqlite3.Row]:
        """Fetches information for all items for statistics display."""
        self.cursor.execute("SELECT item_id, question, history FROM items ORDER BY item_id")
        return self.cursor.fetchall()

    def get_daily_stats(self, today_date: str) -> float:
        """Gets the study time for a specific date."""
        self.cursor.execute("SELECT elapsed_today FROM daily_stats WHERE date = ?", (today_date,))
        row = self.cursor.fetchone()
        return row['elapsed_today'] if row else 0.0

    def save_daily_stats(self, today_date: str, elapsed_time: float):
        """Saves or updates the study time for a specific date."""
        self.cursor.execute("INSERT OR REPLACE INTO daily_stats (date, elapsed_today) VALUES (?, ?)", (today_date, elapsed_time))
        self.conn.commit()

    def delete_items_created_on(self, date: str) -> int:
        """Deletes all items created on a specific date."""
        self.cursor.execute("DELETE FROM items WHERE created_at = ?", (date,))
        self.conn.commit()
        return self.cursor.rowcount

    def get_review_count_for_date(self, date: str) -> int:
        """Gets the number of review items scheduled for a specific date."""
        self.cursor.execute("SELECT COUNT(*) FROM items WHERE status = 'review' AND next_review_date = ?", (date,))
        return self.cursor.fetchone()[0]

    def reset_daily_postponed_status(self, today_date: str):
        """Resets the 'postponed' status of items that were postponed previously."""
        self.cursor.execute("UPDATE items SET postponed = 0 WHERE postponed = 1 AND last_processed_date != ?", (today_date,))
        self.conn.commit()

    def set_postponed_status_for_excess_items(self, item_ids: List[int]):
        """Sets the 'postponed' flag for items exceeding the daily limit."""
        if not item_ids:
            return
        placeholders = ','.join('?' for _ in item_ids)
        self.cursor.execute(f"UPDATE items SET postponed = 1 WHERE item_id IN ({placeholders})", item_ids)
        self.conn.commit()