import asyncio, hashlib, hmac, json, html, os
from urllib.parse import parse_qsl
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton,
                           WebAppInfo, CallbackQuery)

# ====== SOZLAMA ======
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "-1003754555782"))
WEBAPP_URL = os.environ["WEBAPP_URL"]
PORT = int(os.environ.get("PORT", "8080"))

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
e = lambda s: html.escape(str(s or "-"))


def valid_init_data(init_data: str):
    """Telegram initData imzosini tekshiradi, user dict qaytaradi."""
    try:
        d = dict(parse_qsl(init_data, strict_parsing=True))
        got = d.pop("hash")
        check = "\n".join(f"{k}={v}" for k, v in sorted(d.items()))
        key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
        return json.loads(d["user"]) if hmac.compare_digest(calc, got) else None
    except Exception:
        return None


@dp.message(CommandStart())
async def start(m: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🛠️ Ochish", web_app=WebAppInfo(url=WEBAPP_URL))]])
    await m.answer("TOPIB BER — Toshkent bo‘yicha ustalar.", reply_markup=kb)


@dp.callback_query(lambda c: c.data and c.data.startswith("ok:"))
async def approve(c: CallbackQuery):
    await c.message.edit_reply_markup(reply_markup=None)
    await c.message.reply("✅ Tasdiqlandi / ishga olindi")
    await c.answer()


def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


async def options(_):
    return cors(web.Response())


async def handle(request: web.Request):
    kind = request.match_info["kind"]           # client | master
    data = await request.json()
    user = valid_init_data(data.get("initData", ""))
    if not user:
        return cors(web.json_response({"ok": False}, status=403))

    uname = f"@{user['username']}" if user.get("username") else f"id{user['id']}"
    link = f'<a href="tg://user?id={user["id"]}">{uname}</a>'

    if kind == "client":
        text = (f"🔧 <b>Yangi so‘rov</b>\n\n"
                f"Xizmat: {e(data['service'])}\nTuman: {e(data['district'])}\n"
                f"Manzil: {e(data['address'])}\nTelefon: {e(data['phone'])}\n"
                f"Izoh: {e(data.get('note'))}\nMijoz: {link}")
        btn = "✅ Usta topildi"
    else:
        text = (f"👷 <b>Yangi usta arizasi</b>\n\n"
                f"Ism: {e(data['name'])}\nXizmat: {e(data['service'])}\n"
                f"Tuman: {e(data['district'])}\nTajriba: {e(data['exp'])} yil\n"
                f"Telefon: {e(data['phone'])}\nHaqida: {e(data.get('note'))}\nTelegram: {link}")
        btn = "✅ Tasdiqlash"

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=btn, callback_data=f"ok:{user['id']}")]])
    await bot.send_message(ADMIN_CHAT_ID, text, parse_mode="HTML", reply_markup=kb)

    # Foydalanuvchiga tasdiq
    try:
        await bot.send_message(user["id"], "✅ So‘rovingiz qabul qilindi." if kind == "client"
                               else "✅ Arizangiz qabul qilindi. Tez orada bog‘lanamiz.")
    except Exception:
        pass
    return cors(web.json_response({"ok": True}))


async def main():
    app = web.Application()
    app.router.add_get("/", lambda r: web.FileResponse("index.html"))
    app.router.add_route("OPTIONS", "/api/{kind}", options)
    app.router.add_post("/api/{kind:client|master}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
