# config.py
import logging
import os
from dataclasses import dataclass

@dataclass
class Config:
    VIDEO_DIR: str = "/content/videos"
    PROCESSED_VIDEOS_LOG: str = "processed_videos.json"
    MAX_WAIT_TIME: int = 120  # seconds
    WAIT_INTERVAL: int = 5    # seconds
    VIDEO_EXTENSIONS: list = None

    def __post_init__(self):
        self.VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm']
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

# video_manager.py
import os
import json
import logging
from typing import Dict, List, Tuple
import google.generativeai as genai
import time

class VideoManager:
    def __init__(self, config: Config):
        self.config = config
        self.processed_videos = self._load_processed_videos()
        
    def _load_processed_videos(self) -> Dict:
        if os.path.exists(self.config.PROCESSED_VIDEOS_LOG):
            with open(self.config.PROCESSED_VIDEOS_LOG, "r") as f:
                return json.load(f)
        return {}

    def list_video_files(self) -> List[str]:
        if not os.path.exists(self.config.VIDEO_DIR):
            logging.error(f"Directory '{self.config.VIDEO_DIR}' not found.")
            return []
        return [
            os.path.join(self.config.VIDEO_DIR, f) 
            for f in os.listdir(self.config.VIDEO_DIR) 
            if os.path.splitext(f)[1].lower() in self.config.VIDEO_EXTENSIONS
        ]

    def get_uploaded_files(self) -> Dict:
        try:
            return {file.display_name: file for file in genai.list_files()}
        except Exception as e:
            logging.error(f"Error retrieving uploaded files: {e}")
            return {}

    def upload_video(self, file_path: str):
        logging.info(f"Uploading {file_path}...")
        video_file = genai.upload_file(path=file_path)
        logging.info(f"Uploaded: {video_file.uri}, waiting for activation...")

        elapsed_time = 0
        while elapsed_time < self.config.MAX_WAIT_TIME:
            video_status = genai.get_file(video_file.name)
            if video_status.state == "ACTIVE":
                logging.info(f"File {file_path} is now ACTIVE.")
                return video_file
            time.sleep(self.config.WAIT_INTERVAL)
            elapsed_time += self.config.WAIT_INTERVAL
            logging.info(f"Waiting... {elapsed_time}s elapsed")

        logging.error(f"File {file_path} did not become ACTIVE within {self.config.MAX_WAIT_TIME}s.")
        return None

    def save_analysis(self, filename: str, analysis_data: Dict):
        self.processed_videos[filename] = analysis_data
        with open(self.config.PROCESSED_VIDEOS_LOG, "w") as f:
            json.dump(self.processed_videos, f, indent=4)

# analysis_service.py
import re
import json
from typing import Dict
import google.generativeai as genai

class AnalysisService:
    def __init__(self):
        self.model = genai.GenerativeModel(model_name="models/gemini-2.0-flash")

    def analyze_video(self, video_file, prompt: str) -> str:
        logging.info(f"Sending {video_file.display_name} for analysis...")
        response = self.model.generate_content(
            [prompt, video_file], 
            request_options={"timeout": 600}
        )
        return response.text

    @staticmethod
    def extract_json(response: str) -> Dict:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("No valid JSON found")

    @staticmethod
    def format_analysis(json_data: Dict) -> str:
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
            output += f"  Expected Benefit: {mistake['expected_benefit']}\n\n"

        output += "Repeated Errors:\n"
        for error in json_data['repeated_errors']:
            output += f"  Pattern: {error['pattern']}\n"
            output += f"  Occurrences: {', '.join(error['occurrences'])}\n"
            output += f"  Fix: {error['fix']}\n\n"

        output += "Missed Opportunities:\n"
        for opportunity in json_data['missed_opportunities']:
            output += f"  Timestamp: {opportunity['timestamp']}\n"
            output += f"  Missed Action: {opportunity['missed_action']}\n"
            output += f"  Expected Outcome: {opportunity['expected_outcome']}\n\n"

        return output
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

# prompt_generator.py
class PromptGenerator:
    @staticmethod
    def create_game_prompt(game_name: str, focus_on: str = None) -> str:
        return dynamic_game_prompt_template(game_name, focus_on)

# main.py
def initialize_services(api_key: str):
    genai.configure(api_key=api_key)
    config = Config()
    video_manager = VideoManager(config)
    analysis_service = AnalysisService()
    return config, video_manager, analysis_service

def process_videos(video_manager: VideoManager, analysis_service: AnalysisService, game_name: str):
    uploaded_files = video_manager.get_uploaded_files()
    new_videos = []

    for video_path in video_manager.list_video_files():
        filename = os.path.basename(video_path)

        if filename in video_manager.processed_videos:
            logging.info(f"Skipping processed video: {filename}")
            continue

        if filename in uploaded_files:
            logging.info(f"Video {filename} already uploaded, skipping upload.")
            video_file = uploaded_files[filename]
        else:
            video_file = video_manager.upload_video(video_path)
            if not video_file:
                continue

        new_videos.append((filename, video_file))

    if not new_videos:
        logging.info("No new videos to analyze.")
        return

    logging.info(f"Processing {len(new_videos)} new videos.")
    prompt_generator = PromptGenerator()

    for filename, video_file in new_videos:
        prompt = prompt_generator.create_game_prompt(game_name)
        response_text = analysis_service.analyze_video(video_file, prompt)
        json_data = analysis_service.extract_json(response_text)
        formatted_analysis = analysis_service.format_analysis(json_data)
        logging.info(f"Analysis for {filename}:\n{formatted_analysis}")
        video_manager.save_analysis(filename, json_data)

# Usage example
if __name__ == "__main__":
    from google.colab import userdata
    API_KEY = userdata.get('GOOGLE_API_KEY')
    
    config, video_manager, analysis_service = initialize_services(API_KEY)
    process_videos(video_manager, analysis_service, "EA FC 24")