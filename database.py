import aiosqlite

DB_NAME = "kino_master.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                code TEXT PRIMARY KEY,
                title TEXT,
                category TEXT DEFAULT 'Kino',
                file_id TEXT,
                caption TEXT,
                views INTEGER DEFAULT 0
            )
        """)
        # Agar eski bazada category ustuni bo'lmasa, qo'shamiz
        try:
            await db.execute("ALTER TABLE movies ADD COLUMN category TEXT DEFAULT 'Kino'")
            await db.commit()
        except Exception:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT UNIQUE,
                title TEXT,
                url TEXT
            )
        """)
        await db.commit()

async def add_user(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]

async def add_movie(code: str, title: str, category: str, file_id: str, caption: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT OR REPLACE INTO movies (code, title, category, file_id, caption)
            VALUES (?, ?, ?, ?, ?)
        """, (code.strip(), title.strip(), category, file_id, caption))
        await db.commit()

async def get_movie_by_code(code: str):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT file_id, caption, title, views, category FROM movies WHERE code = ?", (code.strip(),)
        ) as cur:
            row = await cur.fetchone()
            if row:
                await db.execute("UPDATE movies SET views = views + 1 WHERE code = ?", (code.strip(),))
                await db.commit()
            return row

async def get_movies_by_category(category: str, page: int = 1, limit: int = 6):
    offset = (page - 1) * limit
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT code, title FROM movies WHERE category = ? ORDER BY rowid DESC LIMIT ? OFFSET ?",
            (category, limit, offset)
        ) as cur:
            items = await cur.fetchall()
        async with db.execute("SELECT COUNT(*) FROM movies WHERE category = ?", (category,)) as cur2:
            total = (await cur2.fetchone())[0]
        return items, total

async def get_top_movies(limit: int = 10):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT code, title, views, category FROM movies ORDER BY views DESC LIMIT ?", (limit,)
        ) as cur:
            return await cur.fetchall()

async def search_movies_by_title(query: str):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT code, title, category FROM movies WHERE title LIKE ? LIMIT 10", (f"%{query}%",)
        ) as cur:
            return await cur.fetchall()

async def delete_movie(code: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM movies WHERE code = ?", (code.strip(),))
        await db.commit()

async def get_random_movie(category: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        if category:
            query = "SELECT file_id, caption, code, title, category FROM movies WHERE category = ? ORDER BY RANDOM() LIMIT 1"
            params = (category,)
        else:
            query = "SELECT file_id, caption, code, title, category FROM movies ORDER BY RANDOM() LIMIT 1"
            params = ()
        async with db.execute(query, params) as cur:
            return await cur.fetchone()

async def add_channel(channel_id: str, title: str, url: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO channels (channel_id, title, url) VALUES (?, ?, ?)", (channel_id.strip(), title, url.strip()))
        await db.commit()

async def get_channels():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, channel_id, title, url FROM channels") as cur:
            return await cur.fetchall()

async def delete_channel(ch_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM channels WHERE id = ?", (ch_id,))
        await db.commit()

async def get_statistics():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c1:
            total_users = (await c1.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM movies") as c2:
            total_movies = (await c2.fetchone())[0]
        async with db.execute("SELECT SUM(views) FROM movies") as c3:
            total_views = (await c3.fetchone())[0] or 0
        async with db.execute("SELECT category, COUNT(*) FROM movies GROUP BY category") as c4:
            cat_stats = await c4.fetchall()
        return total_users, total_movies, total_views, cat_stats
