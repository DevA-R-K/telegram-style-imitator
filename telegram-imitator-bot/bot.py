# bot.py

import logging
import os
import asyncio
from typing import Dict, Any, List, Tuple, Optional
import io
import string
from collections import Counter
import json

from aiogram import Bot, Dispatcher, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, User
from aiogram.enums import ParseMode

from keyboards import get_main_kb, get_targets_kb, get_exit_kb, get_back_to_main_kb
from database import (
    init_db, save_messages, get_messages, clear_data,
    get_style_data_from_db, get_stats_data, sqlite3 as db_sqlite3
)
from html_parser import parse_html
from style_analysis import analyze_style
from ai import generate_response
import profile_management


from config import BOT_TOKEN

#7317483522:AAFqozM8ClB9zPGv50ettX2YBRMyt9RZ1Sw"
MIN_SAMPLES_FOR_STYLE_ANALYSIS = 3
MIN_SAMPLES_FOR_IMITATION = 5


bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


user_states: Dict[int, Dict[str, Any]] = {}
chat_memory: Dict[int, Dict[str, List[Dict[str, str]]]] = {}


try:
    conn, cursor = init_db()
    logger.info("База данных успешно инициализирована.")
except db_sqlite3.Error as e:
    logger.critical(f"Критическая ошибка инициализации базы данных: {e}", exc_info=True)
    exit(1)


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 Привет! Я могу имитировать стиль общения.\n"
        "Загрузи экспорт чата или перейди к управлению профилями:",
        reply_markup=get_main_kb()
    )

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Нажата кнопка 'Назад' (callback_data='back') user_id {user_id}")
    try:
        await callback.message.edit_text(
            "Главное меню:",
            reply_markup=get_main_kb()
        )
    except TelegramBadRequest as e:
        if "message to edit not found" in str(e) or "query is too old" in str(e) or "there is no text in the message to edit" in str(e):
            logger.warning(f"Не удалось отредактировать сообщение в 'back' (user_id {user_id}): {e}. Отправляю новое.")
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(
                text="Главное меню:",
                reply_markup=get_main_kb()
            )
        else:
            logger.error(f"Неожиданная ошибка TelegramBadRequest в 'back' (user_id {user_id}): {e}", exc_info=True)
            await callback.answer("Произошла ошибка при возврате.", show_alert=True)
    finally:
        await callback.answer()


@dp.callback_query(F.data == "imitate_other")
async def imitate_other(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Что вы хотите сделать?\n"
               "📁 - Загрузить новый чат для добавления/обновления профилей.\n"
               "👤 - Выбрать или удалить уже сохраненный профиль для имитации.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📁 Загрузить новый чат", callback_data="upload_other")],
            [InlineKeyboardButton(text="👤 Управление профилями", callback_data="manage_profiles")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "upload_other")
async def upload_other(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📤 Отправьте экспорт чата в HTML формате.\n"
        "Найденные профили (ваш и других участников) будут сохранены или обновлены.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="imitate_other")
        ]])
    )
    await callback.answer()


@dp.message(F.document)
async def handle_document(message: Message):
    user: User = message.from_user
    user_id = user.id
    logger.info(f"Получен документ от user_id {user_id} (@{user.username or 'no_username'}).")

    max_file_size = 20 * 1024 * 1024
    if not message.document:
        logger.warning(f"Сообщение от user_id {user_id} не содержит документа.")
        return
    if message.document.file_size is None or message.document.file_size > max_file_size:
        await message.reply(f"❌ Размер файла превышает лимит в 20MB или неизвестен.")
        logger.warning(f"Файл от user_id {user_id} слишком большой или размер неизвестен: {message.document.file_size}")
        return
    if not message.document.file_name or not message.document.file_name.lower().endswith('.html'):
        await message.reply("❌ Пожалуйста, отправьте HTML-экспорт из Telegram.")
        logger.warning(f"Некорректный тип файла от user_id {user_id}: {message.document.file_name or 'No filename'}")
        return

    processing_message = await message.reply("⏳ Обрабатываю файл...")

    file_path = f"user_data/export_{user_id}_{message.document.file_unique_id}.html"
    try:
        os.makedirs("user_data", exist_ok=True)
        file_info = await bot.get_file(message.document.file_id)
        await bot.download_file(file_info.file_path, file_path)
        logger.info(f"Файл сохранен как {file_path}.")

        your_parsed_messages, other_participants_messages = parse_html(file_path)
        logger.info(f"Парсинг завершен. Найдено сообщений владельца: {len(your_parsed_messages)}, других: {len(other_participants_messages)}.")

        your_name = user.first_name
        if user.last_name:
            your_name += f" {user.last_name}"
        if not your_name.strip() and user.username:
             your_name = user.username
        if not your_name.strip():
            your_name = f"User_{user_id}"
        logger.info(f"Определено имя владельца (из TG): '{your_name}' для user_id {user_id}.")

        if not other_participants_messages and not your_parsed_messages:
            await processing_message.edit_text("❌ В файле не найдено сообщений или возникла ошибка при обработке.")
            logger.warning(f"В файле {file_path} не найдено сообщений.")
            return

        style_data_me = None
        if your_parsed_messages:
            if len(your_parsed_messages) >= MIN_SAMPLES_FOR_STYLE_ANALYSIS:
                try:
                    style_data_me = analyze_style(your_parsed_messages)
                    logger.info(f"Стиль для '{your_name}' (user_id {user_id}) проанализирован.")
                except Exception as e:
                    logger.error(f"Ошибка анализа стиля для '{your_name}' (user_id {user_id}): {e}", exc_info=True)
                    await message.answer(f"⚠️ Не удалось проанализировать ваш стиль ('{your_name}'), сообщения будут сохранены без стиля.")
            else:
                logger.info(f"Недостаточно сообщений ({len(your_parsed_messages)}) для анализа вашего стиля ('{your_name}'), сохраняю без стиля.")

            save_messages(user_id, your_name, your_parsed_messages, style_data_me)
            logger.info(f"Сохранено {len(your_parsed_messages)} сообщений для target '{your_name}' (user_id {user_id}).")

        participants_to_choose = sorted(list({name for name, _ in other_participants_messages if name != "Unknown" and name}))
        saved_count_others = 0
        processed_others = 0
        for target_other in participants_to_choose:
             messages_other = [text for name, text in other_participants_messages if name == target_other]
             processed_others += 1
             if messages_other:
                  style_data_other = None
                  if len(messages_other) >= MIN_SAMPLES_FOR_STYLE_ANALYSIS:
                      try:
                          style_data_other = analyze_style(messages_other)
                          logger.info(f"Стиль для '{target_other}' (user_id {user_id}) проанализирован.")
                      except Exception as e:
                          logger.error(f"Ошибка анализа стиля для '{target_other}' (user_id {user_id}): {e}", exc_info=True)
                          await message.answer(f"⚠️ Не удалось проанализировать стиль для '{target_other}', сообщения будут сохранены без стиля.")
                  else:
                      logger.info(f"Недостаточно сообщений ({len(messages_other)}) для анализа стиля '{target_other}' (user_id {user_id}), сохраняю без стиля.")

                  save_messages(user_id, target_other, messages_other, style_data_other)
                  logger.info(f"Сохранено {len(messages_other)} сообщений для target '{target_other}' (user_id {user_id}).")
                  saved_count_others += 1

        response_text = ""
        if your_parsed_messages:
            response_text += f"✅ Загружено и сохранено {len(your_parsed_messages)} ваших сообщений'.\n"
        else:
             response_text += "✅ Файл обработан. Ваши сообщения не найдены/сохранены.\n"

        if saved_count_others > 0:
             response_text += f"✅ Сохранено/обновлено {saved_count_others} профилей других участников.\n"
             response_text += "👥 Выберите человека для имитации (из только что загруженных):"
             reply_markup_final = get_targets_kb(participants_to_choose)
             logger.info(f"Предложен выбор участников для user_id {user_id}: {participants_to_choose}")
        elif processed_others > 0:
             response_text += "🤷‍♂️ Других участников не найдено/сохранено из этого файла. Вы можете управлять ранее сохраненными профилями в меню."
             reply_markup_final = get_main_kb()
             logger.info(f"Других участников не сохранено из файла для user_id {user_id}.")
        else:
            response_text += "🤷‍♂️ Других участников в этом чате не найдено."
            reply_markup_final = get_main_kb()
            logger.info(f"Других участников не найдено в файле для user_id {user_id}.")


        await processing_message.edit_text(
            response_text,
            reply_markup=reply_markup_final
        )

    except FileNotFoundError:
        logger.error(f"Файл не найден '{file_path}' при обработке user_id {user_id}.", exc_info=True)
        await processing_message.edit_text("❌ Ошибка: Файл не найден после загрузки.", reply_markup=get_main_kb())
    except Exception as e:
        logger.error(f"Критическая ошибка обработки файла user_id {user_id}: {str(e)}", exc_info=True)
        try:
            await processing_message.edit_text( "❌ Произошла ошибка при обработке файла.", reply_markup=get_main_kb())
        except TelegramBadRequest:
             logger.error("Ошибка редактирования сообщения об ошибке обработки файла.", exc_info=True)
             await message.reply("❌ Произошла ошибка при обработке файла.", reply_markup=get_main_kb())
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Временный файл {file_path} удален.")
            except OSError as remove_error:
                logger.error(f"Не удалось удалить временный файл {file_path}: {remove_error}")


@dp.callback_query(F.data == "stats")
async def stats(callback: types.CallbackQuery):
    user: User = callback.from_user
    user_id = user.id
    logger.info(f"Запрошена статистика для user_id {user_id} (@{user.username or 'no_username'}).")
    stats_data = get_stats_data(user_id)

    if not stats_data:
        logger.info(f"Нет данных для статистики user_id {user_id}.")
        await callback.message.edit_text("📊 Нет сохраненных данных для статистики.", reply_markup=get_main_kb())
        await callback.answer()
        return

    user_identifier = user.username if user.username else f"user_{user_id}"
    logger.info(f"Формирую статистику для {user_identifier}.")

    output = io.StringIO()
    output.write(f"📊 Статистика для пользователя @{user_identifier}\n")
    output.write("====================================\n\n")

    total_profiles = len(stats_data)
    total_messages_all = 0
    output.write(f"Общее количество сохраненных профилей: {total_profiles}\n\n")

    translator = str.maketrans('', '', string.punctuation + '—«»”“`‘’')
    common_words_to_exclude = {
        'в', 'на', 'с', 'и', 'не', 'я', 'ты', 'он', 'она', 'оно', 'мы', 'вы', 'они',
        'что', 'как', 'а', 'ну', 'же', 'то', 'это', 'вот', 'бы', 'но', 'или', 'да',
        'блять', 'сука', 'пиздец', 'хуй', 'ебать', 'бля', 'хули', 'мда', 'пон', 'окей', 'ок', 'нахуй', 'нихуя', 'ебаный', 'епта',
        'че', 'мне', 'тебе', 'его', 'ее', 'нас', 'вас', 'их', 'мой', 'твой', 'свой', 'себе', 'меня', 'тебя',
        'за', 'по', 'у', 'из', 'до', 'от', 'к', 'про', 'для', 'со', 'под', 'над', 'без',
        'если', 'когда', 'тоже', 'так', 'нет', 'да', 'еще', 'уже', 'там', 'тут', 'все', 'всё', 'вообще', 'просто', 'типо',
        'этот', 'эта', 'эти', 'тот', 'та', 'те', 'где', 'кто', 'какой', 'какая', 'какое', 'какие', 'который', 'которая',
        'о', 'ж', 'бы', 'ль', 'ли', 'же', 'разве', 'спс', 'пж', 'хз', 'лол'
    }

    for target, messages in stats_data.items():
        message_count = len(messages)
        total_messages_all += message_count

        if message_count > 0:
            total_len = sum(len(str(msg)) for msg in messages)
            avg_len = round(total_len / message_count) if message_count > 0 else 0

            all_text = ' '.join(str(msg) for msg in messages).lower()
            cleaned_text = all_text.translate(translator)
            words = [word for word in cleaned_text.split() if len(word) > 1]
            word_counts = Counter(words)
            filtered_word_counts = Counter({word: count for word, count in word_counts.items() if word not in common_words_to_exclude})
            top_5_words = filtered_word_counts.most_common(5)
            top_words_str = ", ".join([f'"{word}" ({count})' for word, count in top_5_words]) if top_5_words else "Нет данных (после фильтрации)"
        else:
            avg_len = 0
            top_words_str = "Нет сообщений"

        output.write(f"--- Профиль: {target} ---\n")
        output.write(f"Сообщений сохранено: {message_count}\n")
        output.write(f"Средняя длина сообщения: {avg_len} симв.\n")
        output.write(f"Топ-5 частых слов (без стоп-слов, >1 буквы): {top_words_str}\n\n")

    output.write("====================================\n")
    output.write(f"Всего сообщений по всем профилям: {total_messages_all}\n")

    txt_content = output.getvalue().encode('utf-8')
    txt_file = BufferedInputFile(txt_content, filename=f"stats_{user_identifier}.txt")

    logger.info(f"Отправляю файл статистики {txt_file.filename} для user_id {user_id}.")
    try:
        await callback.message.answer_document(
            document=txt_file,
            caption=f"📊 Ваша статистика (@{user_identifier}) в TXT",
            reply_markup=get_back_to_main_kb()
        )
        await callback.message.delete()
    except Exception as send_error:
         logger.error(f"Не удалось отправить/удалить сообщение статистики для user_id {user_id}: {send_error}", exc_info=True)
         await callback.answer("Произошла ошибка при отправке статистики", show_alert=True)
         return

    await callback.answer()


@dp.callback_query(F.data == "clear_data")
async def clear(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Запрошена очистка данных для user_id {user_id}.")
    await callback.message.edit_text(
        "❓ Вы уверены, что хотите удалить ВСЕ свои сохраненные профили и данные?\n"
        "❗️ Это действие необратимо!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить всё", callback_data="clear_data_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="back")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "clear_data_confirm")
async def clear_confirm(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} подтвердил очистку ВСЕХ данных.")
    if clear_data(user_id):
        text = "🧹 Все ваши данные и профили удалены."
        if user_id in user_states:
            del user_states[user_id]
        if user_id in chat_memory:
            del chat_memory[user_id]
        logger.info(f"Данные успешно очищены для user_id {user_id}.")
    else:
        text = "❌ Ошибка очистки данных в базе."
        logger.error(f"Ошибка очистки данных в БД для user_id {user_id}.")

    await callback.message.edit_text(
        text,
        reply_markup=get_main_kb()
    )
    await callback.answer("Данные удалены.")


@dp.callback_query(F.data.startswith("target_"))
async def select_target(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        target_name = callback.data.split("_", 1)[1]
        if not target_name: raise IndexError("Empty target name")
    except IndexError:
        logger.error(f"Не удалось извлечь имя цели из callback_data при выборе: {callback.data} для user_id {user_id}")
        await callback.answer("Ошибка: неверный формат данных.", show_alert=True)
        return

    logger.info(f"Пользователь {user_id} выбрал цель для имитации: {target_name}")

    target_messages = get_messages(user_id, target_name)
    style_data = get_style_data_from_db(user_id, target_name)

    if not target_messages:
        logger.warning(f"Не найдены сообщения для user_id={user_id}, target={target_name} при выборе цели.")
        await callback.answer(f"❌ Ошибка: Нет сохраненных сообщений для {target_name}. Возможно, профиль был удален или поврежден.", show_alert=True)
        return

    if len(target_messages) < MIN_SAMPLES_FOR_IMITATION:
        logger.warning(f"Недостаточно ({len(target_messages)} < {MIN_SAMPLES_FOR_IMITATION}) сообщений для имитации '{target_name}', user_id {user_id}.")
        await callback.answer(f"⚠️ Недостаточно данных ({len(target_messages)}/{MIN_SAMPLES_FOR_IMITATION}) для имитации стиля {target_name}. Загрузите больше сообщений этого профиля.", show_alert=True)
        return

    if not style_data:
        logger.warning(f"Нет данных стиля (style_data) для user_id={user_id}, target={target_name}, но сообщений: {len(target_messages)}. Имитация начнется без глубокого анализа стиля.")

    user_states[user_id] = {
        "imitating": True,
        "target": target_name,
        "style_samples": target_messages,
        "style_data": style_data,
        "response_cache": {}
    }
    if user_id in chat_memory:
        del chat_memory[user_id]
    logger.info(f"Включен режим имитации для user_id={user_id}, target={target_name}.")

    try:
        await callback.message.edit_text(
            f"✅ Выбран стиль **{target_name}**.\n"
            f"Напишите что-нибудь для имитации:",
            reply_markup=get_exit_kb(),
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramBadRequest as e:
        logger.warning(f"Не удалось отредактировать сообщение в select_target (user_id {user_id}): {e}. Отправляю новое.")
        await callback.message.answer(
             f"✅ Выбран стиль **{target_name}**.\n"
             f"Напишите что-нибудь:",
             parse_mode=ParseMode.MARKDOWN
            )
        await callback.message.answer("Используйте кнопку ниже для выхода.", reply_markup=get_exit_kb())

    await callback.answer()


@dp.callback_query(F.data == "exit_imitation")
async def exit_imitation_mode(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} выходит из режима имитации через кнопку.")

    if user_id in user_states:
        user_states[user_id]["imitating"] = False
        logger.info(f"Режим имитации выключен для user_id {user_id} в user_states.")

    if user_id in chat_memory:
        del chat_memory[user_id]
        logger.info(f"Очищена память чата для user_id {user_id}.")

    try:
       await callback.message.edit_text("Режим имитации выключен.", reply_markup=None)
    except TelegramBadRequest as e:
        logger.warning(f"Не удалось отредактировать сообщение при выходе из режима имитации (user_id {user_id}): {e}")
        await callback.message.answer("Режим имитации выключен.")

    await callback.message.answer("Главное меню:", reply_markup=get_main_kb())
    await callback.answer("Вы вышли из режима имитации.")


@dp.message(F.text)
async def text(message: Message):
    user: User = message.from_user
    user_id = user.id
    user_state = user_states.get(user_id, {})

    if user_state.get("imitating"):
        target = user_state.get("target")
        style_samples = user_state.get("style_samples", [])

        if target and style_samples:
            logger.info(f"Пользователь {user_id} отправил сообщение в режиме имитации '{target}': '{message.text[:50]}...'")

            if len(style_samples) < MIN_SAMPLES_FOR_IMITATION:
                logger.error(f"State inconsistency: Imitating mode active but samples < {MIN_SAMPLES_FOR_IMITATION} for user_id {user_id}, target '{target}'.")
                user_states[user_id]["imitating"] = False
                if user_id in chat_memory: del chat_memory[user_id]
                await message.reply(
                     f"⚠️ Ошибка состояния: Недостаточно данных для имитации {target}. Режим выключен.",
                     reply_markup=get_main_kb()
                 )
                return

            try:
                response = await generate_response(user_id, target, message.text, user_states, chat_memory)
                await message.reply(response, reply_markup=get_exit_kb())

                if user_id not in chat_memory:
                    chat_memory[user_id] = {"history": []}
                chat_memory[user_id]["history"].append({"role": "user", "content": message.text})
                chat_memory[user_id]["history"].append({"role": "assistant", "content": response})
                chat_memory[user_id]["history"] = chat_memory[user_id]["history"][-20:]
                logger.debug(f"История чата для user_id {user_id} обновлена. Длина: {len(chat_memory[user_id]['history'])}")

            except Exception as e:
                logger.error(f"Ошибка генерации ответа для user_id {user_id}, target '{target}': {str(e)}", exc_info=True)
                await message.reply("⚠️ Произошла ошибка при генерации ответа.", reply_markup=get_exit_kb())
        else:
             logger.error(f"Неконсистентное состояние для user_id {user_id}: imitating=True, но нет target или style_samples в user_states.")
             user_states[user_id]["imitating"] = False
             await message.answer("Произошла внутренняя ошибка состояния имитации. Режим выключен.", reply_markup=get_main_kb())

    else:
        logger.info(f"Пользователь {user_id} отправил обычное сообщение (не в режиме имитации): '{message.text[:50]}...'")
        await message.answer("Выберите действие в меню:", reply_markup=get_main_kb())


async def main():
    dp.include_router(profile_management.profile_router)
    logger.info("Роутер управления профилями зарегистрирован.")

    logger.info("Запуск бота...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    os.makedirs("user_data", exist_ok=True)
    asyncio.run(main())