from __future__ import annotations

SUPPORTED_ASSESSMENT_LANGUAGES = ("en", "bn")

ASSESSMENT_LANGUAGE_LABELS = {
    "en": "English",
    "bn": "বাংলা",
}

ANSWER_LABELS = {
    "en": ["Never", "Rarely", "Sometimes", "Often", "Always"],
    "bn": ["কখনো না", "খুব কম", "মাঝে মাঝে", "প্রায়ই", "সবসময়"],
}

GENERAL_QUESTION_TRANSLATIONS = {
    1: "Over the past two weeks, how often have you felt down, depressed, or hopeless?",
    2: "Over the past two weeks, how often have you had little interest or pleasure in doing things?",
    3: "Over the past two weeks, how often have you felt nervous, anxious, or on edge?",
    4: "Over the past two weeks, how often have you been unable to stop or control worrying?",
    5: "Over the past two weeks, how often have you had trouble falling or staying asleep, or sleeping too much?",
    6: "Over the past two weeks, how often have you felt tired or had little energy?",
    7: "Over the past two weeks, how often have you felt that you are a failure or have let yourself or your family down?",
}

GENERAL_QUESTION_TRANSLATIONS_BN = {
    1: "গত দুই সপ্তাহে, কতবার আপনি মন খারাপ, বিষণ্ণতা বা হতাশা অনুভব করেছেন?",
    2: "গত দুই সপ্তাহে, কতবার আপনি কাজকর্মে আগ্রহ বা আনন্দ কম অনুভব করেছেন?",
    3: "গত দুই সপ্তাহে, কতবার আপনি নার্ভাস, উদ্বিগ্ন বা অস্থির অনুভব করেছেন?",
    4: "গত দুই সপ্তাহে, কতবার আপনার দুশ্চিন্তা বন্ধ বা নিয়ন্ত্রণ করতে কষ্ট হয়েছে?",
    5: "গত দুই সপ্তাহে, কতবার আপনার ঘুমাতে সমস্যা, ঘুম ধরে রাখতে সমস্যা, অথবা অতিরিক্ত ঘুম হয়েছে?",
    6: "গত দুই সপ্তাহে, কতবার আপনি ক্লান্ত বা শক্তিহীন অনুভব করেছেন?",
    7: "গত দুই সপ্তাহে, কতবার আপনি নিজেকে ব্যর্থ মনে করেছেন বা ভেবেছেন যে আপনি নিজের বা পরিবারের মানুষদের হতাশ করেছেন?",
}

STANDARD_OPTION_CHOICES = [
    {"option_order": 1, "option_text": "Never", "score": 0},
    {"option_order": 2, "option_text": "Rarely", "score": 1},
    {"option_order": 3, "option_text": "Sometimes", "score": 2},
    {"option_order": 4, "option_text": "Often", "score": 3},
    {"option_order": 5, "option_text": "Always", "score": 4},
]

STANDARD_OPTION_CHOICES_BN = [
    {"option_order": 1, "option_text": "কখনো না", "score": 0},
    {"option_order": 2, "option_text": "খুব কম", "score": 1},
    {"option_order": 3, "option_text": "মাঝে মাঝে", "score": 2},
    {"option_order": 4, "option_text": "প্রায়ই", "score": 3},
    {"option_order": 5, "option_text": "সবসময়", "score": 4},
]


def normalize_assessment_lang(raw_lang):
    lang = (raw_lang or "").strip().lower()
    return lang if lang in SUPPORTED_ASSESSMENT_LANGUAGES else "en"


def localized_answer_labels(lang):
    return ANSWER_LABELS.get(normalize_assessment_lang(lang), ANSWER_LABELS["en"])


def get_general_question_text(track_number, lang="en"):
    lang = normalize_assessment_lang(lang)
    if lang == "bn":
        return GENERAL_QUESTION_TRANSLATIONS_BN.get(track_number) or GENERAL_QUESTION_TRANSLATIONS.get(track_number, "")
    return GENERAL_QUESTION_TRANSLATIONS.get(track_number, "")

