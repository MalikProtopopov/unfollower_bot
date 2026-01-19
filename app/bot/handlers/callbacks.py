"""Telegram bot callback handlers for inline buttons."""

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.utils.logger import logger

router = Router()


@router.callback_query(F.data.startswith("check_status:"))
async def callback_check_status(callback: CallbackQuery):
    """Handle check status callback (placeholder for future use)."""
    check_id = callback.data.split(":")[1]
    await callback.answer(f"Статус проверки: {check_id[:8]}...")
    logger.info(f"Status requested for check: {check_id}")


@router.callback_query(F.data.startswith("download:"))
async def callback_download(callback: CallbackQuery):
    """Handle download callback (placeholder for future use)."""
    check_id = callback.data.split(":")[1]
    await callback.answer("Загрузка файла...")
    logger.info(f"Download requested for check: {check_id}")


@router.callback_query()
async def callback_unknown(callback: CallbackQuery):
    """Handle unknown callbacks."""
    logger.warning(f"Unknown callback: {callback.data}")
    await callback.answer("Неизвестное действие")

