import os
import time
import json
import re
import logging
import google.generativeai as genai

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# API Key
from google.colab import userdata
API_KEY = userdata.get('GOOGLE_API_KEY')
genai.configure(api_key=API_KEY)

# Set up paths
video_dir = "/content/videos"
processed_videos_log = "processed_videos.json"

# Load previously processed videos
if os.path.exists(processed_videos_log):
    with open(processed_videos_log, "r") as f:
        processed_videos = json.load(f)
else:
    processed_videos = {}

# List available video files
def list_video_files(directory):
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm']
    if not os.path.exists(directory):
        logging.error(f"Directory '{directory}' not found.")
        return []
    return [os.path.join(directory, f) for f in os.listdir(directory) if os.path.splitext(f)[1].lower() in video_extensions]

# Get already uploaded files from Gemini
def get_uploaded_files():
    try:
        return {file.display_name: file for file in genai.list_files()}
    except Exception as e:
        logging.error(f"Error retrieving uploaded files: {e}")
        return {}

# Upload new videos and wait for activation
def upload_video(file_path):
    logging.info(f"Uploading {file_path}...")
    video_file = genai.upload_file(path=file_path)
    logging.info(f"Uploaded: {video_file.uri}, waiting for activation...")

    # Wait for file to be in ACTIVE state
    max_wait_time = 120  # 2 minutes
    wait_interval = 5
    elapsed_time = 0

    while elapsed_time < max_wait_time:
        video_status = genai.get_file(video_file.name)  # Check file status
        if video_status.state == "ACTIVE":
            logging.info(f"File {file_path} is now ACTIVE.")
            return video_file
        time.sleep(wait_interval)
        elapsed_time += wait_interval
        logging.info(f"Waiting... {elapsed_time}s elapsed")

    logging.error(f"File {file_path} did not become ACTIVE within {max_wait_time}s.")
    return None

# Generate LLM request
def analyze_video(video_file, prompt):
    logging.info(f"Sending {video_file.display_name} for analysis...")
    model = genai.GenerativeModel(model_name="models/gemini-2.0-flash")
    response = model.generate_content([prompt, video_file], request_options={"timeout": 600})
    return response.text

# Extract JSON from response
def extract_json(response):
    match = re.search(r'\{.*\}', response, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("No valid JSON found")

def format_analysis(json_data):
    """Formats the JSON data into a human-readable string.

    Args:
        json_data (dict): The JSON data representing the game analysis.

    Returns:
        str: A formatted string for user readability.
    """

    output = f"Game: {json_data['game']}\n\n"
    output += "Key Focus Areas:\n"
    for area in json_data['key_focus_areas']:
        output += f"- {area}\n"

    output += "\nMistakes:\n"
    for mistake in json_data['mistakes']:
        output += f"  Timestamp: {mistake['timestamp']}\n"
        output += f"  Description: {mistake['description']}\n"
        output += f"  Why Incorrect: {mistake['why_incorrect']}\n"
        output += f"  Better Alternative: {mistake['better_alternative']}\n"
        output += f"  Expected Benefit: {mistake['expected_benefit']}\n"
        output += "\n"

    output += "Repeated Errors:\n"
    for error in json_data['repeated_errors']:
        output += f"  Pattern: {error['pattern']}\n"
        output += f"  Occurrences: {', '.join(error['occurrences'])}\n"
        output += f"  Fix: {error['fix']}\n"
        output += "\n"

    output += "Missed Opportunities:\n"
    for opportunity in json_data['missed_opportunities']:
        output += f"  Timestamp: {opportunity['timestamp']}\n"
        output += f"  Missed Action: {opportunity['missed_action']}\n"
        output += f"  Expected Outcome: {opportunity['expected_outcome']}\n"
        output += "\n"

    return output
# Dynamic prompt
def dynamic_game_prompt_template(game_name: str, focus_on: str = None) -> str:
    """Generates a dynamic game-specific prompt where the LLM determines key mistakes and better alternatives,
       with an optional focus area for more specific feedback."""

    focus_text = (
        f"\n### **Special Focus: {focus_on.capitalize()}**\n"
        f"- Pay particular attention to **{focus_on}** when analyzing the gameplay.\n"
        f"- Identify **mistakes, missed opportunities, and better alternatives** specifically related to {focus_on}.\n"
        f"- Ensure the breakdown prioritizes improvements in {focus_on} over other areas.\n"
        if focus_on else ""
    )

    return (
        f"You are an expert video game coach specializing in analyzing gameplay for {game_name}.\n"
        f"Your task is to analyze a gameplay video and provide **a comprehensive, mistake-focused breakdown** based on the game's mechanics, strategies, and execution.\n\n"

        f"### **Step 1: Identify Key Focus Areas for Analysis**\n"
        f"- Before analyzing the video, list at least **6-8 key factors** that influence success in {game_name}.\n"
        f"- These could include mechanics, strategy, decision-making, positioning, adaptability, execution, etc.\n"
        f"- Weigh their importance before selecting the **4-5 most critical areas** for identifying mistakes.\n\n"

        f"### **Step 2: Extract and List All Mistakes & Better Alternatives**\n"
        f"Provide an exhaustive breakdown of **all major mistakes** made by the player, along with better choices they could have made.\n"
        f"- Each mistake must be accompanied by a **timestamp** and a specific explanation of why it was incorrect.\n"
        f"- Provide **a clearly superior alternative action** with a rationale for why it would have been better.\n\n"
        
        + focus_text +

        f"### **Output Format:**\n"
        f"Return the analysis strictly in the following JSON format:\n"
        f"```json\n"
        f"{{\n"
        f"  \"game\": \"{game_name}\",\n"
        f"  \"key_focus_areas\": [\n"
        f"    \"Factor 1\",\n"
        f"    \"Factor 2\",\n"
        f"    \"Factor 3\",\n"
        f"    \"Factor 4\"\n"
        f"  ],\n"
        f"  \"mistakes\": [\n"
        f"    {{\n"
        f"      \"timestamp\": \"00:00:00\",\n"
        f"      \"description\": \"Brief mistake description.\",\n"
        f"      \"why_incorrect\": \"Explanation of why this mistake is bad.\",\n"
        f"      \"better_alternative\": \"What should have been done instead.\",\n"
        f"      \"expected_benefit\": \"Why the alternative is superior.\"\n"
        f"    }}\n"
        f"  ],\n"
        f"  \"repeated_errors\": [\n"
        f"    {{\n"
        f"      \"pattern\": \"Description of recurring mistake.\",\n"
        f"      \"occurrences\": [\"00:01:30\", \"00:04:15\"],\n"
        f"      \"fix\": \"Advice on how to correct this mistake.\"\n"
        f"    }}\n"
        f"  ],\n"
        f"  \"missed_opportunities\": [\n"
        f"    {{\n"
        f"      \"timestamp\": \"00:02:45\",\n"
        f"      \"missed_action\": \"What could have been done instead.\",\n"
        f"      \"expected_outcome\": \"Benefit of the missed opportunity.\"\n"
        f"    }}\n"
        f"  ]\n"
        f"}}\n"
        f"```\n\n"

        f"### **Important Instructions:**\n"
        f"- **Only return JSON output**—do not include any additional text.\n"
        f"- Focus exclusively on **mistakes, missed opportunities, and better alternatives.**\n"
        f"- Do **not** include strengths or positive feedback.\n"
        f"- Always include timestamps when referring to gameplay moments.\n"
        f"- Ensure all explanations are specific, structured, and **actionable**.\n"
        f"- Provide alternatives in a way that makes it clear **how the player should adjust their playstyle.**\n"
        f"- Do not include unnecessary conversational elements—only return the structured JSON output."
    )

# Main Processing
uploaded_files = get_uploaded_files()
new_videos = []

for video_path in list_video_files(video_dir):
    filename = os.path.basename(video_path)

    if filename in processed_videos:
        logging.info(f"Skipping processed video: {filename}")
        continue  # Already processed

    if filename in uploaded_files:
        logging.info(f"Video {filename} already uploaded, skipping upload.")
        video_file = uploaded_files[filename]
    else:
        video_file = upload_video(video_path)
        if not video_file:
            continue  # Skip failed uploads

    new_videos.append((filename, video_file))

# Process new videos
if not new_videos:
    logging.info("No new videos to analyze.")
else:
    logging.info(f"Processing {len(new_videos)} new videos.")

    for filename, video_file in new_videos:
        response_text = analyze_video(video_file, dynamic_game_prompt_template("EA FC 24"))
        json_data = extract_json(response_text)

        # Save formatted output
        formatted_analysis = format_analysis(json_data)
        logging.info(f"Analysis for {filename}:\n{formatted_analysis}")

        # Mark video as processed
        processed_videos[filename] = json_data
        with open(processed_videos_log, "w") as f:
            json.dump(processed_videos, f, indent=4)
