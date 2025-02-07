from flask import Flask, request, jsonify, render_template, send_from_directory, session
from werkzeug.utils import secure_filename
import os
from functools import wraps
import json
import logging
from typing import Dict, List
import google.generativeai as genai
from cryptography.fernet import Fernet

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Required for session management

class AppConfig:
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
    JSON_FILE = os.environ.get('JSON_FILE', 'processed_videos.json')
    ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv', 'webm'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # API key encryption
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY', Fernet.generate_key())
    KEYS_FILE = 'api_keys.json'
    
    @classmethod
    def init_app(cls):
        os.makedirs(cls.UPLOAD_FOLDER, exist_ok=True)
        if not os.path.exists(cls.JSON_FILE):
            with open(cls.JSON_FILE, 'w') as f:
                json.dump({}, f)
        if not os.path.exists(cls.KEYS_FILE):
            with open(cls.KEYS_FILE, 'w') as f:
                json.dump({}, f)

class APIKeyManager:
    def __init__(self, key_file: str, encryption_key: bytes):
        self.key_file = key_file
        self.fernet = Fernet(encryption_key)
    
    def save_key(self, user_id: str, api_key: str):
        encrypted_key = self.fernet.encrypt(api_key.encode())
        keys = self._load_keys()
        keys[user_id] = encrypted_key.decode()
        self._save_keys(keys)
    
    def get_key(self, user_id: str) -> str:
        keys = self._load_keys()
        if user_id not in keys:
            return None
        encrypted_key = keys[user_id].encode()
        return self.fernet.decrypt(encrypted_key).decode()
    
    def _load_keys(self) -> Dict:
        try:
            with open(self.key_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def _save_keys(self, keys: Dict):
        with open(self.key_file, 'w') as f:
            json.dump(keys, f)

app.config.from_object(AppConfig)
AppConfig.init_app()
key_manager = APIKeyManager(AppConfig.KEYS_FILE, AppConfig.ENCRYPTION_KEY)

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'No session found'}), 401
        api_key = key_manager.get_key(session['user_id'])
        if not api_key:
            return jsonify({'error': 'API key not configured'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api-key', methods=['POST'])
def set_api_key():
    api_key = request.json.get('api_key')
    if not api_key:
        return jsonify({'error': 'No API key provided'}), 400
    
    # Generate a unique user ID if not exists
    if 'user_id' not in session:
        session['user_id'] = os.urandom(16).hex()
    
    # Save encrypted API key
    key_manager.save_key(session['user_id'], api_key)
    return jsonify({'message': 'API key saved successfully'})

@app.route('/api-key/verify', methods=['GET'])
def verify_api_key():
    if 'user_id' not in session:
        return jsonify({'configured': False})
    
    api_key = key_manager.get_key(session['user_id'])
    return jsonify({
        'configured': bool(api_key)
    })

# Modified upload route to use API key
@app.route('/upload', methods=['POST'])
@require_api_key
def upload_file():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    # Get API key for processing
    api_key = key_manager.get_key(session['user_id'])
    genai.configure(api_key=api_key)
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            file.save(file_path)
            
            # Queue the file for analysis
            # This would typically be handled by a background task queue (e.g., Celery)
            # For now, we'll just mark it as pending in the JSON
            analysis_data = load_analysis_data()
            analysis_data[filename] = {"status": "pending"}
            save_analysis_data(analysis_data)
            
            return jsonify({
                'message': 'File uploaded successfully',
                'filename': filename
            }), 200
            
        except Exception as e:
            logging.error(f"Error saving file: {e}")
            return jsonify({'error': 'Error saving file'}), 500
    
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/videos')
def list_videos():
    logging.debug("hello")
    analysis_data = load_analysis_data()
    return jsonify({
        'videos': [
            {
                'filename': filename,
                'status': data.get('status', 'completed'),
                'analysis': data,
            }
            for filename, data in analysis_data.items()
        ]
    })

@app.route('/video/<filename>')
def serve_video(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/analysis/<filename>')
def get_analysis(filename):
    analysis_data = load_analysis_data()
    if filename not in analysis_data:
        return jsonify({'error': 'Video not found'}), 404
    return jsonify(analysis_data[filename])
# Utility functions
def allowed_file(filename: str) -> bool:
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in AppConfig.ALLOWED_EXTENSIONS

def load_analysis_data() -> Dict:
    try:
        with open(AppConfig.JSON_FILE, 'r') as f:
            logging.info("FFF", str(f))
            return json.load(f)
    except FileNotFoundError:
        logging.info(f"no file found")
        print("file not found")
        return {}


# Background task simulation (in production, use Celery or similar)
def process_video(filename: str):
    """
    Process a video file and update its analysis data.
    In production, this would be a Celery task.
    """
    try:
        analysis_data = load_analysis_data()
        if filename not in analysis_data:
            return
        
        # Initialize the video manager and analysis service
        # (Using the classes from our previous implementation)
        video_file = upload_to_gemini(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        if not video_file:
            analysis_data[filename] = {"status": "failed", "error": "Upload to Gemini failed"}
            save_analysis_data(analysis_data)
            return
        
        # Perform analysis
        prompt = create_game_prompt("EA FC 24")  # You might want to make this configurable
        response = analyze_video(video_file, prompt)
        
        # Update analysis data
        analysis_data[filename] = {
            "status": "completed",
            "analysis": extract_json(response)
        }
        save_analysis_data(analysis_data)
        
    except Exception as e:
        logging.error(f"Error processing video {filename}: {e}")
        analysis_data[filename] = {"status": "failed", "error": str(e)}
        save_analysis_data(analysis_data)

# Routes
@app.route('/')
def index():
    return render_template('index.html')
    
if __name__ == '__main__':
    app.run(debug=True)