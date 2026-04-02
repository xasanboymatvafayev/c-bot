"""
Casino Telegram Bot - TO'G'RILANGAN v2
- /start: faqat yangi foydalanuvchiga login/parol
- To'ldirish: CheckCard payurl → to'lov sahifasi
- Yechish: summa → balans tekshir → karta → admin
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

BOT_TOKEN          = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
API_BASE           = os.getenv("API_BASE", "http://localhost:8000/api")
ADMIN_TOKEN        = os.getenv("ADMIN_TOKEN", "admin_super_secret_token")
ADMIN_IDS          = list(map(int, os.getenv("ADMIN_IDS","").split(",") if os.getenv("ADMIN_IDS") else []))
REQUIRED_CHANNEL   = os.getenv("REQUIRED_CHANNEL", "")
WEB_APP_URL        = os.getenv("WEB_APP_URL", "https://yourdomain.com")
CHECKCARD_SHOP_ID  = os.getenv("CHECKCARD_SHOP_ID", "")
CHECKCARD_SHOP_KEY = os.getenv("CHECKCARD_SHOP_KEY", "")

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ── FSM ──────────────────────────────────────────────────────────────
class DepositStates(StatesGroup):
    waiting_amount = State()

class WithdrawStates(StatesGroup):
    waiting_amount = State()
    waiting_card   = State()

class AdminStates(StatesGroup):
    waiting_lose_percent = State()

# ── HELPERS ───────────────────────────────────────────────────────────
def gen_creds():
    login    = "user_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    password = "".join(random.choices(string.ascii_letters + string.digits + "!@#", k=10))
    return login, password

def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

async def check_sub(user_id: int) -> bool:
    if not REQUIRED_CHANNEL:
        return True
    try:
        m = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return m.status not in ["left", "kicked", "banned"]
    except Exception:
        return True

async def _register(telegram_id: int, username: str = None):
    login, password = gen_creds()
    pw_hash = hash_pw(password)
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{API_BASE}/auth/register",
            headers={"X-Admin-Token": ADMIN_TOKEN},
            json={"telegram_id": telegram_id, "username": username,
                  "login": login, "password_hash": pw_hash})
        return r.json(), login, password

async def get_or_create(telegram_id: int, username: str = None):
    """
    FIX #1: Mavjud user → (data, None, None)  — login/parol BERMAYDI
             Yangi user → (data, login, password)
    """
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{API_BASE}/admin/user_by_tg/{telegram_id}",
                        headers={"X-Admin-Token": ADMIN_TOKEN})
    if r.status_code == 200:
        return r.json(), None, None
    return await _register(telegram_id, username)

def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎮 O'yinlar"),   KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="➕ To'ldirish"), KeyboardButton(text="➖ Yechish")],
        [KeyboardButton(text="👤 Profil"),     KeyboardButton(text="📊 Tarix")],
    ], resize_keyboard=True)

# ── /start ────────────────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(message: Message):
    uid  = message.from_user.id
    uname = message.from_user.username

    if not await check_sub(uid):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Obuna bo'lish",
                                  url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}")],
            [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")]
        ])
        await message.answer("⚠️ Bot ishlatish uchun kanalga obuna bo'ling!", reply_markup=kb)
        return

    user, login, password = await get_or_create(uid, uname)

    if login:
        # Yangi foydalanuvchi — login/parol faqat bir marta
        await message.answer(
            f"🎉 Xush kelibsiz! Akkauntingiz yaratildi!\n\n"
            f"🔑 Login: <code>{login}</code>\n"
            f"🔐 Parol: <code>{password}</code>\n\n"
            f"⚠️ Bu ma'lumotlarni saqlang — Web App ga kirish uchun kerak!\n"
            f"❗ Parolni hech kimga bermang!",
            parse_mode="HTML", reply_markup=main_kb()
        )
    else:
        # Mavjud foydalanuvchi — login/parol ko'rsatilmaydi
        await message.answer(
            f"👋 Qaytib keldingiz!\n"
            f"💰 Balans: <b>{user.get('balance',0):,.0f} so'm</b>",
            parse_mode="HTML", reply_markup=main_kb()
        )

@router.callback_query(F.data == "check_sub")
async def cb_check_sub(cb: CallbackQuery):
    if await check_sub(cb.from_user.id):
        await cb.message.delete()
        await cmd_start(cb.message)
    else:
        await cb.answer("❌ Hali obuna bo'lmagansiz!", show_alert=True)

# ── Balans / Profil / Tarix ───────────────────────────────────────────
@router.message(F.text == "🎮 O'yinlar")
async def games_handler(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Casino ochish", web_app=WebAppInfo(url=WEB_APP_URL))]
    ])
    await message.answer("🎮 Casino Web App:", reply_markup=kb)

@router.message(F.text == "💰 Balans")
async def balance_handler(message: Message):
    user, _, _ = await get_or_create(message.from_user.id)
    await message.answer(
        f"💰 Balans: <b>{user.get('balance',0):,.0f} so'm</b>",
        parse_mode="HTML"
    )

@router.message(F.text == "👤 Profil")
async def profile_handler(message: Message):
    user, _, _ = await get_or_create(message.from_user.id)
    reg = user.get("created_at","")[:10] or "—"
    await message.answer(
        f"👤 <b>Profil</b>\n\n"
        f"🆔 TG ID: <code>{message.from_user.id}</code>\n"
        f"🔑 Login: <code>{user.get('login','')}</code>\n"
        f"💰 Balans: <b>{user.get('balance',0):,.0f} so'm</b>\n"
        f"✅ Yutuq: {user.get('total_won',0):,.0f} so'm\n"
        f"❌ Yutqazish: {user.get('total_lost',0):,.0f} so'm\n"
        f"📅 Ro'yxat: {reg}",
        parse_mode="HTML"
    )

@router.message(F.text == "📊 Tarix")
async def history_handler(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Ko'rish", web_app=WebAppInfo(url=f"{WEB_APP_URL}/game/history"))]
    ])
    await message.answer("📊 To'lov tarixi:", reply_markup=kb)

# ── FIX #2: TO'LDIRISH — payurl bilan CheckCard sahifasi ─────────────
@router.message(F.text == "➕ To'ldirish")
async def deposit_start(message: Message, state: FSMContext):
    await message.answer("💳 Necha so'm to'ldirmoqchisiz?\n(Minimum: 1,000 so'm)\n\nSummani kiriting:")
    await state.set_state(DepositStates.waiting_amount)

@router.message(DepositStates.waiting_amount)
async def deposit_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text.replace(",","").replace(" ",""))
        assert amount >= 1000
    except Exception:
        await message.answer("❌ Noto'g'ri summa! Minimum 1,000 so'm kiriting.")
        return

    await state.clear()
    user, _, _ = await get_or_create(message.from_user.id)

    # CheckCard → payurl=true
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://checkcard.uz/api", params={
                "method":   "create",
                "shop_id":  CHECKCARD_SHOP_ID,
                "shop_key": CHECKCARD_SHOP_KEY,
                "amount":   amount,
                "payurl":   "true"
            })
            data = r.json()
    except Exception:
        await message.answer("❌ To'lov tizimi bilan bog'lanib bo'lmadi.")
        return

    if data.get("status") != "success":
        err = data.get("message","")
        if "pending" in err.lower():
            await message.answer(
                f"⚠️ Bu miqdorda kutilayotgan to'lov bor.\n"
                f"💡 Boshqa summa kiriting, masalan: {amount+500:,} so'm"
            )
        else:
            await message.answer(f"❌ Xatolik: {err}")
        return

    order_id = data["order"]
    pay_url  = data.get("payurl","")
    user_db_id = user.get("id")

    # Foydalanuvchiga faqat to'lov tugmasi — adminга HECH NARSA YUBORILMAYDI
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 To'lovni amalga oshirish", url=pay_url)],
        [InlineKeyboardButton(text="✅ To'lovni tekshirish",
                              callback_data=f"chk_{order_id}_{user_db_id}_{amount}_{message.from_user.id}")]
    ])
    await message.answer(
        f"💳 <b>To'lov yaratildi!</b>\n\n"
        f"💰 Summa: <b>{amount:,} so'm</b>\n"
        f"📝 Order: <code>{order_id}</code>\n"
        f"⏰ To'lov muddati: <b>5 daqiqa</b>\n\n"
        f"👇 Tugmani bosib to'lovni amalga oshiring.\n"
        f"To'lov qilingach ✅ tugmasini bosing.",
        parse_mode="HTML", reply_markup=kb
    )
    # ✅ Admin ga HECH NARSA yuborilmaydi — to'liq avtomatik

@router.callback_query(F.data.startswith("chk_"))
async def check_payment_cb(cb: CallbackQuery):
    """Foydalanuvchi 'To'lovni tekshirish' bosadi"""
    # chk_{order_id}_{user_db_id}_{amount}_{tg_id}
    _, order_id, user_db_id, amount, tg_id = cb.data.split("_")
    amount = float(amount)

    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r    = await c.get("https://checkcard.uz/api",
                               params={"method": "check", "order": order_id})
            info = r.json()
    except Exception:
        await cb.answer("❌ API bilan bog'lanib bo'lmadi", show_alert=True)
        return

    status = info.get("data",{}).get("status","")

    if status == "paid":
        # Balansga qo'shish
        async with httpx.AsyncClient(timeout=10) as c:
            add = await c.post(f"{API_BASE}/admin/user/add_balance",
                headers={"X-Admin-Token": ADMIN_TOKEN},
                json={"user_id": int(user_db_id), "amount": amount,
                      "note": f"CheckCard: {order_id}"})
            nb = add.json().get("new_balance", 0)

        await cb.message.edit_text(
            cb.message.text + f"\n\n✅ <b>TO'LOV QABUL QILINDI!</b>",
            parse_mode="HTML"
        )
        await cb.answer("✅ Balansga qo'shildi!", show_alert=True)

        # To'lov avtomatik tasdiqlandi — adminga xabar yuborilmaydi

    elif status == "cancel":
        await cb.message.edit_text(
            cb.message.text + "\n\n❌ <b>TO'LOV BEKOR QILINDI</b>",
            parse_mode="HTML"
        )
        await cb.answer("❌ To'lov bekor qilindi", show_alert=True)

    elif status == "pending":
        await cb.answer("⏳ To'lov hali amalga oshirilmagan. Kuting...", show_alert=True)
    else:
        await cb.answer(f"⚠️ Holat: {status}", show_alert=True)

# cdep_/rdep_ handlerlari olib tashlandi — to'ldirish to'liq avtomatik

# ── FIX #3: YECHISH ───────────────────────────────────────────────────
@router.message(F.text == "➖ Yechish")
async def withdraw_start(message: Message, state: FSMContext):
    user, _, _ = await get_or_create(message.from_user.id)
    balance = user.get("balance", 0)
    if balance < 10000:
        await message.answer(
            f"❌ Balans yetarli emas.\n"
            f"💰 Mavjud: <b>{balance:,.0f} so'm</b>\n"
            f"Minimum yechish: 10,000 so'm", parse_mode="HTML")
        return
    await message.answer(
        f"💸 <b>Pul yechish</b>\n\n"
        f"💰 Mavjud balans: <b>{balance:,.0f} so'm</b>\n\n"
        f"Qancha so'm yechmoqchisiz?", parse_mode="HTML")
    await state.set_state(WithdrawStates.waiting_amount)

@router.message(WithdrawStates.waiting_amount)
async def withdraw_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",","").replace(" ",""))
        assert amount >= 10000
    except Exception:
        await message.answer("❌ Minimum 10,000 so'm kiriting.")
        return

    user, _, _ = await get_or_create(message.from_user.id)
    if user.get("balance", 0) < amount:
        await message.answer(
            f"❌ Balans yetarli emas!\n"
            f"💰 Mavjud: <b>{user.get('balance',0):,.0f} so'm</b>", parse_mode="HTML")
        return

    await state.update_data(amount=amount, user_db_id=user.get("id"))
    await message.answer(
        f"✅ Summa: <b>{amount:,.0f} so'm</b>\n\n"
        f"💳 Pul o'tkaziladigan karta raqamini kiriting (16 ta raqam):",
        parse_mode="HTML")
    await state.set_state(WithdrawStates.waiting_card)

@router.message(WithdrawStates.waiting_card)
async def withdraw_card(message: Message, state: FSMContext):
    card = message.text.strip().replace(" ","")
    if not card.isdigit() or len(card) != 16:
        await message.answer("❌ Noto'g'ri karta! 16 ta raqam kiriting.")
        return

    d = await state.get_data()
    amount, user_db_id = d["amount"], d["user_db_id"]
    await state.clear()
    fmt_card = " ".join(card[i:i+4] for i in range(0, 16, 4))

    # Backendga so'rov
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{API_BASE}/admin/withdraw/create",
                headers={"X-Admin-Token": ADMIN_TOKEN},
                json={"user_id": user_db_id, "amount": amount, "card_number": fmt_card})
            wd = r.json()
    except Exception:
        await message.answer("❌ Server xatosi. Keyinroq urinib ko'ring.")
        return

    tx_id  = wd.get("tx_id","?")
    new_bal = wd.get("new_balance", 0)

    await message.answer(
        f"✅ <b>So'rov yuborildi!</b>\n\n"
        f"💸 Summa: <b>{amount:,.0f} so'm</b>\n"
        f"💳 Karta: <code>{fmt_card}</code>\n"
        f"📝 So'rov #: {tx_id}\n"
        f"💰 Qolgan balans: <b>{new_bal:,.0f} so'm</b>\n\n"
        f"⏳ Admin 5–30 daqiqa ichida kartangizga o'tkazadi.",
        parse_mode="HTML")

    for admin_id in ADMIN_IDS:
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="✅ O'tkazildi",
                    callback_data=f"cwd_{tx_id}_{message.from_user.id}"),
                InlineKeyboardButton(
                    text="❌ Rad etish",
                    callback_data=f"rwd_{tx_id}_{message.from_user.id}_{user_db_id}_{int(amount)}")
            ]])
            await bot.send_message(admin_id,
                f"💸 <b>Yechish so'rovi</b>\n\n"
                f"👤 @{message.from_user.username or 'N/A'} (TG: {message.from_user.id})\n"
                f"🆔 DB: {user_db_id}\n"
                f"💵 <b>{amount:,.0f} so'm</b>\n"
                f"💳 <code>{fmt_card}</code>\n"
                f"📝 So'rov #: {tx_id}\n"
                f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass

@router.callback_query(F.data.startswith("cwd_"))
async def admin_confirm_wd(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("❌ Ruxsat yo'q!")
        return
    _, tx_id, tg_id = cb.data.split("_")
    tg_id = int(tg_id)
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(f"{API_BASE}/admin/confirm_withdraw",
                headers={"X-Admin-Token": ADMIN_TOKEN},
                json={"tx_id": int(tx_id)})
    except Exception:
        pass
    await cb.message.edit_text(cb.message.text + "\n\n✅ <b>O'TKAZILDI</b>", parse_mode="HTML")
    await cb.answer("✅ Tasdiqlandi!")
    try:
        await bot.send_message(tg_id,
            f"✅ <b>Pul kartangizga o'tkazildi!</b>\n"
            f"So'rov #{tx_id} tasdiqlandi. 🎉", parse_mode="HTML")
    except Exception:
        pass

@router.callback_query(F.data.startswith("rwd_"))
async def admin_reject_wd(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("❌ Ruxsat yo'q!")
        return
    # rwd_{tx_id}_{tg_id}_{user_db_id}_{amount}
    parts  = cb.data.split("_")
    tx_id, tg_id, user_db_id, amount = parts[1], int(parts[2]), int(parts[3]), float(parts[4])
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(f"{API_BASE}/admin/user/add_balance",
                headers={"X-Admin-Token": ADMIN_TOKEN},
                json={"user_id": user_db_id, "amount": amount,
                      "note": f"Yechish rad #{tx_id}"})
    except Exception:
        pass
    await cb.message.edit_text(
        cb.message.text + "\n\n❌ <b>RAD ETILDI — BALANS QAYTARILDI</b>", parse_mode="HTML")
    await cb.answer("❌ Rad etildi")
    try:
        await bot.send_message(tg_id,
            f"❌ Yechish so'rovingiz rad etildi.\n"
            f"💰 <b>{amount:,.0f} so'm</b> balansingizga qaytarildi.", parse_mode="HTML")
    except Exception:
        pass

# ── ADMIN PANEL ───────────────────────────────────────────────────────
@router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika",       callback_data="adm_stats")],
        [InlineKeyboardButton(text="💸 Kutayotgan yechish", callback_data="adm_pending_wd")],
        [InlineKeyboardButton(text="🎯 Yutqazdirish %%",  callback_data="adm_lose")],
    ])
    await message.answer("🛠 Admin Panel", reply_markup=kb)

@router.callback_query(F.data == "adm_stats")
async def adm_stats(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        return
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{API_BASE}/admin/stats", headers={"X-Admin-Token": ADMIN_TOKEN})
        s = r.json()
    await cb.message.edit_text(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: {s.get('total_users',0)}\n"
        f"💰 Jami balans: {s.get('total_balance',0):,.0f} so'm\n"
        f"🏦 Foyda: {s.get('house_profit',0):,.0f} so'm\n"
        f"📅 Bugun tikuvlar: {s.get('today_bets',0)}",
        parse_mode="HTML")

@router.callback_query(F.data == "adm_lose")
async def adm_lose(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        return
    await cb.message.edit_text(
        "🎯 Format: <code>USER_ID FOIZ</code>\nMisol: <code>5 60</code>\n0 = o'chirish",
        parse_mode="HTML")
    await state.set_state(AdminStates.waiting_lose_percent)

@router.message(AdminStates.waiting_lose_percent)
async def adm_lose_process(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        uid, pct = message.text.strip().split()
        uid, pct = int(uid), float(pct)
        action = "remove_lose_percent" if pct == 0 else "set_lose_percent"
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(f"{API_BASE}/admin/user/control",
                headers={"X-Admin-Token": ADMIN_TOKEN},
                json={"user_id": uid, "action": action, "lose_percent": pct or None})
        await state.clear()
        await message.answer(
            f"✅ User {uid}: {'foiz ochirildi' if pct==0 else f'{pct}% qoyildi'}")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")

# ── MAIN ──────────────────────────────────────────────────────────────
async def main():
    print("✅ Bot ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
