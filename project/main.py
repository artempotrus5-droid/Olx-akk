# -*- coding: utf-8 -*-
"""
Точка входа: запускает одновременно
  1) Telegram-бота (long polling через aiogram)
  2) FastAPI-сервер (health-check /health, API истории, Mini App)

Оба процесса живут в одном asyncio-event loop — это удобно для Render,
где Web Service должен слушать один порт (переменная окружения PORT).
"""

import asyncio
import logging
import os
import sys

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.access import AccessMiddleware
from bot.handlers import router
from database import db
from web.app import app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("main")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "8080"))


async def run_bot():
    if not BOT_TOKEN:
        logger.error("Переменная окружения BOT_TOKEN не задана. Бот не может быть запущен.")
        return
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(AccessMiddleware())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен (long polling).")
    await dp.start_polling(bot)


async def run_web():
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    logger.info(f"HTTP-сервер запущен на порту {PORT}.")
    await server.serve()


async def main():
    db.init_db()
    logger.info("База данных инициализирована.")

    tasks = [asyncio.create_task(run_web())]
    if BOT_TOKEN:
        tasks.append(asyncio.create_task(run_bot()))
    else:
        logger.warning(
            "Бот не запущен: BOT_TOKEN не указан. Работает только HTTP-сервер "
            "(health-check и Mini App)."
        )

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
