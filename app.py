# -*- coding: utf-8 -*-
import os, json, asyncio, logging
from typing import Optional, Dict, Any, List, Tuple

import httpx
from flask import Flask, request, abort

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

# ===== الإعدادات العامة =====
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("app")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("متغير البيئة TELEGRAM_BOT_TOKEN غير موجود.")

RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")

# إعدادات الذكاء الاصطناعي (اختياري)
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "openrouter/auto")

CONTACT_THERAPIST_URL = os.getenv("CONTACT_THERAPIST_URL", "https://t.me/your_therapist")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "https://t.me/your_psychiatrist")

# لحفظ وضع المحادثة لكل مستخدم (وضع AI DSM مثلاً)
CHAT_MODE: Dict[int, str] = {}

# ===== Flask + PTB =====
flask_app = Flask(__name__)
tg_app: Application = Application.builder().token(TELEGRAM_TOKEN).build()

# ===== أدوات مساعدة =====
def main_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🧠 العلاج السلوكي المعرفي (CBT)", callback_data="cbt"),
        ],
        [
            InlineKeyboardButton("📝 اختبارات نفسية", callback_data="tests"),
            InlineKeyboardButton("🧩 اضطرابات الشخصية", callback_data="pd_info"),
        ],
        [
            InlineKeyboardButton("🤖 تشخيص مبدئي بالذكاء الاصطناعي (DSM-5-TR)", callback_data="ai_dsm"),
        ],
        [
            InlineKeyboardButton("👩‍⚕️ أخصائي نفسي", url=CONTACT_THERAPIST_URL),
            InlineKeyboardButton("🧑‍⚕️ طبيب نفسي", url=CONTACT_PSYCHIATRIST_URL),
        ],
        [
            InlineKeyboardButton("📚 ملاحظة حول DSM-5-TR", callback_data="dsm_note"),
        ],
    ]
    return InlineKeyboardMarkup(rows)

async def send_typing(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

def ensure_markdown(text: str) -> str:
    return text.replace("_", "\\_").replace("*", "\\*")

# ===== أوامر أساسية =====
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    CHAT_MODE.pop(update.effective_chat.id, None)
    welcome = (
        "مرحبًا بك في **Arabi Psycho** 👋\n"
        "أنا مساعد نفسي توعوي — أقدم تمارين CBT واختبارات قصيرة ومعلومات عن اضطرابات الشخصية، "
        "وأيضًا *تشخيصًا مبدئيًا* مدعومًا بالذكاء الاصطناعي وفق إرشادات DSM-5-TR (ليس بديلاً عن زيارة مختص).\n\n"
        "اختر من القائمة:"
    )
    await update.effective_message.reply_text(
        welcome, reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = (
        "الأوامر المتاحة:\n"
        "/start — عرض القائمة الرئيسية\n"
        "/help — مساعدة\n"
        "/menu — فتح القائمة\n\n"
        "يمكنك كذلك كتابة أعراضك مباشرة وسأحاول مساعدتك."
    )
    await update.effective_message.reply_text(msg)

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "القائمة الرئيسية:", reply_markup=main_menu_kb()
    )

# ======= الذكاء الاصطناعي (DSM) =======
AI_SYS_PROMPT = (
    "أنت مساعد صحة نفسية باللغة العربية. قدّم تحليلًا مبدئيًا فقط (ليس تشخيصًا نهائيًا) "
    "بناءً على DSM-5-TR: اذكر الاحتمالات الأكثر منطقية، والمعايير التي تنطبق أو لا تنطبق بإيجاز، "
    "والتفريقات التشخيصية المحتملة، وخطة أولية (تعليمية/سلوكية، ومتى يجب طلب مساعدة فورية). "
    "استخدم لغة واضحة وحنونة، ولا تُصدر أحكامًا. حد أقصى 1800 حرف."
)

async def ai_complete(user_text: str) -> str:
    """
    يستدعي واجهة الذكاء الاصطناعي إن توفرت مفاتيحها، وإلا يرجع ردًا ثابتًا.
    """
    if not AI_API_KEY:
        # وضع بديل بدون API
        return (
            "هذا تحليل مبدئي (تجريبي) بناءً على وصفك. للحصول على تحليل أذكى، "
            "أضف مفتاح AI_API_KEY و AI_MODEL في متغيرات البيئة.\n\n"
            f"وصفك: {user_text[:400]}..."
        )

    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": AI_SYS_PROMPT},
            {"role": "user", "content": user_text},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{AI_BASE_URL}/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            # OpenRouter/OpenAI-like
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            return content or "لم أتمكن من توليد رد الآن."
    except Exception as e:
        LOG.exception("AI error: %s", e)
        return "تعذر الاتصال بخدمة الذكاء الاصطناعي حاليًا."

# ======= أزرار القائمة =======
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id

    if q.data == "cbt":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🧾 سجل الأفكار (Thought Record)", callback_data="cbt_tr")],
            [InlineKeyboardButton("🫁 تمرين تنفس 4-7-8", callback_data="cbt_breath")],
            [InlineKeyboardButton("📅 جدولة أنشطة مُسعدِة", callback_data="cbt_pa")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
        ])
        await q.edit_message_text("اختر أداة CBT:", reply_markup=kb)

    elif q.data == "tests":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("PHQ-2 (مؤشرات مزاج)", callback_data="test_phq2")],
            [InlineKeyboardButton("GAD-2 (مؤشرات قلق)", callback_data="test_gad2")],
            [InlineKeyboardButton("BPD-5 (مؤشرات أولية)", callback_data="test_bpd5")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
        ])
        await q.edit_message_text("اختر اختبارًا قصيرًا:", reply_markup=kb)

    elif q.data == "pd_info":
        text = (
            "🧩 **اضطرابات الشخصية** (تصنيف تقريبي):\n"
            "- المجموعة A (غريبة/غريبة الأطوار): بارانوية، انفصام شخصية فصامي، فصامية.\n"
            "- المجموعة B (درامية/اندفاعية): حدية، نرجسية، هستيرية، معادية للمجتمع.\n"
            "- المجموعة C (قلِقة/خجولة): تجنُّبية، اعتمادية، قسرية وسواسية.\n\n"
            "هذه معلومات تثقيفية وليست تشخيصًا. اطلب تقييمًا مهنيًا عند المعاناة."
        )
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")]]
        ))

    elif q.data == "ai_dsm":
        CHAT_MODE[chat_id] = "dsm"
        await q.edit_message_text(
            "🔎 **تشخيص مبدئي بالذكاء الاصطناعي**\n"
            "اكتب أعراضك (المدة، الشدة، مواقف مثيرة، تأثيرها على الدراسة/العمل/النوم...)\n"
            "سأحلّلها مبدئيًا وفق DSM-5-TR. (ليس بديلاً عن زيارة مختص).",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")]])
        )

    elif q.data == "dsm_note":
        await q.edit_message_text(
            "📚 **ملاحظة حول DSM-5-TR**\n"
            "النسخة الكاملة مرخّصة ومدفوعة ولا أستطيع مشاركتها. "
            "بدلًا من ذلك أوفّر تحليلًا مبدئيًا مستندًا إلى معاييره لأغراض التثقيف فقط.",
            parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")]]
            )
        )

    elif q.data == "back_home":
        CHAT_MODE.pop(chat_id, None)
        await q.edit_message_text("القائمة الرئيسية:", reply_markup=main_menu_kb())

    # محاثات CBT السريعة
    elif q.data == "cbt_breath":
        msg = (
            "🫁 **تنفس 4-7-8**\n"
            "1) شهيق عبر الأنف 4 ثوانٍ\n"
            "2) احتفاظ بالنفَس 7 ثوانٍ\n"
            "3) زفير بطيء عبر الفم 8 ثوانٍ\n"
            "كرّر 4 مرات. يساعد على تهدئة الجهاز العصبي."
        )
        await q.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="cbt")]]))

    elif q.data == "cbt_pa":
        msg = (
            "📅 **جدولة نشاط مُسعد**\n"
            "اختر نشاطًا بسيطًا يُشعرك بالقيمة أو المتعة (مثل المشي 10 دقائق، اتصال بصديق، ترتيب مساحة صغيرة).\n"
            "ضعه في وقت محدد اليوم ونفّذه. راقب مزاجك قبل وبعد."
        )
        await q.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="cbt")]]))

    elif q.data == "cbt_tr":
        await start_cbt_tr(update, context)

    # اختبارات
    elif q.data in {"test_phq2", "test_gad2", "test_bpd5"}:
        await start_test(update, context, q.data)

# ======= CBT Thought Record (محادثة) =======
CBT_EVENT, CBT_THOUGHT, CBT_EMOTION, CBT_ALT = range(4)

async def start_cbt_tr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.edit_message_text("🧾 **سجل الأفكار** — ما الحدث/الموقف الذي حدث؟",
                                  parse_mode=ParseMode.MARKDOWN)
    # تهيئة البيانات
    context.user_data["cbt_tr"] = {}
    # تحويل التفاعل إلى الرسائل (ConversationHandler يتتبع الحالة)
    await tg_app.bot.send_message(chat_id=update.effective_chat.id,
                                  text="اكتب وصف الحدث هنا…")
    # نغيّر الحالة يدويًا بإرسال أمر داخلي
    context.user_data["cbt_state"] = CBT_EVENT

async def cbt_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("cbt_state")
    data = context.user_data.get("cbt_tr", {})
    text = update.message.text.strip()

    if state == CBT_EVENT:
        data["event"] = text
        context.user_data["cbt_state"] = CBT_THOUGHT
        await update.message.reply_text("ما **الفكرة التلقائية** التي خطرت لك؟")
    elif state == CBT_THOUGHT:
        data["thought"] = text
        context.user_data["cbt_state"] = CBT_EMOTION
        await update.message.reply_text("ما **المشاعر** (واحدة أو أكثر) ودرجتها من 0 إلى 100؟")
    elif state == CBT_EMOTION:
        data["emotion"] = text
        context.user_data["cbt_state"] = CBT_ALT
        await update.message.reply_text("ما **الفكرة البديلة المتوازنة** التي يمكن تجربتها؟")
    elif state == CBT_ALT:
        data["alt"] = text
        context.user_data["cbt_state"] = None
        context.user_data["cbt_tr"] = data

        summary = (
            "تمرين **سجل الأفكار**\n\n"
            f"- الحدث: {ensure_markdown(data.get('event',''))}\n"
            f"- الفكرة التلقائية: {ensure_markdown(data.get('thought',''))}\n"
            f"- المشاعر/الدرجة: {ensure_markdown(data.get('emotion',''))}\n"
            f"- الفكرة البديلة: {ensure_markdown(data.get('alt',''))}\n\n"
            "جرّب الفكرة البديلة في موقف مشابه وقيّم الفرق."
        )
        await update.message.reply_text(summary, parse_mode=ParseMode.MARKDOWN,
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="cbt")]]))

# ======= اختبارات قصيرة =======
TEST_ACTIVE = "test_active"
TEST_IDX = "test_idx"
TEST_SCORE = "test_score"
TEST_PAYLOAD = "test_payload"

# تعريفات أسئلة (0..3 نقاط)
PHQ2 = {
    "title": "PHQ-2 (مؤشرات مزاج)",
    "desc": "خلال آخر أسبوعين، كم مرة حدث التالي؟",
    "answers": ["أبدًا (0)", "عدة أيام (1)", "أكثر من النصف (2)", "تقريبًا كل يوم (3)"],
    "qs": [
        "قلة الاهتمام أو المتعة في عمل الأشياء.",
        "الشعور بالاكتئاب أو اليأس.",
    ],
    "cutoff": 3,
}
GAD2 = {
    "title": "GAD-2 (مؤشرات قلق)",
    "desc": "خلال آخر أسبوعين، كم مرة حدث التالي؟",
    "answers": ["أبدًا (0)", "عدة أيام (1)", "أكثر من النصف (2)", "تقريبًا كل يوم (3)"],
    "qs": [
        "التوتر أو القلق أو العصبية.",
        "عدم القدرة على التوقف عن القلق أو التحكم فيه.",
    ],
    "cutoff": 3,
}
BPD5 = {
    "title": "BPD-5 (مؤشرات أولية لاضطراب الشخصية الحدية)",
    "desc": "اختر مدى انطباق كل عبارة (0 لا تنطبق .. 3 جدًا).",
    "answers": ["0", "1", "2", "3"],
    "qs": [
        "مشاعر قوية ومتقلبة تتبدل بسرعة.",
        "سلوكيات اندفاعية قد تضرّ (صرف، طعام، قيادة...).",
        "حساسية شديدة للهجر أو الرفض.",
        "صورة ذاتية غير مستقرة (من أنا؟).",
        "تذبذب شديد بالعلاقات (مثالية ثم خيبة).",
    ],
    "cutoff": 8,  # مؤشر فقط
}

TESTS = {
    "test_phq2": PHQ2,
    "test_gad2": GAD2,
    "test_bpd5": BPD5,
}

async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str) -> None:
    spec = TESTS[key]
    context.user_data[TEST_ACTIVE] = key
    context.user_data[TEST_IDX] = 0
    context.user_data[TEST_SCORE] = 0

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("ابدأ", callback_data="test_next")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="tests")],
    ])
    await update.callback_query.edit_message_text(
        f"**{spec['title']}**\n{spec['desc']}", parse_mode=ParseMode.MARKDOWN, reply_markup=kb
    )

async def test_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()

    active = context.user_data.get(TEST_ACTIVE)
    if not active:
        await q.edit_message_text("لا يوجد اختبار نشِط.", reply_markup=main_menu_kb())
        return

    spec = TESTS[active]
    idx = context.user_data.get(TEST_IDX, 0)

    if q.data == "test_next":
        # عرض السؤال idx
        if idx >= len(spec["qs"]):
            await conclude_test(q, context, spec)
            return
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(spec["answers"][0], callback_data="ans_0"),
            InlineKeyboardButton(spec["answers"][1], callback_data="ans_1"),
            InlineKeyboardButton(spec["answers"][2], callback_data="ans_2"),
            InlineKeyboardButton(spec["answers"][3], callback_data="ans_3"),
        ]])
        await q.edit_message_text(
            f"سؤال {idx+1}/{len(spec['qs'])}\n{spec['qs'][idx]}",
            reply_markup=kb
        )
    elif q.data.startswith("ans_"):
        val = int(q.data.split("_")[1])
        context.user_data[TEST_SCORE] = context.user_data.get(TEST_SCORE, 0) + val
        context.user_data[TEST_IDX] = idx + 1
        # السؤال التالي
        if context.user_data[TEST_IDX] >= len(spec["qs"]):
            await conclude_test(q, context, spec)
        else:
            await test_button(Update.de_json(q.to_dict(), tg_app.bot), context)
            # hack لاستدعاء التالي:
            await q.edit_message_text(
                f"سؤال {context.user_data[TEST_IDX]+0}/{len(spec['qs'])}\n{spec['qs'][context.user_data[TEST_IDX]]}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(spec["answers"][0], callback_data="ans_0"),
                    InlineKeyboardButton(spec["answers"][1], callback_data="ans_1"),
                    InlineKeyboardButton(spec["answers"][2], callback_data="ans_2"),
                    InlineKeyboardButton(spec["answers"][3], callback_data="ans_3"),
                ]])
            )

async def conclude_test(q, context, spec) -> None:
    score = context.user_data.get(TEST_SCORE, 0)
    cutoff = spec["cutoff"]
    note = "النتيجة **ضمن النطاق المنخفض** — مؤشّر ضعيف." if score < cutoff else \
           "النتيجة **مرتفعة نسبيًا** — مؤشّر يستحق المتابعة مع مختص."
    msg = (
        f"**{spec['title']}**\n"
        f"مجموع النقاط: {score}\n\n"
        f"{note}\n\n"
        "⚠️ هذه أدوات تحرّي سريعة وليست تشخيصًا نهائيًا."
    )
    await q.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="tests")]]))
    # تنظيف
    for k in (TEST_ACTIVE, TEST_IDX, TEST_SCORE):
        context.user_data.pop(k, None)

# ===== استقبال رسائل المستخدم =====
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = update.effective_message.text or ""

    # لو المستخدم داخل وضع DSM AI
    if CHAT_MODE.get(chat_id) == "dsm":
        await send_typing(context, chat_id)
        reply = await ai_complete(text)
        await update.effective_message.reply_text(reply)
        return

    # لو داخل محادثة CBT
    if context.user_data.get("cbt_state") is not None:
        await cbt_conversation(update, context)
        return

    # افتراضي: إظهار القائمة إذا كتب أي شيء
    await update.effective_message.reply_text(
        "تم الاستلام ✔️\nاختر من القائمة:", reply_markup=main_menu_kb()
    )

# ===== تسجيل الهاندلرز =====
def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("menu", cmd_menu))

    # الأزرار العامة + اختبارات
    application.add_handler(CallbackQueryHandler(on_button, pattern="^(cbt|tests|pd_info|ai_dsm|dsm_note|back_home|cbt_breath|cbt_pa|cbt_tr|test_phq2|test_gad2|test_bpd5)$"))
    application.add_handler(CallbackQueryHandler(test_button, pattern="^(test_next|ans_0|ans_1|ans_2|ans_3)$"))

    # كل النصوص الأخرى
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

register_handlers(tg_app)

# ===== مسار الويبهوك =====
@flask_app.post("/webhook/secret")
def webhook() -> ("str", int):
    if request.headers.get("content-type") != "application/json":
        abort(403)
    try:
        update = Update.de_json(request.get_json(force=True), tg_app.bot)
        # معالجة غير متزامنة
        asyncio.get_event_loop().create_task(tg_app.process_update(update))
    except Exception as e:
        LOG.exception("webhook error: %s", e)
    return "OK", 200

@flask_app.get("/")
def root_index():
    return "Arabi Psycho OK"

# ===== تشغيل محليًا (اختياري) =====
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    if RENDER_EXTERNAL_URL:
        LOG.info("Running behind Render (webhook mode).")
    else:
        LOG.info("Running local Flask on port %s", port)
    flask_app.run(host="0.0.0.0", port=port)
