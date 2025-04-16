from bs4 import BeautifulSoup
import html
import logging
from typing import Tuple, List

logger = logging.getLogger(__name__)

def parse_html(file_path: str) -> Tuple[List[str], List[Tuple[str, str]]]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')

        header = soup.find('div', class_='page_header')
        your_name = header.find('div', class_='text').text.strip() if header else None

        participants = set()
        your_messages = []
        all_messages = []

        for msg in soup.find_all(class_='message'):
            if 'service' in msg.get('class', []):
                continue

            sender = msg.find(class_='from_name')
            sender_name = sender.text.strip() if sender else "Unknown"

            text = msg.find(class_='text')
            if not text:
                continue

            clean_text = html.unescape(text.get_text().strip())
            if not clean_text:
                continue

            if sender_name != "Unknown":
                participants.add(sender_name)
                all_messages.append((sender_name, clean_text))

            if sender_name == your_name:
                your_messages.append(clean_text)

        return your_messages, all_messages
    except Exception as e:
        logger.error(f"Ошибка парсинга HTML: {e}")
        return [], []

def load_style_from_html(html_path: str, target_name: str) -> List[str]:
    _, all_messages = parse_html(html_path)
    return [
        text for author, text in all_messages
        if author == target_name and len(text.split()) >= 3
    ]