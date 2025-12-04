import uuid
import json
import html
import asyncio
import random
from contextlib import suppress
from aiogram import Router, F
from aiogram.enums import DiceEmoji, ContentType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message
from bot.dice_check import get_score_change, get_super_jackpot
from bot.db import Database
from bot.config_reader import GameConfig

router = Router()

async def delete_message_later(message: Message, delay: int = 60):
    """Удаляет сообщение через delay секунд."""
    await asyncio.sleep(delay)
    with suppress(TelegramBadRequest):
        await message.delete()

# Обработчик команды /balance
@router.message(Command("balance"))
async def cmd_balance(message: Message, db: Database, game_config: GameConfig):
    if not message.from_user:
        return
    user_id = message.from_user.id
    
    if message.from_user.username:
        await db.register_user(user_id, message.from_user.username)

    # Получаем баланс (или начальный, если пользователя нет)
    balance = await db.get_balance(user_id, game_config.starting_points)
    await message.reply(f"Ваш баланс: {balance}")

# Обработчик команды /stats
@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database):
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("Эта команда работает только в группах.")
        return

    top_users = await db.get_top_users_in_group(message.chat.id, limit=30)
    
    if not top_users:
        await message.reply("В этом чате пока нет активных игроков.")
        return

    chat_title = html.escape(message.chat.title or "Unknown Group")
    text = [f"🏆 <b>Топ игроков чата {chat_title}:</b>\n"]
    
    for idx, user in enumerate(top_users, start=1):
        nickname = user['nickname'] or "Безымянный"
        balance = user['balance']
        games = user.get('games_played', 0)
        won = user.get('total_won', 0)
        lost = user.get('total_lost', 0)
        winrate = round(won / (won + lost) * 100, 2) if (won + lost) > 0 else 0
        bk = user.get('bankruptcy_count', 0)
        
        safe_nickname = html.escape(str(nickname))
        # Add stats to display if they exist (games > 0)
        if games > 0:
            stats_part = (
                f"\n      🎰 Всего игр: {games}"
                f"\n      📈 Выиграно очков: {won} | Потрачено: {lost} | WR: {winrate}%"
                f"\n      💀 Банкротств: {bk}"
            )
            text.append(f"{idx}. <b>{safe_nickname}</b> — {balance} очков{stats_part}\n")
        else:
            text.append(f"{idx}. <b>{safe_nickname}</b> — {balance} очков\n")
        
    await message.reply("\n".join(text))

# Обработчик броска кубика
@router.message(F.content_type == ContentType.DICE, F.dice.emoji == DiceEmoji.SLOT_MACHINE)
async def on_dice_roll(message: Message, db: Database, game_config: GameConfig):
    # Check if forwarded
    if message.forward_date or message.forward_from or message.forward_from_chat or getattr(message, 'forward_origin', None):
        return

    # Игнорируем, если сообщение не от пользователя
    if not message.from_user:
        return

    user_id = message.from_user.id
    
    if message.from_user.username:
        await db.register_user(user_id, message.from_user.username)
    
    # Получаем текущий баланс
    current_balance = await db.get_balance(user_id, game_config.starting_points)
    
    # ПРОВЕРКА НА БАНКРОТА: Если баланс <= 0, удаляем сообщение
    if current_balance <= 0:
        with suppress(TelegramBadRequest):
            await message.delete()
        return

    # Получаем ставку пользователя
    user_bid = await db.get_bid(user_id)

    # Проверяем, хватает ли денег на ставку
    if current_balance < user_bid:
        await message.reply(f"Ваш баланс ({current_balance}) меньше текущей ставки ({user_bid}). Снизьте ставку командой /bid или пополните баланс.")
        return

    dice_value = message.dice.value
    
    # Считаем изменение очков
    score_change = get_score_change(dice_value)
    
    # Супер Джекпот логика
    super_multiplier = 1
    jackpot_name = None
    if score_change > 0:
        super_multiplier, jackpot_name = get_super_jackpot()
        
    actual_change = score_change * user_bid * super_multiplier
    new_balance = current_balance + actual_change
    
    # Обновляем баланс в БД
    await db.set_balance(user_id, new_balance)

    # Логируем событие
    event_id = str(uuid.uuid4())
    event_type = 'win' if actual_change > 0 else 'loss'
    metadata_dict = {
        "dice_value": dice_value, 
        "bid": user_bid, 
        "base_score_change": score_change,
        "super_jackpot_multiplier": super_multiplier
    }
    metadata = json.dumps(metadata_dict)
    await db.add_event(event_id, user_id, event_type, actual_change, metadata, chat_id=message.chat.id)
    
    # Обновляем статистику
    is_bankruptcy = new_balance <= 0
    await db.update_user_stats(user_id, actual_change, is_bankruptcy=is_bankruptcy)
    
    if is_bankruptcy:
        # Record explicit bankruptcy event for daily stats
        await db.add_event(str(uuid.uuid4()), user_id, 'bankruptcy', 0, chat_id=message.chat.id)
    
    # Логика отправки сообщений
    
    # 1. Выигрышная комбинация (score_change > 0)
    if actual_change > 0:
        if super_multiplier > 1:
            # Яркие фразы для джекпотов
            if super_multiplier == 2:
                header = "🔥 <b>SUPER JACKPOT! Удача улыбнулась вам!</b>"
            elif super_multiplier == 3:
                header = "⚡️ <b>MEGA WIN! Невероятное везение!</b>"
            elif super_multiplier == 5:
                header = "🚀 <b>COSMIC JACKPOT! Вы сегодня король казино!</b>"
            else: # 10
                header = "👑 <b>LEGENDARY! СУДЬБА ВЫБРАЛА ВАС! ГРАНДИОЗНЫЙ КУШ!</b>"
            
            msg_text = (
                f"{header}\n"
                f"Сработал множитель <b>x{super_multiplier}</b> ({jackpot_name})!\n\n"
                f"💰 Ваша ставка: {user_bid}\n"
                f"💸 Выигрыш: <b>{actual_change}</b> очков! (вместо {score_change * user_bid})\n"
                f"🏦 Ваш баланс: {new_balance}"
            )
            await message.reply(msg_text)
        else:
            await message.reply(
                f"Вы выиграли {actual_change} очков! Ваш баланс: {new_balance}"
            )

    # 2. Банкрот (баланс стал <= 0, но был > 0)
    elif new_balance <= 0:
        player_name = html.escape(message.from_user.first_name)
        bankrupt_phrases = [
            "Вы банкрот! Звоните в екапусту или заложите квартиру",
            "ВЫ — БАНКРОТ!",
            "Поздравляем! Вы успешно достигли финансового дна. 📉",
            "Ваш баланс ушел в отрицательные значения, как и настроение вашего банкира. 💸",
            "Гейм овер. Коллекторы уже выехали. 🚗💨",
            "Кажется, удача взяла выходной. Ваш баланс: 0. 🤷‍♂️",
            "Вам пора открывать сбор средств на доширак. 🍜",
            f"{player_name} собирается в понедельник начать жизнь с нуля. Так бывает после проведенного воскресенья в казино.",
            "Добро пожаловать в клуб анонимных банкротов.",
            f"Сначала {player_name} играл в казино, а потом - на гармошке у прохожих на виду...",
            f"{player_name} из богатой семьи сходил в казино и стал из небогатой.",
            "Иди работать или клянчить фишки у друзей.",
            "Друзья! Подкиньте нищему на додеп.",
            "Упс! Вы всё пролудили и вам пора работать."
        ]
        await message.reply(random.choice(bankrupt_phrases))
    
    # 3. Обычный проигрыш - удаляем сообщение через минуту
    else:
        asyncio.create_task(delete_message_later(message))

