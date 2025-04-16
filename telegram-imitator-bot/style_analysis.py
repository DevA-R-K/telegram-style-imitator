from typing import List, Dict, Any
from collections import Counter
import random

def analyze_style(messages: List[str]) -> Dict[str, Any]:
    style_data = {
        'common_words': [],
        'common_phrases': [],
        'message_lengths': [],
        'punctuation': {},
        'emojis': [],
    }

    for msg in messages:
        if len(msg.split()) < 3:
            continue  # отбрасываем короткие фразы

        style_data['message_lengths'].append(len(msg))

        for char in msg:
            if char in '!?.,;:':
                style_data['punctuation'][char] = style_data['punctuation'].get(char, 0) + 1

        if any(c in msg for c in ['😀', '😂', '😊', '😎', '😢', '😡', '😉', '❤']):
            style_data['emojis'].append(msg)

        words = msg.split()
        style_data['common_words'].extend(words)

        if len(words) >= 2:
            for i in range(len(words)-1):
                phrase = ' '.join(words[i:i+2])
                style_data['common_phrases'].append(phrase)

    # фильтрация слов
    stop_words = set([
        "я", "ты", "он", "она", "мы", "вы", "они", "и", "в", "на", "а", "но", "что", "как", "не", "да", "ну"
    ])

    word_counts = Counter(style_data['common_words'])
    phrase_counts = Counter(style_data['common_phrases'])

    filtered_keywords = [word for word, _ in word_counts.most_common(50) if word.lower() not in stop_words and len(word) > 3]
    filtered_phrases = [phrase for phrase, _ in phrase_counts.most_common(10)]

    avg_len = sum(style_data['message_lengths']) // len(style_data['message_lengths']) if style_data['message_lengths'] else 50

    return {
        'keywords': filtered_keywords[:5],
        'avg_len': avg_len,
        'common_phrases': filtered_phrases,
        'emojis': style_data['emojis']
    }

def inject_error(text, error_rate=0.1):
    words = text.split()
    errored_words = []
    for word in words:
        if random.random() < error_rate and len(word) > 2:
            index_to_replace = random.randint(0, len(word) - 1)
            random_char = chr(random.randint(ord('а'), ord('я')))
            word_list = list(word)
            word_list[index_to_replace] = random_char
            errored_words.append("".join(word_list))
        else:
            errored_words.append(word)
    return " ".join(errored_words)

def adjust_punctuation(text, removal_prob=0.02, replace_prob=0.01):
    punctuations = ['.', ',', '!', '?']
    new_text = ""
    for char in text:
        if char in punctuations:
            if random.random() < removal_prob:
                continue
            elif random.random() < replace_prob:
                new_text += random.choice(punctuations)
            else:
                new_text += char
        else:
            new_text += char
    return new_text