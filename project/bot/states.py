# -*- coding: utf-8 -*-
"""Состояния FSM для пошаговых сценариев бота."""

from aiogram.fsm.state import State, StatesGroup


class AddAccount(StatesGroup):
    email = State()
    password = State()
    year_desc = State()


class TakeAccount(StatesGroup):
    number = State()


class ReturnAccount(StatesGroup):
    number = State()


class DeleteAccount(StatesGroup):
    number = State()
    confirm = State()
