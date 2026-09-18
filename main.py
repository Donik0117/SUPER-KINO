import os
import sys
import asyncio
from dotenv import load_dotenv
from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, FSInputFile
)
from aiogram.exceptions import TelegramRetryAfter

os.chdir(os.path.dirname(os.path.abspath(__file__)))
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import database as db

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

CATEGORIES = ["🎬 Kinolar", "⛩ Anime", "📺 Seriallar", "🎭 Dramalar", "🎞 Multfilm"]

# --- FSM Holatlar ---
class AddContentState(StatesGroup):
    code = State()
    title = State()
    category = State()
    video = State()

class SearchState(StatesGroup):
    query = State()

class DelContentState(StatesGroup):
    code = State()

class AddChannelState(StatesGroup):
    channel_id = State()
    title = State()
    url = State()

class BroadcastState(StatesGroup):
    message = State()

# --- Klaviaturalar ---
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Kinolar"), KeyboardButton(text="⛩ Anime")],
            [KeyboardButton(text="📺 Seriallar"), KeyboardButton(text="🎭 Dramalar")],
            [KeyboardButton(text="🔍 Qidirish"), KeyboardButton(text="🔝 Top 10")],
            [KeyboardButton(text="🎲 Tasodifiy"), KeyboardButton(text="ℹ️ Bot haqida")]
        ],
        resize_keyboard=True
    )

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi kontent qo'shish", callback_data="adm_add_content")],
        [InlineKeyboardButton(text="🗑 Kontentni o'chirish", callback_data="adm_del_content")],
        [InlineKeyboardButton(text="📢 Kanallarni boshqarish (OP)", callback_data="adm_channels")],
        [InlineKeyboardButton(text="✉️ Xabar tarqatish (Rassilka)", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats")],
        [InlineKeyboardButton(text="💾 Baza yuklab olish", callback_data="adm_backup")]
    ])

def category_choose_kb():
    buttons = []
    row = []
    for cat in CATEGORIES:
        clean_cat = cat.split(" ")[-1]
        row.append(InlineKeyboardButton(text=cat, callback_data=f"setcat_{clean_cat}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_pagination_kb(items, total, page, category_name, limit=6):
    buttons = []
    for code, title in items:
        buttons.append([InlineKeyboardButton(text=f"▶️ {title} ({code})", callback_data=f"get_{code}")])
    
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️ Oldingi", callback_data=f"pg_{category_name}_{page - 1}"))
    
    max_page = (total + limit - 1) // limit
    if max_page == 0:
        max_page = 1
    nav_row.append(InlineKeyboardButton(text=f"{page}/{max_page}", callback_data="noop"))
    
    if page < max_page:
        nav_row.append(InlineKeyboardButton(text="Keyingi ▶️", callback_data=f"pg_{category_name}_{page + 1}"))
    
    if nav_row:
        buttons.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def subscription_kb(channels):
    buttons = []
    for _, _, title, url in channels:
        buttons.append([InlineKeyboardButton(text=f"➕ {title}", url=url)])
    buttons.append([InlineKeyboardButton(text="✅ A'zo bo'ldim / Tekshirish", callback_data="check_subscription")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Obuna tekshirish ---
async def is_subscribed(user_id: int):
    channels = await db.get_channels()
    if not channels:
        return True, []
    unsub = []
    for ch in channels:
        try:
            m = await bot.get_chat_member(chat_id=ch[1], user_id=user_id)
            if m.status in ["left", "kicked"]:
                unsub.append(ch)
        except Exception:
            pass
    return len(unsub) == 0, unsub

# Avtomatik zaxiralash funksiyasi
async def send_auto_backup(extra_info=""):
    try:
        if os.path.exists("kino_master.db") and ADMIN_ID:
            file = FSInputFile("kino_master.db")
            caption = f"💾 <b>Avtomatik Zaxira (Backup)</b>\n{extra_info}\nServer o'chsa ham ushbu faylni botga yuborib qayta tiklashingiz mumkin!"
            await bot.send_document(chat_id=ADMIN_ID, document=file, caption=caption, parse_mode="HTML")
    except Exception:
        pass

# --- START & DEEP LINK ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message, command: CommandObject):
    await db.add_user(message.from_user.id)
    passed, _ = await is_subscribed(message.from_user.id)
    if not passed:
        chs = await db.get_channels()
        await message.answer(
            "⚠️ <b>Botdan to'liq foydalanish uchun rasmiy kanallarga a'zo bo'ling:</b>",
            reply_markup=subscription_kb(chs),
            parse_mode="HTML"
        )
        return

    code = command.args
    if code:
        movie = await db.get_movie_by_code(code)
        if movie:
            file_id, caption, title, views, category = movie
            bot_info = await bot.get_me()
            share_url = f"https://t.me/share/url?url=https://t.me/{bot_info.username}?start={code}&text={title}"
            share_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↗️ Do'stlarga ulashish", url=share_url)]
            ])
            await message.answer_video(video=file_id, caption=f"{caption}\n\n📁 Kategoriya: #{category}\n👀 Ko'rishlar: {views}", reply_markup=share_kb)
            return

    await message.answer(
        f"👋 <b>Assalomu alaykum, {message.from_user.full_name}!</b>\n\n"
        "🍿 <b>Kino, Anime, Serial va Dramalar olamiga xush kelibsiz!</b>\n\n"
        "Kerakli bo'limni tanlang yoki to'g'ridan-to'g'ri <b>kodni</b> yuboring:",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "check_subscription")
async def check_sub_cb(call: types.CallbackQuery):
    passed, _ = await is_subscribed(call.from_user.id)
    if passed:
        await call.message.delete()
        await call.message.answer("🎉 <b>Rahmat!</b> Bo'limlardan birini tanlang yoki kino kodini yuboring:", reply_markup=main_menu(), parse_mode="HTML")
    else:
        await call.answer("❌ Hali hamma kanallarga a'zo bo'lmadingiz!", show_alert=True)

# --- BO'LIMLAR ---
@dp.message(F.text.in_(["🎬 Kinolar", "⛩ Anime", "📺 Seriallar", "🎭 Dramalar"]))
async def category_handler(message: types.Message):
    passed, _ = await is_subscribed(message.from_user.id)
    if not passed:
        chs = await db.get_channels()
        await message.answer("⚠️ Avval kanallarga a'zo bo'ling:", reply_markup=subscription_kb(chs))
        return

    cat_name = message.text.split(" ")[-1]
    items, total = await db.get_movies_by_category(cat_name, page=1, limit=6)
    
    if not items:
        await message.answer(f"📁 <b>{message.text}</b> bo'limida hozircha kontent mavjud emas. Tez orada yuklanadi!", parse_mode="HTML")
        return

    kb = build_pagination_kb(items, total, page=1, category_name=cat_name, limit=6)
    await message.answer(f"📁 <b>{message.text}</b> ro'yxati (Jami: {total} ta):", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("pg_"))
async def pagination_cb(call: types.CallbackQuery):
    _, cat_name, page_str = call.data.split("_")
    page = int(page_str)
    items, total = await db.get_movies_by_category(cat_name, page=page, limit=6)
    kb = build_pagination_kb(items, total, page=page, category_name=cat_name, limit=6)
    await call.message.edit_reply_markup(reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "noop")
async def noop_cb(call: types.CallbackQuery):
    await call.answer()

# --- QIDIRUV ---
@dp.message(F.text == "🔍 Qidirish")
async def search_cmd(message: types.Message, state: FSMContext):
    await message.answer("🔎 Qidirmoqchi bo'lgan kino, anime yoki serial <b>nomini</b> yoki <b>kodini</b> yozing:", parse_mode="HTML")
    await state.set_state(SearchState.query)

@dp.message(SearchState.query)
async def process_search_query(message: types.Message, state: FSMContext):
    await state.clear()
    query = message.text.strip()
    
    movie = await db.get_movie_by_code(query)
    if movie:
        file_id, caption, title, views, category = movie
        await message.answer_video(video=file_id, caption=f"{caption}\n\n📁 Kategoriya: #{category}\n👀 Ko'rishlar: {views}")
        return

    results = await db.search_movies_by_title(query)
    if results:
        buttons = []
        for code, title, cat in results:
            buttons.append([InlineKeyboardButton(text=f"▶️ [{cat}] {title} ({code})", callback_data=f"get_{code}")])
        await message.answer(f"🔍 <b>'{query}'</b> bo'yicha topilgan natijalar:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    else:
        await message.answer("😔 Kechirasiz, bunday nom yoki kod bilan hech narsa topilmadi.")

# --- TOP 10 ---
@dp.message(F.text == "🔝 Top 10")
async def top_movies_handler(message: types.Message):
    tops = await db.get_top_movies(10)
    if not tops:
        await message.answer("Bazada hali kontent yo'q.")
        return
    text = "🔥 <b>Eng ko'p ko'rilgan TOP 10 kontent:</b>\n\n"
    buttons = []
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for idx, (code, title, views, cat) in enumerate(tops):
        icon = medals[idx] if idx < len(medals) else f"{idx+1}."
        text += f"{icon} <b>{title}</b> (#{cat}) — <i>{views} marta ko'rilgan</i> (Kodi: <code>{code}</code>)\n"
        buttons.append([InlineKeyboardButton(text=f"▶️ {title}", callback_data=f"get_{code}")])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

# --- TASODIFIY ---
@dp.message(F.text == "🎲 Tasodifiy")
async def random_movie_handler(message: types.Message):
    movie = await db.get_random_movie()
    if movie:
        file_id, caption, code, title, category = movie
        await message.answer_video(video=file_id, caption=f"🎲 <b>Tasodifiy tanlov:</b> {title}\n\n{caption}\n\n🔢 Kodi: <code>{code}</code>\n📁 #{category}", parse_mode="HTML")
    else:
        await message.answer("Bazada hali filmlar mavjud emas.")

# --- BOT HAQIDA ---
@dp.message(F.text == "ℹ️ Bot haqida")
async def about_handler(message: types.Message):
    await message.answer(
        "🍿 <b>Kino, Anime & Serial Bot</b>\n\n"
        "⚡️ Barcha sevimli filmlar, animelar, seriallar va dramalarni bir joyda tomosha qiling!\n\n"
        "🎯 Shunchaki qidiruvga nomini yozing yoki kodini kiriting!",
        parse_mode="HTML"
    )

# --- ADMIN PANEL ---
@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("👑 <b>Admin Boshqaruv Markazi:</b>", reply_markup=admin_menu(), parse_mode="HTML")

# Baza zaxira nusxasi yuklab olish (/backup)
@dp.message(Command("backup"))
@dp.callback_query(F.data == "adm_backup")
async def adm_backup_cb(event: types.Message | types.CallbackQuery):
    msg = event if isinstance(event, types.Message) else event.message
    if msg.chat.id != ADMIN_ID:
        return
    if os.path.exists("kino_master.db"):
        await msg.answer_document(
            FSInputFile("kino_master.db"),
            caption="💾 <b>Kino Bot Ma'lumotlar Bazasi Zaxirasi</b>\nUshbu fayl barcha yuklangan kinolaringiz, foydalanuvchilar va kanallarni o'z ichiga oladi."
        )
    if isinstance(event, types.CallbackQuery):
        await event.answer()

# Baza tiklash (Admin .db fayl yuborsa, uni qabul qilib bazani tiklaydi)
@dp.message(F.document, F.chat.id == ADMIN_ID)
async def restore_database(message: types.Message):
    if message.document.file_name and message.document.file_name.endswith(".db"):
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, "kino_master.db")
        await db.init_db()
        await message.answer("✅ <b>Baza muvaffaqiyatli qayta tiklandi!</b> Barcha kinolaringiz saqlanib qoldi.", parse_mode="HTML")

@dp.callback_query(F.data == "adm_stats")
async def adm_stats_cb(call: types.CallbackQuery):
    users, movies, views, cat_stats = await db.get_statistics()
    text = (
        f"📊 <b>Bot Statistikasi:</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{users:,}</b> ta\n"
        f"🎬 Jami kontent: <b>{movies}</b> ta\n"
        f"👀 Jami ko'rishlar: <b>{views:,}</b> marta\n\n"
        f"📂 <b>Kategoriyalar bo'yicha:</b>\n"
    )
    for cat, count in cat_stats:
        text += f" • {cat}: <b>{count}</b> ta\n"
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()

# Kontent qo'shish
@dp.callback_query(F.data == "adm_add_content")
async def add_c_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("📝 Yangi kontent uchun <b>kod</b> kiriting (masalan: <code>101</code>):", parse_mode="HTML")
    await state.set_state(AddContentState.code)
    await call.answer()

@dp.message(AddContentState.code)
async def add_c_code(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await message.answer("🎬 Kontent <b>nomini</b> kiriting (masalan: <i>Naruto Shippuden 1-fasl</i>):", parse_mode="HTML")
    await state.set_state(AddContentState.title)

@dp.message(AddContentState.title)
async def add_c_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer("📁 Qaysi <b>bo'limga</b> tegishli ekanligini tanlang:", reply_markup=category_choose_kb(), parse_mode="HTML")
    await state.set_state(AddContentState.category)

@dp.callback_query(AddContentState.category, F.data.startswith("setcat_"))
async def add_c_cat(call: types.CallbackQuery, state: FSMContext):
    cat_val = call.data.replace("setcat_", "")
    await state.update_data(category=cat_val)
    await call.message.answer(f"✅ Tanlangan bo'lim: <b>{cat_val}</b>\n\n🎥 Endi <b>video faylni</b> yuboring:", parse_mode="HTML")
    await state.set_state(AddContentState.video)
    await call.answer()

@dp.message(AddContentState.video, F.video)
async def add_c_video(message: types.Message, state: FSMContext):
    data = await state.get_data()
    file_id = message.video.file_id
    caption = message.caption or f"🎬 {data['title']}\n\n🔢 Kodi: {data['code']}"
    
    await db.add_movie(
        code=data['code'],
        title=data['title'],
        category=data['category'],
        file_id=file_id,
        caption=caption
    )
    bot_me = await bot.get_me()
    deep_link = f"https://t.me/{bot_me.username}?start={data['code']}"
    await message.answer(
        f"✅ <b>Muvaffaqiyatli saqlandi!</b>\n\n"
        f"📌 Nomi: <b>{data['title']}</b>\n"
        f"📁 Bo'limi: <b>{data['category']}</b>\n"
        f"🔢 Kodi: <code>{data['code']}</code>\n"
        f"🔗 Reklama havolasi: <code>{deep_link}</code>",
        parse_mode="HTML"
    )
    await state.clear()
    
    # Har bir yangi kino qo'shilganda zaxira nusxasini avtomatik yuborish
    await send_auto_backup(f"Yangi qo'shildi: {data['title']} ({data['code']})")

# Kontent o'chirish
@dp.callback_query(F.data == "adm_del_content")
async def del_c_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("🗑 O'chirmoqchi bo'lgan kontent <b>kodini</b> yozing:", parse_mode="HTML")
    await state.set_state(DelContentState.code)
    await call.answer()

@dp.message(DelContentState.code)
async def del_c_finish(message: types.Message, state: FSMContext):
    await db.delete_movie(message.text.strip())
    await message.answer("✅ Muvaffaqiyatli o'chirildi.")
    await state.clear()

# Kanallar
@dp.callback_query(F.data == "adm_channels")
async def ch_list_cb(call: types.CallbackQuery):
    chs = await db.get_channels()
    kb = [[InlineKeyboardButton(text=f"❌ O'chirish: {c[2]}", callback_data=f"delch_{c[0]}")] for c in chs]
    kb.append([InlineKeyboardButton(text="➕ Yangi kanal qo'shish", callback_data="add_ch")])
    await call.message.answer("📢 <b>Homiy kanallar ro'yxati:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("delch_"))
async def del_ch_cb(call: types.CallbackQuery):
    cid = int(call.data.replace("delch_", ""))
    await db.delete_channel(cid)
    await call.message.answer("✅ Kanal o'chirildi.")
    await call.answer()

@dp.callback_query(F.data == "add_ch")
async def add_ch_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Kanal <b>ID</b> yoki <b>@username</b>ini yuboring:", parse_mode="HTML")
    await state.set_state(AddChannelState.channel_id)
    await call.answer()

@dp.message(AddChannelState.channel_id)
async def add_ch_id(message: types.Message, state: FSMContext):
    await state.update_data(channel_id=message.text.strip())
    await message.answer("Kanal uchun nom yozing:")
    await state.set_state(AddChannelState.title)

@dp.message(AddChannelState.title)
async def add_ch_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer("Kanalga havola (link) yuboring:")
    await state.set_state(AddChannelState.url)

@dp.message(AddChannelState.url)
async def add_ch_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await db.add_channel(data['channel_id'], data['title'], message.text.strip())
    await message.answer("✅ Kanal muvaffaqiyatli qo'shildi! Botni o'sha kanalga admin qilishni unutmang.")
    await state.clear()

# Rassilka (Telegram cheklovlaridan himoyalangan)
@dp.callback_query(F.data == "adm_broadcast")
async def broad_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("📢 Tarqatmoqchi bo'lgan xabaringizni yuboring:")
    await state.set_state(BroadcastState.message)
    await call.answer()

@dp.message(BroadcastState.message)
async def broad_finish(message: types.Message, state: FSMContext):
    users = await db.get_all_users()
    count = 0
    await message.answer(f"⏳ {len(users)} ta foydalanuvchiga yuborilmoqda...")
    for uid in users:
        try:
            await message.copy_to(chat_id=uid)
            count += 1
            await asyncio.sleep(0.04)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await message.copy_to(chat_id=uid)
                count += 1
            except Exception:
                pass
        except Exception:
            pass
    await message.answer(f"✅ Xabar yuborildi: {count} kishiga.")
    await state.clear()

# Inline orqali kino olish
@dp.callback_query(F.data.startswith("get_"))
async def get_inline_movie(call: types.CallbackQuery):
    code = call.data.replace("get_", "")
    movie = await db.get_movie_by_code(code)
    if movie:
        file_id, caption, title, views, category = movie
        await call.message.answer_video(video=file_id, caption=f"{caption}\n\n📁 #{category}\n👀 Ko'rishlar: {views}")
    await call.answer()

# Oddiy xabarlar (kod yozilganda)
@dp.message(F.text)
async def handle_direct_code(message: types.Message):
    passed, _ = await is_subscribed(message.from_user.id)
    if not passed:
        chs = await db.get_channels()
        await message.answer("⚠️ Avval kanallarga a'zo bo'ling:", reply_markup=subscription_kb(chs))
        return

    text = message.text.strip()
    movie = await db.get_movie_by_code(text)
    if movie:
        file_id, caption, title, views, category = movie
        await message.answer_video(video=file_id, caption=f"{caption}\n\n📁 #{category}\n👀 Ko'rishlar: {views}")
    else:
        await message.answer("😔 Kechirasiz, bunday kod topilmadi. Qidirish uchun '🔍 Qidirish' tugmasidan foydalaning.")

# --- 24/7 KEEP-ALIVE VA KUNLIK AVTO-ZAXIRA ---
async def health_check(request):
    return web.Response(text="Kino & Anime Bot 24/7 faol ishlamoqda!")

async def start_web_server():
    port = int(os.getenv("PORT", 8080))
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/ping", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server {port}-portda ishga tushdi.")

async def self_ping_task():
    """Render bepul tarifda uxlab qolmasligi uchun har 9 daqiqada o'z-o'ziga ping yuboradi"""
    await asyncio.sleep(60)
    url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PING_URL")
    if not url:
        return
    print(f"24/7 Keep-Alive faollashtirildi: {url}")
    while True:
        try:
            async with ClientSession() as session:
                async with session.get(url) as resp:
                    pass
        except Exception:
            pass
        await asyncio.sleep(540)

async def daily_backup_task():
    """Har 24 soatda adminga bazani yuborib turadi"""
    while True:
        await asyncio.sleep(86400)
        await send_auto_backup("📅 Kunlik rejaviy zaxira")

async def main():
    await db.init_db()
    if os.getenv("PORT"):
        asyncio.create_task(start_web_server())
        asyncio.create_task(self_ping_task())
    asyncio.create_task(daily_backup_task())
    print(">>> BOT TAYYOR VA ISHGA TUSHDI! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
