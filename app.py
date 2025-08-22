# app.py — Arabi Psycho (Render + Telegram Webhook + OpenRouter)
# Python 3.11 / python-telegram-bot v21
# Start command on Render:
# gunicorn -w 1 -k gthread -b 0.0.0.0:$PORT app:app

import os, re, json, asyncio, logging, threading
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

import httpx
from flask import Flask, request

from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

# ---------- Logging ----------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("arabi-psycho")

# ---------- ENV ----------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
PUBLIC_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
WEBHOOK_PATH = "/webhook/secret"  # نفس المسار الموجود في Route بالأسفل

AI_BASE_URL = (os.getenv("AI_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
AI_API_KEY  = os.getenv("AI_API_KEY", "")
AI_MODEL    = os.getenv("AI_MODEL", "openrouter/auto")

CONTACT_THERAPIST_URL    = os.getenv("CONTACT_THERAPIST_URL", "https://t.me/your_therapist")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "https://t.me/your_psychiatrist")

if not BOT_TOKEN:
    raise RuntimeError("✖ TELEGRAM_BOT_TOKEN مفقود")

# ---------- Flask (لـ gunicorn) ----------
app = Flask(__name__)

@app.get("/")
def health():
    # GET على الجذر يعطي OK — هذا عادي
    return "Arabi Psycho OK"

# Telegram يرسل POST فقط على الويبهوك — لذلك GET يعطي 405 وهذا طبيعي.
@app.get(WEBHOOK_PATH)
def webhook_get_block():
    return ("Method Not Allowed", 405)

# ---------- Telegram Application (يعمل في Thread منفصل) ----------
tg_app: Application = Application.builder().token(BOT_TOKEN).build()
_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()

def _bot_thread():
    asyncio.set_event_loop(_loop)

    async def _startup():
        await tg_app.initialize()
        await tg_app.start()
        if PUBLIC_URL:
            hook = f"{PUBLIC_URL}{WEBHOOK_PATH}"
            await tg_app.bot.set_webhook(url=hook, drop_pending_updates=True)
            log.info(f"✓ Webhook set: {hook}")
        else:
            log.warning("RENDER_EXTERNAL_URL غير محدد؛ لن يتم تعيين Webhook.")

    _loop.run_until_complete(_startup())
    _loop.run_forever()

threading.Thread(target=_bot_thread, daemon=True).start()

@app.post(WEBHOOK_PATH)
def webhook_post():
    """Telegram سيستدعي هذا بالـ POST. ندفع التحديث للـ PTB loop."""
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, tg_app.bot)
        asyncio.run_coroutine_threadsafe(tg_app.process_update(update), _loop)
    except Exception as e:
        log.exception("webhook error: %s", e)
        return "error", 500
    return "ok"

# ---------- Helpers ----------
AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
EN_DIGITS = "0123456789"
TRANS = str.maketrans(AR_DIGITS, EN_DIGITS)

def to_int(s: str) -> Optional[int]:
    try:
        return int(s.strip().translate(TRANS))
    except Exception:
        return None

async def send_long(chat, text, kb=None):
    chunk = 3500
    for i in range(0, len(text), chunk):
        await chat.send_message(text[i:i+chunk], reply_markup=kb if i+chunk >= len(text) else None)

# ---------- Keyboards ----------
TOP_KB = ReplyKeyboardMarkup(
    [
        ["عربي سايكو 🧠"],
        ["العلاج السلوكي المعرفي (CBT) 💊", "الاختبارات النفسية 📝"],
        ["اضطرابات الشخصية 🧩", "التحويل الطبي 🩺"],
    ],
    resize_keyboard=True
)
AI_CHAT_KB = ReplyKeyboardMarkup([["◀️ إنهاء جلسة عربي سايكو"]], resize_keyboard=True)

# ---------- States ----------
MENU, AI_CHAT = range(2)

# ---------- AI ----------
AI_SYSTEM_PROMPT = (
    "أنت «عربي سايكو»، مساعد نفسي عربي يعتمد مبادئ CBT.\n"
    "- تحدث بلطف وبالعربية المبسطة.\n"
    "- ساعد في تنظيم الأفكار وتمارين قصيرة.\n"
    "- لا تشخّص طبيًا ولا تصف أدوية. عند خطر فوري وجّه لطلب مساعدة عاجلة.\n"
    "- اختم بتلخيص قصير وخطوة عملية واحدة."
)

async def ai_complete(messages: List[Dict[str, str]]) -> str:
    if not AI_API_KEY:
        return "(الذكاء الاصطناعي غير مفعّل: AI_API_KEY مفقود)"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": PUBLIC_URL or "https://render.com",
        "X-Title": "Arabi Psycho",
    }
    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 600,
    }
    url = f"{AI_BASE_URL}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.exception("AI error")
        return f"(تعذّر توليد الرد: {e})"

async def ai_respond(user_text: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    hist: List[Dict[str, str]] = context.user_data.get("ai_hist", [])
    hist = hist[-20:]
    convo = [{"role": "system", "content": AI_SYSTEM_PROMPT}] + hist + [{"role": "user", "content": user_text}]
    reply = await ai_complete(convo)
    hist += [{"role": "user", "content": user_text}, {"role": "assistant", "content": reply}]
    context.user_data["ai_hist"] = hist[-20:]
    return reply

# ---------- Commands ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        "مرحبًا! أنا **عربي سايكو**. ابدأ جلسة الذكاء الاصطناعي أو استخدم القوائم.",
        reply_markup=TOP_KB
    )
    return MENU

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اكتب: عربي سايكو 🧠 ثم ابدأ الجلسة. للأكواد: /ai_diag", reply_markup=TOP_KB)
    return MENU

async def cmd_ai_diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    base_ok = "True" if AI_BASE_URL else "False"
    key_ok  = "True" if AI_API_KEY else "False"
    model   = AI_MODEL or "-"
    await update.message.reply_text(f"AI_BASE_URL set={base_ok} | KEY set={key_ok} | MODEL={model}")

# ---------- Routers ----------
async def top_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = (update.message.text or "").strip()
    if t.startswith("عربي سايكو"):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("ابدأ جلسة عربي سايكو 🤖", callback_data="start_ai")],
        ])
        await update.message.reply_text(
            "أنا مساعد نفسي مدعوم بالذكاء الاصطناعي (للتثقيف والدعم السلوكي).",
            reply_markup=kb
        )
        return MENU
    await update.message.reply_text("اختر من الأزرار أو اكتب /start.", reply_markup=TOP_KB)
    return MENU

async def start_ai_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "start_ai":
        context.user_data["ai_hist"] = []
        await q.message.reply_text(
            "بدأت جلسة **عربي سايكو**. اكتب ما يقلقك الآن.\nلإنهاء الجلسة: «◀️ إنهاء جلسة عربي سايكو».",
            reply_markup=AI_CHAT_KB
        )
        return AI_CHAT
    return MENU

async def ai_chat_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text in ("◀️ إنهاء جلسة عربي سايكو", "/خروج", "خروج"):
        await update.message.reply_text("انتهت الجلسة. رجوع للقائمة.", reply_markup=TOP_KB)
        return MENU

    # عرض حالة "يكتب…"
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    except Exception:
        pass

    reply = await ai_respond(text, context)
    await update.message.reply_text(reply, reply_markup=AI_CHAT_KB)
    return AI_CHAT

async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message("اختر من الأزرار أو اكتب /start.", reply_markup=TOP_KB)
    return MENU

def _register_handlers():
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start), CommandHandler("help", cmd_help)],
        states={
            MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, top_router)],
            AI_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat_flow)],
        },
        fallbacks=[MessageHandler(filters.ALL, fallback)],
        allow_reentry=True,
    )
    tg_app.add_handler(conv)
    tg_app.add_handler(CallbackQueryHandler(start_ai_cb, pattern="^start_ai$"))
    tg_app.add_handler(CommandHandler("ai_diag", cmd_ai_diag))

_register_handlers()

# ---------- PTB error log ----------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("PTB Error", exc_info=context.error)
tg_app.add_error_handler(on_error)
