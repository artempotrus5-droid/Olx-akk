# -*- coding: utf-8 -*-
"""Клавиатуры бота."""

import os

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import ReplyKeyboardBuilder

BTN_ADD = "➕ Добавить аккаунт"
BTN_TAKE = "📋 Взять аккаунт"
BTN_RETURN = "🔄 Вернуть аккаунт"
BTN_DELETE = "🗑 Удалить аккаунт"
BTN_HISTORY = "📖 История аккаунтов"
BTN_CANCEL = "❌ Отмена"


def _webapp_url() -> str:
    return os.getenv("WEBAPP_URL", "").strip()


def main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=BTN_ADD), KeyboardButton(text=BTN_TAKE))
    builder.row(KeyboardButton(text=BTN_RETURN), KeyboardButton(text=BTN_DELETE))

    url = _webapp_url()
    if url:
        builder.row(KeyboardButton(text=BTN_HISTORY, web_app=WebAppInfo(url=url)))
    else:
        builder.row(KeyboardButton(text=BTN_HISTORY))

    return builder.as_markup(resize_keyboard=True)


def cancel_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=BTN_CANCEL))
    return builder.as_markup(resize_keyboard=True)
