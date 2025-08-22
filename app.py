# app.py — Webhook smoke test (Render + Telegram)
import os, asyncio, logging, threading
from flask import Flask, request

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("webhook-test")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
PUBLIC_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBHOOK_PATH = "/webhook/secret"

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")

# ---------- Flask ----------
app = Flask(__name__)

@app.get("/")
def health():
    return "Arabi Psycho OK"

# ---------- Telegram ----------
tg_app: Application = Application.builder().token(BOT_TOKEN).build()
_event_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ البوت شغال (Webhook OK). اكتب أي كلمة أشوفها.")

async def cmd_ai_diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    base_ok = "True" if PUBLIC_URL else "False"
    await update.message.reply_text(f"WEBHOOK = {PUBLIC_URL or '-'} | set={base_ok}")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    await update.message.reply_text(f"سمعتك: {txt}")

def _register_handlers():
    tg_app.add_handler(CommandHandler("start", cmd_start))
    tg_app.add_handler(CommandHandler("ai_diag", cmd_ai_diag))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

_register_handlers()

def _bot_loop():
    asyncio.set_event_loop(_event_loop)
    async def _startup():
        await tg_app.initialize()
        await tg_app.start()
        if PUBLIC_URL:
            hook_url = f"{PUBLIC_URL}{WEBHOOK_PATH}"
            await tg_app.bot.set_webhook(url=hook_url, drop_pending_updates=True)
            log.info(f"✓ Webhook set: {hook_url}")
        else:
            log.warning("RENDER_EXTERNAL_URL is empty; webhook not set.")
    _event_loop.run_until_complete(_startup())
    _event_loop.run_forever()

threading.Thread(target=_bot_loop, daemon=True).start()

@app.post(WEBHOOK_PATH)
def webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, tg_app.bot)
        asyncio.run_coroutine_threadsafe(tg_app.process_update(update), _event_loop)
    except Exception as e:
        log.exception("webhook error: %s", e)
        return "error", 500
    return "ok"
