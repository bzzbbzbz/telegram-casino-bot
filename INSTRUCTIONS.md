# Инструкция по расширению функционала бота для групповых чатов

Следуйте этим шагам, чтобы добавить поддержку групповых чатов, сохранение баланса в SQLite, команду /balance и логику обработки выигрышей/проигрышей.

## Шаг 1: Установка зависимостей

Нам понадобится библиотека `aiosqlite` для асинхронной работы с базой данных SQLite.

1.  Откройте `pyproject.toml`.
2.  В секцию `dependencies` добавьте `"aiosqlite>=0.19.0"`.
3.  Если вы используете `uv` или `pip`, обновите окружение.

## Шаг 2: Создание слоя работы с базой данных

Создайте новый файл `bot/db.py`. В нем мы опишем класс для работы с SQLite.

```python
import aiosqlite
from pathlib import Path

class Database:
    def __init__(self, db_path: str = "casino.db"):
        self.db_path = db_path

    async def create_tables(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER NOT NULL DEFAULT 0
                )
            """)
            await db.commit()

    async def get_balance(self, user_id: int, default_balance: int = 0) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0]
                
                # Если пользователя нет, создаем его
                await db.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, default_balance))
                await db.commit()
                return default_balance

    async def update_balance(self, user_id: int, amount: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            await db.commit()
            
    async def set_balance(self, user_id: int, new_balance: int):
         async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
            await db.commit()
```

## Шаг 3: Создание обработчика для групповых чатов

Создайте файл `bot/handlers/group_games.py`. Здесь будет логика перехвата кубика, проверки баланса и удаления сообщений банкротов.

```python
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
```

## Шаг 4: Обновление точки входа (`bot/__main__.py`)

Нам нужно инициализировать базу данных, убрать фильтр приватных чатов и зарегистрировать новый роутер.

1.  **Уберите фильтр приватных чатов.**
    Найдите и удалите или закомментируйте строку:
    ```python
    # dp.message.filter(F.chat.type == "private")  <-- Удалить или закомментировать
    ```

2.  **Инициализация БД.**
    В начале функции `main`:
    ```python
    from bot.db import Database
    # ...
    db = Database()
    await db.create_tables()
    ```

3.  **Передача БД в диспетчер.**
    Добавьте `db=db` в `Dispatcher`:
    ```python
    dp = Dispatcher(
        storage=storage,
        l10n=l10n,
        game_config=game_config,
        db=db,  # <-- Добавляем сюда
    )
    ```

4.  **Регистрация нового роутера.**
    Добавьте импорт и включите роутер:
    ```python
    from bot.handlers import default_commands, spin, group_games # <-- Добавить импорт

    # ...
    
    dp.include_router(group_games.router) # <-- Добавить регистрацию
    ```

## Шаг 5: (Опционально) Обновление существующей логики (`bot/handlers/spin.py`)

Если вы хотите, чтобы команда `/spin` в ЛС тоже использовала общую базу данных, вам нужно будет обновить `cmd_spin` в `bot/handlers/spin.py`:
1.  Добавить аргумент `db: Database`.
2.  Заменить использование `state.get_data` и `state.update_data` на вызовы `db.get_balance` и `db.set_balance`.

Теперь бот будет слушать отправку эмодзи 🎰 в любых чатах, обрабатывать команду `/balance`, удалять сообщения банкротов и сохранять результаты в `casino.db`.
