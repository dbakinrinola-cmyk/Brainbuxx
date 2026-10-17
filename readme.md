# BRAINBUXX

## VHS Innovation Edition

**Think · Explore · Invent**

Developed by VHS Science & Innovation Club.

BRAINBUXX is an AI-powered educational assistant built with
Flask, SQLite, HTML, CSS, JavaScript, and the Groq API.

## Features

- User registration and login
- Hashed passwords
- SQLite conversation history
- Groq-powered AI chat
- Wikipedia search
- Wikimedia Commons image search
- Browser-based voice input
- Text-file attachments
- Responsive mobile interface
- Basic PWA installation metadata

## Technology

- Python
- Flask
- SQLite
- HTML5
- CSS3
- JavaScript
- Groq API
- Wikipedia API
- Wikimedia Commons API

## Installation

Install Python and the dependencies:

    pip install -r requirements.txt

Create a `.env` file containing:

    SECRET_KEY=your_random_secret
    GROQ_API_KEY=your_groq_api_key
    GROQ_MODEL=llama-3.3-70b-versatile

Start the application:

    python app.py

Open:

    http://127.0.0.1:5000

## Termux

Install Python:

    pkg update
    pkg install python
    pip install -r requirements.txt

Start the application:

    python app.py

Open the local address in your Android browser.

## Security

Never commit `.env` or publish API credentials.

Before public deployment, configure HTTPS, secure session cookies,
CSRF protection, request rate limits, and production-grade logging.

## Attribution

Developed by VHS Science & Innovation Club.

BRAINBUXX — Think · Explore · Invent.