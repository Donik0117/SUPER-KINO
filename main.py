import sys
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, FSInputFile

import database as db

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class AddMovieState(StatesGroup):
    code = State()
    title = State()
    video = State()

class DelMovieState(StatesGroup):
    code = State()

class AddChannelState(StatesGroup):
    channel_id = State()
    title = State()
    url = State()

class BroadcastState(StatesGroup):
    message = State()

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎲 Tasodifiy kino"), KeyboardButton(text="ℹ️ Bot haqida")]
        ],
        resize_keyboard=True
    )

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Yangi kino qo'shish", callback_data="adm_add_movie")],
        [InlineKeyboardButton(text="🗑 Kinoni o'chirish", callback_data="adm_del_movie")],
        [InlineKeyboardButton(text="📢 Kanallarni boshqarish", callback_data="adm_channels")],
        [InlineKeyboardButton(text="✉️ Xabar tarqatish", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats")],
        [InlineKeyboardButton(text="💾 Baza yuklab olish", callback_data="adm_backup")]
    ])

def subscription_kb(channels):
    buttons = []
    for _, _, title, url in channels:
        buttons.append([InlineKeyboardButton(text=f"➕ {title}", url=url)])
    buttons.append([InlineKeyboardButton(text="✅ A'zo bo'ldim / Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def is_subscribed(user_id: int):
    channels = await db.get_channels()
    if not channels:
        return True
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch[1], user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            pass
    return True

@dp.message(CommandStart())
async def start_cmd(message: types.Message, command: CommandObject):
    await db.add_user(message.from_user.id)
    if not await is_subscribed(message.from_user.id):
        chs = await db.get_channels()
        await message.answer("⚠️ <b>Kino ko'rish uchun quyidagi kanallarga a'zo bo'ling:</b>", reply_markup=subscription_kb(chs), parse_mode="HTML")
        return

    code = command.args
    if code:
        movie = await db.get_movie_by_code(code)
        if movie:
            file_id, caption, title, _ = movie
            await message.answer_video(video=file_id, caption=caption)
            return

    await message.answer("👋 <b>Assalomu alaykum!</b>\n\n🎬 Kino ko'rish uchun uning <b>kodini</b> yuboring:", reply_markup=main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "check_sub")
async def check_sub_cb(call: types.CallbackQuery):
    if await is_subscribed(call.from_user.id):
        await call.message.delete()
        await call.message.answer("✅ A'zo bo'ldingiz! Endi kino kodini yuborishingiz mumkin.", reply_markup=main_menu())
    else:
        await call.answer("❌ Hamma kanallarga a'zo bo'lmadingiz!", show_alert=True)

@dp.message(F.text == "🎲 Tasodifiy kino")
async def random_movie(message: types.Message):
    movie = await db.get_random_movie()
    if movie:
        file_id, caption, code, _ = movie
        await message.answer_video(video=file_id, caption=f"{caption}\n\n🔢 Kodi: <code>{code}</code>", parse_mode="HTML")
    else:
        await message.answer("Bazada hali kinolar mavjud emas.")

@dp.message(F.text == "ℹ️ Bot haqida")
async def about(message: types.Message):
    await message.answer("🍿 Ushbu bot orqali eng sara filmlarni tezkor yuklab olishingiz mumkin.")

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("👑 <b>Admin Paneli:</b>", reply_markup=admin_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_stats")
async def adm_stats(call: types.CallbackQuery):
    users, movies, views = await db.get_statistics()
    await call.message.answer(f"📊 <b>Statistika:</b>\n\n👥 Foydalanuvchilar: <b>{users}</b>\n🎬 Kinolar: <b>{movies}</b>\n👀 Ko'rishlar: <b>{views}</b>", parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "adm_backup")
async def adm_backup(call: types.CallbackQuery):
    if os.path.exists("kino_master.db"):
        await call.message.answer_document(FSInputFile("kino_master.db"), caption="💾 Baza zaxirasi.")
    await call.answer()

@dp.callback_query(F.data == "adm_add_movie")
async def add_m_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Kino uchun <b>kod</b> kiriting (masalan: <code>101</code>):", parse_mode="HTML")
    await state.set_state(AddMovieState.code)
    await call.answer()

@dp.message(AddMovieState.code)
async def add_m_code(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await message.answer("Film <b>nomini</b> kiriting:")
    await state.set_state(AddMovieState.title)

@dp.message(AddMovieState.title)
async def add_m_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer("Endi kino <b>videosini</b> yuboring:")
    await state.set_state(AddMovieState.video)

@dp.message(AddMovieState.video, F.video)
async def add_m_video(message: types.Message, state: FSMContext):
    data = await state.get_data()
    file_id = message.video.file_id
    caption = message.caption or f"🎬 {data['title']}\n🔢 Kodi: {data['code']}"
    await db.add_movie(data['code'], data['title'], file_id, caption)
    await message.answer(f"✅ Kino saqlandi!\nNomi: {data['title']}\nKodi: {data['code']}")
    await state.clear()

@dp.callback_query(F.data == "adm_del_movie")
async def del_m_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("O'chirmoqchi bo'lgan kino <b>kodini</b> yuboring:", parse_mode="HTML")
    await state.set_state(DelMovieState.code)
    await call.answer()

@dp.message(DelMovieState.code)
async def del_m_finish(message: types.Message, state: FSMContext):
    await db.delete_movie(message.text.strip())
    await message.answer("✅ Kino o'chirildi.")
    await state.clear()

@dp.callback_query(F.data == "adm_channels")
async def ch_list(call: types.CallbackQuery):
    chs = await db.get_channels()
    kb = [[InlineKeyboardButton(text=f"❌ {c[2]}", callback_data=f"delch_{c[0]}")] for c in chs]
    kb.append([InlineKeyboardButton(text="➕ Yangi kanal qo'shish", callback_data="add_ch")])
    await call.message.answer("📢 Kanallar ro'yxati:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("delch_"))
async def del_ch(call: types.CallbackQuery):
    cid = int(call.data.split("_")[1])
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
    await message.answer("Kanal nomini yozing:")
    await state.set_state(AddChannelState.title)

@dp.message(AddChannelState.title)
async def add_ch_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer("Kanalga kirish havolasini (link) yuboring:")
    await state.set_state(AddChannelState.url)

@dp.message(AddChannelState.url)
async def add_ch_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await db.add_channel(data['channel_id'], data['title'], message.text.strip())
    await message.answer("✅ Kanal qo'shildi! Botni o'sha kanalga admin qilishni unutmang.")
    await state.clear()

@dp.callback_query(F.data == "adm_broadcast")
async def broad_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Barchaga tarqatmoqchi bo'lgan xabaringizni yuboring:")
    await state.set_state(BroadcastState.message)
    await call.answer()

@dp.message(BroadcastState.message)
async def broad_finish(message: types.Message, state: FSMContext):
    users = await db.get_all_users()
    count = 0
    await message.answer(f"⏳ {len(users)} kishiga yuborilmoqda...")
    for uid in users:
        try:
            await message.copy_to(chat_id=uid)
            count += 1
            await asyncio.sleep(0.04)
        except Exception:
            pass
    await message.answer(f"✅ Xabar yuborildi: {count} kishiga.")
    await state.clear()

@dp.message(F.text)
async def search_handler(message: types.Message):
    if not await is_subscribed(message.from_user.id):
        chs = await db.get_channels()
        await message.answer("⚠️ <b>Kanallarga a'zo bo'ling:</b>", reply_markup=subscription_kb(chs), parse_mode="HTML")
        return

    text = message.text.strip()
    movie = await db.get_movie_by_code(text)
    if movie:
        file_id, caption, _, _ = movie
        await message.answer_video(video=file_id, caption=caption)
        return

    results = await db.search_movies_by_title(text)
    if results:
        kb = [[InlineKeyboardButton(text=f"🎬 {t} (Kodi: {c})", callback_data=f"get_{c}")] for c, t in results]
        await message.answer("🔍 <b>Qidiruv natijalari:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    else:
        await message.answer("😔 Bunday kod yoki nomli kino topilmadi.")

@dp.callback_query(F.data.startswith("get_"))
async def get_cb(call: types.CallbackQuery):
    c = call.data.replace("get_", "")
    m = await db.get_movie_by_code(c)
    if m:
        await call.message.answer_video(video=m[0], caption=m[1])
    await call.answer()


from aiohttp import web

async def health_check(request):
    return web.Response(text="Kino Bot 24/7 faol ishlamoqda!")

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

async def main():
    if os.getenv('PORT'):
        asyncio.create_task(start_web_server())
    await db.init_db()
    print(">>> BOT ISHGA TUSHDI! <<<")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
