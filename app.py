import os
import io
import sqlite3
import secrets
import base64
from functools import wraps
from pathlib import Path

import requests

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash, g
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from werkzeug.utils import secure_filename
from dotenv import load_dotenv


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

DATABASE = BASE_DIR / "brainbuxx.db"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.3-70b-versatile"
)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

ALLOWED_EXTENSIONS = {
    "txt", "pdf", "png", "jpg", "jpeg", "webp"
}

SYSTEM_PROMPT = """
You are BRAINBUXX, the AI learning and innovation assistant
developed by the VHS Science & Innovation Club.

Your motto is: Think, Explore, Invent.

Help students understand science, mathematics, technology,
programming, engineering, creativity, and innovation.

Explain difficult topics in clear language.
Use examples, step-by-step explanations, and practice questions
when appropriate.

When helping with schoolwork, explain the reasoning instead
of merely giving unexplained answers.

Never pretend that you searched the web if you did not.
Be honest when uncertain.
"""


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(str(DATABASE))
        g.db.row_factory = sqlite3.Row

    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)

    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(str(DATABASE))

    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT 'New conversation',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(conversation_id)
                REFERENCES conversations(id)
        );
    """)

    db.commit()
    db.close()


# --------------------------------------------------
# AUTHENTICATION
# --------------------------------------------------

def login_required(function):
    @wraps(function)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return decorated


@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("chat"))

    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if len(username) < 3 or len(username) > 30:
            flash("Username must contain 3–30 characters.", "error")
            return redirect(url_for("signup"))

        if len(email) > 254 or "@" not in email:
            flash("Enter a valid email address.", "error")
            return redirect(url_for("signup"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return redirect(url_for("signup"))

        db = get_db()

        existing = db.execute(
            "SELECT id FROM users WHERE username=? OR email=?",
            (username, email)
        ).fetchone()

        if existing:
            flash("Username or email is already registered.", "error")
            return redirect(url_for("signup"))

        password_hash = generate_password_hash(password)

        try:
            cursor = db.execute(
                """
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
                """,
                (username, email, password_hash)
            )

            db.commit()

            session.clear()
            session["user_id"] = cursor.lastrowid
            session["username"] = username

            return redirect(url_for("chat"))

        except sqlite3.IntegrityError:
            flash("Account could not be created.", "error")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")

        user = get_db().execute(
            """
            SELECT * FROM users
            WHERE username=? OR email=?
            """,
            (identity, identity.lower())
        ).fetchone()

        if user and check_password_hash(
            user["password_hash"], password
        ):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect(url_for("chat"))

        flash("Incorrect username, email, or password.", "error")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("index"))


# --------------------------------------------------
# CHAT DASHBOARD
# --------------------------------------------------

@app.route("/chat")
@login_required
def chat():
    db = get_db()

    conversations = db.execute(
        """
        SELECT id, title, created_at
        FROM conversations
        WHERE user_id=?
        ORDER BY id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    return render_template(
        "chat.html",
        conversations=conversations,
        username=session.get("username")
    )


@app.route("/api/conversations", methods=["POST"])
@login_required
def create_conversation():
    db = get_db()

    cursor = db.execute(
        """
        INSERT INTO conversations (user_id, title)
        VALUES (?, ?)
        """,
        (session["user_id"], "New conversation")
    )

    db.commit()

    return jsonify({
        "id": cursor.lastrowid,
        "title": "New conversation"
    })


def get_owned_conversation(conversation_id):
    return get_db().execute(
        """
        SELECT * FROM conversations
        WHERE id=? AND user_id=?
        """,
        (conversation_id, session["user_id"])
    ).fetchone()


@app.route("/api/conversations/<int:conversation_id>")
@login_required
def get_conversation(conversation_id):
    conversation = get_owned_conversation(conversation_id)

    if not conversation:
        return jsonify({"error": "Conversation not found"}), 404

    messages = get_db().execute(
        """
        SELECT role, content, created_at
        FROM messages
        WHERE conversation_id=?
        ORDER BY id ASC
        """,
        (conversation_id,)
    ).fetchall()

    return jsonify({
        "conversation": dict(conversation),
        "messages": [dict(message) for message in messages]
    })


@app.route(
    "/api/conversations/<int:conversation_id>",
    methods=["DELETE"]
)
@login_required
def delete_conversation(conversation_id):
    db = get_db()

    conversation = get_owned_conversation(conversation_id)

    if not conversation:
        return jsonify({"error": "Conversation not found"}), 404

    db.execute(
        "DELETE FROM messages WHERE conversation_id=?",
        (conversation_id,)
    )

    db.execute(
        "DELETE FROM conversations WHERE id=? AND user_id=?",
        (conversation_id, session["user_id"])
    )

    db.commit()

    return jsonify({"success": True})


# --------------------------------------------------
# GROQ AI
# --------------------------------------------------

def ask_groq(messages):
    if not GROQ_API_KEY:
        raise RuntimeError(
            "Groq API key is missing. Configure GROQ_API_KEY in .env."
        )

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.5,
        "max_tokens": 2000
    }

    response = requests.post(
        GROQ_URL,
        headers=headers,
        json=payload,
        timeout=90
    )

    if response.status_code != 200:
        app.logger.error(
            "Groq request failed with HTTP %s",
            response.status_code
        )

        raise RuntimeError(
            "The AI service could not complete your request. "
            "Check your API configuration and model availability."
        )

    data = response.json()

    return data["choices"][0]["message"]["content"]


@app.route("/api/chat", methods=["POST"])
@login_required
def chat_api():
    data = request.get_json(silent=True) or {}

    message = str(data.get("message", "")).strip()

    conversation_id = data.get("conversation_id")

    if not message:
        return jsonify({"error": "Enter a message first."}), 400

    if len(message) > 12000:
        return jsonify({"error": "Message is too long."}), 400

    db = get_db()

    if conversation_id:
        conversation = get_owned_conversation(conversation_id)

        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404

    else:
        cursor = db.execute(
            """
            INSERT INTO conversations (user_id, title)
            VALUES (?, ?)
            """,
            (session["user_id"], message[:45])
        )

        conversation_id = cursor.lastrowid

        db.commit()

    previous = db.execute(
        """
        SELECT role, content FROM messages
        WHERE conversation_id=?
        ORDER BY id DESC
        LIMIT 12
        """,
        (conversation_id,)
    ).fetchall()

    history = list(reversed(previous))

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for item in history:
        if item["role"] in ("user", "assistant"):
            messages.append({
                "role": item["role"],
                "content": item["content"]
            })

    messages.append({"role": "user", "content": message})

    try:
        answer = ask_groq(messages)

    except (requests.RequestException, RuntimeError, KeyError, ValueError):
        app.logger.exception("AI response failed")

        return jsonify({
            "error": "BRAINBUXX could not generate a response. "
                     "Please try again."
        }), 502

    db.execute(
        """
        INSERT INTO messages (conversation_id, role, content)
        VALUES (?, 'user', ?)
        """,
        (conversation_id, message)
    )

    db.execute(
        """
        INSERT INTO messages (conversation_id, role, content)
        VALUES (?, 'assistant', ?)
        """,
        (conversation_id, answer)
    )

    db.commit()

    return jsonify({
        "answer": answer,
        "conversation_id": conversation_id
    })


# --------------------------------------------------
# FILE ATTACHMENTS
# --------------------------------------------------

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


@app.route("/api/upload", methods=["POST"])
@login_required
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file selected."}), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({"error": "No file selected."}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type."}), 400

    filename = secure_filename(file.filename)

    content = file.read(6 * 1024 * 1024 + 1)

    if len(content) > 6 * 1024 * 1024:
        return jsonify({"error": "File is too large."}), 400

    extension = filename.rsplit(".", 1)[1].lower()

    if extension == "txt":
        try:
            text = content.decode("utf-8")

            return jsonify({
                "filename": filename,
                "type": "text",
                "content": text[:12000]
            })

        except UnicodeDecodeError:
            return jsonify({"error": "Text file is not UTF-8 encoded."}), 400

    if extension == "pdf":
        # PDF upload is supported, but PDF text extraction
        # requires an additional PDF parsing dependency.
        return jsonify({
            "filename": filename,
            "type": "pdf",
            "content": base64.b64encode(content).decode("ascii"),
            "message": "PDF attached. Text extraction is not enabled yet."
        })

    if extension in ("png", "jpg", "jpeg", "webp"):
        mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp"
        }[extension]

        return jsonify({
            "filename": filename,
            "type": "image",
            "content": base64.b64encode(content).decode("ascii"),
            "mime": mime
        })

    return jsonify({"error": "Unsupported file."}), 400


# --------------------------------------------------
# WIKIPEDIA SEARCH
# --------------------------------------------------

@app.route("/api/wiki")
@login_required
def wikipedia_search():
    query = request.args.get("q", "").strip()[:200]

    if not query:
        return jsonify({"results": []})

    try:
        response = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": 0,
                "gsrlimit": 8,
                "prop": "extracts|pageimages|info",
                "exintro": 1,
                "explaintext": 1,
                "exchars": 500,
                "piprop": "thumbnail",
                "pithumbsize": 400,
                "inprop": "url",
                "format": "json"
            },
            headers={
                "User-Agent": "Brainbuxx/1.0 educational application"
            },
            timeout=15
        )

        response.raise_for_status()

        pages = response.json().get("query", {}).get("pages", {})

        results = []

        for page in pages.values():
            results.append({
                "title": page.get("title", ""),
                "extract": page.get("extract", ""),
                "url": page.get(
                    "fullurl",
                    "https://en.wikipedia.org/"
                ),
                "thumbnail": page.get("thumbnail", {}).get("source")
            })

        return jsonify({"results": results})

    except requests.RequestException:
        return jsonify({"error": "Wikipedia search failed."}), 502


# --------------------------------------------------
# WIKIMEDIA COMMONS IMAGE SEARCH
# --------------------------------------------------

@app.route("/api/images")
@login_required
def image_search():
    query = request.args.get("q", "").strip()[:200]

    if not query:
        return jsonify({"results": []})

    try:
        response = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": "filetype:bitmap " + query,
                "gsrnamespace": 6,
                "gsrlimit": 12,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": 400,
                "format": "json"
            },
            headers={
                "User-Agent": "Brainbuxx/1.0 educational application"
            },
            timeout=20
        )

        response.raise_for_status()

        pages = response.json().get("query", {}).get("pages", {})

        results = []

        for page in pages.values():
            image_info = page.get("imageinfo", [{}])[0]

            metadata = image_info.get("extmetadata", {})

            results.append({
                "title": page.get("title", ""),
                "url": image_info.get("url", ""),
                "thumbnail": image_info.get("thumburl")
                    or image_info.get("url", ""),
                "description": metadata.get(
                    "ImageDescription", {}
                ).get("value", ""),
                "license": metadata.get(
                    "LicenseShortName", {}
                ).get("value", "Check original page"),
                "source": image_info.get("descriptionurl", "")
            })

        return jsonify({"results": results})

    except requests.RequestException:
        return jsonify({"error": "Image search failed."}), 502


# --------------------------------------------------
# SECURITY HEADERS
# --------------------------------------------------

@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(self), geolocation=()"
    )

    return response


# --------------------------------------------------
# START APPLICATION
# --------------------------------------------------

init_db()


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.getenv("PORT", "5000")),
        debug=False
    )