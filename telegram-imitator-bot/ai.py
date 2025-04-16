import json
import aiohttp
import logging
import random
from typing import Dict, Any, List
from collections import Counter
from style_analysis import analyze_style, adjust_punctuation
from html_parser import load_style_from_html 

logger = logging.getLogger(__name__)

from config import OPENROUTER_API_KEY

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

class StyleAdapter:
    def __init__(self, style_data: Dict[str, Any]):
        self.style_data = style_data

    def make_coherent(self, reply: str, context: List[str]) -> str:
        reply_lower = reply.lower()

        if any(phrase in reply_lower for phrase in ["повторюсь", "как я уже говорил"]):
            return random.choice(["Давай по-другому.", "Уточни вопрос."])
        if len(reply.strip()) < 3:
            return random.choice(["Не понял вопрос.", "Можешь уточнить?"])
        if "?" in reply and not any(c in reply for c in [" ", ".", ","]) and len(reply) < 10:
            return random.choice(["Не совсем понял.", "О чем ты?"])
        return reply

async def generate_response(
    user_id: int,
    target: str,
    prompt: str,
    user_states: Dict[int, Dict[str, Any]],
    chat_memory: Dict[int, Dict[str, List[Dict[str, str]]]]
) -> str:
    try:
        state = user_states.get(user_id, {})
        style_samples = state.get("style_samples", [])

        style_data = state.get("style_data", {})
        if not style_data and len(style_samples) >= 5:
            style_data = {
                "keywords": [word for word, _ in Counter([
                    w.lower() for msg in style_samples 
                    for w in msg.split() if len(w) > 3
                ]).most_common(5)],
                "avg_len": sum(len(m) for m in style_samples) // len(style_samples)
            }

        system_prompt = f"""Ты точно имитируешь {target}. Правила:
1. Отвечай КОРОТКО ({style_data.get('avg_len', 50)} символов максимум)
2. Используй характерные слова: {', '.join(style_data.get('keywords', []))[:50]}
3. Избегай общих фраз ("Что ты хотел?", "Повторяю")
4. Если не понял вопрос — скажи "Че?" или "Не понял" 
5. Никогда не повторяй фразы дословно из примеров

Примеры стиля:
{random.sample(style_samples, min(2, len(style_samples))) if style_samples else "Нет данных"}

Текущий диалог:
{chat_memory.get(user_id, {}).get("history", [])[-2:]}

Задача: ответь на "{prompt}" как {target}. Только 1 предложение!"""

        async with aiohttp.ClientSession() as session:
            response = await session.post(
                OPENROUTER_API_URL,
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={
                    "model": "anthropic/claude-3-haiku",
                    "messages": [{"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 100,
                    "stop_sequences": ["\n"]
                }
            )

            reply = (await response.json())["choices"][0]["message"]["content"]

            adapter = StyleAdapter(style_data)
            reply = adapter.make_coherent(reply, chat_memory.get(user_id, {}).get("history", []))
            reply = adjust_punctuation(reply[:150])

            return reply if reply.strip() else "🤷‍♂️"

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return random.choice(["Че?", "Ошибка", "..."])

def update_style_data(user_id: int, new_message: str, user_states: Dict):
    if user_id not in user_states:
        user_states[user_id] = {"style_samples": [], "style_data": {}}

    user_states[user_id]["style_samples"].append(new_message)
    if len(user_states[user_id]["style_samples"]) % 10 == 0:
        user_states[user_id]["style_data"] = analyze_style(user_states[user_id]["style_samples"])

def init_user_style(user_id: int, html_path: str, target: str, user_states: Dict):
    style_samples = load_style_from_html(html_path, target)
    user_states[user_id] = {
        "style_samples": style_samples,
        "style_data": analyze_style(style_samples)
    }
