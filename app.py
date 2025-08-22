# app.py — Webhook deep debug (Render + Telegram)
import os, json, asyncio, logging, threading
from flask import Flask, request

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ---------- Logging ----------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("webhook-debug")

# ---------- ENV ----------
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

# ردود اختبار
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ البوت شغال (Webhook OK).")

async def cmd_ai_diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"RENDER_EXTERNAL_URL={PUBLIC_URL or '-'}")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    await update.message.reply_text(f"سمعتك: {txt}")

def _register_handlers():
    tg_app.add_handler(CommandHandler("start", cmd_start))
    tg_app.add_handler(CommandHandler("ai_diag", cmd_ai_diag))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

_register_handlers()

# نشغّل PTB في لوب مستقل
_event_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()

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

# ---------- Webhook endpoint ----------
@app.post(WEBHOOK_PATH)
def webhook():
    try:
        data = request.get_json(force=True, silent=False)
        # لوق كامل للتحديث
        log.info("<< UPDATE JSON: %s", json.dumps(data, ensure_ascii=False))
        update = Update.de_json(data, tg_app.bot)
        fut = asyncio.run_coroutine_threadsafe(tg_app.process_update(update), _event_loop)
        # لو صار استثناء داخل الكوروتين يطلع هنا
        try:
            fut.result(timeout=5)
            log.info(">> processed OK")
        except Exception as e:
            log.exception("process_update error: %s", e)
    except Exception as e:
        log.exception("webhook error: %s", e)
        return "error", 500
    return "ok"
