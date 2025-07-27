import json
import statistics

def analyze_memory_data(file_path="memory_data.json"):
    """
    Analyzes the memory data from a JSON file to provide insights into learning patterns,
    item difficulty, and the effectiveness of the spaced repetition system.

    Args:
        file_path (str): The path to the memory data JSON file.
    """
    try:
        # Attempt to open and load the JSON data from the specified file path.
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        # Handle the case where the file does not exist.
        print(f"Error: {file_path} not found.")
        return
    except json.JSONDecodeError:
        # Handle the case where the file content is not valid JSON.
        print(f"Error: Could not decode JSON from {file_path}.")
        return

    total_items = len(data)
    if total_items == 0:
        # If there are no items in the data, print a message and exit.
        print("No items to analyze.")
        return

    # --- Global Statistics Initialization ---
    # Lists to store lengths of all questions and answers for overall statistics.
    all_q_lengths = []
    all_a_lengths = []
    # List to store all recorded response times for overall statistics.
    all_response_times = []
    # Counters for total correct and incorrect answers across all items.
    total_correct_answers = 0
    total_incorrect_answers = 0

    # --- Stage-wise Statistics Initialization ---
    # Dictionary to store aggregated statistics for each learning stage.
    # Each stage will have:
    # - 'count': Number of items in this stage.
    # - 'total_q_len': Sum of question lengths for items in this stage.
    # - 'total_a_len': Sum of answer lengths for items in this stage.
    # - 'total_response_time': Sum of response times for items in this stage.
    # - 'correct_count': Total correct answers for items in this stage.
    # - 'total_attempts': Total attempts (correct + incorrect) for items in this stage.
    # - 'response_times_list': List of all response times for items in this stage.
    stage_stats = {}

    # --- Data Aggregation Loop ---
    # Iterate through each item in the loaded memory data to collect statistics.
    for item_id, item in data.items():
        # Get question and answer lengths, defaulting to empty string length if not present.
        q_len = len(item.get("question", ""))
        a_len = len(item.get("answer", ""))
        all_q_lengths.append(q_len)
        all_a_lengths.append(a_len)

        # Determine the current learning stage of the item, defaulting to 0 if not present.
        current_stage = item.get("stage", 0)
        # Initialize stage_stats for this stage if it doesn't exist yet.
        if current_stage not in stage_stats:
            stage_stats[current_stage] = {
                "count": 0,
                "total_q_len": 0,
                "total_a_len": 0,
                "total_response_time": 0,
                "correct_count": 0,
                "total_attempts": 0,
                "response_times_list": []
            }
        # Update counts and total lengths for the current stage.
        stage_stats[current_stage]["count"] += 1
        stage_stats[current_stage]["total_q_len"] += q_len
        stage_stats[current_stage]["total_a_len"] += a_len

        # Aggregate response times if available.
        if "response_times" in item and item["response_times"]:
            for rt in item["response_times"]:
                all_response_times.append(rt)
                stage_stats[current_stage]["response_times_list"].append(rt)
            stage_stats[current_stage]["total_response_time"] += sum(item["response_times"])

        # Aggregate history (correct/incorrect answers) if available.
        if "history" in item:
            correct_in_history = item["history"].count('O')
            incorrect_in_history = item["history"].count('X')
            total_correct_answers += correct_in_history
            total_incorrect_answers += incorrect_in_history
            stage_stats[current_stage]["correct_count"] += correct_in_history
            stage_stats[current_stage]["total_attempts"] += (correct_in_history + incorrect_in_history)

            # Note: Separating correct/incorrect response times would require a more
            # detailed mapping between 'history' entries and 'response_times' entries,
            # which is not directly available in the current data structure.
            # For this script, overall response times are used.

    # --- Print Global Statistics Summary ---
    print("--- Memory Data Analysis Summary ---")
    print(f"Total Items: {total_items}")
    print(f"Total Correct Answers Recorded: {total_correct_answers}")
    print(f"Total Incorrect Answers Recorded: {total_incorrect_answers}")
    # Calculate and print overall accuracy if there are any attempts.
    if (total_correct_answers + total_incorrect_answers) > 0:
        overall_accuracy = (total_correct_answers / (total_correct_answers + total_incorrect_answers)) * 100
        print(f"Overall Accuracy: {overall_accuracy:.2f}%")

    # --- Print Question/Answer Length Statistics ---
    print("\n--- Question/Answer Length Statistics ---")
    if all_q_lengths:
        # Calculate and print average question and answer lengths.
        print(f"Avg Question Length: {statistics.mean(all_q_lengths):.2f} chars")
        print(f"Avg Answer Length: {statistics.mean(all_a_lengths):.2f} chars")

    # --- Print Response Time Statistics ---
    print("\n--- Response Time Statistics ---")
    if all_response_times:
        # Calculate and print various statistics for all response times.
        print(f"Overall Avg Response Time: {statistics.mean(all_response_times):.2f} seconds")
        print(f"Min Response Time: {min(all_response_times):.2f} seconds")
        print(f"Max Response Time: {max(all_response_times):.2f} seconds")
        print(f"Median Response Time: {statistics.median(all_response_times):.2f} seconds")

    # --- Print Analysis by Learning Stage ---
    print("\n--- Analysis by Learning Stage ---")
    # Sort stages for consistent output order.
    sorted_stages = sorted(stage_stats.keys())
    for stage in sorted_stages:
        stats = stage_stats[stage]
        # Calculate average question/answer length for the current stage.
        avg_q_len = stats["total_q_len"] / stats["count"] if stats["count"] > 0 else 0
        avg_a_len = stats["total_a_len"] / stats["count"] if stats["count"] > 0 else 0
        # Calculate average response time for the current stage.
        avg_response_time = statistics.mean(stats["response_times_list"]) if stats["response_times_list"] else 0
        # Calculate accuracy for the current stage.
        accuracy = (stats["correct_count"] / stats["total_attempts"]) * 100 if stats["total_attempts"] > 0 else 0

        # Print statistics for the current stage.
        print(f"\nStage {stage}:")
        print(f"  Number of Items: {stats['count']}")
        print(f"  Avg Q Length: {avg_q_len:.2f} chars")
        print(f"  Avg A Length: {avg_a_len:.2f} chars")
        print(f"  Avg Response Time: {avg_response_time:.2f} seconds")
        print(f"  Accuracy: {accuracy:.2f}%")

    # --- Insights on Correct Streaks and Memorization (Conceptual) ---
    # This section provides conceptual insights that would require more complex
    # analysis (e.g., tracking individual item's progression through stages)
    # than what this script currently performs.
    print("\n--- Insights on Correct Streaks and Memorization ---")
    print("The system uses 'REQUIRED_STREAK = 3' to promote items from learning to review.")
    print("To analyze its effectiveness, we would need to track items that achieved this streak")
    print("and then observe their performance (accuracy, response times) in subsequent review stages.")
    print("This requires a more complex script to trace individual item's journey through stages.")
    print("However, the 'Accuracy' by Stage above gives a general idea: higher stages should have higher accuracy.")

# Entry point for the script execution.
if __name__ == "__main__":
    analyze_memory_data()
