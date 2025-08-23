# features.py
# -*- coding: utf-8 -*-
import os
import json
import logging
from typing import Dict, Any, Optional, List

import httpx
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application, ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters,
)

log = logging.getLogger(__name__)

# ===== إعدادات الذكاء الاصطناعي وروابط التواصل =====
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1")
AI_API_KEY  = os.getenv("AI_API_KEY", "")
AI_MODEL    = os.getenv("AI_MODEL", "openrouter/auto")

CONTACT_THERAPIST_URL    = os.getenv("CONTACT_THERAPIST_URL", "https://t.me/your_therapist")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "https://t.me/your_psychiatrist")

# ===== حالات المحادثات =====
(
    CBT_TR_SITUATION, CBT_TR_THOUGHTS, CBT_TR_EMOTION, CBT_TR_ALT,
    EXP_TITLE, EXP_STEPS,
    TEST_ASK,
    DSM_COLLECT,
) = range(8)

# ===== القايمة الرئيسية =====
def main_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("💡 العلاج السلوكي (CBT)", callback_data="menu_cbt"),
            InlineKeyboardButton("🧪 اختبارات نفسية", callback_data="menu_tests"),
        ],
        [
            InlineKeyboardButton("🧩 اضطرابات الشخصية", callback_data="menu_pd"),
            InlineKeyboardButton("🧠 عربي سايكو (DSM AI)", callback_data="menu_dsm"),
        ],
        [
            InlineKeyboardButton("👩‍⚕️ أخصائي نفسي", url=CONTACT_THERAPIST_URL),
            InlineKeyboardButton("👨‍⚕️ طبيب نفسي", url=CONTACT_PSYCHIATRIST_URL),
        ],
        [InlineKeyboardButton("📚 نسخة DSM مختصرة", callback_data="menu_dsm_copy")],
    ]
    return InlineKeyboardMarkup(rows)

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "اختر من القائمة 👇"
    if update.message:
        await update.message.reply_text(text, reply_markup=main_menu_kb())
    else:
        await update.callback_query.edit_message_text(text, reply_markup=main_menu_kb())

# ===== 1) CBT =====
async def cbt_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 سجل الأفكار", callback_data="cbt_thought_record")],
        [InlineKeyboardButton("🪜 سلّم التعرّض", callback_data="cbt_exposure")],
        [InlineKeyboardButton("◀️ رجوع", callback_data="menu_home")],
    ])
    await q.edit_message_text("العلاج السلوكي: اختر أداة 👇", reply_markup=kb)

# — سجل الأفكار
async def tr_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _typing(update)
    context.user_data["tr"] = {}
    await _reply(update, "1/4) صف الموقف بإيجاز (الزمان/المكان/من معك؟)")
    return CBT_TR_SITUATION

async def tr_situation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tr"]["situation"] = update.message.text.strip()
    await _reply(update, "2/4) ما الأفكار التلقائية التي خطرت ببالك؟")
    return CBT_TR_THOUGHTS

async def tr_thoughts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tr"]["thoughts"] = update.message.text.strip()
    await _reply(update, "3/4) ما المشاعر (والشدة 0-100)؟")
    return CBT_TR_EMOTION

async def tr_emotion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tr"]["emotion"] = update.message.text.strip()
    await _reply(update, "4/4) اكتب أفكارًا بديلة أكثر توازنًا/دليلك ضد الفكرة.")
    return CBT_TR_ALT

async def tr_alt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tr = context.user_data.get("tr", {})
    tr["alt"] = update.message.text.strip()
    txt = (
        "✅ **ملخّص سجل الأفكار**\n"
        f"- الموقف: {tr.get('situation','')}\n"
        f"- الأفكار: {tr.get('thoughts','')}\n"
        f"- المشاعر: {tr.get('emotion','')}\n"
        f"- البدائل: {tr.get('alt','')}\n\n"
        "جرب إعادة تقييم الموقف وفق البدائل. أحسنت 👏"
    )
    await _reply(update, txt)
    await _reply(update, "يمكنك الرجوع للقائمة أو بدء سجل جديد.", reply_markup=main_menu_kb())
    return ConversationHandler.END

# — سلّم التعرّض
async def exp_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _typing(update)
    context.user_data["exp"] = {"title": None, "steps": []}
    await _reply(update, "اكتب اسم الخوف/الموقف المستهدف (مثال: قيادة السيارة).")
    return EXP_TITLE

async def exp_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["exp"]["title"] = update.message.text.strip()
    await _reply(update, "أضف خطوات التعرّض من الأسهل للأصعب. أرسل كل خطوة في رسالة منفصلة.\n"
                          "عندما تنتهي، أرسل كلمة: انتهيت")
    return EXP_STEPS

async def exp_steps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "انتهيت":
        steps = context.user_data["exp"]["steps"]
        if not steps:
            await _reply(update, "لسه ما أضفت خطوات. أرسل خطوة أو اكتب انتهيت للإلغاء.")
            return EXP_STEPS
        lst = "\n".join([f"{i+1}. {s}" for i, s in enumerate(steps)])
        await _reply(update, f"✅ **سلّم التعرّض**: {context.user_data['exp']['title']}\n{lst}\n\n"
                             "ابدأ من 1 وتدرّج. قيّم قلقك قبل/بعد كل خطوة.")
        await _reply(update, "رجوع للقائمة:", reply_markup=main_menu_kb())
        return ConversationHandler.END
    else:
        context.user_data["exp"]["steps"].append(text)
        await _reply(update, f"تمت الإضافة ✅ (الخطوة رقم {len(context.user_data['exp']['steps'])}).")
        return EXP_STEPS

# ===== 2) اختبارات نفسية =====
TESTS: Dict[str, Dict[str, Any]] = {
    "phq9": {
        "title": "PHQ-9 (الاكتئاب)",
        "items": [
            "قلة الاهتمام أو المتعة بالقيام بالأشياء",
            "الشعور بالإحباط أو الاكتئاب أو اليأس",
            "مشاكل في النوم (قلّة/كثرة)",
            "التعب أو نقص الطاقة",
            "ضعف الشهية أو فرط الأكل",
            "سوء تقدير الذات أو الشعور بالفشل",
            "صعوبة التركيز",
            "بطء أو تهيّج ملحوظ في الحركة/الكلام",
            "أفكار بأنك ستكون أفضل حالًا لو متَّ أو إيذاء النفس",
        ],
        "scale": "0=أبدًا, 1=عدة أيام, 2=نصف الأيام, 3=تقريبًا كل يوم",
        "cutoffs": [(0,4,"حد أدنى"),(5,9,"خفيف"),(10,14,"متوسط"),(15,19,"شديد"),(20,27,"شديد جدًا")],
    },
    "gad7": {
        "title": "GAD-7 (القلق العام)",
        "items": [
            "الشعور بالتوتر أو القلق أو العصبية",
            "عدم القدرة على التوقف عن القلق أو التحكم به",
            "القلق المفرط بشأن أمور مختلفة",
            "صعوبة الاسترخاء",
            "التململ لدرجة صعوبة الجلوس ساكنًا",
            "الانزعاج بسهولة أو التهيّج",
            "الشعور بالخوف كأن شيئًا رهيبًا قد يحدث",
        ],
        "scale": "0=أبدًا, 1=عدة أيام, 2=نصف الأيام, 3=تقريبًا كل يوم",
        "cutoffs": [(0,4,"حد أدنى"),(5,9,"خفيف"),(10,14,"متوسط"),(15,21,"شديد")],
    },
    "sapas": {
        "title": "SAPAS (فحص اضطرابات الشخصية) - 8 أسئلة نعم/لا",
        "items": [
            "هل تجد صعوبة في تكوين صداقات قريبة؟",
            "هل تغضب بسهولة لدرجة تؤثر على علاقاتك؟",
            "هل أنت متهور غالبًا؟",
            "هل تجد صعوبة في الثقة بالآخرين؟",
            "هل تفضّل العزلة معظم الوقت؟",
            "هل تتقلب صورتك عن نفسك كثيرًا؟",
            "هل تخالف القواعد أو تتورط في مشاكل متكررة؟",
            "هل تقلق جدًا من أن يتركك الآخرون؟",
        ],
        "scale": "أجب بـ: نعم / لا",
        "threshold": 3,
    },
}

def tests_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("PHQ-9 (اكتئاب)", callback_data="t_phq9")],
        [InlineKeyboardButton("GAD-7 (قلق)",   callback_data="t_gad7")],
        [InlineKeyboardButton("SAPAS (شخصية)", callback_data="t_sapas")],
        [InlineKeyboardButton("◀️ رجوع", callback_data="menu_home")],
    ])

async def tests_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("اختر اختبارًا. النتائج إرشادية وليست تشخيصًا.", reply_markup=tests_menu_kb())

async def tests_start(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str):
    await _typing(update)
    t = TESTS[key]
    context.user_data["test"] = {"key": key, "i": 0, "score": 0}
    intro = f"🧪 {t['title']}\nالمقياس: {t['scale']}\n"
    intro += "\nأرسل رقم الدرجة (0-3) لكل بند." if key != "sapas" else "\nأجب: نعم / لا."
    await _reply(update, intro + f"\nالسؤال 1/{len(t['items'])}: {t['items'][0]}")
    return TEST_ASK

async def tests_on_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get("test")
    if not data:
        await _reply(update, "انتهت الجلسة. استخدم /menu لإعادة البدء.")
        return ConversationHandler.END
    key = data["key"]; t = TESTS[key]; msg = update.message.text.strip()
    if key == "sapas":
        val = 1 if msg in ("نعم","ايوه","ايوا","Yes","YES","yes") else 0
    else:
        if msg not in ("0","1","2","3"):
            await _reply(update, "أرسل 0 أو 1 أو 2 أو 3.")
            return TEST_ASK
        val = int(msg)
    data["score"] += val; data["i"] += 1
    if data["i"] >= len(t["items"]):
        score = data["score"]
        if key == "sapas":
            thr = t["threshold"]
            flag = "قد توجد احتمالية اضطراب شخصية وتحتاج تقييمًا متخصصًا." if score >= thr else "لا مؤشرات مرتفعة."
            txt = f"نتيجة SAPAS = **{score}** / 8\n> {flag}"
        else:
            level = None
            for lo, hi, name in t["cutoffs"]:
                if lo <= score <= hi: level = name; break
            txt = f"المجموع = **{score}** — الشدة: **{level}**"
        await _reply(update, "✅ تم.\n" + txt + "\n⚠️ الفحوصات إرشادية وليست تشخيصًا.")
        await _reply(update, "القائمة الرئيسية:", reply_markup=main_menu_kb())
        return ConversationHandler.END
    else:
        i = data["i"]
        await _reply(update, f"السؤال {i+1}/{len(t['items'])}: {t['items'][i]}")
        return TEST_ASK

# ===== 3) اضطرابات الشخصية (ملخّصات) =====
PD_INFO = {
    "العنقودية A": "بارانوية/فُصامية/فُصامية نمطية: شك/غرابة/انسحاب.",
    "العنقودية B": "حدّية/نرجسية/معادية للمجتمع/هستيرية: اندفاع وعدم استقرار.",
    "العنقودية C": "تجنّبية/اعتمادية/وسواسية قسرية (شخصية): قلق وكمالية.",
    "الحدّية": "عدم استقرار العلاقات/الذات/العاطفة + اندفاع، وقد يحدث إيذاء ذاتي.",
    "النرجسية": "تعاظم الذات، حاجة للإعجاب، نقص التعاطف.",
    "المعادية للمجتمع": "تجاهل حقوق الآخرين، خداع/اندفاع/عدوان.",
    "التجنّبية": "تجنّب العلاقات خوفًا من الرفض مع شعور بالنقص.",
    "الوسواسية القسرية (شخصية)": "كمالية وترتيب وسيطرة تعيق المرونة.",
}
def pd_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("العنقودية A", callback_data="pd_A"),
         InlineKeyboardButton("العنقودية B", callback_data="pd_B")],
        [InlineKeyboardButton("العنقودية C", callback_data="pd_C"),
         InlineKeyboardButton("الحدّية", callback_data="pd_الحدّية")],
        [InlineKeyboardButton("النرجسية", callback_data="pd_النرجسية"),
         InlineKeyboardButton("المعادية للمجتمع", callback_data="pd_المعادية للمجتمع")],
        [InlineKeyboardButton("التجنّبية", callback_data="pd_التجنّبية"),
         InlineKeyboardButton("الوسواسية القسرية (شخصية)", callback_data="pd_الوسواسية القسرية (شخصية)")],
        [InlineKeyboardButton("◀️ رجوع", callback_data="menu_home")],
    ])

async def pd_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("اختر موضوعًا للاطلاع:", reply_markup=pd_menu_kb())

async def pd_show(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str):
    await _typing(update)
    txt = f"**{key}**\n{PD_INFO.get(key,'—')}\n\n⚠️ للتثقيف فقط — التشخيص عند المختص."
    if update.callback_query:
        await update.callback_query.edit_message_text(txt, reply_markup=pd_menu_kb())
    else:
        await update.message.reply_text(txt, reply_markup=pd_menu_kb())

# ===== 4) وضع DSM بالذكاء الاصطناعي =====
DSM_SYSTEM = (
    "أنت مساعد للصحة النفسية وفق DSM-5-TR كتوجيه عام دون نسخ حرفي. "
    "استوضح الأعراض (المدة/الشدة/التأثير) واستبعد الأسباب الطبية/المواد، وقدّم تفريقًا وخطة مساعدة ذاتية. "
    "عند خطر انتحاري اطلب مساعدة فورية."
)

async def dsm_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("🧠 اكتب وصف أعراضك (المدّة/الشدة/المثيرات/الأثر على حياتك).")
    return DSM_COLLECT

async def dsm_collect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    await _typing(update)
    reply = await call_ai_chat([
        {"role": "system", "content": DSM_SYSTEM},
        {"role": "user", "content": user_text},
    ])
    await _reply(update, "— **ملخص مبدئي بمساعدة الذكاء الاصطناعي** —\n" + reply +
                 "\n\n⚠️ ليس تشخيصًا طبيًا. راجع مختصًا عند الحاجة.")
    await _reply(update, "القائمة الرئيسية:", reply_markup=main_menu_kb())
    return ConversationHandler.END

async def call_ai_chat(messages: List[Dict[str, str]]) -> str:
    if not (AI_API_KEY and AI_BASE_URL and AI_MODEL):
        return "إعدادات الذكاء الاصطناعي غير مكتملة."
    url = AI_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": AI_MODEL, "messages": messages, "temperature": 0.2}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.exception("AI error")
        return f"تعذّر الاتصال بالمحرك ({e})."

# ===== 5) نسخة DSM مختصرة =====
DSM_SNIPPETS = {
    "الاكتئاب": "مزاج مكتئب و/أو فقدان متعة + أعراض جسدية/معرفية ≥ أسبوعين وتأثر الوظيفة.",
    "القلق العام": "قلق مفرط معظم الأيام ≥ 6 أشهر مع صعوبة التحكم وأعراض توتر متعددة.",
    "الهلع": "نوبات هلع مفاجئة متكررة + قلق توقّعي وتجنّب.",
    "PTSD": "حدث صادم + إعادة معايشة + تجنّب + مزاج/إثارة سلبية > شهر وتأثر واضح.",
    "الحدّية": "عدم استقرار شديد في العلاقات/الذات/العاطفة + اندفاع وقد يحدث إيذاء ذاتي.",
}
def dsm_copy_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("الاكتئاب", callback_data="dsmc_الاكتئاب"),
         InlineKeyboardButton("القلق العام", callback_data="dsmc_القلق العام")],
        [InlineKeyboardButton("الهلع", callback_data="dsmc_الهلع"),
         InlineKeyboardButton("PTSD", callback_data="dsmc_PTSD")],
        [InlineKeyboardButton("الحدّية", callback_data="dsmc_الحدّية")],
        [InlineKeyboardButton("◀️ رجوع", callback_data="menu_home")],
    ])

async def dsm_copy_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("اختر ملخّص DSM مبسّط:", reply_markup=dsm_copy_menu())

async def dsm_copy_show(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str):
    await _typing(update)
    txt = f"**{key} (ملخص DSM مبسّط)**\n{DSM_SNIPPETS.get(key,'—')}\n\n"
    txt += "لتحليل أوسع استخدم: عربي سايكو (DSM AI)."
    if update.callback_query:
        await update.callback_query.edit_message_text(txt, reply_markup=dsm_copy_menu())
    else:
        await update.message.reply_text(txt, reply_markup=dsm_copy_menu())

# ===== أدوات مساعدة =====
async def _typing(update: Update):
    try:
        await update.effective_chat.send_action(ChatAction.TYPING)
    except Exception:
        pass

async def _reply(update: Update, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, disable_web_page_preview=True)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, disable_web_page_preview=True)

# ===== تسجيل المعالجات في التطبيق الرئيسي =====
def register_handlers(app: Application):
    # أوامر عامة
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CallbackQueryHandler(lambda u,c: cmd_menu(u,c), pattern="^menu_home$"))

    # CBT
    app.add_handler(CallbackQueryHandler(cbt_entry, pattern="^menu_cbt$"))
    tr_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(tr_start, pattern="^cbt_thought_record$")],
        states={
            CBT_TR_SITUATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_situation)],
            CBT_TR_THOUGHTS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_thoughts)],
            CBT_TR_EMOTION:   [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_emotion)],
            CBT_TR_ALT:       [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_alt)],
        },
        fallbacks=[CommandHandler("menu", cmd_menu)],
        name="cbt_tr",
        persistent=False,
    )
    app.add_handler(tr_conv)

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(exp_start, pattern="^cbt_exposure$")],
        states={
            EXP_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, exp_title)],
            EXP_STEPS: [MessageHandler(filters.TEXT & ~filters.COMMAND, exp_steps)],
        },
        fallbacks=[CommandHandler("menu", cmd_menu)],
        name="cbt_exp",
        persistent=False,
    ))

    # اختبارات
    app.add_handler(CallbackQueryHandler(tests_entry, pattern="^menu_tests$"))
    app.add_handler(ConversationHandler(
        entry_points=[
            CallbackQueryHandler(lambda u,c: tests_start(u,c,"phq9"), pattern="^t_phq9$"),
            CallbackQueryHandler(lambda u,c: tests_start(u,c,"gad7"), pattern="^t_gad7$"),
            CallbackQueryHandler(lambda u,c: tests_start(u,c,"sapas"), pattern="^t_sapas$"),
        ],
        states={ TEST_ASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, tests_on_answer)] },
        fallbacks=[CommandHandler("menu", cmd_menu)],
        name="tests_conv",
        persistent=False,
    ))

    # اضطرابات الشخصية
    app.add_handler(CallbackQueryHandler(pd_entry, pattern="^menu_pd$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: pd_show(u,c,"العنقودية A"), pattern="^pd_A$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: pd_show(u,c,"العنقودية B"), pattern="^pd_B$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: pd_show(u,c,"العنقودية C"), pattern="^pd_C$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: pd_show(u,c,"الحدّية"), pattern="^pd_الحدّية$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: pd_show(u,c,"النرجسية"), pattern="^pd_النرجسية$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: pd_show(u,c,"المعادية للمجتمع"), pattern="^pd_المعادية للمجتمع$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: pd_show(u,c,"التجنّبية"), pattern="^pd_التجنّبية$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: pd_show(u,c,"الوسواسية القسرية (شخصية)"), pattern="^pd_الوسواسية القسرية \(شخصية\)$"))

    # DSM AI
    app.add_handler(CallbackQueryHandler(dsm_entry, pattern="^menu_dsm$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(dsm_entry, pattern="^menu_dsm$")],
        states={ DSM_COLLECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, dsm_collect)] },
        fallbacks=[CommandHandler("menu", cmd_menu)],
        name="dsm_ai_conv",
        persistent=False,
    ))

    # نسخة DSM
    app.add_handler(CallbackQueryHandler(dsm_copy_entry, pattern="^menu_dsm_copy$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: dsm_copy_show(u,c,"الاكتئاب"), pattern="^dsmc_الاكتئاب$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: dsm_copy_show(u,c,"القلق العام"), pattern="^dsmc_القلق العام$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: dsm_copy_show(u,c,"الهلع"), pattern="^dsmc_الهلع$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: dsm_copy_show(u,c,"PTSD"), pattern="^dsmc_PTSD$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: dsm_copy_show(u,c,"الحدّية"), pattern="^dsmc_الحدّية$"))

    # /start لفتح القائمة مباشرة
    app.add_handler(CommandHandler("start", lambda u,c: cmd_menu(u,c)))
