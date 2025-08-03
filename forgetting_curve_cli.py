#!/usr/bin/env python3
"""
Spaced Repetition CLI for Memorization Using the Forgetting Curve

This script provides a command-line interface to help users memorize
information effectively using the spaced repetition technique.

The application is built with a class-based structure for clarity and
maintainability, and it delegates all database operations to a dedicated
DBManager class.
"""
import argparse
import datetime
import json
import math
import os
import platform
import random
import sys
import time
import sqlite3
from typing import List, Dict, Any, Callable, Tuple, Optional

from prompt_toolkit import prompt
from gtts import gTTS

# Import the DBManager class from the db_manager.py file.
# This file and db_manager.py must be in the same directory.
try:
    from db_manager import DBManager
except ImportError:
    print("❌ Critical Error: 'db_manager.py' not found.")
    print("Please make sure 'db_manager.py' is in the same directory as this script.")
    sys.exit(1)

# --- Utility Functions ---

def clear_screen():
    """Clears the terminal screen."""
    command = 'cls' if platform.system() == 'Windows' else 'clear'
    os.system(command)

def get_input_func():
    """Returns prompt_toolkit if in an interactive terminal, otherwise the built-in input."""
    return prompt if sys.stdin.isatty() else input

def speak(text: str, lang: str = 'en'):
    """Converts text to speech and plays it."""
    try:
        tts = gTTS(text=text, lang=lang)
        filename = "temp_answer.mp3"
        tts.save(filename)
        if platform.system() == 'Darwin': # macOS
            os.system(f"afplay {filename}")
        elif platform.system() == 'Windows':
            os.system(f"start {filename}")
        else: # Linux
            os.system(f"mpg123 {filename}")
        os.remove(filename)
    except Exception as e:
        print(f"❌ Could not play audio: {e}")

def highlight_differences(user_answer: str, correct_answer: str) -> str:
    """Returns a string visually highlighting the differences between two strings."""
    max_len = max(len(user_answer), len(correct_answer))
    user_padded = user_answer.ljust(max_len)
    correct_padded = correct_answer.ljust(max_len)
    
    highlight = ''.join('^' if u.lower() != c.lower() else ' ' for u, c in zip(user_padded, correct_padded))
    
    return f"Your answer:    {user_answer}\n" \
           f"                {highlight}\n" \
           f"Correct answer: {correct_answer}"

def display_progress(current: int, total: int, bar_length: int = 20) -> str:
    """Creates a text progress bar."""
    if total == 0:
        return "[No items]"
    progress = current / total
    filled = int(bar_length * progress)
    bar = '█' * filled + '-' * (bar_length - filled)
    return f"[{bar}] {current}/{total} items"

# --- Main Application Class ---

class SpacedRepetitionApp:
    """Class that encapsulates the main logic of the Spaced Repetition application."""
    
    def __init__(self):
        # Settings
        self.FORGETTING_SCHEDULE = [1, 2, 3, 7, 15, 30, 60, 90, 120]  # Review intervals (days)
        self.REQUIRED_STREAK = 3  # Number of consecutive correct answers to complete learning
        self.DAILY_TOTAL_LIMIT = 30 # Maximum number of learning + review items per day

        # Date and Time
        now = datetime.datetime.now()
        self.DATE_TODAY = str((now - datetime.timedelta(days=1)).date() if now.hour < 3 else now.date())

        # Database Manager
        self.db = DBManager("memory.db")
        self.elapsed_today = 0.0

    def run(self):
        """Controls the main execution flow of the application."""
        parser = self._create_arg_parser()
        args = parser.parse_args()

        with self.db: # Use a 'with' statement for automatic DB connection and disconnection
            self.db.initialize_database()

            if self._handle_early_exit_commands(args):
                return
            
            if args.filename:
                self.add_items_from_file(args.filename)
                get_input_func()("Items added from file. Press Enter to start the learning session...")

            # Preparation before starting the session
            self.prepare_daily_session()

            # Main application loop
            while True:
                learning_ids, review_ids = self.db.get_due_item_ids(self.DATE_TODAY)
                
                if not learning_ids and not review_ids:
                    break # Exit loop if no items are due

                if learning_ids:
                    print(f"\n📚 Starting learning round for {len(learning_ids)} items. (Required streak: {self.REQUIRED_STREAK})")
                    get_input_func()("Press Enter to start...")
                    self._run_learning_session(learning_ids)

                if review_ids:
                    print(f"\n✨ Starting review session for {len(review_ids)} items.")
                    get_input_func()("Press Enter to start...")
                    self._run_review_session(review_ids)


            # Save and display final results
            self.db.save_daily_stats(self.DATE_TODAY, self.elapsed_today)
            self._display_final_summary()

    def _create_arg_parser(self) -> argparse.ArgumentParser:
        """Creates and returns an ArgumentParser for parsing command-line arguments."""
        parser = argparse.ArgumentParser(
            description="Spaced Repetition CLI Tool.",
            epilog="""Available commands during a session:
  !edit_now      Edit the current question/answer
  !edit_before   Edit the previous question/answer
  !pause         Pause and save the session""",
            formatter_class=argparse.RawTextHelpFormatter
        )
        parser.add_argument("filename", nargs="?", help="Path to a text file containing Q&A pairs (e.g., task.txt).")
        parser.add_argument("-today", action="store_true", help="View today's learning/review schedule.")
        parser.add_argument("-tomorrow", action="store_true", help="View tomorrow's review schedule.")
        parser.add_argument("-delete-today", action="store_true", help="Delete all items added today.")
        return parser

    def _handle_early_exit_commands(self, args: argparse.Namespace) -> bool:
        """Handles commands that cause the program to exit immediately after execution."""
        if args.delete_today:
            count = self.db.delete_items_created_on(self.DATE_TODAY)
            print(f"🗑️ Deleted {count} items created today.")
            return True
        if args.today:
            self.show_schedule_for_today()
            return True
        if args.tomorrow:
            self.show_schedule_for_tomorrow()
            return True
        if not sys.stdin.isatty():
            print("💡 Not an interactive terminal. Displaying scheduled items and exiting.")
            self.show_schedule_for_today()
            return True
        return False

    def prepare_daily_session(self):
        """Performs necessary preparations before starting a day's session."""
        print("\n📖 Spaced Repetition CLI — Memorize Smarter with Spaced Repetition!")
        self.elapsed_today = self.db.get_daily_stats(self.DATE_TODAY)
        self.db.reset_daily_postponed_status(self.DATE_TODAY)

        # Set postponed flag for items exceeding the daily limit
        learning_ids, review_ids = self.db.get_due_item_ids(self.DATE_TODAY)
        all_due_ids = learning_ids + review_ids
        if len(all_due_ids) > self.DAILY_TOTAL_LIMIT:
            excess_ids = all_due_ids[self.DAILY_TOTAL_LIMIT:]
            self.db.set_postponed_status_for_excess_items(excess_ids)
            print(f"⚠️ Daily limit ({self.DAILY_TOTAL_LIMIT} items) exceeded. {len(excess_ids)} items will be postponed to tomorrow.")

    def _run_learning_session(self, learning_ids):
        """Conducts a session for items in the 'learning' state."""
        while True:
            if not learning_ids:
                break
            self._process_session(learning_ids, self._handle_learning_answer)
            # Check for remaining learning items for the next round
            learning_ids, _ = self.db.get_due_item_ids(self.DATE_TODAY)


    def _run_review_session(self, review_ids):
        """Conducts a session for items in the 'review' state."""
        if not review_ids:
            return
        self._process_session(review_ids, self._handle_review_answer)

    def _process_session(self, item_ids: List[int], answer_handler: Callable):
        """Core method that handles the common logic of learning/review sessions."""
        random.shuffle(item_ids)
        previous_key = None

        for i, item_id in enumerate(item_ids):
            item = self.db.get_item(item_id)
            if not item: continue

            clear_screen()
            print(display_progress(i + 1, len(item_ids)))
            print(f"\n[Q] {item['question']}")

            start_time = time.time()
            user_input = get_input_func()("> ").strip()
            elapsed = time.time() - start_time
            self.elapsed_today += elapsed
            
            # Command processing
            if user_input.lower() == "!pause":
                print("⏸️ Pausing the session. Your progress has been saved.")
                self.db.save_daily_stats(self.DATE_TODAY, self.elapsed_today)
                sys.exit()
            if user_input.lower() == "!edit_now":
                self.edit_item_interactively(item_id)
                item_ids.insert(i + 1, item_id) # Re-ask the current question
                continue
            if user_input.lower() == "!edit_before":
                if previous_key:
                    self.edit_item_interactively(previous_key)
                    item_ids.insert(i + 1, previous_key) # Re-ask the previous question
                else:
                    print("No previous item to edit.")
                item_ids.insert(i + 1, item_id) # Also re-ask the current question
                continue

            # Call the answer handling logic
            is_correct = user_input.lower() == item['answer'].strip().lower()
            answer_handler(item, is_correct, elapsed, user_input)

            previous_key = item_id
            get_input_func()("\nPress Enter to continue...")

    def _robust_json_loads(self, json_str: Optional[str], default_val: list = []) -> list:
        """Safely loads a JSON string, handling None, empty strings, and double-encoded strings."""
        if not json_str:
            return default_val
        try:
            data = json.loads(json_str)
            if isinstance(data, str):
                # Handle cases where data might be double-encoded (e.g., '"[]"')
                data = json.loads(data)
            return data if isinstance(data, list) else default_val
        except (json.JSONDecodeError, TypeError):
            return default_val

    def _handle_learning_answer(self, item: sqlite3.Row, is_correct: bool, elapsed: float, user_answer: str):
        """Handles correct/incorrect answers for learning items."""
        history = self._robust_json_loads(item['history'])
        response_times = self._robust_json_loads(item['response_times'])
        error_ratios = self._robust_json_loads(item['error_ratios'])
        
        response_times.append(elapsed)
        history.append('O' if is_correct else 'X')
        
        total_answers = len(history)
        total_errors = history.count('X')
        current_error_ratio = total_errors / total_answers if total_answers > 0 else 0
        error_ratios.append(current_error_ratio)
        
        updates = {
            "response_times": response_times,
            "history": history,
            "error_ratios": error_ratios,
            "last_processed_date": self.DATE_TODAY
        }
        
        if is_correct:
            new_streak = item['correct_streak'] + 1
            print(f"✅ Correct! (Streak {new_streak}/{self.REQUIRED_STREAK})")
            print(f"Answer: {item['answer']}")
            speak(item['answer'])
        
            updates['correct_streak'] = new_streak
            if new_streak >= self.REQUIRED_STREAK:
                updates['status'] = 'review'
                updates['stage'] = 1
                updates['correct_streak'] = 0
                next_review = datetime.date.fromisoformat(self.DATE_TODAY) + datetime.timedelta(days=self.FORGETTING_SCHEDULE[0])
                updates['next_review_date'] = str(next_review)
                print(f"🎉 Learning complete! This item will now be reviewed.")
        else:
            new_streak = 0
            print(f"❌ Incorrect.")
            print(highlight_differences(user_answer, item['answer']))
            speak(item['answer'])
            updates['correct_streak'] = new_streak
        
        self.db.update_item_after_session(item['item_id'], updates)
    
    def _handle_review_answer(self, item: sqlite3.Row, is_correct: bool, elapsed: float, user_answer: str):
        """Handles correct/incorrect answers for review items."""
        history = self._robust_json_loads(item['history'])
        response_times = self._robust_json_loads(item['response_times'])
        review_log = self._robust_json_loads(item['review_log'])
        error_ratios = self._robust_json_loads(item['error_ratios'])
        
        response_times.append(elapsed)
        history.append('O' if is_correct else 'X')
        
        total_answers = len(history)
        total_errors = history.count('X')
        current_error_ratio = total_errors / total_answers if total_answers > 0 else 0
        error_ratios.append(current_error_ratio)

        updates = {
            "response_times": response_times,
            "history": history,
            "error_ratios": error_ratios,
            "last_processed_date": self.DATE_TODAY
        }
        
        if is_correct:
            print(f"✅ Correct!")
            print(f"Answer: {item['answer']}")
            speak(item['answer'])

            new_stage = item['stage'] + 1
            if new_stage <= len(self.FORGETTING_SCHEDULE):
                interval = self.FORGETTING_SCHEDULE[new_stage - 1]
                next_review = datetime.date.fromisoformat(self.DATE_TODAY) + datetime.timedelta(days=interval)
                updates['stage'] = new_stage
                updates['next_review_date'] = str(next_review)
                print(f"📅 Next review in {interval} days.")
            else:
                updates['status'] = 'done'
                updates['next_review_date'] = None
                print("🎉 Perfectly memorized! All review cycles are complete.")
        else:
            print(f"❌ Incorrect.")
            print(highlight_differences(user_answer, item['answer']))
            speak(item['answer'])
            updates['status'] = 'learning'
            updates['stage'] = 0
            updates['correct_streak'] = 0
            updates['next_review_date'] = self.DATE_TODAY
            print("📉 This item will return to the 'learning' phase.")

        review_log.append({"date": self.DATE_TODAY, "is_correct": is_correct, "response_time": elapsed})
        updates['review_log'] = review_log
        self.db.update_item_after_session(item['item_id'], updates)

    def add_items_from_file(self, filename: str):
        """Reads Q&A pairs from a text file and adds them to the DB."""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
            if len(lines) % 2 != 0:
                print("❌ The file must contain pairs of 'question-answer'.")
                return
            
            items_to_add = [(lines[i], lines[i+1]) for i in range(0, len(lines), 2)]
            count = self.db.add_items(items_to_add, self.DATE_TODAY)
            print(f"✅ Added {count} items from file '{filename}'.")
        except FileNotFoundError:
            print(f"❌ File '{filename}' not found.")
        except Exception as e:
            print(f"❌ Error processing file: {e}")

    def edit_item_interactively(self, item_id: int):
        """Edits an item based on user input."""
        item = self.db.get_item(item_id)
        if not item:
            print(f"❌ Item ID {item_id} not found.")
            return

        print(f"\n✏️ Editing Item (ID: {item_id}):")
        print(f"Current Question: {item['question']}")
        new_q = get_input_func()("New Question (Enter to keep): ").strip()
        print(f"Current Answer: {item['answer']}")
        new_a = get_input_func()("New Answer (Enter to keep): ").strip()
        
        if new_q or new_a:
            self.db.edit_item(item_id, new_q or None, new_a or None)
            print("✅ Item updated successfully.")
        else:
            print("Edit canceled.")

    def show_schedule_for_today(self):
        learning_ids, review_ids = self.db.get_due_item_ids(self.DATE_TODAY)
        print("\n--- Today's Learning/Review Schedule ---")
        print(f"📚 New items to learn: {len(learning_ids)}")
        print(f"✨ Items to review: {len(review_ids)}")
        print(f"🗓️ A total of {len(learning_ids) + len(review_ids)} items are scheduled.")

    def show_schedule_for_tomorrow(self):
        tomorrow = str(datetime.date.fromisoformat(self.DATE_TODAY) + datetime.timedelta(days=1))
        review_count = self.db.get_review_count_for_date(tomorrow)
        print("\n--- Tomorrow's Review Schedule ---")
        print(f"✨ Items scheduled for review: {review_count}")
    
    def _display_final_summary(self):
        """Displays the final summary after the session ends."""
        minutes, seconds = divmod(int(self.elapsed_today), 60)
        print("\n🎉 Today's learning and review are complete!")
        print(f"⏱️ Total study time: {minutes} minutes {seconds} seconds")
        print(f"📅 Reference date: {self.DATE_TODAY}")


if __name__ == "__main__":
    app = SpacedRepetitionApp()
    app.run()