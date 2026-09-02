# -*- coding: utf-8 -*-
"""Контроль доступа: админы, одноразовый пароль, менеджеры, блокировки."""

from aiogram import BaseMiddleware
from aiogram.types import Message

from database import db

# Эти ID всегда имеют полный доступ без пароля и могут управлять доступом других.
ADMIN_IDS = {1045593643, 6354040832, 8329719916}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def user_label(user) -> str:
    return user.username or (user.full_name or str(user.id))


class AccessMiddleware(BaseMiddleware):
    """Пропускает только админов и уже авторизованных пользователей.
    Остальным предлагает ввести одноразовый пароль и ничего больше не делает,
    пока пароль не будет введён верно."""

    async def __call__(self, handler, event: Message, data):
        user = event.from_user
        if user is None:
            return await handler(event, data)

        uid = user.id
        uname = user_label(user)
        db.touch_user(uid, uname)

        if is_admin(uid):
            return await handler(event, data)

        if db.is_blocked(uid):
            await event.answer("🚫 Доступ к боту заблокирован.")
            return

        if db.is_authorized(uid):
            return await handler(event, data)

        # Пользователь ещё не авторизован — принимаем только одноразовый пароль
        text = (event.text or "").strip()
        if text and db.try_use_code(text, uid, uname):
            db.authorize_user(uid, uname)
            from bot.keyboards import main_menu

            await event.answer(
                "✅ Пароль верный, доступ открыт.\n\n👋 Выберите действие в меню ниже.",
                reply_markup=main_menu(),
            )
            return

        await event.answer("🔒 Для доступа к боту введите одноразовый пароль.")
        return
