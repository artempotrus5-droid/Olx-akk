# -*- coding: utf-8 -*-
"""Обработчики всех сценариев бота."""

import re

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.formatting import (
    format_account_detail,
    format_accounts_table,
    format_history_text,
    format_user_accounts,
)
from bot.keyboards import (
    BTN_ADD,
    BTN_CANCEL,
    BTN_DELETE,
    BTN_HISTORY,
    BTN_RETURN,
    BTN_TAKE,
    cancel_menu,
    main_menu,
)
from bot.states import AddAccount, DeleteAccount, ReturnAccount, TakeAccount
from database import db

router = Router()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
YEAR_DESC_RE = re.compile(r"^\s*(\d{4})[\s,]*(.*)$", re.DOTALL)


def user_label(user) -> str:
    return user.username or (user.full_name or str(user.id))


async def send_long(message: Message, chunks, **kwargs):
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            await message.answer(chunk, **kwargs)
        else:
            await message.answer(chunk)


# ---------------------------------------------------------------------------
# Старт / Отмена
# ---------------------------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет! Это внутренний бот учёта корпоративных OLX-аккаунтов.\n\n"
        "➕ Добавить аккаунт — добавить новый аккаунт в общий пул\n"
        "📋 Взять аккаунт — посмотреть список и занять свободный\n"
        "🔄 Вернуть аккаунт — вернуть аккаунт, который вы сейчас используете\n"
        "🗑 Удалить аккаунт — удалить аккаунт из пула\n"
        "📖 История аккаунтов — журнал всех действий\n\n"
        "Выберите действие в меню ниже.",
        reply_markup=main_menu(),
    )


@router.message(Command("cancel"))
@router.message(F.text == BTN_CANCEL)
async def cancel_any(message: Message, state: FSMContext):
    current = await state.get_state()
    await state.clear()
    if current is None:
        await message.answer("Сейчас нет активного действия для отмены.", reply_markup=main_menu())
    else:
        await message.answer("Действие отменено.", reply_markup=main_menu())


# ---------------------------------------------------------------------------
# Добавление аккаунта
# ---------------------------------------------------------------------------
@router.message(StateFilter(None), F.text == BTN_ADD)
async def add_start(message: Message, state: FSMContext):
    await state.set_state(AddAccount.email)
    await message.answer(
        "➕ Добавить аккаунт\n\nШаг 1 из 3\nОтправьте email аккаунта:",
        reply_markup=cancel_menu(),
    )


@router.message(AddAccount.email)
async def add_email(message: Message, state: FSMContext):
    email = (message.text or "").strip()
    if not EMAIL_RE.match(email):
        await message.answer(
            "⚠️ Это не похоже на email. Отправьте адрес в формате name@example.com:",
            reply_markup=cancel_menu(),
        )
        return
    await state.update_data(email=email)
    await state.set_state(AddAccount.password)
    await message.answer(
        "✅ Email получен.\n\nШаг 2 из 3\nТеперь отправьте пароль:",
        reply_markup=cancel_menu(),
    )


@router.message(AddAccount.password)
async def add_password(message: Message, state: FSMContext):
    password = (message.text or "").strip()
    if not password:
        await message.answer("⚠️ Пароль не может быть пустым. Отправьте пароль:", reply_markup=cancel_menu())
        return
    await state.update_data(password=password)
    await state.set_state(AddAccount.year_desc)
    await message.answer(
        "✅ Пароль получен.\n\n"
        "Шаг 3 из 3\nУкажите год аккаунта и краткое описание.\n\n"
        "Например:\n2024, основной аккаунт",
        reply_markup=cancel_menu(),
    )


@router.message(AddAccount.year_desc)
async def add_year_desc(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    match = YEAR_DESC_RE.match(text)
    if not match:
        await message.answer(
            "⚠️ Не удалось распознать год. Отправьте в формате:\n2024, основной аккаунт",
            reply_markup=cancel_menu(),
        )
        return

    year = int(match.group(1))
    if year < 2000 or year > 2100:
        await message.answer(
            "⚠️ Похоже, год указан некорректно. Отправьте в формате:\n2024, основной аккаунт",
            reply_markup=cancel_menu(),
        )
        return
    description = match.group(2).strip() or "-"

    data = await state.get_data()
    who = user_label(message.from_user)
    row = db.add_account(
        email=data["email"],
        password=data["password"],
        year=year,
        description=description,
        user_id=message.from_user.id,
        username=who,
    )
    db.add_history(
        account_id=row["id"],
        event_type=db.EVENT_ADDED,
        email=row["email"],
        password=row["password"],
        year=row["year"],
        description=row["description"],
        username=who,
    )

    await state.clear()
    await message.answer(
        f"✅ Аккаунт №{row['id']} успешно добавлен.",
        reply_markup=main_menu(),
    )
    await message.answer(format_account_detail(row))


# ---------------------------------------------------------------------------
# Взять аккаунт
# ---------------------------------------------------------------------------
@router.message(StateFilter(None), F.text == BTN_TAKE)
async def take_start(message: Message, state: FSMContext):
    rows = db.list_active_accounts()
    free_rows = [r for r in rows if r["status"] == "free"]
    if not rows:
        await message.answer("Список аккаунтов пуст. Сначала добавьте аккаунт.", reply_markup=main_menu())
        return
    if not free_rows:
        await message.answer("Сейчас все аккаунты заняты. Свободных нет.", reply_markup=main_menu())
        return

    chunks = format_accounts_table(rows)
    await send_long(message, chunks)
    await state.set_state(TakeAccount.number)
    await message.answer(
        "💡 Чтобы взять аккаунт, отправьте его номер.",
        reply_markup=cancel_menu(),
    )


@router.message(TakeAccount.number)
async def take_number(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Отправьте номер аккаунта цифрой, например: 3", reply_markup=cancel_menu())
        return
    num = int(text)

    who = user_label(message.from_user)
    row, conflict = db.take_account(num, message.from_user.id, who)

    if row is None:
        if conflict is None:
            await message.answer(f"❌ Аккаунт №{num} не найден. Проверьте номер и попробуйте снова.", reply_markup=cancel_menu())
        elif conflict["status"] == "deleted":
            await message.answer(f"❌ Аккаунт №{num} был удалён и больше недоступен.", reply_markup=cancel_menu())
        else:
            holder = conflict["taken_by_username"] or "другим пользователем"
            await message.answer(f"❌ Аккаунт №{num} уже взят пользователем @{holder}.", reply_markup=cancel_menu())
        return

    db.add_history(
        account_id=row["id"], event_type=db.EVENT_TAKEN,
        email=row["email"], password=row["password"], year=row["year"],
        description=row["description"], username=who,
    )
    await state.clear()
    await message.answer(f"✅ Аккаунт №{num} успешно взят.", reply_markup=main_menu())
    await message.answer(format_account_detail(row))


# ---------------------------------------------------------------------------
# Вернуть аккаунт
# ---------------------------------------------------------------------------
@router.message(StateFilter(None), F.text == BTN_RETURN)
async def return_start(message: Message, state: FSMContext):
    rows = db.list_user_accounts(message.from_user.id)
    if not rows:
        await message.answer("У вас сейчас нет взятых аккаунтов.", reply_markup=main_menu())
        return

    await message.answer(format_user_accounts(rows))
    await state.set_state(ReturnAccount.number)
    await message.answer(
        "💡 Отправьте номер аккаунта, который хотите вернуть.",
        reply_markup=cancel_menu(),
    )


@router.message(ReturnAccount.number)
async def return_number(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Отправьте номер аккаунта цифрой, например: 1", reply_markup=cancel_menu())
        return
    num = int(text)

    row, conflict = db.return_account(num, message.from_user.id)
    if row is None:
        if conflict is None:
            await message.answer(f"❌ Аккаунт №{num} не найден.", reply_markup=cancel_menu())
        else:
            await message.answer(f"❌ Аккаунт №{num} не числится взятым вами.", reply_markup=cancel_menu())
        return

    who = user_label(message.from_user)
    db.add_history(
        account_id=row["id"], event_type=db.EVENT_RETURNED,
        email=row["email"], password=row["password"], year=row["year"],
        description=row["description"], username=who,
    )
    await state.clear()
    await message.answer(f"✅ Вы успешно вернули аккаунт №{num}.", reply_markup=main_menu())


# ---------------------------------------------------------------------------
# Удалить аккаунт
# ---------------------------------------------------------------------------
@router.message(StateFilter(None), F.text == BTN_DELETE)
async def delete_start(message: Message, state: FSMContext):
    rows = db.list_active_accounts()
    if not rows:
        await message.answer("Список аккаунтов пуст.", reply_markup=main_menu())
        return

    chunks = format_accounts_table(rows)
    await send_long(message, chunks)
    await state.set_state(DeleteAccount.number)
    await message.answer(
        "💡 Отправьте номер аккаунта, который хотите удалить.",
        reply_markup=cancel_menu(),
    )


@router.message(DeleteAccount.number)
async def delete_number(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("⚠️ Отправьте номер аккаунта цифрой, например: 7", reply_markup=cancel_menu())
        return
    num = int(text)

    row = db.get_account(num)
    if not row or row["status"] == "deleted":
        await message.answer(f"❌ Аккаунт №{num} не найден. Попробуйте другой номер.", reply_markup=cancel_menu())
        return

    await state.update_data(delete_id=num)
    await state.set_state(DeleteAccount.confirm)
    await message.answer(
        f"Вы действительно хотите удалить аккаунт №{num}?\n\n"
        f"{row['email']}\n\n"
        f"Напишите «ДА» для подтверждения.",
        reply_markup=cancel_menu(),
    )


@router.message(DeleteAccount.confirm)
async def delete_confirm(message: Message, state: FSMContext):
    text = (message.text or "").strip().upper()
    if text != "ДА":
        await message.answer(
            "Напишите «ДА» для подтверждения удаления, либо нажмите «❌ Отмена».",
            reply_markup=cancel_menu(),
        )
        return

    data = await state.get_data()
    num = data.get("delete_id")
    row = db.delete_account(num)
    await state.clear()

    if row is None:
        await message.answer("❌ Не удалось удалить: аккаунт уже удалён или не найден.", reply_markup=main_menu())
        return

    who = user_label(message.from_user)
    db.add_history(
        account_id=row["id"], event_type=db.EVENT_DELETED,
        email=row["email"], password=row["password"], year=row["year"],
        description=row["description"], username=who,
    )
    await message.answer(f"🗑 Аккаунт №{num} успешно удалён.", reply_markup=main_menu())


# ---------------------------------------------------------------------------
# История (текстовый фолбэк, если Mini App недоступна / открыта без web_app)
# ---------------------------------------------------------------------------
@router.message(StateFilter(None), F.text == BTN_HISTORY)
async def history_fallback(message: Message):
    items = db.list_history(limit=50)
    chunks = format_history_text(items)
    await send_long(message, chunks, reply_markup=main_menu())


# ---------------------------------------------------------------------------
# Прочее: неизвестные команды и сообщения вне сценариев
# ---------------------------------------------------------------------------
@router.message(StateFilter(None))
async def unknown(message: Message):
    await message.answer(
        "Не понимаю эту команду 🤔 Пожалуйста, воспользуйтесь кнопками меню ниже.",
        reply_markup=main_menu(),
    )
