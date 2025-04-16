from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List

def get_main_kb() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Имитировать", callback_data="imitate_other")],
        [InlineKeyboardButton(text="👤 Управление профилями", callback_data="manage_profiles")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="🧹 Очистить все данные", callback_data="clear_data")]
    ])
    return keyboard

def get_targets_kb(participants: List[str]) -> InlineKeyboardMarkup:
    buttons = []
    valid_participants = [str(p) for p in participants if p and isinstance(p, str)]

    if valid_participants:
        max_name_len = 30
        for name in valid_participants:
            display_name = name if len(name) <= max_name_len else name[:max_name_len-3] + "..."
            buttons.append([InlineKeyboardButton(text=display_name, callback_data=f"target_{name}")])
    else:
        buttons.append([InlineKeyboardButton(text="Нет участников для выбора", callback_data="no_targets_uploaded")])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_exit_kb() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚪 Выйти из режима имитации", callback_data="exit_imitation")]
    ])
    return keyboard

def get_back_to_main_kb() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])
    return keyboard
