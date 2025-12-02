from contextlib import suppress
from aiogram import Router, F
from aiogram.enums import DiceEmoji, ContentType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message
from bot.dice_check import get_score_change
from bot.db import Database
from bot.config_reader import GameConfig

router = Router()

# Обработчик команды /balance
@router.message(Command("balance"))
async def cmd_balance(message: Message, db: Database, game_config: GameConfig):
    if not message.from_user:
        return
    user_id = message.from_user.id
    # Получаем баланс (или начальный, если пользователя нет)
    balance = await db.get_balance(user_id, game_config.starting_points)
    await message.reply(f"Ваш баланс: {balance}")

# Обработчик броска кубика
@router.message(F.content_type == ContentType.DICE, F.dice.emoji == DiceEmoji.SLOT_MACHINE)
async def on_dice_roll(message: Message, db: Database, game_config: GameConfig):
    # Игнорируем, если сообщение не от пользователя
    if not message.from_user:
        return

    user_id = message.from_user.id
    
    # Получаем текущий баланс
    current_balance = await db.get_balance(user_id, game_config.starting_points)
    
    # ПРОВЕРКА НА БАНКРОТА: Если баланс <= 0, удаляем сообщение
    if current_balance <= 0:
        with suppress(TelegramBadRequest):
            await message.delete()
        return

    dice_value = message.dice.value
    
    # Считаем изменение очков
    score_change = get_score_change(dice_value)
    new_balance = current_balance + score_change
    
    # Обновляем баланс в БД
    await db.set_balance(user_id, new_balance)
    
    # Логика отправки сообщений
    
    # 1. Выигрышная комбинация (score_change > 0)
    if score_change > 0:
        await message.reply(
            f"Вы выиграли {score_change} очков! Ваш баланс: {new_balance}"
        )

    # 2. Банкрот (баланс стал <= 0, но был > 0)
    elif new_balance <= 0:
        await message.reply(
            "Вы банкрот! Звоните в екапусту или заложите квартиру"
        )

