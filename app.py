
# -*- coding: utf-8 -*-
# app.py — Arabi Psycho Telegram bot (Flask Webhook + PTB v21)

import os
import json
import logging
import threading
import asyncio
from typing import Optional

import httpx
from flask import Flask, request, abort

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================== Logging ==================
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("arabi_psycho")

# ================== Env ==================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("Environment TELEGRAM_BOT_TOKEN مفقود.")

RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
WEBHOOK_SECRET = "secret"  # المسار: /webhook/secret

# إعدادات الذكاء الاصطناعي (OpenRouter أو متوافق OpenAI)
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
AI_API_KEY = os.getenv("AI_API_KEY", "")  # ضع مفتاح OpenRouter هنا
AI_MODEL = os.getenv("AI_MODEL", "google/gemini-1.5-flash")

CONTACT_THERAPIST_URL = os.getenv("CONTACT_THERAPIST_URL", "https://t.me/your_therapist")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "https://t.me/your_psychiatrist")

# ================== Flask & PTB ==================
app = Flask(__name__)

# مهم: نمنع الـ Updater (Polling) لأننا نستخدم Webhook
tg_app: Application = Application.builder().token(TELEGRAM_TOKEN).updater(None).build()

# سنشغّل حلقة asyncio خاصة بالبوت في خيط خلفي (متوافق مع Flask 3)
_bg_loop: Optional[asyncio.AbstractEventLoop] = None
_started = False


def _run_loop(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _start_ptb_background():
    """تشغيل PTB في خيط خلفي + ضبط الويبهوك."""
    global _bg_loop, _started
    if _started:
        return
    _started = True

    _bg_loop = asyncio.new_event_loop()
    threading.Thread(target=_run_loop, args=(_bg_loop,), daemon=True).start()

    # initialize / start PTB داخل الحلقة الخلفية (وننتظر النتيجة)
    asyncio.run_coroutine_threadsafe(tg_app.initialize(), _bg_loop).result()
    asyncio.run_coroutine_threadsafe(tg_app.start(), _bg_loop).result()

    # اضبط الويبهوك إن وُجد URL
    if RENDER_URL:
        url = f"{RENDER_URL}/webhook/{WEBHOOK_SECRET}"
        asyncio.run_coroutine_threadsafe(
            tg_app.bot.set_webhook(
                url=url,
                allowed_updates=["message", "callback_query"],
                max_connections=40,
            ),
            _bg_loop,
        ).result()
        info = asyncio.run_coroutine_threadsafe(tg_app.bot.get_webhook_info(), _bg_loop).result()
        LOG.info("Webhook set: %s | pending: %s", info.url, info.pending_update_count)
    else:
        LOG.warning("RENDER_EXTERNAL_URL غير معيّن؛ لن أضبط webhook تلقائياً.")


# نشغّل البوت أول مرّة عند أول طلب يأتي للسيرفر
@app.before_request
def _ensure_boot():
    if not _started:
        _start_ptb_background()


# ================== واجهات المستخدم ==================
AI_MODE_FLAG = "ai_dsm_mode"
TEST_STATE = "test_state"  # dict: {name, idx, score}

PHQ9_QUESTIONS = [
    "قلّة الاهتمام أو المتعة بالقيام بالأمور",
    "الشعور بالإحباط أو الكآبة أو اليأس",
    "صعوبة النوم أو كثرة النوم",
    "الشعور بالتعب أو قلة الطاقة",
    "ضعف الشهية أو الإفراط في الأكل",
    "الشعور بسوء عن النفس أو بالفشل",
    "صعوبة التركيز",
    "بطء الحركة/الكلام أو التململ الشديد",
    "أفكار بأنك ستكون أفضل حالاً لو متَّ أو إيذاء النفس",
]
GAD7_QUESTIONS = [
    "الشعور بالتوتر أو القلق أو على الحافة",
    "عدم القدرة على التوقف عن القلق أو السيطرة عليه",
    "القلق المفرط تجاه أمور مختلفة",
    "صعوبة الاسترخاء",
    "التململ إلى حد صعوبة الجلوس بثبات",
    "الانزعاج بسرعة أو التهيّج",
    "الشعور بالخوف كأن شيئاً سيئاً قد يحدث",
]
ANS_KB = InlineKeyboardMarkup.from_row(
    [InlineKeyboardButton("0", callback_data="ans:0"),
     InlineKeyboardButton("1", callback_data="ans:1"),
     InlineKeyboardButton("2", callback_data="ans:2"),
     InlineKeyboardButton("3", callback_data="ans:3")]
)


def main_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🧠 العلاج السلوكي (CBT)", callback_data="cbt"),
            InlineKeyboardButton("🧪 اختبارات نفسية", callback_data="tests"),
        ],
        [
            InlineKeyboardButton("🧩 اضطرابات الشخصية", callback_data="personality"),
            InlineKeyboardButton("🤖 تشخيص DSM (ذكاء اصطناعي)", callback_data="ai_dsm"),
        ],
        [
            InlineKeyboardButton("👩‍⚕️ الأخصائي النفسي", url=CONTACT_THERAPIST_URL),
            InlineKeyboardButton("👨‍⚕️ الطبيب النفسي", url=CONTACT_PSYCHIATRIST_URL),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع للقائمة", callback_data="back_home")]])


def cbt_kb() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("📝 سجل المزاج", callback_data="cbt_mood"),
            InlineKeyboardButton("💭 سجل الأفكار", callback_data="cbt_thought"),
        ],
        [
            InlineKeyboardButton("🚶‍♂️ تعرّض تدريجي", callback_data="cbt_exposure"),
            InlineKeyboardButton("🧰 أدوات سريعة", callback_data="cbt_tools"),
        ],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
    ]
    return InlineKeyboardMarkup(rows)


def tests_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("PHQ-9 (اكتئاب)", callback_data="test_phq9")],
        [InlineKeyboardButton("GAD-7 (قلق)", callback_data="test_gad7")],
        [InlineKeyboardButton("PCL-5 (صدمة) — قريبًا", callback_data="test_soon")],
        [InlineKeyboardButton("اضطرابات الشخصية (مختصر) — قريبًا", callback_data="test_soon")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
    ]
    return InlineKeyboardMarkup(rows)


def personality_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("حدّية", callback_data="pd_bpd"),
         InlineKeyboardButton("انعزالية", callback_data="pd_schizoid")],
        [InlineKeyboardButton("نرجسية", callback_data="pd_npd"),
         InlineKeyboardButton("وسواسية قهرية", callback_data="pd_ocpd")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
    ]
    return InlineKeyboardMarkup(rows)


# ================== ذكاء اصطناعي ==================
async def ai_dsm_reply(prompt: str) -> Optional[str]:
    """يُنتج استجابة فرز تشخيصي أولي (DSM-5-TR). يرجّع None إذا المفتاح غير موجود أو حدث خطأ."""
    if not AI_API_KEY:
        return None

    system = (
        "أنت مساعد طبّي نفسي افتراضي. لا تقدّم تشخيصًا نهائيًا أو أدوية. "
        "اعتمد DSM-5-TR للوصف، اطرح أسئلة فرز قصيرة، ثم قدّم احتمالات أولية مع تنبيه بضرورة التقييم السريري."
    )

    try:
        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
            # لتجنّب أخطاء OpenRouter 401 في بعض الحالات:
            "X-Title": "ArabiPsycho Telegram Bot",
        }
        if RENDER_URL:
            headers["HTTP-Referer"] = RENDER_URL

        payload = {
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 800,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{AI_BASE_URL}/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        # متوافق مع واجهة OpenAI/OpenRouter
        return data["choices"][0]["message"]["content"].strip()

    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        LOG.error("arabi_psycho AI HTTP %s: %s", e.response.status_code, detail)
        return None
    except Exception as e:
        LOG.exception("AI error: %s", e)
        return None


# ================== Handlers ==================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop(AI_MODE_FLAG, None)
    context.user_data.pop(TEST_STATE, None)
    await update.effective_chat.send_action(ChatAction.TYPING)
    await update.effective_message.reply_text("القائمة الرئيسية:", reply_markup=main_menu_kb())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "الأوامر:\n"
        "/start — القائمة الرئيسية\n"
        "/help — المساعدة\n"
        "/ping — اختبار سريع"
    )


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("pong ✅")


async def cb_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()
    data = q.data

    # رجوع
    if data == "back_home":
        context.user_data.pop(AI_MODE_FLAG, None)
        context.user_data.pop(TEST_STATE, None)
        await q.edit_message_text("القائمة الرئيسية:", reply_markup=main_menu_kb())
        return

    # ========== CBT ==========
    if data == "cbt":
        msg = (
            "العلاج السلوكي المعرفي (CBT): اختر أداة لبدء خطوة عملية.\n"
            "يمكنك تسجيل المزاج، أو عمل سجل أفكار، أو التعرّض التدريجي."
        )
        await q.edit_message_text(msg, reply_markup=cbt_kb())
        return

    if data == "cbt_mood":
        txt = (
            "📝 **سجل المزاج (يومي)**\n"
            "- قيّم مزاجك من 0 إلى 10 الآن.\n"
            "- اذكر حدث اليوم ومَن حولك.\n"
            "- ما الفكرة السائدة؟ وما السلوك الذي فعلته؟\n"
            "- ماذا ستجرّب لاحقاً لتحسين نقطة واحدة؟"
        )
        await q.edit_message_text(txt, reply_markup=cbt_kb(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "cbt_thought":
        txt = (
            "💭 **سجل الأفكار**\n"
            "1) الموقف\n2) الفكرة التلقائية\n3) الدليل مع/ضد\n4) إعادة الصياغة المتوازنة\n5) شدة الشعور قبل/بعد"
        )
        await q.edit_message_text(txt, reply_markup=cbt_kb(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "cbt_exposure":
        txt = (
            "🚶‍♂️ **التعرّض التدريجي (للقلق/الرهاب)**\n"
            "- اكتب سلماً من 0 (سهل) إلى 10 (أصعب موقف)\n"
            "- ابدأ من 3–4 وكرّر التعرض حتى تنخفض شدة القلق 50%.\n"
            "- تقدّم تدريجاً درجة بعد درجة."
        )
        await q.edit_message_text(txt, reply_markup=cbt_kb(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "cbt_tools":
        txt = (
            "🧰 أدوات سريعة:\n"
            "- تنفس 4-4-6 (شهيق 4ث، حبس 4ث، زفير 6ث)\n"
            "- تفعيل الحواس 5-4-3-2-1\n"
            "- نشاط قصير ممتع/مفيد لمدة 10 دقائق"
        )
        await q.edit_message_text(txt, reply_markup=cbt_kb())
        return

    # ========== Tests ==========
    if data == "tests":
        await q.edit_message_text("اختر اختباراً:", reply_markup=tests_kb())
        return

    if data == "test_soon":
        await q.edit_message_text("هذا الاختبار سيُضاف قريبًا بإذن الله.", reply_markup=tests_kb())
        return

    if data in ("test_phq9", "test_gad7"):
        if data == "test_phq9":
            name, questions = "PHQ-9", PHQ9_QUESTIONS
        else:
            name, questions = "GAD-7", GAD7_QUESTIONS
        context.user_data[TEST_STATE] = {"name": name, "idx": 0, "score": 0, "q": questions}
        await q.edit_message_text(
            f"📋 {name}\nأجب بالضغط على 0/1/2/3 لكل سؤال (0=أبدًا … 3=تقريبًا يوميًا).",
            reply_markup=back_kb(),
        )
        await q.message.reply_text(f"س1) {questions[0]}", reply_markup=ANS_KB)
        return

    if data.startswith("ans:"):
        ts = context.user_data.get(TEST_STATE)
        if not ts:
            await q.answer("لا يوجد اختبار نشط.")
            return
        val = int(data.split(":")[1])
        ts["score"] += val
        ts["idx"] += 1

        if ts["idx"] < len(ts["q"]):
            await q.message.reply_text(f"س{ts['idx']+1}) {ts['q'][ts['idx']]}", reply_markup=ANS_KB)
        else:
            # انتهى الاختبار
            name, total = ts["name"], ts["score"]
            context.user_data.pop(TEST_STATE, None)
            interpretation = ""
            if name == "PHQ-9":
                # 0–4 طبيعي، 5–9 خفيف، 10–14 متوسط، 15–19 شديد، 20–27 شديد جدًا
                if total <= 4: interpretation = "النتيجة ضمن الطبيعي."
                elif total <= 9: interpretation = "اكتئاب خفيف محتمل."
                elif total <= 14: interpretation = "اكتئاب متوسط محتمل."
                elif total <= 19: interpretation = "اكتئاب شديد محتمل."
                else: interpretation = "اكتئاب شديد جدًا محتمل."
                max_score = 27
            else:
                # GAD-7: 0–4 طبيعي، 5–9 خفيف، 10–14 متوسط، 15–21 شديد
                if total <= 4: interpretation = "النتيجة ضمن الطبيعي."
                elif total <= 9: interpretation = "قلق خفيف محتمل."
                elif total <= 14: interpretation = "قلق متوسط محتمل."
                else: interpretation = "قلق شديد محتمل."
                max_score = 21

            await q.message.reply_text(
                f"انتهى {name} ✅\nالدرجة: {total}/{max_score}\n{interpretation}\n\n"
                "⚠️ النتائج للفحص الأولي وليست تشخيصًا نهائيًا.",
                reply_markup=tests_kb(),
            )
        return

    # ========== Personality summaries ==========
    if data == "personality":
        await q.edit_message_text(
            "اختر اضطرابًا للاطلاع على ملخص توصيفي (DSM-5-TR):",
            reply_markup=personality_kb(),
        )
        return

    pd_map = {
        "pd_bpd": "الحدّية: تقلب وجداني شديد، اندفاعية، حساسية للهجر، علاقات متقلبة.",
        "pd_schizoid": "الانعزالية: انطواء وفتور عاطفي وقلة اهتمام بالعلاقات.",
        "pd_npd": "النرجسية: شعور بالعظمة، حاجة لإعجاب، حساسية للنقد، تعاطف منخفض.",
        "pd_ocpd": "الوسواسية القهرية (شخصية): كمالية، تصلّب، انشغال بالقواعد على حساب المرونة.",
    }
    if data in pd_map:
        await q.edit_message_text(
            f"🧩 {pd_map[data]}\n\nللاستشارة المتخصصة:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👩‍⚕️ الأخصائي النفسي", url=CONTACT_THERAPIST_URL)],
                [InlineKeyboardButton("👨‍⚕️ الطبيب النفسي", url=CONTACT_PSYCHIATRIST_URL)],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
            ]),
        )
        return

    # ========== AI DSM mode ==========
    if data == "ai_dsm":
        context.user_data[AI_MODE_FLAG] = True
        await q.edit_message_text(
            "✅ دخلت وضع *تشخيص DSM (ذكاء اصطناعي)*.\n"
            "اكتب مشكلتك/أعراضك بإيجاز، وسأطرح أسئلة فرز ثم أعطيك ملخص احتمالات أولية.\n"
            "للخروج اضغط «رجوع».",
            reply_markup=back_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.effective_message.text or "").strip()
    LOG.info("arabi_psycho INCOMING update: message")

    # وضع الذكاء الاصطناعي
    if context.user_data.get(AI_MODE_FLAG):
        await update.effective_chat.send_action(ChatAction.TYPING)
        ai_text = await ai_dsm_reply(text)
        if ai_text:
            suffix = "\n\n⚠️ هذه نتيجة أولية ولا تُعد تشخيصًا. يُنصح بالتقييم السريري."
            await update.effective_message.reply_text(ai_text + suffix, parse_mode=ParseMode.HTML)
        else:
            await update.effective_message.reply_text(
                "تعذّر استخدام الذكاء الاصطناعي حاليًا (تحقق من المفتاح/النموذج). أعد المحاولة لاحقًا أو تواصل مع مختص.",
            )
        return

    # الرد الافتراضي
    await update.effective_message.reply_text("القائمة الرئيسية:", reply_markup=main_menu_kb())


# ================== Register handlers ==================
def register_handlers() -> None:
    tg_app.add_handler(CommandHandler("start", cmd_start))
    tg_app.add_handler(CommandHandler("help", cmd_help))
    tg_app.add_handler(CommandHandler("ping", cmd_ping))
    tg_app.add_handler(CallbackQueryHandler(cb_router))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    LOG.info("Handlers registered")


register_handlers()

# ================== Flask routes ==================
@app.get("/")
def root_alive():
    return "OK", 200


@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    if request.headers.get("content-type") != "application/json":
        abort(403)
    try:
        data = request.get_json(force=True, silent=False)
        update = Update.de_json(data, tg_app.bot)
        # ضع التحديث في صف PTB داخل الحلقة الخلفية بأمان
        if _bg_loop is None:
            abort(503)
        fut = asyncio.run_coroutine_threadsafe(tg_app.update_queue.put(update), _bg_loop)
        fut.result(timeout=5)
        return "OK", 200
    except Exception as e:
        LOG.exception("webhook error: %s", e)
        return "ERR", 200

# ملاحظة: نقطة الدخول لـ gunicorn هي app:app
