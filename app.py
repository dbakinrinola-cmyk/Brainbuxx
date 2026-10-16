  
import os
import uuid
import logging
import base64
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
import requests
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("BRAINBUXX_DATA_DIR", BASE_DIR />
UPLOAD_DIR = DATA_DIR / "uploads"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    if os.getenv("FLASK_ENV") == "production":
        raise RuntimeError("Set a strong FLASK_SECRET_KEY >
    app.secret_key = "dev-only-change-me"
app.config.update(
    MAX_CONTENT_LENGTH=15 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0")

if os.getenv("TRUST_PROXY", "0") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto>

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("brainbuxx")

API_KEY = os.getenv("GROQ_API_KEY")
MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.>
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

def groq_headers():
    return {"Authorization": f"Bearer {API_KEY}", "Content

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json"}
IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp", "i
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".mpga>
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".png", ".
MAX_HISTORY = 24

