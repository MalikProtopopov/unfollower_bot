"""Info command handlers: about, last check, offer, privacy."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.bot.http_client import APIError, api_get
from app.bot.keyboards import (
    get_about_keyboard,
    get_back_to_main_keyboard,
    get_offer_keyboard,
    get_privacy_keyboard,
)
from app.bot.utils import format_number, get_manager_username
from app.utils.logger import logger

router = Router()


# --- /about command ---


@router.message(Command("about"))
async def cmd_about(message: Message) -> None:
    """Handle /about command - show info about the service."""
    await show_about(message)


async def show_about(message: Message) -> None:
    """Show about page with inline buttons."""
    about_text = f"""
ℹ️ <b>О сервисе</b>

<b>CheckFollowers Bot</b> — это сервис для анализа взаимных подписок в Instagram.

🔍 <b>Что мы делаем:</b>
Анализируем ваши подписки и подписчиков, чтобы показать, кто не подписан на вас взаимно. Формируем удобный Excel-отчёт со всеми данными.

⚡️ <b>Преимущества:</b>
• Быстрый анализ аккаунтов
• Подробные отчёты в Excel
• Автоматические уведомления
• Реферальная программа

📊 Работаем с аккаунтами до 10 000 подписок/подписчиков.

По всем вопросам обращайтесь к менеджеру 👇
"""

    await message.answer(about_text, reply_markup=get_about_keyboard())


# --- /last command ---


@router.message(Command("last"))
async def cmd_last(message: Message) -> None:
    """Handle /last command - get last check result."""
    user_id = message.from_user.id

    try:
        # Get user's check history
        result = await api_get("/checks", params={"user_id": user_id, "limit": 1})

        if not result["checks"]:
            await message.answer(
                "📭 <b>У вас пока нет проверок</b>\n\n"
                "Используйте /check чтобы начать первую проверку."
            )
            return

        last_check = result["checks"][0]
        check_id = last_check["check_id"]
        status = last_check["status"]
        username = last_check["target_username"]

        if status == "completed":
            # Get full check details
            check_data = await api_get(f"/check/{check_id}")

            total_followers = check_data.get("total_followers", 0)
            total_following = check_data.get("total_subscriptions", 0)
            total_non_mutual = check_data.get("total_non_mutual", 0)
            file_path = check_data.get("file_path")

            text = f"""
✅ <b>Последняя проверка: @{username}</b>

📊 <b>Результаты:</b>
• Подписчиков: <b>{format_number(total_followers)}</b>
• Подписок: <b>{format_number(total_following)}</b>
• Не взаимных: <b>{format_number(total_non_mutual)}</b>
"""
            await message.answer(text, reply_markup=get_back_to_main_keyboard())

            # Send file if exists
            if file_path:
                try:
                    file = FSInputFile(file_path)
                    await message.answer_document(file, caption="📄 Отчёт в Excel")
                except Exception as e:
                    logger.error(f"Error sending file: {e}")
                    await message.answer("⚠️ Не удалось отправить файл")

        elif status == "processing":
            await message.answer(
                f"⏳ <b>Проверка @{username} ещё выполняется...</b>\n\n"
                "Подождите завершения или используйте /check для новой проверки.",
                reply_markup=get_back_to_main_keyboard(),
            )

        elif status == "failed":
            error_msg = last_check.get("error_message", "Неизвестная ошибка")
            await message.answer(
                f"❌ <b>Последняя проверка @{username} завершилась с ошибкой</b>\n\n"
                f"{error_msg}\n\n"
                "Используйте /check для новой проверки.",
                reply_markup=get_back_to_main_keyboard(),
            )

        else:
            await message.answer(
                f"⏳ <b>Проверка @{username} в очереди</b>\n\n" "Подождите завершения.",
                reply_markup=get_back_to_main_keyboard(),
            )

    except APIError as e:
        logger.error(f"Error in /last command: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении данных.\n\n" "Попробуйте позже.",
            reply_markup=get_back_to_main_keyboard(),
        )


# --- Callbacks ---


@router.callback_query(F.data == "about")
async def callback_about(callback: CallbackQuery) -> None:
    """Handle about button."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await show_about(callback.message)


@router.callback_query(F.data == "last_check")
async def callback_last_check(callback: CallbackQuery) -> None:
    """Handle last check button."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await cmd_last(callback.message)


@router.callback_query(F.data == "public_offer")
async def callback_public_offer(callback: CallbackQuery) -> None:
    """Handle public offer button - show offer text."""
    await callback.answer()

    manager = get_manager_username()
    offer_text = f"""
📄 <b>Публичная оферта</b>

<b>1. Общие положения</b>
Настоящий документ является публичной офертой сервиса CheckFollowers Bot для анализа взаимных подписок в Instagram.

<b>2. Описание услуги</b>
Сервис предоставляет возможность анализа подписок и подписчиков аккаунтов Instagram для выявления невзаимных подписок.

<b>3. Стоимость услуг</b>
Стоимость услуг определяется действующими тарифами, доступными в разделе /buy.

<b>4. Порядок оказания услуг</b>
• Услуга предоставляется после списания проверки с баланса
• Результат формируется в виде Excel-отчёта
• Время обработки зависит от размера аккаунта

<b>5. Ограничения</b>
• Сервис работает только с публичными аккаунтами
• Максимальный размер аккаунта: 10 000 подписок/подписчиков

<b>6. Ответственность</b>
Сервис не несёт ответственности за действия Instagram и изменения в их API.

<b>7. Контакты</b>
По всем вопросам: @{manager}
"""

    await callback.message.edit_text(offer_text, reply_markup=get_offer_keyboard())


@router.callback_query(F.data == "privacy_policy")
async def callback_privacy_policy(callback: CallbackQuery) -> None:
    """Handle privacy policy button - show privacy policy text."""
    await callback.answer()

    manager = get_manager_username()
    privacy_text = f"""
🔒 <b>Политика конфиденциальности</b>

<b>1. Какие данные мы собираем</b>
Для оказания услуг сервис собирает и обрабатывает следующие данные:
• Telegram ID пользователя
• Telegram username (имя пользователя)
• Имя и фамилия в Telegram (если указаны)
• Номер телефона (если предоставлен через Telegram)

<b>2. Цель сбора данных</b>
Данные используются исключительно для:
• Идентификации пользователя в системе
• Начисления и учёта баланса проверок
• Отправки уведомлений о результатах проверок
• Связи с пользователем по вопросам сервиса
• Работы реферальной программы

<b>3. Хранение данных</b>
• Данные хранятся на защищённых серверах
• Доступ к данным имеют только администраторы сервиса
• Данные не передаются третьим лицам

<b>4. Удаление данных</b>
Вы можете запросить удаление своих данных, написав менеджеру @{manager}

<b>5. Согласие</b>
Используя сервис, вы соглашаетесь с данной политикой конфиденциальности.

<b>6. Контакты</b>
По вопросам обработки данных: @{manager}
"""

    await callback.message.edit_text(privacy_text, reply_markup=get_privacy_keyboard())

