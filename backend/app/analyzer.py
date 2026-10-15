import re


# Suspicious words for the basic demo
SUSPICIOUS_KEYWORDS = {
    "fake",
    "hoax",
    "scam",
    "shocking",
    "fraud",
    "secret",
    "exposed",
    "urgent",
    "banned",
    "conspiracy",
}


# Common clickbait phrases
CLICKBAIT_PHRASES = [
    "you won't believe",
    "you will not believe",
    "shocking truth",
    "what happens next",
    "must see",
    "click here",
    "you need to know",
]


def analyze_text(text):

    score = 0
    indicators = []

    # Convert text to lowercase for matching
    lowercase_text = text.lower()

    # -----------------------------------------
    # 1. Suspicious keyword detection
    # -----------------------------------------

    words = re.findall(r"\b[a-zA-Z]+\b", lowercase_text)

    detected_keywords = []

    for word in words:
        if word in SUSPICIOUS_KEYWORDS:
            if word not in detected_keywords:
                detected_keywords.append(word)

    if detected_keywords:
        points = min(len(detected_keywords) * 10, 30)
        score += points

        indicators.append(
            f"Suspicious keywords detected: {', '.join(detected_keywords)}"
        )

    # -----------------------------------------
    # 2. Clickbait phrase detection
    # -----------------------------------------

    detected_phrases = []

    for phrase in CLICKBAIT_PHRASES:
        if phrase in lowercase_text:
            detected_phrases.append(phrase)

    if detected_phrases:
        points = min(len(detected_phrases) * 15, 30)
        score += points

        indicators.append(
            f"Clickbait phrases detected: {', '.join(detected_phrases)}"
        )

    # -----------------------------------------
    # 3. Excessive capitalization
    # -----------------------------------------

    letters = [character for character in text if character.isalpha()]
    uppercase_letters = [
        character for character in letters if character.isupper()
    ]

    if letters:
        uppercase_ratio = len(uppercase_letters) / len(letters)

        if uppercase_ratio > 0.50:
            score += 10

            indicators.append(
                "Excessive capitalization detected."
            )

    # -----------------------------------------
    # 4. Excessive punctuation
    # -----------------------------------------

    exclamation_count = text.count("!")
    question_count = text.count("?")

    if exclamation_count >= 3:
        score += 10

        indicators.append(
            "Excessive exclamation marks detected."
        )

    if question_count >= 3:
        score += 5

        indicators.append(
            "Excessive question marks detected."
        )

    # -----------------------------------------
    # Keep score between 0 and 100
    # -----------------------------------------

    score = min(score, 100)

    # -----------------------------------------
    # Classification
    # -----------------------------------------

    if score <= 30:
        classification = "Credible"
    elif score <= 60:
        classification = "Suspicious"
    else:
        classification = "Likely Fake"

    # -----------------------------------------
    # No indicators
    # -----------------------------------------

    if not indicators:
        indicators.append(
            "No major suspicious indicators detected."
        )

    return {
        "score": score,
        "classification": classification,
        "indicators": indicators,
        "word_count": len(words),
    }