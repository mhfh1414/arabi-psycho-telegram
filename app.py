# app.py — Arabi Psycho (Render + Telegram Webhook + OpenRouter)
# Python 3.10+ | python-telegram-bot v21
# Start command on Render:
#   gunicorn -w 1 -k gthread -b 0.0.0.0:$PORT app:app

import os, asyncio, logging, threading
from typing import List, Dict

import httpx
from flask import Flask, request

from telegram import (
    Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

# ============ Logs ============
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("arabi-psycho")

# ============ ENV ============
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
PUBLIC_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
WEBHOOK_PATH = "/webhook/secret"

AI_BASE_URL = (os.getenv("AI_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
AI_API_KEY  = os.getenv("AI_API_KEY", "")
AI_MODEL    = os.getenv("AI_MODEL", "openrouter/auto")

CONTACT_THERAPIST_URL    = os.getenv("CONTACT_THERAPIST_URL", "https://t.me/your_therapist")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "https://t.me/your_psychiatrist")

if not BOT_TOKEN:
    raise RuntimeError("✖ TELEGRAM_BOT_TOKEN is missing")

# ============ Flask (for gunicorn) ============
app = Flask(__name__)

@app.get("/")
def health():
    return "Arabi Psycho OK"

# ============ Telegram Application in a background thread ============
tg_app: Application = Application.builder().token(BOT_TOKEN).build()
_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()

def _runner():
    asyncio.set_event_loop(_loop)

    async def _startup():
        await tg_app.initialize()
        await tg_app.start()
        if PUBLIC_URL:
            hook_url = f"{PUBLIC_URL}{WEBHOOK_PATH}"
            await tg_app.bot.set_webhook(url=hook_url, drop_pending_updates=True)
            log.info(f"✓ Webhook set: {hook_url}")
        else:
            log.warning("RENDER_EXTERNAL_URL not set; webhook won't be configured.")

    _loop.run_until_complete(_startup())
    _loop.run_forever()

threading.Thread(target=_runner, daemon=True).start()

@app.post(WEBHOOK_PATH)
def webhook():
    """Receive Telegram updates and pass them to PTB."""
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, tg_app.bot)
        asyncio.run_coroutine_threadsafe(tg_app.process_update(update), _loop)
    except Exception as e:
        log.exception("webhook error: %s", e)
        return "error", 500
    return "ok"

# ============ AI (OpenRouter) ============
AI_SYSTEM_PROMPT = (
    "أنت «عربي سايكو»، مساعد نفسي عربي يعتمد مبادئ CBT.\n"
    "- تحدث بلطف وبالعربية المبسطة.\n"
    "- ساعد في تنظيم الأفكار وتمارين قصيرة.\n"
    "- لا تقدّم تشخيصًا طبيًا أو أدوية.\n"
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
    hist = context.user_data.get("ai_hist", [])
    hist = hist[-20:]
    convo = [{"role": "system", "content": AI_SYSTEM_PROMPT}] + hist + [{"role": "user", "content": user_text}]
    reply = await ai_complete(convo)
    hist += [{"role": "user", "content": user_text}, {"role": "assistant", "content": reply}]
    context.user_data["ai_hist"] = hist[-20:]
    return reply

# ============ Keyboards ============
TOP_KB = ReplyKeyboardMarkup(
    [
        ["عربي سايكو 🧠"],
        ["التحويل الطبي 🩺"],
    ],
    resize_keyboard=True
)
AI_CHAT_KB = ReplyKeyboardMarkup([["◀️ إنهاء جلسة عربي سايكو"]], resize_keyboard=True)

# ============ States ============
MENU, AI_CHAT = range(2)

# ============ Commands & Flows ============
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        "مرحبًا! أنا **عربي سايكو**. ابدأ جلسة الذكاء الاصطناعي.",
        reply_markup=TOP_KB
    )
    return MENU

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اكتب /start للعودة للقائمة.", reply_markup=TOP_KB)
    return MENU

async def cmd_ai_diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    base_ok = "True" if AI_BASE_URL else "False"
    key_ok  = "True" if AI_API_KEY else "False"
    model   = AI_MODEL or "-"
    await update.message.reply_text(f"AI_BASE_URL set={base_ok} | KEY set={key_ok} | MODEL={model}")

async def top_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = (update.message.text or "").strip()

    if t.startswith("عربي سايكو"):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("ابدأ جلسة عربي سايكو 🤖", callback_data="start_ai")],
        ])
        await update.message.reply_text(
            "أنا مساعد نفسي مدعوم بالذكاء الاصطناعي.\n"
            "ملاحظة: دعم تعليمي/سلوكي وليس تشخيصًا طبيًا.",
            reply_markup=kb
        )
        return MENU

    if t.startswith("التحويل الطبي"):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("تحويل إلى أخصائي نفسي 🎓", url=CONTACT_THERAPIST_URL)],
            [InlineKeyboardButton("تحويل إلى طبيب نفسي 🩺", url=CONTACT_PSYCHIATRIST_URL)],
        ])
        await update.message.reply_text("اختر نوع التحويل:", reply_markup=kb)
        return MENU

    await update.message.reply_text("اختر من الأزرار أو اكتب /start.", reply_markup=TOP_KB)
    return MENU

async def start_ai_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["ai_hist"] = []
    await q.message.reply_text(
        "بدأت جلسة **عربي سايكو**. اكتب ما يشغلك الآن.\nلإنهاء الجلسة: «◀️ إنهاء جلسة عربي سايكو».",
        reply_markup=AI_CHAT_KB
    )
    return AI_CHAT

async def ai_chat_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text in ("◀️ إنهاء جلسة عربي سايكو", "/خروج", "خروج"):
        await update.message.reply_text("انتهت الجلسة. رجوع للقائمة.", reply_markup=TOP_KB)
        return MENU

    # typing…
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    except Exception:
        pass

    reply = await ai_respond(text, context)
    await update.message.reply_text(reply, reply_markup=AI_CHAT_KB)
    return AI_CHAT

async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر من الأزرار أو اكتب /start.", reply_markup=TOP_KB)
    return MENU

# ============ Register Handlers ============
def _register_handlers():
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("help", cmd_help),
            CommandHandler("ai_diag", cmd_ai_diag),
        ],
        states={
            MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, top_router),
                CallbackQueryHandler(start_ai_cb, pattern="^start_ai$"),
            ],
            AI_CHAT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat_flow),
            ],
        },
        fallbacks=[MessageHandler(filters.ALL, fallback)],
        allow_reentry=True
    )
    tg_app.add_handler(conv)

_register_handlers()
