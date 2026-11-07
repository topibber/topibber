import asyncio, hashlib, hmac, json, html, os
import asyncpg
from urllib.parse import parse_qsl
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton,
                           WebAppInfo, CallbackQuery)

# ====== SOZLAMA ======
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "-1003754555782"))
WEBAPP_URL = os.environ["WEBAPP_URL"]
PORT = int(os.environ.get("PORT", "8080"))
DATABASE_URL = os.environ["DATABASE_URL"].split("?")[0]
pool = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS masters(
 id SERIAL PRIMARY KEY, user_id BIGINT, name TEXT, service TEXT, district TEXT,
 exp TEXT, phone TEXT, note TEXT, status TEXT DEFAULT 'new', created TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS requests(
 id SERIAL PRIMARY KEY, user_id BIGINT, service TEXT, district TEXT, address TEXT,
 phone TEXT, note TEXT, status TEXT DEFAULT 'new', created TIMESTAMPTZ DEFAULT now());
"""

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


@dp.callback_query(lambda c: c.data and c.data.split(":")[0] in ("mok", "mno", "rdone"))
async def admin_action(c: CallbackQuery):
    if c.message.chat.id != ADMIN_CHAT_ID:
        return await c.answer("Ruxsat yo'q", show_alert=True)
    act, rid = c.data.split(":")
    rid = int(rid)
    if act in ("mok", "mno"):
        st = "approved" if act == "mok" else "rejected"
        row = await pool.fetchrow("UPDATE masters SET status=$1 WHERE id=$2 RETURNING user_id", st, rid)
        label = "✅ Tasdiqlandi" if act == "mok" else "❌ Rad etildi"
        if row:
            try:
                await bot.send_message(row["user_id"],
                    "✅ Arizangiz tasdiqlandi! Mijozlar so'rovi sizga yuboriladi." if act == "mok"
                    else "Afsuski, arizangiz hozircha qabul qilinmadi.")
            except Exception:
                pass
    else:
        await pool.execute("UPDATE requests SET status='done' WHERE id=$1", rid)
        label = "✅ Usta topildi"
    await c.message.edit_reply_markup(reply_markup=None)
    await c.message.reply(label)
    await c.answer()


@dp.message(Command("ustalar"))
async def list_masters(m: Message):
    if m.chat.id != ADMIN_CHAT_ID:
        return
    rows = await pool.fetch("SELECT * FROM masters WHERE status='approved' ORDER BY id DESC LIMIT 30")
    if not rows:
        return await m.answer("Tasdiqlangan ustalar yo'q.")
    await m.answer("👷 <b>Tasdiqlangan ustalar</b>\n\n" + "\n".join(
        f"{r['id']}. {e(r['name'])} — {e(r['service'])}, {e(r['district'])}, {e(r['phone'])}" for r in rows),
        parse_mode="HTML")


@dp.message(Command("sorovlar"))
async def list_requests(m: Message):
    if m.chat.id != ADMIN_CHAT_ID:
        return
    rows = await pool.fetch("SELECT * FROM requests ORDER BY id DESC LIMIT 15")
    if not rows:
        return await m.answer("So'rovlar yo'q.")
    await m.answer("🔧 <b>Oxirgi so'rovlar</b>\n\n" + "\n".join(
        f"{r['id']}. [{r['status']}] {e(r['service'])}, {e(r['district'])}, {e(r['phone'])}" for r in rows),
        parse_mode="HTML")


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
        rid = await pool.fetchval(
            "INSERT INTO requests(user_id,service,district,address,phone,note) VALUES($1,$2,$3,$4,$5,$6) RETURNING id",
            user["id"], data["service"], data["district"], data["address"], data["phone"], data.get("note"))
        text = (f"🔧 <b>Yangi so‘rov</b>\n\n"
                f"Xizmat: {e(data['service'])}\nTuman: {e(data['district'])}\n"
                f"Manzil: {e(data['address'])}\nTelefon: {e(data['phone'])}\n"
                f"Izoh: {e(data.get('note'))}\nMijoz: {link}")
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Usta topildi", callback_data=f"rdone:{rid}")]])
    else:
        rid = await pool.fetchval(
            "INSERT INTO masters(user_id,name,service,district,exp,phone,note) VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING id",
            user["id"], data["name"], data["service"], data["district"], data["exp"], data["phone"], data.get("note"))
        text = (f"👷 <b>Yangi usta arizasi</b>\n\n"
                f"Ism: {e(data['name'])}\nXizmat: {e(data['service'])}\n"
                f"Tuman: {e(data['district'])}\nTajriba: {e(data['exp'])} yil\n"
                f"Telefon: {e(data['phone'])}\nHaqida: {e(data.get('note'))}\nTelegram: {link}")
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"mok:{rid}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"mno:{rid}")]])

    await bot.send_message(ADMIN_CHAT_ID, text, parse_mode="HTML", reply_markup=kb)

    # Foydalanuvchiga tasdiq
    try:
        await bot.send_message(user["id"], "✅ So‘rovingiz qabul qilindi." if kind == "client"
                               else "✅ Arizangiz qabul qilindi. Tez orada bog‘lanamiz.")
    except Exception:
        pass
    return cors(web.json_response({"ok": True}))


async def main():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, ssl="require", statement_cache_size=0)
    await pool.execute(SCHEMA)
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
