# -*- coding: utf-8 -*-
"""Форматирование сообщений: таблицы аккаунтов, группировка по годам, история."""

from typing import List

MAX_CHUNK = 3500  # запас от лимита Telegram в 4096 символов


def bucket_year(year: int) -> int:
    """2024, 2025, 2026... объединяются в одну группу '2024 и старше'."""
    return year if year < 2024 else 2024


def bucket_header(bucket: int) -> str:
    if bucket >= 2024:
        return "📅 2024 и старше"
    return f"📅 {bucket}"


def status_line(row) -> str:
    if row["status"] == "free":
        return "🟢 Свободен"
    username = row["taken_by_username"] or "пользователем"
    return f"🔴 Взят @{username}"


def account_block(row, show_password: bool = True) -> str:
    lines = [f"{row['id']}. {row['email']}"]
    if show_password:
        lines.append(f"   Пароль: {row['password']}")
    lines.append(f"   📅 {row['year']}")
    lines.append(f"   📝 {row['description'] or '-'}")
    lines.append(f"   {status_line(row)}")
    return "\n".join(lines)


def chunk_sections(sections: List[str], limit: int = MAX_CHUNK) -> List[str]:
    """Собирает секции (тексты с заголовками) в сообщения не длиннее лимита."""
    chunks: List[str] = []
    current = ""
    for section in sections:
        candidate = section if not current else current + "\n\n" + section
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(section) <= limit:
                current = section
            else:
                lines = section.split("\n")
                piece = ""
                for line in lines:
                    cand2 = line if not piece else piece + "\n" + line
                    if len(cand2) <= limit:
                        piece = cand2
                    else:
                        if piece:
                            chunks.append(piece)
                        piece = line
                current = piece
    if current:
        chunks.append(current)
    return chunks


def format_accounts_table(rows, show_password: bool = True,
                           empty_text: str = "Список аккаунтов пуст.") -> List[str]:
    """Группирует аккаунты по годам и возвращает список готовых к отправке сообщений."""
    if not rows:
        return [empty_text]

    groups = {}
    order = []
    for row in rows:
        b = bucket_year(row["year"])
        if b not in groups:
            groups[b] = []
            order.append(b)
        groups[b].append(row)

    order.sort(reverse=True)

    sections = []
    for b in order:
        header = bucket_header(b)
        blocks = "\n".join(account_block(r, show_password=show_password) for r in groups[b])
        sections.append(f"{header}\n{blocks}")

    return chunk_sections(sections)


def format_account_detail(row) -> str:
    return (
        f"Аккаунт №{row['id']}\n\n"
        f"Email:\n{row['email']}\n\n"
        f"Пароль:\n{row['password']}\n\n"
        f"Год:\n{row['year']}\n\n"
        f"Описание:\n{row['description'] or '-'}\n\n"
        f"Статус:\n{status_line(row)}"
    )


def format_user_accounts(rows) -> str:
    lines = ["Ваши аккаунты:", ""]
    for r in rows:
        lines.append(f"{r['id']}. {r['email']}")
        lines.append(f"   📅 {r['year']}")
        lines.append(f"   📝 {r['description'] or '-'}")
        lines.append("")
    return "\n".join(lines).rstrip()


HISTORY_ICONS = {
    "added": "🟢",
    "deleted": "🔴",
    "taken": "📤",
    "returned": "📥",
}

HISTORY_TITLES = {
    "added": "Добавлен аккаунт №{n}",
    "deleted": "Удалён аккаунт №{n}",
    "taken": "Аккаунт №{n} взят",
    "returned": "Аккаунт №{n} возвращён",
}


def format_history_entry(item: dict) -> str:
    icon = HISTORY_ICONS.get(item["event_type"], "•")
    title = HISTORY_TITLES.get(item["event_type"], "Событие №{n}").format(n=item["account_id"])
    lines = [f"{icon} {title}", ""]

    if item["event_type"] in ("added", "deleted"):
        lines.append(f"Email: {item['email']}")
        lines.append(f"Пароль: {item['password']}")
        lines.append(f"Год: {item['year']}")
        lines.append(f"Описание: {item['description'] or '-'}")
        lines.append("")
        who = "Добавил" if item["event_type"] == "added" else "Удалил"
        lines.append(f"{who}: @{item['username']}")
    elif item["event_type"] == "taken":
        lines.append(f"Взял: @{item['username']}")
    elif item["event_type"] == "returned":
        lines.append(f"Вернул: @{item['username']}")

    lines.append(f"Дата: {item['created_at']}")
    return "\n".join(lines)


def format_history_text(items) -> List[str]:
    if not items:
        return ["История пока пуста."]
    sections = [format_history_entry(i) for i in items]
    return chunk_sections(sections)
