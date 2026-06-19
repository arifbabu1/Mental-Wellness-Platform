# PythonAnywhere-Safe Chatbot Architecture

## Goal

The emergency page chatbot runs on normal Django WSGI views and is safe for PythonAnywhere free-plan deployment. It does not require Ollama, Channels, Redis, Celery, Daphne, ASGI, WebSockets, or background workers.

## Runtime Flow

Browser:
- `/emergency/` renders the existing chatbot UI.
- The browser posts messages to `/emergency/chat/` with CSRF protection.
- `emergencyChatSessionId` is kept in the browser so the same chat session can continue.

Django:
- `POST /emergency/chat/` handles chatbot replies.
- `GET /emergency/chat/history/?session_id=...` loads prior messages.
- `POST /emergency/chat/recommend-doctors/` recommends doctors from local data.
- `POST /emergency/chat/detect-emergency/` runs local emergency detection.

AI:
- Emergency/self-harm/suicide/violence detection is always local and instant.
- Primary AI is Gemini REST API when `CHATBOT_AI_ENABLED=True`, `CHATBOT_AI_PROVIDER=gemini`, and `GEMINI_API_KEY` is set.
- If Gemini is missing, blocked, timed out, invalid, over quota, or returns an API error, the chatbot falls back to local rule-based responses.
- Platform knowledge retrieval uses local hash embeddings stored in the database, not remote embedding services.

## Environment

Use `.env.example` as the template:

```env
CHATBOT_AI_ENABLED=True
CHATBOT_AI_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-1.5-flash
CHATBOT_TIMEOUT=6
CHATBOT_MAX_MESSAGE_LENGTH=1000
```

Never commit real API keys.

## Safety Behavior

The chatbot:
- Keeps replies compact, usually 3-6 short sentences.
- Supports English, Bangla, and Banglish fallback replies.
- Remembers recent conversation context from `ChatSession` / `ChatMessage`, limited to recent user messages.
- Does not diagnose, prescribe medicine, provide unsafe medical advice, or claim to replace professional care.
- Never exposes API keys, environment variables, stack traces, or raw server errors.
- Logs emergency-risk messages to `EmergencyLog` for audit.

## Production Check

Run:

```bash
python manage.py check_chatbot_ai
```

The command prints only safe success/failure messages. If Gemini is unavailable, production still works with local fallback.
