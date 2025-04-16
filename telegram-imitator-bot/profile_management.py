import logging
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
import database
from keyboards import get_main_kb
from typing import List

logger = logging.getLogger(__name__)

profile_router = Router()

async def get_saved_targets(user_id: int) -> List[str]:
    targets = []
    try:
        database.cursor.execute("""
            SELECT DISTINCT target FROM imitation_data WHERE user_id = ? ORDER BY target
        """, (user_id,))
        rows = database.cursor.fetchall()
        targets = sorted([row[0] for row in rows if row and row[0]])
        logger.debug(f"Найдены сохраненные профили для user_id {user_id}: {targets}")
    except database.sqlite3.Error as e:
        logger.error(f"Ошибка БД при получении сохраненных профилей для user_id {user_id}: {e}")
    return targets

async def delete_target_profile(user_id: int, target: str) -> bool:
    success = False
    try:
        database.cursor.execute("SELECT 1")
    except (database.sqlite3.ProgrammingError, database.sqlite3.InterfaceError) as conn_err:
         logger.error(f"Соединение с БД потеряно перед удалением профиля '{target}' user_id {user_id}: {conn_err}")
         return False

    try:
        database.cursor.execute("""
            DELETE FROM imitation_data WHERE user_id = ? AND target = ?
        """, (user_id, target))
        database.conn.commit()
        deleted_rows = database.cursor.rowcount
        if deleted_rows > 0:
            logger.info(f"Удалено {deleted_rows} записей для user_id {user_id}, target '{target}'.")
            success = True
        else:
            logger.warning(f"Не найдены записи для удаления (user_id {user_id}, target '{target}').")
            success = True
    except database.sqlite3.Error as e:
        logger.error(f"Ошибка БД при удалении профиля '{target}' для user_id {user_id}: {e}")
        try:
            database.conn.rollback()
        except database.sqlite3.Error as rb_err:
             logger.error(f"Ошибка при откате транзакции после ошибки удаления: {rb_err}")
    return success

def get_profile_management_kb(targets: List[str]) -> InlineKeyboardMarkup:
    buttons = []
    if targets:
        max_name_len = 30
        for target in targets:
            display_name = target if len(target) <= max_name_len else target[:max_name_len-3] + "..."
            buttons.append([
                InlineKeyboardButton(text=f"🎯 {display_name}", callback_data=f"target_{target}"),
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"del_req_{target}")
            ])
    else:
        buttons.append([InlineKeyboardButton(text="Нет сохраненных профилей", callback_data="no_profiles")])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_profile_deletion_confirm_kb(target: str) -> InlineKeyboardMarkup:
    max_name_len_confirm = 25
    display_target = target if len(target) <= max_name_len_confirm else target[:max_name_len_confirm-3] + "..."
    buttons = [
        [InlineKeyboardButton(text=f"✅ Да, удалить {display_target}", callback_data=f"del_conf_{target}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="del_cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@profile_router.callback_query(F.data == "manage_profiles")
async def manage_profiles_entry(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} вошел в управление профилями.")
    targets = await get_saved_targets(user_id)

    text = "👤 Управление профилями:\nВыберите профиль для имитации или удаления."
    if not targets:
        text = "👤 Управление профилями:\nУ вас пока нет сохраненных профилей."

    try:
        if callback.message and callback.message.text:
             await callback.message.edit_text(
                text,
                reply_markup=get_profile_management_kb(targets)
            )
        else:
             await callback.message.answer(text, reply_markup=get_profile_management_kb(targets))
             if callback.message: await callback.message.delete()

    except TelegramBadRequest as e:
         if "message to edit not found" in str(e) or "query is too old" in str(e):
             logger.warning(f"Не удалось отредактировать сообщение в manage_profiles_entry для user_id {user_id}: {e}. Отправляю новое.")
             await callback.message.answer(text, reply_markup=get_profile_management_kb(targets))
         else:
             logger.error(f"Ошибка редактирования сообщения в manage_profiles_entry для user_id {user_id}: {e}", exc_info=True)
             await callback.answer("Произошла ошибка отображения профилей", show_alert=True)
             await callback.message.answer("Главное меню:", reply_markup=get_main_kb())
    finally:
        await callback.answer()


@profile_router.callback_query(F.data.startswith("del_req_"))
async def request_delete_target(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        target_to_delete = callback.data[len("del_req_"):]
        if not target_to_delete: raise ValueError("Empty target name")
    except (IndexError, ValueError) as e:
        logger.error(f"Не удалось извлечь имя цели из callback_data: {callback.data} для user_id {user_id}: {e}")
        await callback.answer("Ошибка: неверный идентификатор профиля.", show_alert=True)
        return

    logger.info(f"Пользователь {user_id} запросил удаление профиля: {target_to_delete}")

    if callback.message and callback.message.text:
        await callback.message.edit_text(
            f"Вы уверены, что хотите удалить профиль\n'{target_to_delete}'?\n\n"
            "❗️ Это действие необратимо и удалит все сохраненные сообщения и стиль для этого профиля.",
            reply_markup=get_profile_deletion_confirm_kb(target_to_delete)
        )
    else:
        logger.warning(f"Не текстовое сообщение для редактирования в request_delete_target (user_id {user_id}).")
        await callback.answer("Не удалось отобразить подтверждение.", show_alert=True)

    await callback.answer()


@profile_router.callback_query(F.data.startswith("del_conf_"))
async def confirm_delete_target(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        target_to_delete = callback.data[len("del_conf_"):]
        if not target_to_delete: raise ValueError("Empty target name")
    except (IndexError, ValueError) as e:
        logger.error(f"Не удалось извлечь имя цели из callback_data при подтверждении: {callback.data} для user_id {user_id}: {e}")
        await callback.answer("Ошибка: неверный идентификатор профиля для удаления.", show_alert=True)
        return

    logger.info(f"Пользователь {user_id} подтвердил удаление профиля: {target_to_delete}")
    deleted = await delete_target_profile(user_id, target_to_delete)

    if deleted:
        await callback.answer(f"Профиль '{target_to_delete}' удален.")

        from bot import user_states, chat_memory
        if user_id in user_states and user_states[user_id].get("target") == target_to_delete:
            if user_states[user_id].get("imitating"):
                 logger.info(f"Пользователь {user_id} был в режиме имитации удаленного профиля '{target_to_delete}'. Выключаю режим.")
            user_states[user_id] = {"imitating": False}
            if user_id in chat_memory: del chat_memory[user_id]
            logger.info(f"Сброшено user_state и chat_memory для удаленного профиля '{target_to_delete}' user_id {user_id}")

        targets = await get_saved_targets(user_id)
        text = f"✅ Профиль '{target_to_delete}' удален.\n\n👤 Управление профилями:"
        if not targets:
            text += "\nУ вас больше нет сохраненных профилей."

        if callback.message and callback.message.text:
             await callback.message.edit_text(
                text,
                reply_markup=get_profile_management_kb(targets)
            )
        else:
             await callback.message.answer(text, reply_markup=get_profile_management_kb(targets))
             if callback.message: await callback.message.delete()

    else:
        await callback.answer("❌ Не удалось удалить профиль. Возможно, он уже был удален или произошла ошибка БД.", show_alert=True)
        targets = await get_saved_targets(user_id)
        if callback.message and callback.message.text:
            await callback.message.edit_text(
                "👤 Управление профилями:",
                reply_markup=get_profile_management_kb(targets)
            )

@profile_router.callback_query(F.data == "del_cancel")
async def cancel_delete_target(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} отменил удаление профиля.")
    await callback.answer("Удаление отменено.")
    targets = await get_saved_targets(user_id)
    text = "👤 Управление профилями:\nВыберите профиль для имитации или удаления."
    if not targets:
        text = "👤 Управление профилями:\nУ вас пока нет сохраненных профилей."

    if callback.message and callback.message.text:
         await callback.message.edit_text(
            text,
            reply_markup=get_profile_management_kb(targets)
        )
    else:
        await callback.message.answer(text, reply_markup=get_profile_management_kb(targets))
        if callback.message: await callback.message.delete()


@profile_router.callback_query(F.data == "back_to_main_menu")
async def back_to_main_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} возвращается в главное меню из управления профилями.")
    if callback.message and callback.message.text:
        await callback.message.edit_text(
            "Главное меню:",
            reply_markup=get_main_kb()
        )
    else:
         await callback.message.answer("Главное меню:", reply_markup=get_main_kb())
         if callback.message: await callback.message.delete()
    await callback.answer()

@profile_router.callback_query(F.data == "no_profiles")
async def handle_no_profiles(callback: types.CallbackQuery):
    await callback.answer("У вас пока нет сохраненных профилей.")