import hashlib
import html
import json
import logging
import math
import re
import time
from pathlib import Path
from urllib import error, request

from django.conf import settings
from django.db import transaction
from django.urls import reverse

from .models import (
    AssessmentQuestion,
    BlogPost,
    ChatMessage,
    ChatSession,
    ChatbotKnowledgeChunk,
    Doctor,
    DoctorPrimaryFocus,
    DoctorSchedule,
    DoctorSpecialization,
    EmergencyLog,
    HealthTaskTemplate,
)

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = getattr(settings, 'OLLAMA_BASE_URL', 'http://127.0.0.1:11434')
OLLAMA_CHAT_MODEL = getattr(settings, 'OLLAMA_CHAT_MODEL', 'llama3.2:1b')
OLLAMA_EMBED_MODEL = getattr(settings, 'OLLAMA_EMBED_MODEL', 'nomic-embed-text')
CHAT_TIMEOUT = getattr(settings, 'OLLAMA_CHAT_TIMEOUT', 30)
EMBED_TIMEOUT = getattr(settings, 'OLLAMA_EMBED_TIMEOUT', 5)
LOCAL_EMBED_DIM = 384
SYNC_INTERVAL_SECONDS = 30
_last_sync_at = 0
_next_chat_retry_at = 0
_next_embed_retry_at = 0
_chat_available = True
_embed_available = True
RETRY_UNAVAILABLE_AFTER_SECONDS = 60
MAX_HISTORY_MESSAGES = 8
MAX_CONTEXT_CHARS = 1800


CRISIS_PATTERNS = [
    r'\bsuicid(?:e|al)\b',
    r'\bkill myself\b',
    r'\bself harm\b',
    r'\bend my life\b',
    r'\bwant to die\b',
    r"\bdon'?t want to live\b",
    r'\bself[-\s]?harm\b',
    r'\bhurt myself\b',
    r'\bcut myself\b',
    r'\boverdose\b',
    r'\bmedical emergency\b',
    r"\bcan'?t stay safe\b",
    r'\bextreme depression\b',
    r'\bviolent thoughts\b',
    r'\bhurt someone\b',
    r'\bkill someone\b',
    'আত্মহত্যা',
    r'নিজেকে\s*মেরে\s*ফেলব',
    r'নিজেকে\s*মেরে',
    r'মরে\s*যেতে',
    r'মরতে\s*চাই',
    r'বাঁচতে\s*চাই\s*না',
    r'নিজেকে\s*আঘাত\s*করব',
    r'নিজেকে\s*আঘাত',
    r'জীবন\s*শেষ',
    r'সব\s*শেষ\s*করে\s*দেব',
    r'মেরে\s*ফেলব',
]


PLATFORM_KEYWORDS = {
    'appointment', 'appointments', 'book', 'booking', 'doctor', 'doctors',
    'therapist', 'therapy', 'dashboard', 'assessment', 'clinical', 'phq',
    'gad', 'blog', 'blogs', 'payment', 'prescription', 'task', 'tasks',
    'hotline', '999', 'center', 'centers', 'schedule', 'login', 'register',
    'platform', 'website', 'service', 'services', 'consultation',
}

GENERAL_WELLNESS_KEYWORDS = {
    'anxiety', 'anxious', 'stress', 'stressed', 'depression', 'depressed',
    'sad', 'sleep', 'panic', 'overwhelmed', 'lonely', 'mindfulness',
    'breathing', 'coping', 'relationship', 'work', 'burnout', 'grief',
}

SYMPTOM_KEYWORDS = {
    'anxiety': {
        'en': ['anxiety', 'anxious', 'panic', 'panic attack', 'worry', 'fear', 'nervous'],
        'bn': ['উদ্বেগ', 'দুশ্চিন্তা', 'আতঙ্ক', 'ভয়', 'প্যানিক'],
        'doctor_terms': ['anxiety', 'panic', 'psychiatrist', 'therapist', 'counselor'],
    },
    'depression': {
        'en': ['depression', 'depressed', 'sad', 'hopeless', 'empty', 'numb'],
        'bn': ['বিষণ্ণ', 'ডিপ্রেশন', 'মন খারাপ', 'হতাশ', 'শূন্য'],
        'doctor_terms': ['depression', 'mood', 'psychiatrist', 'therapist', 'counselor'],
    },
    'sleep': {
        'en': ['sleep', 'insomnia', 'nightmare', 'cannot sleep', "can't sleep", 'cant sleep', 'sleepless'],
        'bn': ['ঘুম', 'অনিদ্রা', 'ঘুমাতে পারি না', 'দুঃস্বপ্ন'],
        'doctor_terms': ['sleep', 'insomnia', 'psychiatrist', 'therapist'],
    },
    'stress': {
        'en': ['stress', 'stressed', 'overwhelmed', 'burnout', 'pressure'],
        'bn': ['চাপ', 'স্ট্রেস', 'অতিরিক্ত চাপ', 'ক্লান্ত'],
        'doctor_terms': ['stress', 'burnout', 'counselor', 'therapist'],
    },
    'trauma': {
        'en': ['trauma', 'ptsd', 'flashback', 'abuse', 'assault'],
        'bn': ['ট্রমা', 'আঘাতজনিত', 'নির্যাতন', 'ফ্ল্যাশব্যাক'],
        'doctor_terms': ['trauma', 'ptsd', 'therapist', 'clinical psychologist'],
    },
    'addiction': {
        'en': ['addiction', 'alcohol', 'drug', 'substance', 'relapse'],
        'bn': ['আসক্তি', 'মাদক', 'অ্যালকোহল', 'নেশা'],
        'doctor_terms': ['addiction', 'substance', 'psychiatrist', 'counselor'],
    },
    'ocd': {
        'en': ['ocd', 'obsession', 'compulsion', 'intrusive thoughts'],
        'bn': ['ওসিডি', 'বারবার চিন্তা', 'বাধ্যতামূলক'],
        'doctor_terms': ['ocd', 'obsessive', 'psychiatrist', 'therapist'],
    },
    'relationship': {
        'en': ['relationship', 'breakup', 'family', 'spouse', 'marriage'],
        'bn': ['সম্পর্ক', 'বিচ্ছেদ', 'পরিবার', 'সঙ্গী', 'বিয়ে'],
        'doctor_terms': ['relationship', 'family', 'therapist', 'counselor'],
    },
}


def is_crisis_query(text):
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in CRISIS_PATTERNS)


def detect_crisis_terms(text):
    lowered = text.lower()
    return [pattern for pattern in CRISIS_PATTERNS if re.search(pattern, lowered)]


def crisis_response(language='en', doctors=None):
    doctor_text = doctor_recommendation_text(doctors or [], language, emergency=True)
    if language == 'bn':
        return (
            'আপনি আমাকে বলেছেন বলে ধন্যবাদ। এটা জরুরি মনে হচ্ছে, আর এখন আপনার নিরাপত্তাই সবচেয়ে গুরুত্বপূর্ণ। '
            'যদি আপনি নিজেকে আঘাত করার ঝুঁকিতে থাকেন, নিরাপদ থাকতে না পারেন, অথবা এটি মেডিক্যাল ইমার্জেন্সি হয়, এখনই জরুরি সেবা নিন বা নিকটস্থ জরুরি বিভাগে যান। '
            'এ প্ল্যাটফর্মের ২৪/৭ জরুরি হটলাইন 999-এও কল করতে পারেন। সম্ভব হলে ক্ষতি করতে পারে এমন জিনিস থেকে দূরে যান এবং একজন বিশ্বস্ত মানুষকে আপনার পাশে থাকতে বলুন। '
            f'{doctor_text}'
        )
    return (
        "I'm really glad you told me. This sounds urgent, and your safety matters most right now. "
        "If you might hurt yourself, feel unable to stay safe, or this is a medical emergency, please call emergency services now or go to the nearest emergency room. "
        "You can also call Bangladesh emergency services at 999. "
        "If possible, move away from anything you could use to harm yourself and contact a trusted person to stay with you while you get help. "
        f'{doctor_text}'
    )


def classify_query(message):
    base_category = classify_query_without_retrieval(message)
    if base_category == 'platform_specific':
        return base_category

    words = set(tokenize(message))
    if words & GENERAL_WELLNESS_KEYWORDS:
        return 'general_wellness'

    top_context = retrieve_context(message, top_k=1, minimum_score=0.22)
    if top_context:
        return 'platform_specific'
    return base_category


def classify_query_without_retrieval(message):
    words = set(re.findall(r'[a-z0-9]+', message.lower()))
    if words & PLATFORM_KEYWORDS:
        return 'platform_specific'
    return 'general_wellness'


def retrieve_context(query, top_k=4, minimum_score=0.18):
    query_embedding, embedding_model = embed_text(query)
    query_tokens = set(tokenize(query))
    scored = []
    for chunk in ChatbotKnowledgeChunk.objects.exclude(embedding=[]):
        vector_score = cosine_similarity(query_embedding, chunk.embedding)
        lexical_score = lexical_similarity(query_tokens, f"{chunk.title} {chunk.content}")
        if embedding_model == 'local-hash-embedding':
            if lexical_score == 0 and vector_score < 0.35:
                continue
            score = (lexical_score * 0.85) + (vector_score * 0.15)
        else:
            score = (vector_score * 0.75) + (lexical_score * 0.25)
        if score >= minimum_score:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            'score': round(score, 4),
            'title': chunk.title,
            'url': chunk.url,
            'content': chunk.content,
            'source_type': chunk.source_type,
        }
        for score, chunk in scored[:top_k]
    ]


def generate_platform_response(message, contexts, history=None, language='en', doctors=None):
    if should_use_direct_platform_answer(message):
        return platform_context_fallback(message, contexts, language, doctors)

    context_text = '\n\n'.join(
        f"Source: {context['title'] or context['source_type']} ({context['url'] or 'internal'})\n{context['content']}"
        for context in contexts
    )
    system_prompt = build_system_prompt(language, platform_mode=True)
    doctor_text = doctor_recommendation_text(doctors or [], language)
    user_prompt = (
        f"Recent conversation:\n{format_history(history or [])}\n\n"
        f"Platform context:\n{context_text[:MAX_CONTEXT_CHARS]}\n\n"
        f"Relevant doctors:\n{doctor_text}\n\n"
        f"User question: {message}"
    )
    response = ollama_chat(system_prompt, user_prompt)
    return response or platform_context_fallback(message, contexts, language, doctors)


def should_use_direct_platform_answer(message):
    lowered = message.lower()
    direct_terms = [
        'appointment', 'appointments', 'book', 'booking', 'schedule',
        'service', 'services', 'offer', 'offers',
        'assessment', 'phq', 'gad', 'screening',
        'hotline', 'emergency', 'crisis', 'center',
    ]
    return any(term in lowered for term in direct_terms)


def build_system_prompt(language='en', platform_mode=False):
    language_rule = (
        "Reply in Bangla because the user is writing in Bangla."
        if language == 'bn'
        else "Reply in English unless the user switches language."
    )
    source_rule = (
        "You are the offline AI assistant for a Mental Wellness Platform. "
        "Use only the provided platform context for platform-specific facts. "
        if platform_mode
        else "You are an offline AI mental health support assistant. "
    )
    return (
        f"{source_rule}"
        "Your personality is calm, caring, professional, emotionally supportive, and friendly. "
        "You are not a licensed doctor and must not claim to diagnose, prescribe medicine, or replace therapy. "
        "Use recent conversation context so the user does not need to repeat themselves. "
        "For mental health topics, validate feelings, ask one gentle follow-up when useful, and suggest professional consultation when symptoms are persistent, severe, or impairing daily life. "
        "For crisis, self-harm, suicide, violence, or medical emergency, prioritize immediate safety, Bangladesh emergency services at 999, and emergency doctor consultation. "
        "Do not provide harmful instructions, methods, medication dosages, or dangerous medical advice. "
        "Keep responses short, natural, and non-repetitive. "
        f"{language_rule}"
    )


def generate_general_response(message, history=None, language='en', doctors=None):
    system_prompt = build_system_prompt(language)
    user_prompt = (
        f"Recent conversation:\n{format_history(history or [])}\n\n"
        f"Relevant doctor options:\n{doctor_recommendation_text(doctors or [], language)}\n\n"
        f"User message: {message}"
    )
    response = ollama_chat(system_prompt, user_prompt)
    return response or safe_fallback_response(message, language, doctors)


def chatbot_reply(message, user=None, session_id=None, django_session_key=''):
    message = (message or '').strip()
    language = detect_language(message)
    chat_session = get_or_create_chat_session(session_id, user, django_session_key, language)
    history = get_recent_history(chat_session)
    history_text = ' '.join(
        [message] + [item.content for item in history if item.role == 'user']
    )
    crisis = is_crisis_query(message)
    symptoms = extract_symptoms_from_history(history_text)
    recommended_doctors = recommend_doctors_for_symptoms(symptoms, crisis=crisis, limit=3)
    category = 'crisis' if crisis else classify_query(message)
    contexts = []
    used_rag = False

    ChatMessage.objects.create(
        session=chat_session,
        role='user',
        content=message,
        category=category,
        metadata={'language': language, 'symptoms': symptoms},
    )

    if crisis:
        response = crisis_response(language, recommended_doctors)
        EmergencyLog.objects.create(
            session=chat_session,
            user=user if getattr(user, 'is_authenticated', False) else None,
            message=message,
            detected_terms=detect_crisis_terms(message),
            risk_level='critical',
            recommended_action='Call Bangladesh emergency services at 999 or go to the nearest emergency department.',
        )
    elif category == 'platform_specific':
        try:
            ensure_knowledge_base_synced()
            contexts = retrieve_context(message)
        except Exception as exc:
            logger.warning('Chatbot knowledge lookup unavailable: %s', exc)
            contexts = []
        used_rag = bool(contexts)
        if contexts:
            response = generate_platform_response(message, contexts, history, language, recommended_doctors)
        else:
            response = safe_fallback_response(message, language, recommended_doctors)
    else:
        response = generate_general_response(message, history, language, recommended_doctors)

    ChatMessage.objects.create(
        session=chat_session,
        role='assistant',
        content=response,
        category=category,
        metadata={
            'language': language,
            'used_rag': used_rag,
            'doctors': serialize_doctors(recommended_doctors),
        },
    )
    update_session_title(chat_session, message, language)
    return {
        'response': response,
        'category': category,
        'used_rag': used_rag,
        'session_id': str(chat_session.id),
        'language': language,
        'is_emergency': crisis,
        'doctors': serialize_doctors(recommended_doctors),
    }


def safe_fallback_response(message, language='en', doctors=None):
    if is_crisis_query(message):
        return crisis_response(language, doctors)

    lowered = message.lower()
    doctor_text = doctor_recommendation_text(doctors or [], language)
    if language == 'bn':
        if any(word in lowered for word in ['anxiety', 'panic', 'anxious']) or any(term in message for term in SYMPTOM_KEYWORDS['anxiety']['bn']):
            return f'এটা খুব অস্বস্তিকর লাগতে পারে। একটু ধীরে শ্বাস নিন: ৪ গণনা করে শ্বাস নিন, ৬ গণনা করে ছাড়ুন। উদ্বেগ বারবার হলে একজন মানসিক স্বাস্থ্য বিশেষজ্ঞের সাথে কথা বলা সহায়ক হতে পারে। {doctor_text}'
        if any(word in lowered for word in ['sad', 'depressed', 'hopeless']) or any(term in message for term in SYMPTOM_KEYWORDS['depression']['bn']):
            return f'আপনার কষ্টটা সত্যিই ভারী শোনাচ্ছে। আপনি একা নন। একজন বিশ্বস্ত মানুষকে জানান এবং প্রয়োজন হলে থেরাপিস্ট/ডাক্তারের সাহায্য নেওয়া ভালো হতে পারে। {doctor_text}'
        if any(word in lowered for word in ['stress', 'overwhelmed', 'burnout']) or any(term in message for term in SYMPTOM_KEYWORDS['stress']['bn']):
            return f'একসাথে অনেক চাপ এলে এমন লাগা স্বাভাবিক। এখন একটি ছোট কাজ বেছে নিন, একটু বিরতি নিন, এবং ধীরে শ্বাস নিন। চাপ দীর্ঘদিন থাকলে পেশাদার সাহায্য নিন। {doctor_text}'
        if any(term in lowered for term in ['sleep', 'insomnia', 'cannot sleep', 'cant sleep']) or any(term in message for term in SYMPTOM_KEYWORDS['sleep']['bn']):
            return f'ঘুম না হওয়া শরীর ও মনের জন্য খুব ক্লান্তিকর। আজ রাতে আলো কমিয়ে, স্ক্রিন থেকে বিরতি নিয়ে, ধীরে শ্বাস নেওয়ার চেষ্টা করুন। সমস্যা চলতে থাকলে ডাক্তারের সাথে কথা বলা ভালো। {doctor_text}'
        return f'আমি আপনার সাথে আছি। কী হয়েছে আরেকটু বলবেন? আমি সহানুভূতির সাথে সাহায্য করার চেষ্টা করব। {doctor_text}'

    if any(word in lowered for word in ['anxiety', 'panic', 'anxious']):
        return f"That sounds really uncomfortable. Try slowing your breathing for a moment: breathe in for 4 counts, then out for 6. If anxiety keeps interfering with daily life, a mental health professional can help you build a plan. {doctor_text}"
    if any(word in lowered for word in ['sad', 'depressed', 'hopeless']):
        return f"I'm sorry you're feeling this heaviness. You do not have to sort it out alone. Consider reaching out to someone you trust, and if this has been lasting or worsening, booking support with a therapist or doctor can help. {doctor_text}"
    if any(word in lowered for word in ['stress', 'overwhelmed', 'burnout']):
        return f"It makes sense to feel overloaded when too much is landing at once. Pick one small next step, pause anything non-urgent, and take a few slow breaths. Professional support can also help if stress is becoming hard to manage. {doctor_text}"
    if any(term in lowered for term in ['sleep', 'insomnia', 'cannot sleep', 'cant sleep', "can't sleep"]):
        return f"Not being able to sleep can make everything feel harder. Try keeping the room dark and cool, put screens away for a bit, and do a few slow breaths. If sleep problems continue, a doctor or therapist can help you find the cause. {doctor_text}"
    return f"I'm here with you. Tell me a little more about what's going on, and I'll do my best to support you. {doctor_text}"


def platform_context_fallback(message, contexts, language='en', doctors=None):
    lowered = message.lower()
    if any(word in lowered for word in ['book', 'appointment', 'schedule']):
        if language == 'bn':
            return 'অ্যাপয়েন্টমেন্ট বুক করতে Doctors পেজে যান, একজন উপলব্ধ মানসিক স্বাস্থ্য বিশেষজ্ঞ নির্বাচন করুন, প্রোফাইল দেখুন, তারপর বুকিং অপশন থেকে কনসালটেশন টাইপ ও সময় বেছে নিন।'
        return (
            'To book an appointment, open the Doctors page, choose an available mental health professional, '
            'view their profile, then use the booking option to select a consultation type and available time. '
            'You can manage upcoming appointments from the patient dashboard.'
        )
    if any(word in lowered for word in ['service', 'services', 'offer', 'offers']):
        if language == 'bn':
            return 'এই প্ল্যাটফর্মে পেশাদার কনসালটেশন, মানসিক স্বাস্থ্য অ্যাসেসমেন্ট, ডাক্তার খোঁজা, অ্যাপয়েন্টমেন্ট বুকিং, ওয়েলনেস ব্লগ, প্রেসক্রিপশন, দৈনিক স্বাস্থ্য টাস্ক এবং 999 জরুরি সাপোর্ট আছে।'
        return (
            'The platform supports mental wellness care through professional consultations, mental health assessments, '
            'doctor discovery, appointment booking, published wellness blogs, prescriptions, daily health tasks, '
            'and emergency guidance that directs immediate danger to Bangladesh emergency services at 999.'
        )
    if any(word in lowered for word in ['assessment', 'phq', 'gad', 'screening']):
        if language == 'bn':
            return 'প্ল্যাটফর্মে ডিপ্রেশন ও উদ্বেগ স্ক্রিনিংয়ের জন্য PHQ-9 এবং GAD-7 অ্যাসেসমেন্ট আছে। অ্যাসেসমেন্ট শেষে উপযুক্ত ডাক্তার রেকমেন্ডেশন পাওয়া যায়।'
        return (
            'The platform offers mental health assessments, including PHQ-9 and GAD-7 screening for depression and anxiety. '
            'After completing an assessment, the platform can show severity information and recommend suitable doctors.'
        )
    if any(word in lowered for word in ['hotline', 'emergency', 'crisis', 'center']):
        if language == 'bn':
            return 'জরুরি সহায়তার জন্য emergency পেজ ব্যবহার করুন এবং ২৪/৭ হটলাইন 999-এ কল করুন। তাৎক্ষণিক বিপদ হলে জরুরি সেবা বা নিকটস্থ ইমার্জেন্সি বিভাগে যান।'
        return (
            'For urgent support, use the emergency page and call Bangladesh emergency services at 999. '
            'If there is immediate danger or a medical emergency, contact local emergency services or go to the nearest emergency room.'
        )

    best = contexts[0]
    answer = best['content'].strip()
    if len(answer) > 700:
        answer = answer[:700].rsplit(' ', 1)[0] + '...'
    prefix = 'প্ল্যাটফর্ম তথ্য থেকে যা পেলাম: ' if language == 'bn' else 'Here is what I found in the platform information: '
    return f'{prefix}{answer} {doctor_recommendation_text(doctors or [], language)}'


def ollama_chat(system_prompt, user_prompt):
    global _chat_available, _next_chat_retry_at
    now = time.time()
    if not _chat_available and now < _next_chat_retry_at:
        return ''

    payload = {
        'model': OLLAMA_CHAT_MODEL,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'stream': False,
        'options': {'temperature': 0.3, 'num_predict': 350},
    }
    try:
        data = _post_ollama('/api/chat', payload, CHAT_TIMEOUT)
        _chat_available = True
        return data.get('message', {}).get('content', '').strip()
    except Exception as exc:
        _chat_available = False
        _next_chat_retry_at = now + RETRY_UNAVAILABLE_AFTER_SECONDS
        logger.warning('Ollama chat unavailable: %s', exc)
        return ''


def embed_text(text):
    global _embed_available, _next_embed_retry_at
    now = time.time()
    if not _embed_available and now < _next_embed_retry_at:
        return local_hash_embedding(text), 'local-hash-embedding'

    try:
        data = _post_ollama('/api/embeddings', {'model': OLLAMA_EMBED_MODEL, 'prompt': text}, EMBED_TIMEOUT)
        embedding = data.get('embedding') or []
        if embedding:
            _embed_available = True
            return normalize_vector(embedding), OLLAMA_EMBED_MODEL
    except Exception as exc:
        _embed_available = False
        _next_embed_retry_at = now + RETRY_UNAVAILABLE_AFTER_SECONDS
        logger.warning('Ollama embeddings unavailable; using local lexical embedding: %s', exc)
    return local_hash_embedding(text), 'local-hash-embedding'


def _post_ollama(path, payload, timeout):
    url = f"{OLLAMA_BASE_URL.rstrip('/')}{path}"
    body = json.dumps(payload).encode('utf-8')
    req = request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def get_or_create_chat_session(session_id=None, user=None, django_session_key='', language='en'):
    session = None
    if session_id:
        try:
            session = ChatSession.objects.filter(pk=session_id).first()
        except (ValueError, TypeError):
            session = None

    if session is None:
        session = ChatSession.objects.create(
            user=user if getattr(user, 'is_authenticated', False) else None,
            session_key=django_session_key or '',
            language=language,
        )
    else:
        changed_fields = []
        if language and session.language != language:
            session.language = language
            changed_fields.append('language')
        if getattr(user, 'is_authenticated', False) and session.user_id != user.pk:
            session.user = user
            changed_fields.append('user')
        if django_session_key and session.session_key != django_session_key:
            session.session_key = django_session_key
            changed_fields.append('session_key')
        if changed_fields:
            session.save(update_fields=changed_fields + ['last_activity_at'])

    return session


def update_session_title(chat_session, message, language):
    if chat_session.title:
        return
    title = message[:80].strip()
    chat_session.title = title or ('নতুন চ্যাট' if language == 'bn' else 'New chat')
    chat_session.save(update_fields=['title', 'language', 'last_activity_at'])


def get_recent_history(chat_session, limit=MAX_HISTORY_MESSAGES):
    messages = list(chat_session.messages.order_by('-created_at')[:limit])
    return list(reversed(messages))


def format_history(messages):
    if not messages:
        return "No previous messages."
    lines = []
    for message in messages[-MAX_HISTORY_MESSAGES:]:
        content = re.sub(r'\s+', ' ', message.content).strip()
        lines.append(f"{message.role}: {content[:450]}")
    return '\n'.join(lines)


def detect_language(text):
    bangla_chars = len(re.findall(r'[\u0980-\u09FF]', text or ''))
    return 'bn' if bangla_chars >= 2 else 'en'


def translate_static(text, language):
    if language == 'bn':
        translations = {
            "I'm here with you. What would you like to talk about?": "আমি আপনার সাথে আছি। আপনি কী নিয়ে কথা বলতে চান?",
        }
        return translations.get(text, text)
    return text


def extract_symptoms_from_history(history_or_text):
    if isinstance(history_or_text, str):
        text = history_or_text
    else:
        text = ' '.join(message.content for message in history_or_text if message.role == 'user')
    lowered = text.lower()
    symptoms = set()
    for symptom, config in SYMPTOM_KEYWORDS.items():
        if any(term in lowered for term in config['en']) or any(term in text for term in config['bn']):
            symptoms.add(symptom)
    return sorted(symptoms)


def recommend_doctors_for_symptoms(symptoms, crisis=False, limit=3):
    if not symptoms and not crisis:
        return []

    doctors = Doctor.objects.filter(is_available=True).select_related('user').prefetch_related('specializations', 'primary_focuses')
    scored = []
    desired_terms = set()
    for symptom in symptoms:
        desired_terms.update(SYMPTOM_KEYWORDS.get(symptom, {}).get('doctor_terms', []))
    if crisis:
        desired_terms.update(['psychiatrist', 'emergency', 'crisis'])

    for doctor in doctors:
        searchable = ' '.join([
            doctor.name or '',
            doctor.specialty or '',
            doctor.primary_focus or '',
            doctor.qualification or '',
            doctor.bio or '',
            ' '.join(doctor.expertise_tags or []),
        ]).lower()
        score = 0
        matched_terms = []
        for term in desired_terms:
            if term and term.lower() in searchable:
                score += 4
                matched_terms.append(term)
        for symptom in symptoms:
            if symptom in searchable:
                score += 3
                matched_terms.append(symptom)
        if crisis and doctor.emergency_support:
            score += 8
            matched_terms.append('emergency support')
        if doctor.available_online:
            score += 1
        score += min(doctor.years_of_experience, 20) / 10
        score += min(doctor.availability_score, 5) / 2

        if score > 0:
            scored.append((score, doctor, sorted(set(matched_terms))))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            'id': doctor.pk,
            'name': doctor.name or doctor.user.get_full_name() or doctor.user.username,
            'specializations': doctor.specialization_labels,
            'primary_focuses': doctor.primary_focus_labels,
            'experience_years': doctor.years_of_experience,
            'available_online': doctor.available_online,
            'emergency_support': doctor.emergency_support,
            'consultation_fee': str(doctor.consultation_fee) if doctor.consultation_fee is not None else '',
            'profile_url': reverse('doctor_details', kwargs={'doctor_id': doctor.pk}),
            'score': round(score, 2),
            'matched_terms': matched_terms,
        }
        for score, doctor, matched_terms in scored[:limit]
    ]


def serialize_doctors(doctors):
    return doctors or []


def doctor_recommendation_text(doctors, language='en', emergency=False):
    if not doctors:
        return ''
    if language == 'bn':
        intro = 'জরুরি সহায়তার জন্য উপযুক্ত ডাক্তার: ' if emergency else 'আপনার কথার ভিত্তিতে উপযুক্ত ডাক্তার: '
        names = '; '.join(
            f"{doctor['name']} ({', '.join(doctor['specializations'] or doctor['primary_focuses'] or ['Mental Health'])})"
            for doctor in doctors[:3]
        )
        return f"{intro}{names}."
    intro = 'Emergency doctor options: ' if emergency else 'Relevant doctor options: '
    names = '; '.join(
        f"{doctor['name']} ({', '.join(doctor['specializations'] or doctor['primary_focuses'] or ['Mental Health'])})"
        for doctor in doctors[:3]
    )
    return f"{intro}{names}."


def get_chat_history(session_id, user=None, limit=50):
    session = ChatSession.objects.filter(pk=session_id).first()
    if not session:
        return None
    if session.user_id and getattr(user, 'is_authenticated', False) and session.user_id != user.pk:
        return None
    messages = session.messages.order_by('-created_at')[:limit]
    return {
        'session_id': str(session.id),
        'language': session.language,
        'messages': [
            {
                'role': message.role,
                'content': message.content,
                'category': message.category,
                'metadata': message.metadata,
                'created_at': message.created_at.isoformat(),
            }
            for message in reversed(list(messages))
        ],
    }


def detect_emergency_payload(message):
    language = detect_language(message)
    is_crisis = is_crisis_query(message)
    return {
        'is_emergency': is_crisis,
        'risk_level': 'critical' if is_crisis else 'low',
        'language': language,
        'detected_terms': detect_crisis_terms(message) if is_crisis else [],
        'message': crisis_response(language) if is_crisis else translate_static("I'm here with you. What would you like to talk about?", language),
    }


def ensure_knowledge_base_synced(force=False):
    global _last_sync_at
    now = time.time()
    if not force and ChatbotKnowledgeChunk.objects.exists() and now - _last_sync_at < SYNC_INTERVAL_SECONDS:
        return
    sync_knowledge_base()
    _last_sync_at = now


@transaction.atomic
def sync_knowledge_base(source_filter=None):
    docs = collect_platform_documents()
    seen_keys = set()

    for doc in docs:
        if source_filter and doc['source_type'] not in source_filter:
            continue
        chunks = chunk_text(doc['content'])
        for index, chunk in enumerate(chunks):
            seen_keys.add((doc['source_type'], doc['source_id'], index))
            embedding_input = f"{doc['title']}\n{chunk}"
            content_hash = hashlib.sha256(embedding_input.encode('utf-8')).hexdigest()
            existing = ChatbotKnowledgeChunk.objects.filter(
                source_type=doc['source_type'],
                source_id=doc['source_id'],
                chunk_index=index,
            ).first()
            if (
                existing
                and existing.content_hash == content_hash
                and existing.embedding_model == OLLAMA_EMBED_MODEL
            ):
                continue
            embedding, embedding_model = embed_text(embedding_input)
            ChatbotKnowledgeChunk.objects.update_or_create(
                source_type=doc['source_type'],
                source_id=doc['source_id'],
                chunk_index=index,
                defaults={
                    'title': doc['title'][:255],
                    'url': doc.get('url', '')[:500],
                    'content': chunk,
                    'content_hash': content_hash,
                    'embedding': embedding,
                    'embedding_model': embedding_model,
                },
            )

    if not source_filter:
        for chunk in ChatbotKnowledgeChunk.objects.all():
            key = (chunk.source_type, chunk.source_id, chunk.chunk_index)
            if key not in seen_keys:
                chunk.delete()


def collect_platform_documents():
    docs = [
        {
            'source_type': 'platform_static',
            'source_id': 'emergency_resources',
            'title': 'Emergency Support Resources',
            'url': '/emergency/',
            'content': (
                "Emergency Mental Health Support. AI Emergency Support is available on the emergency page. "
                "Bangladesh emergency services are available at 999. Crisis steps include stop, stay safe, think again, talk to someone, take care of your body, get help, and make a plan. "
                "Users can call the helpline, find a therapist, visit centers, and use the 3-3-3 breathing exercise."
            ),
        },
        {
            'source_type': 'platform_static',
            'source_id': 'appointments',
            'title': 'Appointments and Doctors',
            'url': '/patient/doctors/',
            'content': (
                "Patients can browse doctors, view doctor profiles, book appointments, choose consultation types, and manage appointments from the patient dashboard. "
                "Doctors have specializations, primary focus areas, schedules, consultation fees, online availability, and emergency support status."
            ),
        },
        {
            'source_type': 'platform_static',
            'source_id': 'assessments',
            'title': 'Mental Health Assessments',
            'url': '/patient/clinical-assessment/',
            'content': (
                "The platform includes PHQ-9 and GAD-7 clinical assessments for depression and anxiety screening. "
                "Assessment results can recommend doctors and identify emergency risk when responses indicate possible self-harm."
            ),
        },
    ]
    docs.extend(collect_template_documents())
    docs.extend(collect_database_documents())
    return [doc for doc in docs if doc.get('content', '').strip()]


def collect_template_documents():
    template_dir = Path(settings.BASE_DIR) / 'home' / 'templates' / 'home'
    docs = []
    for template_path in template_dir.glob('*.html'):
        raw = template_path.read_text(encoding='utf-8', errors='ignore')
        text = extract_template_text(raw)
        if not text:
            continue
        source_id = f"{template_path.stem}:{int(template_path.stat().st_mtime)}"
        docs.append({
            'source_type': 'template_page',
            'source_id': source_id,
            'title': f"{template_path.stem.replace('_', ' ').title()} Page",
            'url': f"/{'' if template_path.stem == 'homepage' else template_path.stem + '/'}",
            'content': text,
        })
    return docs


def collect_database_documents():
    docs = []

    for blog in BlogPost.objects.filter(status='published').select_related('author__user'):
        docs.append({
            'source_type': 'blog_post',
            'source_id': str(blog.pk),
            'title': blog.title,
            'url': reverse('blog_detail', kwargs={'slug': blog.slug}),
            'content': f"{blog.title}\n{blog.excerpt}\n{blog.content}\nCategory: {blog.get_category_display()}",
        })

    doctors = Doctor.objects.select_related('user').prefetch_related('specializations', 'primary_focuses')
    for doctor in doctors:
        schedule = []
        for item in DoctorSchedule.objects.filter(doctor=doctor, is_available=True):
            schedule.append(f"{item.get_day_of_week_display()} {item.start_time}-{item.end_time}")
        docs.append({
            'source_type': 'doctor_profile',
            'source_id': str(doctor.pk),
            'title': f"Doctor Profile: {doctor.name or doctor.user.get_full_name()}",
            'url': reverse('doctor_details', kwargs={'doctor_id': doctor.pk}),
            'content': (
                f"Doctor name: {doctor.name or doctor.user.get_full_name()}. "
                f"Specializations: {doctor.specialty}. Primary focus: {doctor.primary_focus}. "
                f"Qualification: {doctor.qualification}. Experience: {doctor.years_of_experience} years. "
                f"Bio: {doctor.bio}. Clinic: {doctor.clinic_name or ''} {doctor.clinic_address or ''}. "
                f"Available online: {doctor.available_online}. Emergency support: {doctor.emergency_support}. "
                f"Consultation fee: {doctor.consultation_fee or 'not listed'}. Schedule: {', '.join(schedule) or 'not listed'}."
            ),
        })

    for template in HealthTaskTemplate.objects.filter(is_active=True):
        docs.append({
            'source_type': 'health_task_template',
            'source_id': str(template.pk),
            'title': f"Health Task: {template.title}",
            'url': '/patient/dashboard/',
            'content': f"{template.title}. Category: {template.get_category_display()}. {template.description}",
        })

    for question in AssessmentQuestion.objects.all():
        docs.append({
            'source_type': 'assessment_question',
            'source_id': str(question.pk),
            'title': f"Assessment Question: {question.category}",
            'url': '/patient/assessment/',
            'content': f"Assessment question category {question.category}: {question.question_text}",
        })

    for specialization in DoctorSpecialization.objects.filter(is_active=True):
        docs.append({
            'source_type': 'doctor_specialization',
            'source_id': str(specialization.pk),
            'title': f"Doctor Specialization: {specialization.label}",
            'url': '/patient/doctors/',
            'content': f"Doctor specialization option: {specialization.label} ({specialization.value}).",
        })

    for focus in DoctorPrimaryFocus.objects.filter(is_active=True):
        docs.append({
            'source_type': 'doctor_primary_focus',
            'source_id': str(focus.pk),
            'title': f"Doctor Primary Focus: {focus.label}",
            'url': '/patient/doctors/',
            'content': f"Doctor primary focus option: {focus.label} ({focus.value}).",
        })

    return docs


def extract_template_text(raw):
    cleaned = re.sub(r'<script[\s\S]*?</script>', ' ', raw, flags=re.IGNORECASE)
    cleaned = re.sub(r'<style[\s\S]*?</style>', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'{%[\s\S]*?%}|{{[\s\S]*?}}|{#[\s\S]*?#}', ' ', cleaned)
    cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()


def chunk_text(text, max_chars=1000, overlap=120):
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = text.rfind('. ', start, end)
            if boundary > start + 300:
                end = boundary + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def local_hash_embedding(text, dimensions=LOCAL_EMBED_DIM):
    vector = [0.0] * dimensions
    tokens = re.findall(r'[a-z0-9]{2,}', text.lower())
    for token in tokens:
        digest = hashlib.md5(token.encode('utf-8')).digest()
        index = int.from_bytes(digest[:4], 'big') % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    return normalize_vector(vector)


def normalize_vector(vector):
    values = [float(value) for value in vector]
    norm = math.sqrt(sum(value * value for value in values))
    if not norm:
        return values
    return [value / norm for value in values]


def cosine_similarity(left, right):
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    return sum(float(left[index]) * float(right[index]) for index in range(size))


def tokenize(text):
    return [
        token
        for token in re.findall(r'[a-z0-9]{2,}', text.lower())
        if token not in STOPWORDS
    ]


def lexical_similarity(query_tokens, text):
    if not query_tokens:
        return 0.0
    doc_tokens = set(tokenize(text))
    if not doc_tokens:
        return 0.0
    overlap = len(query_tokens & doc_tokens)
    return overlap / math.sqrt(len(query_tokens) * len(doc_tokens))


def _source_payload(context):
    return {
        'title': context.get('title', ''),
        'url': context.get('url', ''),
        'score': context.get('score', 0),
    }


def schedule_knowledge_sync():
    try:
        sync_knowledge_base()
    except (error.URLError, TimeoutError, OSError):
        logger.warning('Knowledge sync could not contact Ollama; local embeddings will be used on next sync.')
        sync_knowledge_base()
    except Exception:
        logger.exception('Knowledge sync failed.')

