#!/usr/bin/env python3
"""
Spaced Repetition CLI for Memorization Using the Forgetting Curve

This script implements a command-line interface tool to help users memorize
information effectively by leveraging the forgetting curve concept. Users can
add new question-answer pairs, review items according to a spaced repetition
schedule, and track their progress over time.

Key features:
- Add new Q&A pairs either interactively or from a file.
- Test learning items with a required correct streak before promotion.
- Review memorized items with intervals adjusted based on performance and lateness.
- Save and load progress from a JSON file.
- Provide statistics on answer history when enabled.

The forgetting schedule is predefined, and the system adapts review intervals
based on response quality and timeliness.
"""
import sqlite3
import random
import datetime
import time
import json

from pathlib import Path
import math
import sys
import os
import platform
import matplotlib.pyplot as plt
from prompt_toolkit import prompt
from gtts import gTTS
import argparse

def clear_screen():
    """Clears the terminal screen."""
    command = 'cls' if platform.system() == 'Windows' else 'clear'
    os.system(command)

def get_input_func():
    """
    Returns prompt_toolkit.prompt if running in an interactive terminal,
    otherwise returns the built-in input function.
    """
    if sys.stdin.isatty():
        return prompt
    else:
        return input

def speak(text, lang='en'):
    """
    Converts text to speech and plays it.
    Requires gTTS and playsound to be installed.
    """
    try:
        tts = gTTS(text=text, lang=lang)
        filename = "temp_answer.mp3"
        tts.save(filename)
        os.system(f"afplay {filename}") # For macOS
        # For Windows: os.system(f"start {filename}")
        # For Linux: os.system(f"mpg123 {filename}") or os.system(f"aplay {filename}")
        os.remove(filename)
    except Exception as e:
        print(f"❌ Could not play audio: {e}")

def highlight_differences(user_answer, correct_answer):
    """
    Compares two strings and returns a formatted string highlighting differences.
    Differences are marked with '^' below the user's answer.
    """
    highlight = []
    display_user_answer = []
    display_correct_answer = []

    # Pad the shorter string with spaces to match the length of the longer string
    max_len = max(len(user_answer), len(correct_answer))
    padded_user_answer = user_answer.ljust(max_len)
    padded_correct_answer = correct_answer.ljust(max_len)

    for i in range(max_len):
        u_char = padded_user_answer[i]
        c_char = padded_correct_answer[i]

        display_user_answer.append(u_char)
        display_correct_answer.append(c_char)

        if u_char.lower() != c_char.lower():
            highlight.append('^')
        else:
            highlight.append(' ')

    user_label = "Your answer:"
    correct_label = "Correct answer:"
    max_label_len = max(len(user_label), len(correct_label))

    user_line = f"{user_label.ljust(max_label_len)} {user_answer}"
    highlight_line = f"{' ' * (max_label_len + 1)}{''.join(highlight)}"
    correct_line = f"{correct_label.ljust(max_label_len)} {correct_answer}"

    return f"{user_line}\n{highlight_line}\n{correct_line}"""

def display_progress(current, total, bar_length=20):
    """
    Displays a progress bar.
    """
    if total == 0:
        return "[No items]"
    
    progress = (current / total)
    filled_length = int(bar_length * progress)
    bar = '█' * filled_length + '-' * (bar_length - filled_length)
    return f"[{bar}] {current}/{total} items"

DB_FILE = Path("memory.db")
FORGETTING_SCHEDULE = [1, 2, 3, 7, 15, 30, 60, 90, 120]  # days
REQUIRED_STREAK = 3  # number of consecutive correct answers required
DAILY_TOTAL_LIMIT = 30  # maximum number of total items (learning + review) per day

# Calculate DATE_TODAY based on a 3 AM boundary
now = datetime.datetime.now()
if now.hour < 3:
    DATE_TODAY = str((now - datetime.timedelta(days=1)).date())
else:
    DATE_TODAY = str(now.date())
SHOW_HISTORY = False

def init_db():
    """Initialize the database and create tables if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Create items table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS items (
        item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        stage INTEGER DEFAULT 0,
        correct_streak INTEGER DEFAULT 0,
        next_review_date TEXT,
        last_processed_date TEXT,
        postponed INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT,
        status TEXT DEFAULT 'learning',
        history TEXT DEFAULT '[]'
    )
    """)
    # Create daily_stats table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_stats (
        date TEXT PRIMARY KEY,
        elapsed_today REAL DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

def add_new_items(filename=None):
    """
    Add new question-answer pairs to the database.

    If a filename is provided, load pairs from the file. Otherwise, prompt the
    user interactively.

    Args:
        filename (str, optional): Path to a file containing Q&A pairs.

    Returns:
        bool: True if items were added, False otherwise.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    items_added = False

    if filename:
        try:
            with open(filename, 'r') as f:
                lines = [line.strip() for line in f if line.strip()]
            if len(lines) % 2 != 0:
                print("❌ The input file must contain pairs of lines (question followed by answer).")
                return False
            
            for i in range(0, len(lines), 2):
                q = lines[i]
                a = lines[i+1]
                cursor.execute("""
                INSERT INTO items (question, answer, next_review_date, created_at, status)
                VALUES (?, ?, ?, ?, ?)
                """, (q, a, DATE_TODAY, DATE_TODAY, 'learning'))
                items_added = True

            if items_added:
                print(f"✅ Added {len(lines)//2} Q&A pairs from {filename}")

        except Exception as e:
            print(f"❌ Failed to load from {filename}: {e}")
            return False
    else:
        print("📚 Enter new Q&A pairs. Press Enter without typing a question to finish.")
        while True:
            q = get_input_func()("Question: ").strip()
            if q == "":
                break
            a = get_input_func()("Answer: ").strip()
            cursor.execute("""
            INSERT INTO items (question, answer, next_review_date, created_at, last_processed_date, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (q, a, DATE_TODAY, DATE_TODAY, DATE_TODAY, 'learning'))
            items_added = True

    if items_added:
        conn.commit()
    conn.close()
    return items_added

def edit_item(item_id):
    """
    Allows the user to edit the question and answer of a specific item in the database.

    Args:
        item_id (int): The ID of the item to edit.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    
    cursor.execute("SELECT * FROM items WHERE item_id = ?", (item_id,))
    item = cursor.fetchone()

    if not item:
        print(f"❌ Item with ID {item_id} not found.")
        conn.close()
        return

    print(f"\n✏️ Editing Item {item_id}:")
    print(f"Current Question: {item['question']}")
    new_q = get_input_func()("New Question (leave blank to keep current): ").strip()
    if new_q:
        cursor.execute("UPDATE items SET question = ? WHERE item_id = ?", (new_q, item_id))

    print(f"Current Answer: {item['answer']}")
    new_a = get_input_func()("New Answer (leave blank to keep current): ").strip()
    if new_a:
        cursor.execute("UPDATE items SET answer = ? WHERE item_id = ?", (new_a, item_id))

    conn.commit()
    conn.close()
    print(f"✅ Item {item_id} updated.")

def estimate_r(item, is_correct, response_time):
    """
    Estimate a rating 'r' value based on recent answer history and response time.
    """
    history = json.loads(item["history"])
    x_count = history[-5:].count('X')
    o_streak = 0
    for h in reversed(history):
        if h == 'O':
            o_streak += 1
        else:
            break

    # The response_times are not stored in the DB in this version for simplicity

    if not is_correct:
        return 0
    else:
        if o_streak >= 3:
            return 5
        elif o_streak == 2:
            return 4
        elif o_streak == 1:
            return 3
        else:
            return 2

def get_learning_items():
    """
    Retrieve all learning items from the database, ordered by creation date.

    Returns:
        list: List of item IDs to be tested.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT item_id FROM items 
        WHERE status = 'learning' AND correct_streak < ? 
        ORDER BY created_at
    """, (REQUIRED_STREAK,))
    learning_keys = [row[0] for row in cursor.fetchall()]
    conn.close()
    return learning_keys

def test_items(elapsed_today, learning_keys_for_session):
    """
    Conduct testing of learning items, prompting user for answers and updating item states in the database.

    Args:
        elapsed_today (float): The accumulated time spent today.
        learning_keys_for_session (list): List of item IDs to be tested in this session.

    Returns:
        float: The updated accumulated time spent today.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    previous_key = None

    random.shuffle(learning_keys_for_session)
    total_learning_items = len(learning_keys_for_session)
    for i, key in enumerate(learning_keys_for_session):
        clear_screen()
        cursor.execute("SELECT * FROM items WHERE item_id = ?", (key,))
        item = cursor.fetchone()
        if not item:
            continue

        print(display_progress(i + 1, total_learning_items))
        print("")
        print(f"[Q] {item['question']}")
        start_time = time.time()
        user_input = get_input_func()("> ")
        elapsed = time.time() - start_time
        elapsed_today += elapsed

        if user_input.strip().lower() == "!edit_now":
            edit_item(key)
            continue
        if user_input.strip().lower() == "!edit_before":
            if previous_key:
                edit_item(previous_key)
            else:
                print("No previous item to edit.")
            continue
        if user_input.strip().lower() == "!pause":
            print("Pausing session. Your progress has been saved.")
            cursor.execute("INSERT OR REPLACE INTO daily_stats (date, elapsed_today) VALUES (?, ?)", (DATE_TODAY, elapsed_today))
            conn.commit()
            conn.close()
            sys.exit()

        user_answer = user_input
        is_correct = user_answer.strip().lower() == item['answer'].strip().lower()
        history = json.loads(item['history'])
        r = estimate_r(item, is_correct, elapsed)
        cursor.execute("UPDATE items SET last_processed_date = ? WHERE item_id = ?", (DATE_TODAY, key))

        if is_correct:
            history.append('O')
            new_streak = item['correct_streak'] + 1
            print(f"✅ Correct! ({new_streak}/{REQUIRED_STREAK})")
            print(f"Correct answer: {item['answer']}")
            speak(item['answer'])
            if new_streak >= REQUIRED_STREAK:
                next_day = datetime.date.fromisoformat(DATE_TODAY) + datetime.timedelta(days=FORGETTING_SCHEDULE[0])
                cursor.execute("""UPDATE items SET status = 'review', stage = 1, next_review_date = ?, correct_streak = 0, history = ? WHERE item_id = ?""", 
                               (str(next_day), json.dumps(history), key))
            else:
                cursor.execute("UPDATE items SET correct_streak = ?, history = ? WHERE item_id = ?", (new_streak, json.dumps(history), key))
            get_input_func()("Press Enter to continue...")
        else:
            history.append('X')
            print("❌ Incorrect.")
            print(highlight_differences(user_answer, item['answer']))
            speak(item['answer'])
            get_input_func()("Press Enter to continue...")
            new_streak = max(0, item['correct_streak'] - 1)
            cursor.execute("""UPDATE items SET correct_streak = ?, stage = 0, status = 'learning', next_review_date = ?, history = ? WHERE item_id = ?""", 
                           (new_streak, DATE_TODAY, json.dumps(history), key))
        previous_key = key
        conn.commit()
    
    conn.close()
    return elapsed_today

def update_review_items(elapsed_today, review_keys_for_session):
    """
    Update review items scheduled for today, prompting user and adjusting next review dates in the database.

    Args:
        elapsed_today (float): The accumulated time spent today.
        review_keys_for_session (list): List of item IDs to be reviewed in this session.

    Returns:
        float: The updated accumulated time spent today.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    previous_key = None

    random.shuffle(review_keys_for_session)
    if review_keys_for_session:
        print("\n✨ Starting review session. Press Enter to begin...")
        get_input_func()("")
    
    total_review_items = len(review_keys_for_session)
    for i, key in enumerate(review_keys_for_session):
        clear_screen()
        cursor.execute("SELECT * FROM items WHERE item_id = ?", (key,))
        item = cursor.fetchone()
        if not item:
            continue

        print(display_progress(i + 1, total_review_items))
        print("")
        print(f"[Review] {item['question']}")
        start_time = time.time()
        user_input = get_input_func()("> ")
        elapsed = time.time() - start_time
        elapsed_today += elapsed

        if user_input.strip().lower() == "!edit_now":
            edit_item(key)
            continue
        if user_input.strip().lower() == "!edit_before":
            if previous_key:
                edit_item(previous_key)
            else:
                print("No previous item to edit.")
            continue
        if user_input.strip().lower() == "!pause":
            print("Pausing session. Your progress has been saved.")
            cursor.execute("INSERT OR REPLACE INTO daily_stats (date, elapsed_today) VALUES (?, ?)", (DATE_TODAY, elapsed_today))
            conn.commit()
            conn.close()
            sys.exit()

        user_answer = user_input
        is_correct = user_answer.strip().lower() == item['answer'].strip().lower()
        history = json.loads(item['history'])
        r = estimate_r(item, is_correct, elapsed)

        if is_correct:
            history.append('O')
            print("✅ Correct!")
            print(f"Correct answer: {item['answer']}")
            speak(item['answer'])
            new_stage = item['stage'] + 1
            if new_stage <= len(FORGETTING_SCHEDULE):
                base_days = FORGETTING_SCHEDULE[new_stage - 1]
                # ... (rest of the logic for calculating next review date)
                next_day = datetime.date.fromisoformat(DATE_TODAY) + datetime.timedelta(days=base_days)
                cursor.execute("UPDATE items SET stage = ?, next_review_date = ?, history = ? WHERE item_id = ?", 
                               (new_stage, str(next_day), json.dumps(history), key))
                print(f"📅 Next review scheduled in {base_days} days.")
            else:
                cursor.execute("UPDATE items SET next_review_date = 'done', history = ? WHERE item_id = ?", (json.dumps(history), key))
                print("🎉 Fully memorized!")
            get_input_func()("Press Enter to continue...")
        else:
            history.append('X')
            print("❌ Incorrect.")
            print(highlight_differences(user_answer, item['answer']))
            speak(item['answer'])
            get_input_func()("Press Enter to continue...")
            cursor.execute("""UPDATE items SET status = 'learning', correct_streak = 0, stage = 0, next_review_date = ?, history = ? WHERE item_id = ?""", 
                           (DATE_TODAY, json.dumps(history), key))
        previous_key = key
        conn.commit()

    conn.close()
    return elapsed_today




def show_statistics():
    """
    Display answer history sequences for all items from the database.
    """
    if not SHOW_HISTORY:
        return
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    print("\n📊 Answer History Sequences:")
    cursor.execute("SELECT item_id, question, history FROM items ORDER BY item_id")
    for item in cursor.fetchall():
        q_short = item['question'][:30] + ('...' if len(item['question']) > 30 else '')
        history = ''.join(json.loads(item['history']))
        print(f"Q{item['item_id']}: {q_short}\n  History: {history}")
    conn.close()


def main():
    """
    Main entry point for the CLI application.

    Initializes the database, handles command-line arguments, runs learning and 
    review sessions, and displays statistics.
    """
    init_db() # Ensure DB and tables exist
    parser = argparse.ArgumentParser(
        description="Spaced Repetition CLI for Memorization Using the Forgetting Curve.",
        epilog="""Interactive Commands (during learning/review sessions):
  !edit_now      Edit the current question or answer.
  !edit_before   Edit the previous question or answer.
  !pause         Pause the current session and save progress.
""",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "filename",
        nargs="?",
        help="Path to a file containing Q&A pairs to add (e.g., task.txt)."
    )
    parser.add_argument(
        "-today",
        action="store_true",
        help="Show today's scheduled review and learning items."
    )
    parser.add_argument(
        "-tomorrow",
        action="store_true",
        help="Show tomorrow's scheduled review and learning items."
    )
    parser.add_argument(
        "-delete-today",
        action="store_true",
        help="Delete all items created today."
    )
    args = parser.parse_args()

    print("\n📖 Spaced Repetition CLI — Memorize with the Forgetting Curve!")
    print(f"\n⚙️ Current Settings:")
    print(f"   Forgetting Schedule (days): {FORGETTING_SCHEDULE}")
    print(f"   Required Correct Streak: {REQUIRED_STREAK}")
    print(f"   DAILY_TOTAL_LIMIT: {DAILY_TOTAL_LIMIT}  # maximum number of total items (learning + review) per day")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Get elapsed_today from the database
    cursor.execute("SELECT elapsed_today FROM daily_stats WHERE date = ?", (DATE_TODAY,))
    row = cursor.fetchone()
    elapsed_today = row[0] if row else 0

    # Reset postponed status for items from previous days
    cursor.execute("UPDATE items SET postponed = 0 WHERE postponed = 1 AND last_processed_date != ?", (DATE_TODAY,))
    conn.commit()

    # Handle arguments that exit early
    if args.delete_today:
        cursor.execute("DELETE FROM items WHERE created_at = ?", (DATE_TODAY,))
        conn.commit()
        print(f"🗑️ Deleted {cursor.rowcount} items created today.")
        conn.close()
        sys.exit()

    items_added = add_new_items(args.filename)
    if items_added:
        get_input_func()("Press Enter to start the learning session...")


    # Get all due learning and review items from the database
    cursor.execute("SELECT item_id, created_at FROM items WHERE status = 'learning' ORDER BY created_at DESC")
    all_due_learning_keys = [row[0] for row in cursor.fetchall()]
    
    cursor.execute("SELECT item_id FROM items WHERE status = 'review' AND next_review_date <= ?", (DATE_TODAY,))
    all_due_review_keys = [row[0] for row in cursor.fetchall()]

    # Combine and apply DAILY_TOTAL_LIMIT
    combined_due_keys = all_due_learning_keys + all_due_review_keys
    
    # Set postponed flag for items exceeding the daily limit
    for i, key in enumerate(combined_due_keys):
        cursor.execute("UPDATE items SET postponed = ? WHERE item_id = ?", (1 if i >= DAILY_TOTAL_LIMIT else 0, key))
    conn.commit()

    # Filter items for today's session based on postponed status
    learning_keys_for_session = [k for k in all_due_learning_keys if not is_postponed(k, cursor)]
    review_keys_for_session = [k for k in all_due_review_keys if not is_postponed(k, cursor)]

    # Show how many review items are scheduled today
    print(f"\n🗓️  You have {len(review_keys_for_session)} item(s) scheduled for review today.")
    print(f"🆕 You have {len(learning_keys_for_session)} new learning item(s) for today.")

    if args.today:
        print(f"\n📌 Today's scheduled items:")
        print(f"🔁 Review items: {len(review_keys_for_session)}")
        print(f"🆕 Learning items: {len(learning_keys_for_session)}")
        conn.close()
        sys.exit()
    if args.tomorrow:
        tomorrow = str(datetime.date.fromisoformat(DATE_TODAY) + datetime.timedelta(days=1))
        cursor.execute("SELECT COUNT(*) FROM items WHERE status = 'review' AND next_review_date = ?", (tomorrow,))
        review_tomorrow_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM items WHERE status = 'learning' AND created_at = ?", (tomorrow,))
        learning_tomorrow_count = cursor.fetchone()[0]
        print(f"\n🔮 Tomorrow's scheduled items:")
        print(f"🔁 Review items: {review_tomorrow_count}")
        print(f"🆕 Learning items (pre-added for tomorrow): {learning_tomorrow_count}")

    while True:
        # Recalculate session items in each iteration
        cursor.execute("SELECT item_id FROM items WHERE status = 'learning' AND postponed = 0")
        learning_keys_for_session = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT item_id FROM items WHERE status = 'review' AND next_review_date <= ? AND postponed = 0", (DATE_TODAY,))
        review_keys_for_session = [row[0] for row in cursor.fetchall()]

        if not learning_keys_for_session and not review_keys_for_session:
            break # No more items to process

        if learning_keys_for_session:
            elapsed_today = test_items(elapsed_today, learning_keys_for_session)
        
        if review_keys_for_session:
            elapsed_today = update_review_items(elapsed_today, review_keys_for_session)

    show_statistics()

    # Save final elapsed time for the day
    cursor.execute("INSERT OR REPLACE INTO daily_stats (date, elapsed_today) VALUES (?, ?)", (DATE_TODAY, elapsed_today))
    conn.commit()
    conn.close()

    minutes = int(elapsed_today // 60)
    print(f"⏱️  Time spent today: {minutes} min")
    print(f"📅 Simulated date: {DATE_TODAY}")
    print("🎯 Today's memorization and review are complete!")

def is_postponed(item_id, cursor):
    cursor.execute("SELECT postponed FROM items WHERE item_id = ?", (item_id,))
    result = cursor.fetchone()
    return result[0] == 1 if result else True

if __name__ == "__main__":
    main()

