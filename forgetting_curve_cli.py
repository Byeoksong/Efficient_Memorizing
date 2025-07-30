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
import json
import random
import datetime
import time
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

DATA_FILE = Path("memory_data.json")


DATA_FILE = Path("memory_data.json")
FORGETTING_SCHEDULE = [1, 2, 3, 7, 15, 30, 60, 90, 120]  # days
REQUIRED_STREAK = 3  # number of consecutive correct answers required
DAILY_TOTAL_LIMIT = 30  # maximum number of total items (learning + review) per day

# ✅ Manual control for testing
# ✅ Manual control for testing
# DATE_TODAY = str(datetime.date.today())
# Calculate DATE_TODAY based on a 3 AM boundary
now = datetime.datetime.now()
if now.hour < 3:
    DATE_TODAY = str((now - datetime.timedelta(days=1)).date())
else:
    DATE_TODAY = str(now.date())
SHOW_HISTORY = False

# Load or initialize memory data
def load_data():
    """
    Load memory data from the JSON file if it exists.

    Returns:
        tuple: A tuple containing (data, daily_stats).
               data: The loaded memory data mapping item IDs to their data dictionaries.
               daily_stats: A dictionary storing daily elapsed times.
               Returns (empty dict, empty dict) if the file does not exist.
    """
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r") as f:
                full_data = json.load(f)

                items = {}
                daily_stats = {}

                # Check if it's the new format (contains 'items' and 'daily_stats' keys)
                if isinstance(full_data, dict) and "items" in full_data and "daily_stats" in full_data:
                    items = full_data.get("items", {})
                    daily_stats = full_data.get("daily_stats", {})
                # Check if it's the old format (items dictionary at top level)
                elif isinstance(full_data, dict):
                    items = full_data
                    daily_stats = {} # Old format didn't have daily_stats at top level
                else:
                    return {}, {}

                return items, daily_stats
        except json.JSONDecodeError:
            return {}, {} # Return empty if JSON is invalid
        except Exception:
            return {}, {}
    return {}, {}

def save_data(items, daily_stats):
    """
    Save the memory data and daily statistics to the JSON file with pretty formatting.

    Args:
        items (dict): The memory items data to save.
        daily_stats (dict): The daily statistics to save.
    """
    full_data = {"items": items, "daily_stats": daily_stats}
    with open(DATA_FILE, "w") as f:
        json.dump(full_data, f, indent=2, default=str, ensure_ascii=False)

# Add new Q&A entries
def add_new_items(items, daily_stats, filename=None):
    """
    Add new question-answer pairs to the memory data.

    If a filename is provided, load pairs from the file where each pair consists
    of two consecutive lines (question followed by answer). Otherwise, prompt the
    user interactively to enter Q&A pairs until an empty question is entered.

    Args:
        items (dict): The existing memory data to update.
        daily_stats (dict): The daily statistics to update.
        filename (str, optional): Path to a file containing Q&A pairs.
    
    Returns:
        bool: True if items were added from a file, False otherwise.
    """
    if filename:
        try:
            with open(filename, 'r') as f:
                lines = [line.strip() for line in f if line.strip()]
            if len(lines) % 2 != 0:
                print("❌ The input file must contain pairs of lines (question followed by answer).")
                return False
            items_added_from_file = False
            for i in range(0, len(lines), 2):
                q = lines[i]
                a = lines[i+1]
                # Find the next available item_id
                if items:
                    max_id = max(int(k) for k in items.keys() if k.isdigit())
                    item_id = str(max_id + 1)
                else:
                    item_id = "0"
                items[item_id] = {
                    "question": q,
                    "answer": a,
                    "correct_streak": 0,
                    "stage": 0,
                    "next_review": DATE_TODAY,
                    "status": "learning",
                    "history": [],
                    "postponed": False,
                    "created_at": DATE_TODAY,
                    "response_times": [],
                    "error_ratios": []
                }
                items_added_from_file = True
            if items_added_from_file:
                print(f"✅ Added {len(lines)//2} Q&A pairs from {filename}")
                save_data(items, daily_stats)
                return True
        except Exception as e:
            print(f"❌ Failed to load from {filename}: {e}")
        return False
    else:
        print("📚 Enter new Q&A pairs. Press Enter without typing a question to finish.")
        items_added_interactively = False
        while True:
            q = get_input_func()("Question: ").strip()
            if q == "":
                break
            a = get_input_func()("Answer: ").strip()
            # Find the next available item_id
            if items:
                max_id = max(int(k) for k in items.keys() if k.isdigit())
                item_id = str(max_id + 1)
            else:
                item_id = "0"
            items[item_id] = {
                "question": q,
                "answer": a,
                "correct_streak": 0,
                "stage": 0,
                "next_review": DATE_TODAY,
                "status": "learning",
                "history": [],
                "postponed": False,
                "created_at": DATE_TODAY,
                "response_times": [],
                "error_ratios": [],
                "last_processed_date": DATE_TODAY
            }
            items_added_interactively = True
        if items_added_interactively:
            save_data(items, daily_stats)
    return False

def edit_item(items, daily_stats, item_id):
    """
    Allows the user to edit the question and answer of a specific item.

    Args:
        items (dict): The existing memory data.
        daily_stats (dict): The daily statistics to update.
        item_id (str): The ID of the item to edit.
    """
    item = items[item_id]
    print(f"\n✏️ Editing Item {item_id}:")
    print(f"Current Question: {item['question']}")
    new_q = get_input_func()("New Question (leave blank to keep current): ").strip()
    if new_q:
        item['question'] = new_q

    print(f"Current Answer: {item['answer']}")
    new_a = get_input_func()("New Answer (leave blank to keep current): ").strip()
    if new_a:
        item['answer'] = new_a

    save_data(items, daily_stats)
    print(f"✅ Item {item_id} updated.")

def estimate_r(item, is_correct, response_time):
    """
    Estimate a rating 'r' value based on recent answer history and response time.

    The rating influences how the review interval is adjusted. Correct streaks
    increase the rating, while incorrect answers reset it.

    Args:
        item (dict): The memory item data.
        is_correct (bool): Whether the user's answer was correct.
        response_time (float): Time taken by the user to answer.

    Returns:
        int: The estimated rating value (0 to 5).
    """
    history = item["history"]
    x_count = history[-5:].count('X')
    o_streak = 0
    for h in reversed(history):
        if h == 'O':
            o_streak += 1
        else:
            break

    item.setdefault("response_times", []).append(response_time)

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

def get_learning_items(data):
    """
    Retrieve learning items to be tested today, enforcing daily limits and postponing excess.

    New items created today are prioritized, followed by older learning items up to the daily limit.
    Items beyond the limit are marked as postponed.

    Args:
        data (dict): The memory data.

    Returns:
        list: List of item IDs to be tested today.
    """
    today_new = [
        (k, v) for k, v in data.items()
        if v["status"] == "learning" and v["created_at"] == DATE_TODAY and v["correct_streak"] < REQUIRED_STREAK
    ]
    others = [
        (k, v) for k, v in data.items()
        if v["status"] == "learning" and v["created_at"] != DATE_TODAY and v["correct_streak"] < REQUIRED_STREAK
    ]
    others.sort(key=lambda x: x[1].get("created_at", DATE_TODAY))

    all_learning_items = today_new + others
    return [k for k, _ in all_learning_items]

def test_items(items, elapsed_today, daily_stats, learning_keys_for_session):
    """
    Conduct testing of learning items, prompting user for answers and updating item states.

    Items are shuffled and presented. Correct answers increment the correct streak.
    When the required streak is reached, items are promoted to review status with scheduling.
    Incorrect answers reduce streaks and reset stage/status as needed.

    Args:
        items (dict): The memory data.
        elapsed_today (float): The accumulated time spent today.
        daily_stats (dict): The daily statistics to update.
        learning_keys_for_session (list): List of item IDs to be tested in this session.

    Returns:
        float: The updated accumulated time spent today.
    """
    previous_key = None # Initialize previous_key
    while True:
        # Use the provided learning_keys_for_session instead of calling get_learning_items
        learning_keys = [k for k in learning_keys_for_session if items[k]["status"] == "learning" and not items[k].get("postponed", False)]
        if not learning_keys:
            print("\n🎉 All learning items completed for today (or none allowed today)!")
            break

        random.shuffle(learning_keys)
        total_learning_items = len(learning_keys)
        for i, key in enumerate(learning_keys):
            clear_screen()
            item = items[key]
            print(display_progress(i + 1, total_learning_items))
            print("")
            print(f"[Q] {item['question']}")
            start_time = time.time()
            user_input = get_input_func()("> ")
            elapsed = time.time() - start_time
            elapsed_today += elapsed

            if user_input.strip().lower() == "!edit_now":
                edit_item(items, daily_stats, key)
                continue
            if user_input.strip().lower() == "!edit_before":
                if previous_key:
                    edit_item(items, daily_stats, previous_key)
                else:
                    print("No previous item to edit.")
                continue
            if user_input.strip().lower() == "!pause":
                print("Pausing session. Your progress has been saved.")
                daily_stats[DATE_TODAY] = elapsed_today
                save_data(items, daily_stats)
                sys.exit()
            user_answer = user_input
            is_correct = user_answer.strip().lower() == item['answer'].strip().lower()
            r = estimate_r(item, is_correct, elapsed)
            item['last_processed_date'] = DATE_TODAY

            if is_correct:
                # Correct answer: increment streak and check if promotion criteria met
                item['correct_streak'] += 1
                item['history'].append('O')
                print(f"✅ Correct! ({item['correct_streak']}/{REQUIRED_STREAK})")
                print(f"Correct answer: {item['answer']}")
                speak(item['answer'])
                if item['correct_streak'] >= REQUIRED_STREAK:
                    # Promote to review stage
                    item['status'] = "review"
                    item['stage'] = 1
                    next_day = datetime.date.fromisoformat(DATE_TODAY) + datetime.timedelta(days=FORGETTING_SCHEDULE[0])
                    item['next_review'] = str(next_day)
                    item['correct_streak'] = 0
                get_input_func()("Press Enter to continue...")
            else:
                # Incorrect answer: reset streak, stage and keep in learning
                item['history'].append('X')
                print("❌ Incorrect.")
                print(highlight_differences(user_answer, item['answer']))
                speak(item['answer'])
                get_input_func()("Press Enter to continue...")
                item['correct_streak'] = max(0, item['correct_streak'] - 1)
                item['stage'] = 0
                item['status'] = "learning"
                item['next_review'] = DATE_TODAY
            previous_key = key
        save_data(items, daily_stats)
    return elapsed_today

def update_review_items(items, elapsed_today, daily_stats, review_keys_for_session, learning_keys_for_session):
    """
    Update review items scheduled for today, prompting user and adjusting next review dates.

    Items answered correctly advance to the next stage with intervals adjusted by performance
    rating and lateness. Incorrect answers demote items back to learning status.

    Args:
        items (dict): The memory data.
        elapsed_today (float): The accumulated time spent today.
        daily_stats (dict): The daily statistics to update.
        review_keys_for_session (list): List of item IDs to be reviewed in this session.
        learning_keys_for_session (list): List of item IDs to be tested in this session (passed for recursive call).

    Returns:
        float: The updated accumulated time spent today.
    """
    review_targets = [k for k in review_keys_for_session if items[k]["status"] == "review" and items[k]["next_review"] <= DATE_TODAY and not items[k].get("postponed", False)]
    random.shuffle(review_targets)
    previous_key = None
    if review_targets:
        print("\n✨ Starting review session. Press Enter to begin...")
        get_input_func()("")
    total_review_items = len(review_targets)
    for i, key in enumerate(review_targets):
        clear_screen()
        item = items[key]
        print(display_progress(i + 1, total_review_items))
        print("")
        print(f"[Review] {item['question']}")
        start_time = time.time()
        user_input = get_input_func()("> ")
        elapsed = time.time() - start_time
        elapsed_today += elapsed

        if user_input.strip().lower() == "!edit_now":
            edit_item(items, daily_stats, key)
            continue
        if user_input.strip().lower() == "!edit_before":
            if previous_key:
                edit_item(items, daily_stats, previous_key)
            else:
                print("No previous item to edit.")
            continue
        if user_input.strip().lower() == "!pause":
            print("Pausing session. Your progress has been saved.")
            daily_stats[DATE_TODAY] = elapsed_today
            save_data(items, daily_stats)
            sys.exit()
        user_answer = user_input
        is_correct = user_answer.strip().lower() == item['answer'].strip().lower()
        r = estimate_r(item, is_correct, elapsed)

        if is_correct:
            # Correct review: append success, advance stage, and schedule next review
            item['history'].append('O')
            print("✅ Correct!")
            print(f"Correct answer: {item['answer']}")
            speak(item['answer'])
            if item['stage'] < len(FORGETTING_SCHEDULE):
                item['stage'] += 1
                base_days = FORGETTING_SCHEDULE[item['stage'] - 1]
                scheduled_date = datetime.date.fromisoformat(item['next_review'])
                today = datetime.date.fromisoformat(DATE_TODAY)
                days_late = max(0, (today - scheduled_date).days)

                # Non-linear adjustment using exponential decay:
                # r = 5 → factor ≈ 1.0 (no reduction)
                # r = 3 → factor ≈ 0.55
                # r = 1 → factor ≈ 0.30
                r_factor = max(0.3, math.exp(-0.3 * (5 - r)))
                adjusted_by_r = base_days * r_factor

                # lateness adjustment: increase interval proportionally if late
                lateness_factor = days_late / base_days if base_days > 0 else 0
                final_interval = max(1, int(adjusted_by_r * (1 + lateness_factor)))

                # Append review log entry with performance data
                item.setdefault("review_log", []).append({
                    "date": DATE_TODAY,
                    "scheduled_interval": base_days,
                    "actual_interval": base_days + days_late,
                    "is_correct": is_correct,
                    "r": r,
                    "response_time": elapsed
                })

                next_day = today + datetime.timedelta(days=final_interval)
                item['next_review'] = str(next_day)
                print(f"📅 Next review scheduled in {final_interval} days.")
            else:
                # Maximum stage reached: mark as fully memorized
                item['next_review'] = "done"
                print("🎉 Fully memorized!")
            get_input_func()("Press Enter to continue...")
        else:
            # Incorrect review: demote to learning and reset progress
            item['history'].append('X')
            print("❌ Incorrect.")
            print(highlight_differences(user_answer, item['answer']))
            speak(item['answer'])
            get_input_func()("Press Enter to continue...")
            item['status'] = "learning"
            item['correct_streak'] = 0
            item['stage'] = 0
            item.setdefault("review_log", []).append({
                "date": DATE_TODAY,
                "scheduled_interval": item.get("stage", 1),
                "actual_interval": (datetime.date.fromisoformat(DATE_TODAY) - datetime.date.fromisoformat(item["next_review"])).days,
                "is_correct": False,
                "r": r,
                "response_time": elapsed
            })
            item['next_review'] = DATE_TODAY
        previous_key = key

    save_data(items, daily_stats)
    return elapsed_today




def show_statistics(items):
    """
    Display answer history sequences for all items if history display is enabled.

    Args:
        items (dict): The memory data.
    """
    if not SHOW_HISTORY:
        return
    print("\n📊 Answer History Sequences:")
    for key, item in items.items():
        q_short = item['question'][:30] + ('...' if len(item['question']) > 30 else '')
        history = ''.join(item['history'])
        print(f"Q{key}: {q_short}\n  History: {history}")


def main():
    """
    Main entry point for the CLI application.

    Loads data, handles command-line arguments for adding new items or showing today's summary,
    runs learning and review sessions, and displays statistics and completion messages.
    """
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

    import time
    print("\n📖 Spaced Repetition CLI — Memorize with the Forgetting Curve!")
    print(f"\n⚙️ Current Settings:")
    print(f"   Forgetting Schedule (days): {FORGETTING_SCHEDULE}")
    print(f"   Required Correct Streak: {REQUIRED_STREAK}")
    print(f"   DAILY_TOTAL_LIMIT: {DAILY_TOTAL_LIMIT}  # maximum number of total items (learning + review) per day")
    items, daily_stats = load_data()

    elapsed_today = daily_stats.get(DATE_TODAY, 0)

    # Reset postponed status for items from previous days
    postponed_status_changed = False
    for item_id, item in items.items():
        if item.get("postponed", False) and item.get("last_processed_date") != DATE_TODAY:
            item["postponed"] = False
            postponed_status_changed = True

    if postponed_status_changed:
        save_data(items, daily_stats)

    # Handle arguments that exit early
    if args.delete_today:
        original_len = len(items)
        items = {k: v for k, v in items.items() if v.get("created_at") != DATE_TODAY}
        print(f"🗑️ Deleted {original_len - len(items)} items created today.")
        save_data(items, daily_stats)
        sys.exit()

    items_added = add_new_items(items, daily_stats, args.filename)
    if items_added:
        get_input_func()("Press Enter to start the learning session...")

    # Get all due learning items (without internal limit)
    all_due_learning_keys = get_learning_items(items)
    # Get all due review items
    all_due_review_keys = [k for k, v in items.items() if v['status'] == 'review' and v['next_review'] <= DATE_TODAY]

    # Combine and sort items based on priority: new learning > old learning > review
    combined_due_items = []
    # Add new learning items (created today)
    for key in all_due_learning_keys:
        if items[key].get("created_at") == DATE_TODAY:
            combined_due_items.append((key, items[key]))
    # Add older learning items
    for key in all_due_learning_keys:
        if items[key].get("created_at") != DATE_TODAY:
            combined_due_items.append((key, items[key]))
    # Add review items
    for key in all_due_review_keys:
        combined_due_items.append((key, items[key]))

    # Apply DAILY_TOTAL_LIMIT
    for i, (key, item) in enumerate(combined_due_items):
        if i < DAILY_TOTAL_LIMIT:
            item["postponed"] = False
        else:
            item["postponed"] = True
    save_data(items, daily_stats) # Save postponed status

    # Filter items for today's session based on postponed status
    learning_keys_for_session = [k for k, v in items.items() if v['status'] == 'learning' and not v.get('postponed', False)]
    review_keys_for_session = [k for k, v in items.items() if v['status'] == 'review' and v['next_review'] <= DATE_TODAY and not v.get('postponed', False)]

    # Show how many review items are scheduled today
    print(f"\n🗓️  You have {len(review_keys_for_session)} item(s) scheduled for review today.")
    print(f"🆕 You have {len(learning_keys_for_session)} new learning item(s) for today.")


    if args.today:
        print(f"\n📌 Today's scheduled items:")
        print(f"🔁 Review items: {len(review_keys_for_session)}")
        print(f"🆕 Learning items: {len(learning_keys_for_session)}")
        sys.exit()
    if args.tomorrow:
        tomorrow = str(datetime.date.fromisoformat(DATE_TODAY) + datetime.timedelta(days=1))
        review_tomorrow = [v for v in items.values() if v['status'] == 'review' and v['next_review'] == tomorrow]
        learning_tomorrow = [k for k, v in items.items() if v['status'] == 'learning' and v['created_at'] == tomorrow]
        print(f"\n🔮 Tomorrow's scheduled items:")
        print(f"🔁 Review items: {len(review_tomorrow)}")
        print(f"🆕 Learning items (pre-added for tomorrow): {len(learning_tomorrow)}")
        # No sys.exit() here, as per user's request to continue flow after displaying tomorrow's items.

    

    while True:
        # Recalculate session items in each iteration to include demoted items
        learning_keys_for_session = [k for k, v in items.items() if v['status'] == 'learning' and not v.get('postponed', False)]
        review_keys_for_session = [k for k, v in items.items() if v['status'] == 'review' and v['next_review'] <= DATE_TODAY and not v.get('postponed', False)]

        if not learning_keys_for_session and not review_keys_for_session:
            break # No more items to process

        # Prioritize learning items if any
        if learning_keys_for_session:
            elapsed_today = test_items(items, elapsed_today, daily_stats, learning_keys_for_session)
        
        # Then process review items
        if review_keys_for_session:
            elapsed_today = update_review_items(items, elapsed_today, daily_stats, review_keys_for_session, learning_keys_for_session)

        # After processing, save data to ensure postponed status is persisted
        save_data(items, daily_stats)

    show_statistics(items)

    daily_stats[DATE_TODAY] = elapsed_today
    save_data(items, daily_stats)

    minutes = int(elapsed_today // 60)
    print(f"⏱️  Time spent today: {minutes} min")
    print(f"📅 Simulated date: {DATE_TODAY}")
    print("🎯 Today's memorization and review are complete!")

if __name__ == "__main__":
    main()

