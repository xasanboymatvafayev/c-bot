"""
Casino Telegram Bot
aiogram 3.x + Python
"""
import asyncio
import random
import string
import bcrypt
import httpx
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
API_BASE = os.getenv("API_BASE", "http://localhost:8000/api")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "admin_super_secret_token")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",") if os.getenv("ADMIN_IDS") else []))
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@your_channel")  # Majburiy kanal
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://yourdomain.com")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ========================
# FSM STATES
# ========================

class DepositStates(StatesGroup):
    waiting_amount = State()

class AdminStates(StatesGroup):
    waiting_user_id = State()
    waiting_action = State()
    waiting_amount = State()
    waiting_lose_percent = State()

# ========================
# UTILITY
# ========================

def generate_credentials():
    """Login va parol yaratish"""
    login = "user_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    password = "".join(random.choices(string.ascii_letters + string.digits + "!@#", k=10))
    return login, password

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

async def check_subscription(user_id: int) -> bool:
    """Kanal obunasini tekshirish"""
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status not in ["left", "kicked", "banned"]
    except Exception:
        return True  # Kanal yo'q bo'lsa o'tkazib yuborish

async def api_post(endpoint: str, data: dict, token: str = None) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{API_BASE}{endpoint}", json=data, headers=headers)
        return resp.json()

async def api_get(endpoint: str, token: str = None, params: dict = None) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{API_BASE}{endpoint}", headers=headers, params=params)
        return resp.json()

async def register_user(telegram_id: int, username: str = None):
    """Yangi foydalanuvchi ro'yxatdan o'tkazish"""
    login, password = generate_credentials()
    password_hash = hash_password(password)
    
    # API orqali yaratish - to'g'ridan-to'g'ri DB ga
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{API_BASE}/auth/register", 
            headers={"X-Admin-Token": ADMIN_TOKEN},
            json={
                "telegram_id": telegram_id,
                "username": username,
                "login": login,
                "password_hash": password_hash
            }
        )
        return resp.json(), login, password

async def get_or_create_user(telegram_id: int, username: str = None):
    """Foydalanuvchi mavjud bo'lsa ol, yo'q bo'lsa yaratish"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{API_BASE}/admin/user_by_tg/{telegram_id}",
                               headers={"X-Admin-Token": ADMIN_TOKEN})
        if resp.status_code == 200:
            return resp.json(), None, None
        
        # Yangi foydalanuvchi yaratish
        return await register_user(telegram_id, username)

def main_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎮 O'yinlar"), KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="➕ To'ldirish"), KeyboardButton(text="➖ Yechish")],
        [KeyboardButton(text="👤 Profil"), KeyboardButton(text="📊 Tarix")]
    ], resize_keyboard=True)

def games_keyboard(web_app_url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Casino ochish", web_app=WebAppInfo(url=web_app_url))]
    ])

# ========================
# HANDLERS
# ========================

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Majburiy kanal tekshirish
    if REQUIRED_CHANNEL and not await check_subscription(user_id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}")],
            [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")]
        ])
        await message.answer(
            "⚠️ Bot ishlatish uchun kanalga obuna bo'ling!",
            reply_markup=kb
        )
        return
    
    user_data, login, password = await get_or_create_user(user_id, username)
    
    if login:  # Yangi foydalanuvchi
        await message.answer(
            f"🎉 Xush kelibsiz! Akkauntingiz yaratildi!\n\n"
            f"🔑 Login: <code>{login}</code>\n"
            f"🔐 Parol: <code>{password}</code>\n\n"
            f"⚠️ Bu ma'lumotlarni saqlang - Web App ga kirish uchun kerak!\n"
            f"❗️ Parolni hech kimga bermang!",
            parse_mode="HTML",
            reply_markup=main_keyboard()
        )
    else:
        await message.answer(
            f"👋 Qaytib keldingiz!\n💰 Balansingiz: {user_data.get('balance', 0):,.0f} so'm",
            reply_markup=main_keyboard()
        )

@router.callback_query(F.data == "check_sub")
async def check_subscription_cb(callback: CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        await cmd_start(callback.message)
    else:
        await callback.answer("❌ Hali obuna bo'lmagansiz!", show_alert=True)

@router.message(F.text == "🎮 O'yinlar")
async def games_menu(message: Message):
    # Kanal tekshirish
    if REQUIRED_CHANNEL and not await check_subscription(message.from_user.id):
        await message.answer("❌ Avval kanalga obuna bo'ling!")
        return
    
    await message.answer(
        "🎮 Casino o'yinlari:\n\n"
        "✈️ Aviator\n🍎 Apple of Fortune\n💣 Mines\n\n"
        "Casino Web App da o'ynang:",
        reply_markup=games_keyboard(WEB_APP_URL)
    )

@router.message(F.text == "💰 Balans")
async def check_balance(message: Message):
    user_data, _, _ = await get_or_create_user(message.from_user.id)
    balance = user_data.get("balance", 0)
    await message.answer(
        f"💰 Balansingiz: <b>{balance:,.0f} so'm</b>",
        parse_mode="HTML"
    )

@router.message(F.text == "👤 Profil")
async def profile(message: Message):
    user_data, _, _ = await get_or_create_user(message.from_user.id)
    
    created = user_data.get("created_at", "")[:10] if user_data.get("created_at") else "Noma'lum"
    
    text = (
        f"👤 <b>Profil</b>\n\n"
        f"🆔 Telegram ID: <code>{message.from_user.id}</code>\n"
        f"🔑 Login: <code>{user_data.get('login', '')}</code>\n"
        f"💰 Balans: <b>{user_data.get('balance', 0):,.0f} so'm</b>\n"
        f"✅ Jami yutuq: {user_data.get('total_won', 0):,.0f} so'm\n"
        f"❌ Jami yutqazish: {user_data.get('total_lost', 0):,.0f} so'm\n"
        f"📅 Ro'yxat sanasi: {created}"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "➕ To'ldirish")
async def deposit_menu(message: Message, state: FSMContext):
    await message.answer(
        "💳 Necha so'm to'ldirmoqchisiz?\n"
        "(Minimum: 1,000 so'm)\n\n"
        "Summani kiriting:"
    )
    await state.set_state(DepositStates.waiting_amount)

@router.message(DepositStates.waiting_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "").replace(" ", ""))
        if amount < 1000:
            await message.answer("❌ Minimum 1,000 so'm!")
            return
    except ValueError:
        await message.answer("❌ Noto'g'ri summa! Faqat raqam kiriting.")
        return
    
    await state.clear()
    
    # CheckCard orqali to'lov yaratish
    user_data, _, _ = await get_or_create_user(message.from_user.id)
    
    # API dan to'lov yaratish
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://checkcard.uz/api", params={
                "method": "create",
                "shop_id": os.getenv("CHECKCARD_SHOP_ID"),
                "shop_key": os.getenv("CHECKCARD_SHOP_KEY"),
                "amount": int(amount)
            })
            data = resp.json()
    except Exception:
        await message.answer("❌ To'lov tizimi bilan bog'lanib bo'lmadi. Keyinroq urinib ko'ring.")
        return
    
    if data.get("status") == "success":
        order_id = data["order"]
        await message.answer(
            f"✅ To'lov so'rovi yaratildi!\n\n"
            f"📝 Order ID: <code>{order_id}</code>\n"
            f"💰 Summa: {amount:,.0f} so'm\n\n"
            f"⏳ Admin tasdiqlashini kuting...\n"
            f"Tasdiqlanganidan keyin balansingizga tushadi.",
            parse_mode="HTML"
        )
        
        # Admin ga xabar
        for admin_id in ADMIN_IDS:
            try:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"confirm_dep_{order_id}_{user_data.get('id')}_{amount}"),
                        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_dep_{order_id}")
                    ]
                ])
                await bot.send_message(
                    admin_id,
                    f"💰 <b>Yangi to'lov so'rovi</b>\n\n"
                    f"👤 User: @{message.from_user.username or 'N/A'} (ID: {message.from_user.id})\n"
                    f"💵 Summa: {amount:,.0f} so'm\n"
                    f"📝 Order: {order_id}\n"
                    f"⏰ Vaqt: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
                    parse_mode="HTML",
                    reply_markup=kb
                )
            except Exception:
                pass
    else:
        await message.answer(f"❌ Xatolik: {data.get('message', 'Noma\\'lum xato')}")

@router.callback_query(F.data.startswith("confirm_dep_"))
async def confirm_deposit_cb(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q!")
        return
    
    parts = callback.data.split("_")
    order_id = parts[2]
    user_db_id = int(parts[3])
    amount = float(parts[4])
    
    # CheckCard da tekshirish
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get("https://checkcard.uz/api", params={"method": "check", "order": order_id})
        data = resp.json()
    
    # Balansga qo'shish
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(f"{API_BASE}/admin/user/add_balance",
            headers={"X-Admin-Token": ADMIN_TOKEN},
            json={"user_id": user_db_id, "amount": amount, "note": f"CheckCard order: {order_id}"}
        )
    
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ <b>TASDIQLANDI</b>",
        parse_mode="HTML"
    )
    await callback.answer("✅ To'lov tasdiqlandi!")

@router.callback_query(F.data.startswith("reject_dep_"))
async def reject_deposit_cb(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q!")
        return
    await callback.message.edit_text(callback.message.text + "\n\n❌ <b>RAD ETILDI</b>", parse_mode="HTML")
    await callback.answer("❌ To'lov rad etildi")

@router.message(F.text == "➖ Yechish")
async def withdraw_menu(message: Message, state: FSMContext):
    await message.answer(
        "💸 Yechish so'rovi yuborish\n\n"
        "Yechmoqchi bo'lgan summani kiriting:"
    )
    await state.set_state(DepositStates.waiting_amount)

# ========================
# ADMIN COMMANDS
# ========================

@router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin_users")],
        [InlineKeyboardButton(text="💳 Kutayotgan to'lovlar", callback_data="admin_pending")],
        [InlineKeyboardButton(text="🛑 Bloklash", callback_data="admin_block")],
        [InlineKeyboardButton(text="🎯 Yutqazdirish %%", callback_data="admin_lose")],
    ])
    await message.answer("🛠 Admin Panel", reply_markup=kb)

@router.callback_query(F.data == "admin_stats")
async def admin_stats_cb(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{API_BASE}/admin/stats", headers={"X-Admin-Token": ADMIN_TOKEN})
        stats = resp.json()
    
    text = (
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: {stats.get('total_users', 0)}\n"
        f"💰 Jami balans: {stats.get('total_balance', 0):,.0f} so'm\n"
        f"✅ Jami yutuqlar: {stats.get('total_won', 0):,.0f} so'm\n"
        f"❌ Jami yutqazishlar: {stats.get('total_lost', 0):,.0f} so'm\n"
        f"🏦 Foyda: {stats.get('house_profit', 0):,.0f} so'm\n\n"
        f"📅 Bugun:\n"
        f"  Tikuvlar: {stats.get('today_bets', 0)}\n"
        f"  Hajm: {stats.get('today_volume', 0):,.0f} so'm"
    )
    await callback.message.edit_text(text, parse_mode="HTML")

@router.callback_query(F.data == "admin_lose")
async def admin_lose_cb(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await callback.message.edit_text(
        "🎯 Foydalanuvchi ID va yutqazdirish % ni kiriting:\n"
        "Format: <code>USER_ID FOIZ</code>\n"
        "Misol: <code>123 60</code>\n"
        "(60% degani - 60% hollarda yutqazadi)\n"
        "0 kiritsangiz - o'chiriladi",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_lose_percent)

@router.message(AdminStates.waiting_lose_percent)
async def process_lose_percent(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        parts = message.text.strip().split()
        user_id = int(parts[0])
        percent = float(parts[1])
        
        if percent == 0:
            action = "remove_lose_percent"
            lose_percent = None
        else:
            action = "set_lose_percent"
            lose_percent = percent
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{API_BASE}/admin/user/control",
                headers={"X-Admin-Token": ADMIN_TOKEN},
                json={"user_id": user_id, "action": action, "lose_percent": lose_percent}
            )
        
        await state.clear()
        msg = f"✅ User {user_id}: yutqazdirish foizi {percent}% qo'yildi" if lose_percent else f"✅ User {user_id}: foiz o'chirildi"
        await message.answer(msg)
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")

# ========================
# MAIN
# ========================

async def main():
    print("Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
