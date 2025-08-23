# -*- coding: utf-8 -*-
"""
Arabi Psycho Bot - Flask + PTB v21 (Webhook)
"""
import os
import json
import asyncio
import logging
import threading
from typing import Optional

from flask import Flask, request, abort
from telegram import Update
from telegram.ext import Application

# موديول الميزات والقوائم (تأكد أن features.py موجود)
from features import register_handlers

# ====== إعداد اللوج ======
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("app")

# ====== متغيرات البيئة ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN غير موجد في إعدادات Render → Environment")

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "secret")  # مسار آمن بسيط

# ====== Flask ======
flask_app = Flask(__name__)

# ====== PTB Application + Event Loop في خيط خلفي ======
application: Optional[Application] = None
_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()


async def _ptb_start():
    """تهيئة تطبيق PTB وتشغيله (بدون polling؛ نعالج التحديثات يدوياً من الويبهوك)."""
    global application
    application = Application.builder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()

    # سجّل الهاندلرز (قوائم/CBT/اختبارات/DSM/…)
    register_handlers(application)

    await application.initialize()
    await application.start()

    # اضبط الويبهوك تلقائيًا إذا كان عنوان ريندر معروف
    if RENDER_URL:
        url = f"{RENDER_URL}/webhook/{WEBHOOK_SECRET}"
        try:
            await application.bot.set_webhook(url=url, drop_pending_updates=False)
            LOG.info("Webhook set to %s", url)
        except Exception as e:
            LOG.warning("set_webhook skipped/failed: %s", e)


# شغّل تهيئة PTB داخل اللوب الخلفي
asyncio.run_coroutine_threadsafe(_ptb_start(), _loop)

# ====== Routes ======
@flask_app.get("/")
def index():
    return "Arabi Psycho OK", 200


@flask_app.get("/health")
def health():
    return "ok", 200


@flask_app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST", "GET"])
def telegram_webhook():
    # بعض الخدمات تعمل GET/HEAD للفحص الصحي — نرجّع 200
    if request.method != "POST":
        return "Webhook OK", 200

    if application is None:
        abort(503)

    data = request.get_json(silent=True, force=True)
    if not data:
        abort(400)

    try:
        update = Update.de_json(data, application.bot)
        # مرّر المعالجة لكوروتين PTB داخل اللوب الخلفي
        fut = asyncio.run_coroutine_threadsafe(application.process_update(update), _loop)
        fut.result(timeout=0)  # لا ننتظر التنفيذ؛ فقط حتى تُسجّل المهمّة
    except Exception as e:
        LOG.exception("webhook error: %s", e)
        abort(500)

    return "OK", 200


@flask_app.get("/ai_diag")
def ai_diag():
    """تشخيص مبسّط لإعدادات الذكاء الاصطناعي (بدون كشف أسرار)."""
    from features import AI_BASE_URL, AI_MODEL, CONTACT_THERAPIST_URL, CONTACT_PSYCHIATRIST_URL
    info = {
        "render_url": RENDER_URL or None,
        "webhook_path": f"/webhook/{WEBHOOK_SECRET}",
        "ai_base_url": AI_BASE_URL,
        "ai_model": AI_MODEL,
        "ai_key_set": bool(os.getenv("AI_API_KEY", "")),
        "contact_therapist": CONTACT_THERAPIST_URL,
        "contact_psychiatrist": CONTACT_PSYCHIATRIST_URL,
    }
    return flask_app.response_class(
        response=json.dumps(info, ensure_ascii=False, indent=2),
        mimetype="application/json",
        status=200,
    )


# ========== تشغيل عبر gunicorn ==========
# Procfile/gunicorn يتولى تشغيل: gunicorn -w 1 -k gthread -b 0.0.0.0:$PORT app:flask_app
