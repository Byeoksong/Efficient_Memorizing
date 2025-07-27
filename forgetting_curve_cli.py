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

    return f"{user_line}\n{highlight_line}\n{correct_line}"

DATA_FILE = Path("memory_data.json")
FORGETTING_SCHEDULE = [1, 2, 3, 7, 15, 30, 60, 90, 120]  # days
REQUIRED_STREAK = 3  # number of consecutive correct answers required
DAILY_LEARNING_LIMIT = 30  # maximum number of repeated (non-new) items per day

# ✅ Manual control for testing
DATE_TODAY = str(datetime.date.today())
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
        with open(DATA_FILE, "r") as f:
            full_data = json.load(f)
            return full_data.get("items", {}), full_data.get("daily_stats", {})
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
    """
    if filename:
        try:
            with open(filename, 'r') as f:
                lines = [line.strip() for line in f if line.strip()]
            if len(lines) % 2 != 0:
                print("❌ The input file must contain pairs of lines (question followed by answer).")
                return
            for i in range(0, len(lines), 2):
                q = lines[i]
                a = lines[i+1]
                item_id = str(len(items))
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
            print(f"✅ Added {len(lines)//2} Q&A pairs from {filename}")
        except Exception as e:
            print(f"❌ Failed to load from {filename}: {e}")
    else:
        print("📚 Enter new Q&A pairs. Press Enter without typing a question to finish.")
        while True:
            q = get_input_func()("Question: ").strip()
            if q == "":
                break
            a = get_input_func()("Answer: ").strip()
            item_id = str(len(items))
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
    save_data(items, daily_stats)

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

    allowed_others = others[:DAILY_LEARNING_LIMIT]
    postponed = others[DAILY_LEARNING_LIMIT:]

    # Mark postponed items to avoid testing today
    for key, item in postponed:
        item["postponed"] = True
    for key, item in allowed_others + today_new:
        item["postponed"] = False

    return [k for k, _ in today_new + allowed_others]

def test_items(items, elapsed_today, daily_stats):
    """
    Conduct testing of learning items, prompting user for answers and updating item states.

    Items are shuffled and presented. Correct answers increment the correct streak.
    When the required streak is reached, items are promoted to review status with scheduling.
    Incorrect answers reduce streaks and reset stage/status as needed.

    Args:
        items (dict): The memory data.
        elapsed_today (float): The accumulated time spent today.
        daily_stats (dict): The daily statistics to update.

    Returns:
        float: The updated accumulated time spent today.
    """
    while True:
        learning_keys = get_learning_items(items)
        if not learning_keys:
            print("\n🎉 All learning items completed for today (or none allowed today)!")
            break

        random.shuffle(learning_keys)
        previous_key = None
        for key in learning_keys:
            clear_screen()
            item = items[key]
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
                print(f"Correct answer: {item['answer']}")
                speak(item['answer'])
                get_input_func()("Press Enter to continue...")
                item['correct_streak'] = max(0, item['correct_streak'] - 1)
                item['stage'] = 0
                item['status'] = "learning"
                item['next_review'] = DATE_TODAY
            previous_key = key
        save_data(items, daily_stats)
    return elapsed_today

def update_review_items(items, elapsed_today, daily_stats):
    """
    Update review items scheduled for today, prompting user and adjusting next review dates.

    Items answered correctly advance to the next stage with intervals adjusted by performance
    rating and lateness. Incorrect answers demote items back to learning status.

    Args:
        items (dict): The memory data.
        elapsed_today (float): The accumulated time spent today.
        daily_stats (dict): The daily statistics to update.

    Returns:
        float: The updated accumulated time spent today.
    """
    review_targets = [k for k, v in items.items() if v['status'] == "review" and v['next_review'] <= DATE_TODAY]
    random.shuffle(review_targets)
    previous_key = None
    if review_targets:
        print("\n✨ Starting review session. Press Enter to begin...")
        get_input_func()("")
    for key in review_targets:
        clear_screen()
        item = items[key]
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
            print(f"Correct answer: {item['answer']}")
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
    # After updating reviews, test any learning items remaining
    elapsed_today = test_items(items, elapsed_today, daily_stats)
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
    import time
    print("\n📖 Spaced Repetition CLI — Memorize with the Forgetting Curve!")
    print(f"\n⚙️ Current Settings:")
    print(f"   Forgetting Schedule (days): {FORGETTING_SCHEDULE}")
    print(f"   Required Correct Streak: {REQUIRED_STREAK}")
    print(f"   Daily Learning Limit: {DAILY_LEARNING_LIMIT}")
    items, daily_stats = load_data()
    
    elapsed_today = daily_stats.get(DATE_TODAY, 0)

    # Reset postponed status for items from previous days
    for item_id, item in items.items():
        if item.get("postponed", False) and item.get("last_processed_date") != DATE_TODAY:
            item["postponed"] = False
    save_data(items, daily_stats)
    # Show how many review items are scheduled today
    today_review_count = sum(1 for v in items.values() if v['status'] == 'review' and v['next_review'] <= DATE_TODAY)
    print(f"\n🗓️  You have {today_review_count} item(s) scheduled for review today.")

    # Handle -delete-today argument to remove items created today
    if len(sys.argv) > 1 and sys.argv[1] == "-delete-today":
        original_len = len(items)
        items = {k: v for k, v in items.items() if v.get("created_at") != DATE_TODAY}
        print(f"🗑️ Deleted {original_len - len(items)} items created today.")
        save_data(items, daily_stats)
        sys.exit()
    # Handle -today argument for quick summary and exit
    if len(sys.argv) > 1 and sys.argv[1] == "-today":
        review_today = [v for v in items.values() if v['status'] == 'review' and v['next_review'] <= DATE_TODAY]
        learning_today = get_learning_items(items)
        print(f"\n📌 Today's scheduled items:")
        print(f"🔁 Review items: {len(review_today)}")
        print(f"🆕 Learning items: {len(learning_today)}")
        sys.exit()
    # Handle -tomorrow argument for quick tomorrow's summary and exit
    if len(sys.argv) > 1 and sys.argv[1] == "-tomorrow":
        tomorrow = str(datetime.date.fromisoformat(DATE_TODAY) + datetime.timedelta(days=1))
        review_tomorrow = [v for v in items.values() if v['status'] == 'review' and v['next_review'] == tomorrow]
        learning_tomorrow = [k for k, v in items.items() if v['status'] == 'learning' and v['created_at'] == tomorrow]
        print(f"\n🔮 Tomorrow's scheduled items:")
        print(f"🔁 Review items: {len(review_tomorrow)}")
        print(f"🆕 Learning items (pre-added for tomorrow): {len(learning_tomorrow)}")
        sys.exit()
    filename = sys.argv[1] if len(sys.argv) > 1 else None
    add_new_items(items, daily_stats, filename)
    elapsed_today = test_items(items, elapsed_today, daily_stats)
    elapsed_today = update_review_items(items, elapsed_today, daily_stats)
    show_statistics(items)
    
    daily_stats[DATE_TODAY] = elapsed_today
    save_data(items, daily_stats)

    minutes = int(elapsed_today // 60)
    print(f"⏱️  Time spent today: {minutes} min")
    print(f"\n📅 Simulated date: {DATE_TODAY}")
    print("🎯 Today's memorization and review are complete!")

if __name__ == "__main__":
    main()
