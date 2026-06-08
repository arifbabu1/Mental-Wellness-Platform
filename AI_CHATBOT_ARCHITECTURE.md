# Free Offline AI Chatbot Architecture

## Goal

The emergency page chatbot is a free, AI-powered mental health assistant for the Online Mental Patient Consultation System. It uses Django, local Ollama models, session memory, emergency detection, RAG over platform content, and doctor matching.

No paid API is required.

## Architecture

Browser emergency page:
- Existing `/emergency/` UI remains simple: chat bubbles, input, send button.
- Stores `emergencyChatSessionId` in `localStorage`.
- Sends messages to Django with CSRF protection.

Django backend:
- `POST /emergency/chat/`: main AI response API.
- `GET /emergency/chat/history/?session_id=...`: chat history API.
- `POST /emergency/chat/recommend-doctors/`: doctor recommendation API.
- `POST /emergency/chat/detect-emergency/`: emergency detection API.

AI service:
- `home/rag_chatbot.py`
- Uses Ollama at `OLLAMA_BASE_URL`, default `http://127.0.0.1:11434`.
- Default chat model: `llama3.2:1b` for low-RAM systems.
- Default embedding model: `nomic-embed-text`.
- Falls back to safe local responses and local lexical embeddings if Ollama is offline.

Database:
- Local development defaults to SQLite.
- Production can use free PostgreSQL by setting `DATABASE_URL` from Neon or Supabase.
- Models added:
  - `ChatSession`
  - `ChatMessage`
  - `EmergencyLog`
  - `ChatbotKnowledgeChunk`

## AI Behavior

The assistant:
- Responds naturally and empathetically.
- Supports English and Bangla by detecting Bangla Unicode text.
- Maintains recent session context.
- Avoids diagnosis, prescriptions, dangerous medical advice, and claims of being a licensed doctor.
- Encourages therapy or doctor consultation when appropriate.

## Hybrid Routing

Every message follows this order:

1. Emergency safety detection
2. Platform-specific routing and RAG retrieval
3. General wellness response using local LLM
4. Safe fallback response if model/retrieval fails

## Emergency Detection

Emergency detection catches English and Bangla patterns for:
- Suicide
- Self-harm
- Violence
- Extreme depression
- Medical emergency

When detected:
- The chatbot bypasses normal generation.
- A safe crisis response is returned.
- `EmergencyLog` is created.
- Emergency-support doctors are prioritized.
- Bangladesh emergency services `999` and immediate professional help are recommended.

## Doctor Matching Algorithm

The matcher extracts symptoms from recent user messages:
- Anxiety
- Depression
- Sleep problems
- Stress
- Trauma
- Addiction
- OCD
- Relationship concerns

Doctors are scored using:
- Specialization labels
- Primary focus labels
- Bio
- Expertise tags
- Emergency support
- Online availability
- Availability score
- Years of experience

Example:

User: `I have anxiety and sleep problems`

Preferred matches:
- Psychiatrist
- Anxiety specialist
- Sleep-focused therapist
- Counselor with relevant focus areas

## Ollama Setup

Install Ollama, then pull free local models:

```bash
ollama pull llama3.2:1b
ollama pull mistral
ollama pull gemma:2b
ollama pull nomic-embed-text
```

Run Ollama locally:

```bash
ollama serve
```

Use a smaller model for low RAM:

```env
OLLAMA_CHAT_MODEL=gemma:2b
```

## Environment

Create `.env` from `.env.example`.

Important values:

```env
SECRET_KEY=change-me
DEBUG=False
ALLOWED_HOSTS=your-domain.onrender.com,127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=https://your-domain.onrender.com,http://127.0.0.1:8000
DATABASE_URL=postgresql://user:password@host:5432/database
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CHAT_MODEL=llama3.2:1b
OLLAMA_EMBED_MODEL=nomic-embed-text
```

## Free Deployment

Recommended free stack:

- Frontend/templates: Django served by Render free tier, or static assets via WhiteNoise.
- Backend: Render/Railway free tier.
- Database: Neon or Supabase free PostgreSQL.
- AI: Ollama locally on the same machine for development, or a low-resource free/self-hosted server with `gemma:2b` for production.

Important: free cloud containers often do not have enough RAM for larger LLMs. For zero-cost production, use the smallest model that works (`gemma:2b`) or keep Ollama on a free/local institutional machine and set `OLLAMA_BASE_URL` to that host.

## Performance Rules

Implemented:
- Short timeouts for Ollama.
- Cooldown after Ollama connection failure.
- Safe fallback responses.
- Local lexical embeddings if embedding model is unavailable.
- Recent-memory limit of 8 messages.
- Context length cap for RAG prompts.
- No typing animation.
- No paid API calls.

## Security Improvements

Implemented:
- CSRF-protected chat POST.
- Environment-driven secret key, hosts, CSRF origins, database, and Ollama URL.
- No API keys required for AI.
- Emergency logs are stored server-side for audit.

Recommended before production:
- Set `DEBUG=False`.
- Set a strong `SECRET_KEY`.
- Restrict `ALLOWED_HOSTS`.
- Use HTTPS.
- Add rate limiting on `/emergency/chat/`.
- Review emergency logs only with authorized admin/staff access.

## Production Structure

Key files:

- `home/rag_chatbot.py`: AI orchestration, routing, RAG, Ollama, doctor matching.
- `home/models.py`: chat memory, emergency logs, vector chunks.
- `home/views.py`: API endpoints.
- `home/urls.py`: API routes.
- `home/templates/home/emergency.html`: existing chatbot UI and fetch integration.
- `wellness_platform/settings.py`: free/local configuration and production env support.
