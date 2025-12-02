import aiosqlite
from pathlib import Path

class Database:
    def __init__(self, db_path: str = "casino.db"):
        self.db_path = db_path

    async def create_tables(self):
        async with aiosqlite.connect(self.db_path) as db:
            # 1. Users table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    nickname TEXT,
                    balance INTEGER NOT NULL DEFAULT 0,
                    bid INTEGER DEFAULT 1,
                    state TEXT DEFAULT 'IDLE',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 2. Event history table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS event_history (
                    event_id TEXT PRIMARY KEY,
                    user_id INTEGER,
                    event_type TEXT NOT NULL,
                    amount INTEGER DEFAULT 0,
                    metadata TEXT, -- JSON storage
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
            """)

            # 3. AI Credit Sessions
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ai_credit_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER,
                    status TEXT DEFAULT 'active', -- active, completed, rejected
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    finished_at DATETIME,
                    ai_score INTEGER,
                    reward_amount INTEGER,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
            """)

            # 4. AI Dialogue Messages
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ai_dialogue_messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT NOT NULL, -- user, assistant
                    content TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES ai_credit_sessions(session_id)
                )
            """)
            
            # Attempt to migrate existing users table (add new columns if missing)
            # This is a basic migration strategy for development
            try:
                await db.execute("ALTER TABLE users ADD COLUMN nickname TEXT")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE users ADD COLUMN bid INTEGER DEFAULT 10")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE users ADD COLUMN state TEXT DEFAULT 'IDLE'")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE users ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP")
            except Exception:
                pass

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

