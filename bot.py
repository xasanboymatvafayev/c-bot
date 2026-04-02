"""
Casino Telegram Bot - TO'G'RILANGAN VERSIYA
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
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@your_channel")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://yourdomain.com")
CHECKCARD_SHOP_ID = os.getenv("CHECKCARD_SHOP_ID")
CHECKCARD_SHOP_KEY = os.getenv("CHECKCARD_SHOP_KEY")
PAYMENT_CARD = os.getenv("PAYMENT_CARD", "5614 6835 8227 9246")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ========================
# FSM STATES
# ========================

class DepositStates(StatesGroup):
    waiting_amount = State()

class WithdrawStates(StatesGroup):
    waiting_amount = State()
    waiting_card = State()   # YANGI: karta raqami

class AdminStates(StatesGroup):
    waiting_lose_percent = State()

# ========================
# UTILITY
# ========================

def generate_credentials():
    login = "user_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    password = "".join(random.choices(string.ascii_letters + string.digits + "!@#", k=10))
    return login, password

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status not in ["left", "kicked", "banned"]
    except Exception:
        return True

async def register_user(telegram_id: int, username: str = None):
    login, password = generate_credentials()
    password_hash = hash_password(password)
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
    """
    FIX #1: Mavjud foydalanuvchi bo'lsa qaytaradi (login/parol BERMAYDI).
    Yangi bo'lsa yaratadi va login/parol beradi.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{API_BASE}/admin/user_by_tg/{telegram_id}",
                               headers={"X-Admin-Token": ADMIN_TOKEN})
        if resp.status_code == 200:
            return resp.json(), None, None  # Mavjud — None, None
        return await register_user(telegram_id, username)  # Yangi

def main_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎮 O'yinlar"), KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="➕ To'ldirish"), KeyboardButton(text="➖ Yechish")],
        [KeyboardButton(text="👤 Profil"), KeyboardButton(text="📊 Tarix")]
    ], resize_keyboard=True)

# ========================
# HANDLERS
# ========================

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username

    if REQUIRED_CHANNEL and not await check_subscription(user_id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}")],
            [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")]
        ])
        await message.answer("⚠️ Bot ishlatish uchun kanalga obuna bo'ling!", reply_markup=kb)
        return

    user_data, login, password = await get_or_create_user(user_id, username)

    if login:
        # FIX #1: Faqat YANGI foydalanuvchiga login/parol beriladi
        await message.answer(
            f"🎉 Xush kelibsiz! Akkauntingiz yaratildi!\n\n"
            f"🔑 Login: <code>{login}</code>\n"
            f"🔐 Parol: <code>{password}</code>\n\n"
            f"⚠️ Bu ma'lumotlarni saqlang — Web App ga kirish uchun kerak!\n"
            f"❗️ Parolni hech kimga bermang!",
            parse_mode="HTML",
            reply_markup=main_keyboard()
        )
    else:
        # FIX #1: Mavjud foydalanuvchiga shunchaki salom
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
    if REQUIRED_CHANNEL and not await check_subscription(message.from_user.id):
        await message.answer("❌ Avval kanalga obuna bo'ling!")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Casino ochish", web_app=WebAppInfo(url=WEB_APP_URL))]
    ])
    await message.answer("🎮 Casino Web App da o'ynang:", reply_markup=kb)

@router.message(F.text == "💰 Balans")
async def check_balance(message: Message):
    user_data, _, _ = await get_or_create_user(message.from_user.id)
    await message.answer(
        f"💰 Balansingiz: <b>{user_data.get('balance', 0):,.0f} so'm</b>",
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

@router.message(F.text == "📊 Tarix")
async def history_menu(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Tarixni ko'rish", web_app=WebAppInfo(url=f"{WEB_APP_URL}/game/history"))]
    ])
    await message.answer("📊 To'lov tarixi:", reply_markup=kb)

# ========================
# FIX #2: TO'LDIRISH — CheckCard + karta ko'rsatish
# ========================

@router.message(F.text == "➕ To'ldirish")
async def deposit_menu(message: Message, state: FSMContext):
    await message.answer(
        "💳 Necha so'm to'ldirmoqchisiz?\n(Minimum: 1,000 so'm)\n\nSummani kiriting:"
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
    user_data, _, _ = await get_or_create_user(message.from_user.id)

    # FIX #2: CheckCard orqali order yaratish
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://checkcard.uz/api", params={
                "method": "create",
                "shop_id": CHECKCARD_SHOP_ID,
                "shop_key": CHECKCARD_SHOP_KEY,
                "amount": int(amount)
            })
            data = resp.json()
    except Exception:
        await message.answer("❌ To'lov tizimi bilan bog'lanib bo'lmadi. Keyinroq urinib ko'ring.")
        return

    if data.get("status") != "success":
        await message.answer(f"❌ Xatolik: {data.get('message', 'Noma\\'lum xato')}")
        return

    order_id = data["order"]

    # FIX #2: Foydalanuvchiga KARTAGA PUL O'TKAZISH ko'rsatmasi
    await message.answer(
        f"💳 <b>To'lov ma'lumotlari</b>\n\n"
        f"💰 Summa: <b>{int(amount):,} so'm</b>\n"
        f"🏦 Kartaga o'tkazing: <code>{PAYMENT_CARD}</code>\n"
        f"📝 To'lov izohi: <code>{order_id}</code>\n\n"
        f"⚠️ <b>Muhim:</b> To'lov qilganda izohga yuqoridagi kodni yozing!\n\n"
        f"✅ To'lov qilgandan so'ng admin 5-15 daqiqa ichida tasdiqlaydi.",
        parse_mode="HTML"
    )

    # Admin ga xabar
    for admin_id in ADMIN_IDS:
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="✅ Tasdiqlash",
                    callback_data=f"cdep_{order_id}_{user_data.get('id')}_{int(amount)}_{message.from_user.id}"
                ),
                InlineKeyboardButton(
                    text="❌ Rad etish",
                    callback_data=f"rdep_{order_id}_{message.from_user.id}"
                )
            ]])
            await bot.send_message(
                admin_id,
                f"💰 <b>Yangi to'lov so'rovi</b>\n\n"
                f"👤 @{message.from_user.username or 'N/A'} (TG: {message.from_user.id})\n"
                f"🆔 DB ID: {user_data.get('id')}\n"
                f"💵 Summa: <b>{int(amount):,} so'm</b>\n"
                f"📝 Order: <code>{order_id}</code>\n"
                f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
                parse_mode="HTML",
                reply_markup=kb
            )
        except Exception:
            pass

@router.callback_query(F.data.startswith("cdep_"))
async def confirm_deposit_cb(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q!")
        return

    # cdep_{order_id}_{user_db_id}_{amount}_{tg_user_id}
    _, order_id, user_db_id, amount, tg_user_id = callback.data.split("_")
    user_db_id, amount, tg_user_id = int(user_db_id), float(amount), int(tg_user_id)

    # CheckCard holatini tekshirish
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get("https://checkcard.uz/api", params={"method": "check", "order": order_id})
            cc_status = r.json().get("data", {}).get("status", "unknown")
    except Exception:
        cc_status = "check_failed"

    # Balansga qo'shish
    async with httpx.AsyncClient(timeout=10.0) as client:
        add_r = await client.post(f"{API_BASE}/admin/user/add_balance",
            headers={"X-Admin-Token": ADMIN_TOKEN},
            json={"user_id": user_db_id, "amount": amount, "note": f"CheckCard: {order_id}"}
        )
        new_balance = add_r.json().get("new_balance", 0)

    await callback.message.edit_text(
        callback.message.text + f"\n\n✅ <b>TASDIQLANDI</b> | CC: {cc_status} | Balans: {new_balance:,.0f} so'm",
        parse_mode="HTML"
    )
    await callback.answer("✅ Tasdiqlandi!")

    # Foydalanuvchiga xabar
    try:
        await bot.send_message(
            tg_user_id,
            f"✅ <b>To'lovingiz tasdiqlandi!</b>\n\n"
            f"💰 <b>{amount:,.0f} so'm</b> balansingizga qo'shildi.\n"
            f"💳 Joriy balans: <b>{new_balance:,.0f} so'm</b>",
            parse_mode="HTML"
        )
    except Exception:
        pass

@router.callback_query(F.data.startswith("rdep_"))
async def reject_deposit_cb(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q!")
        return

    # rdep_{order_id}_{tg_user_id}
    parts = callback.data.split("_")
    order_id, tg_user_id = parts[1], int(parts[2])

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.get("https://checkcard.uz/api", params={"method": "cancel", "order": order_id})
    except Exception:
        pass

    await callback.message.edit_text(
        callback.message.text + "\n\n❌ <b>RAD ETILDI</b>",
        parse_mode="HTML"
    )
    await callback.answer("❌ Rad etildi")

    try:
        await bot.send_message(
            tg_user_id,
            f"❌ To'lov so'rovingiz rad etildi.\nSavol bo'lsa admin bilan bog'laning.",
            parse_mode="HTML"
        )
    except Exception:
        pass

# ========================
# FIX #3: YECHISH — summa → balans tekshir → KARTA SO'RA → admin
# ========================

@router.message(F.text == "➖ Yechish")
async def withdraw_menu(message: Message, state: FSMContext):
    user_data, _, _ = await get_or_create_user(message.from_user.id)
    balance = user_data.get("balance", 0)

    if balance < 10000:
        await message.answer(
            f"❌ Yechish uchun balans yetarli emas.\n"
            f"💰 Mavjud balans: <b>{balance:,.0f} so'm</b>\n"
            f"Minimum yechish: 10,000 so'm",
            parse_mode="HTML"
        )
        return

    await message.answer(
        f"💸 <b>Pul yechish</b>\n\n"
        f"💰 Mavjud balans: <b>{balance:,.0f} so'm</b>\n\n"
        f"Qancha so'm yechmoqchisiz? (Minimum: 10,000 so'm)",
        parse_mode="HTML"
    )
    await state.set_state(WithdrawStates.waiting_amount)

@router.message(WithdrawStates.waiting_amount)
async def process_withdraw_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "").replace(" ", ""))
        if amount < 10000:
            await message.answer("❌ Minimum yechish: 10,000 so'm!")
            return
    except ValueError:
        await message.answer("❌ Noto'g'ri summa! Faqat raqam kiriting.")
        return

    user_data, _, _ = await get_or_create_user(message.from_user.id)
    balance = user_data.get("balance", 0)

    if balance < amount:
        await message.answer(
            f"❌ Balans yetarli emas!\n"
            f"💰 Mavjud: <b>{balance:,.0f} so'm</b>\n"
            f"💸 So'ralgan: <b>{amount:,.0f} so'm</b>",
            parse_mode="HTML"
        )
        return

    # FIX #3: Summani saqlab, KARTA SO'RASH
    await state.update_data(withdraw_amount=amount, user_db_id=user_data.get("id"))
    await message.answer(
        f"✅ Summa: <b>{amount:,.0f} so'm</b>\n\n"
        f"💳 Pul o'tkaziladigan karta raqamingizni kiriting:\n"
        f"(16 ta raqam, masalan: 8600 1234 5678 9012)",
        parse_mode="HTML"
    )
    await state.set_state(WithdrawStates.waiting_card)

@router.message(WithdrawStates.waiting_card)
async def process_withdraw_card(message: Message, state: FSMContext):
    card_number = message.text.strip().replace(" ", "")

    if not card_number.isdigit() or len(card_number) != 16:
        await message.answer(
            "❌ Noto'g'ri karta raqami!\n"
            "16 ta raqam kiriting (probelsiz yoki bo'shliqli)."
        )
        return

    data = await state.get_data()
    amount = data.get("withdraw_amount")
    user_db_id = data.get("user_db_id")
    await state.clear()

    formatted_card = " ".join([card_number[i:i+4] for i in range(0, 16, 4)])

    # Backend'ga so'rov — balansdan ayirish
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{API_BASE}/admin/withdraw/create",
                headers={"X-Admin-Token": ADMIN_TOKEN},
                json={"user_id": user_db_id, "amount": amount, "card_number": formatted_card}
            )
            wd_data = resp.json()
    except Exception:
        await message.answer("❌ Xatolik yuz berdi. Keyinroq urinib ko'ring.")
        return

    tx_id = wd_data.get("tx_id", "?")
    new_balance = wd_data.get("new_balance", 0)

    # FIX #3: Foydalanuvchiga tasdiqlash
    await message.answer(
        f"✅ <b>Yechish so'rovi yuborildi!</b>\n\n"
        f"💸 Summa: <b>{amount:,.0f} so'm</b>\n"
        f"💳 Karta: <code>{formatted_card}</code>\n"
        f"📝 So'rov #: {tx_id}\n"
        f"💰 Qolgan balans: <b>{new_balance:,.0f} so'm</b>\n\n"
        f"⏳ Admin 5-30 daqiqa ichida kartangizga o'tkazadi.",
        parse_mode="HTML"
    )

    # FIX #3: Admin ga xabar — karta raqami bilan
    for admin_id in ADMIN_IDS:
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="✅ O'tkazildi",
                    callback_data=f"cwd_{tx_id}_{message.from_user.id}"
                ),
                InlineKeyboardButton(
                    text="❌ Rad etish",
                    callback_data=f"rwd_{tx_id}_{message.from_user.id}_{user_db_id}_{int(amount)}"
                )
            ]])
            await bot.send_message(
                admin_id,
                f"💸 <b>Yangi yechish so'rovi</b>\n\n"
                f"👤 @{message.from_user.username or 'N/A'} (TG: {message.from_user.id})\n"
                f"🆔 DB ID: {user_db_id}\n"
                f"💵 Summa: <b>{amount:,.0f} so'm</b>\n"
                f"💳 Karta: <code>{formatted_card}</code>\n"
                f"📝 So'rov #: {tx_id}\n"
                f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
                parse_mode="HTML",
                reply_markup=kb
            )
        except Exception:
            pass

@router.callback_query(F.data.startswith("cwd_"))
async def confirm_withdraw_cb(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q!")
        return

    # cwd_{tx_id}_{tg_user_id}
    _, tx_id, tg_user_id = callback.data.split("_")
    tg_user_id = int(tg_user_id)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{API_BASE}/admin/confirm_withdraw",
                headers={"X-Admin-Token": ADMIN_TOKEN},
                json={"tx_id": int(tx_id)}
            )
    except Exception:
        pass

    await callback.message.edit_text(
        callback.message.text + "\n\n✅ <b>O'TKAZILDI — TASDIQLANDI</b>",
        parse_mode="HTML"
    )
    await callback.answer("✅ Tasdiqlandi!")

    try:
        await bot.send_message(
            tg_user_id,
            f"✅ <b>Pul kartangizga o'tkazildi!</b>\n\n"
            f"So'rov #{tx_id} tasdiqlandi.\n"
            f"Pul 5-10 daqiqa ichida kartangizga tushadi. 🎉",
            parse_mode="HTML"
        )
    except Exception:
        pass

@router.callback_query(F.data.startswith("rwd_"))
async def reject_withdraw_cb(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q!")
        return

    # rwd_{tx_id}_{tg_user_id}_{user_db_id}_{amount}
    parts = callback.data.split("_")
    tx_id, tg_user_id, user_db_id, amount = parts[1], int(parts[2]), int(parts[3]), float(parts[4])

    # Balansni qaytarish
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{API_BASE}/admin/user/add_balance",
                headers={"X-Admin-Token": ADMIN_TOKEN},
                json={"user_id": user_db_id, "amount": amount, "note": f"Yechish rad #{tx_id}"}
            )
    except Exception:
        pass

    await callback.message.edit_text(
        callback.message.text + "\n\n❌ <b>RAD ETILDI — BALANS QAYTARILDI</b>",
        parse_mode="HTML"
    )
    await callback.answer("❌ Rad etildi")

    try:
        await bot.send_message(
            tg_user_id,
            f"❌ Yechish so'rovingiz rad etildi.\n"
            f"💰 <b>{amount:,.0f} so'm</b> balansingizga qaytarildi.\n\n"
            f"Savol bo'lsa admin bilan bog'laning.",
            parse_mode="HTML"
        )
    except Exception:
        pass

# ========================
# ADMIN COMMANDS
# ========================

@router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💳 Kutayotgan to'lovlar", callback_data="admin_pending")],
        [InlineKeyboardButton(text="💸 Kutayotgan yechishlar", callback_data="admin_pending_wd")],
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
        f"🏦 Foyda: {stats.get('house_profit', 0):,.0f} so'm\n"
        f"📅 Bugun tikuvlar: {stats.get('today_bets', 0)}"
    )
    await callback.message.edit_text(text, parse_mode="HTML")

@router.callback_query(F.data == "admin_lose")
async def admin_lose_cb(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await callback.message.edit_text(
        "🎯 Format: <code>USER_ID FOIZ</code>\nMisol: <code>123 60</code>\n0 = o'chirish",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_lose_percent)

@router.message(AdminStates.waiting_lose_percent)
async def process_lose_percent(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.strip().split()
        user_id, percent = int(parts[0]), float(parts[1])
        action = "remove_lose_percent" if percent == 0 else "set_lose_percent"
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{API_BASE}/admin/user/control",
                headers={"X-Admin-Token": ADMIN_TOKEN},
                json={"user_id": user_id, "action": action, "lose_percent": percent if percent else None}
            )
        await state.clear()
        msg = f"✅ User {user_id}: {percent}% foiz qo'yildi" if percent else f"✅ User {user_id}: foiz o'chirildi"
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
