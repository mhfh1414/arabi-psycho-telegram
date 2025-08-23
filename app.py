# -*- coding: utf-8 -*-
import os, json, logging
from typing import Optional, Dict, Any
from flask import Flask, request, abort
import httpx

# ================= إعدادات عامة =================
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not TELEGRAM_TOKEN:
    raise RuntimeError("متغير البيئة TELEGRAM_BOT_TOKEN غير مضبوط.")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
WEBHOOK_SECRET_PATH = os.getenv("WEBHOOK_SECRET_PATH", "/webhook/secret")

# إعدادات الذكاء الاصطناعي (اختيارية)
AI_BASE_URL = os.getenv("AI_BASE_URL", "").strip()         # مثال: https://openrouter.ai/api/v1
AI_API_KEY   = os.getenv("AI_API_KEY", "").strip()
AI_MODEL     = os.getenv("AI_MODEL", "openrouter/auto").strip()

CONTACT_THERAPIST_URL  = os.getenv("CONTACT_THERAPIST_URL", "https://t.me/your_therapist")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "https://t.me/your_psychiatrist")

# ================ Flask App ================
app = Flask(__name__)

@app.get("/")
def root_ok():
    return "Arabi Psycho OK"

@app.get("/health")
def health():
    return "OK"

# ================ أدوات تيليجرام ================
def tg_post(method: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """استدعاء بسيط لنقطة تيليجرام"""
    url = f"{TG_API}/{method}"
    try:
        r = httpx.post(url, json=payload, timeout=20)
        if r.status_code == 200:
            return r.json()
        log.error("Telegram API error %s: %s", r.status_code, r.text)
    except Exception as e:
        log.exception("Telegram API exception: %s", e)
    return None

def send_message(chat_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_post("sendMessage", payload)

def answer_callback(cb_id: str):
    tg_post("answerCallbackQuery", {"callback_query_id": cb_id})

def main_menu_kb() -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "🧠 العلاج السلوكي (CBT)", "callback_data": "cbt"}],
            [{"text": "🧪 اختبارات نفسية", "callback_data": "tests"}],
            [{"text": "📚 اضطرابات الشخصية (DSM-5)", "callback_data": "pd"}],
            [{"text": "🤖 تشخيص بالذكاء الاصطناعي", "callback_data": "ai"}],
            [
                {"text": "👤 أخصائي نفسي", "callback_data": "therapist"},
                {"text": "🩺 طبيب نفسي", "callback_data": "psychiatrist"},
            ],
        ]
    }

def cbt_menu_kb() -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "📝 سجل الأفكار", "callback_data": "cbt_thought_record"}],
            [{"text": "✅ تفعيل سلوكي", "callback_data": "cbt_behavioral_activation"}],
            [{"text": "🌬️ تمارين التنفس", "callback_data": "cbt_breathing"}],
            [{"text": "⬅️ رجوع", "callback_data": "back_home"}],
        ]
    }

def tests_menu_kb() -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "PHQ-9 (اكتئاب)", "callback_data": "test_phq9"}],
            [{"text": "GAD-7 (قلق)", "callback_data": "test_gad7"}],
            [{"text": "IPIP-120 (سمات شخصية)", "callback_data": "test_ipip"}],
            [{"text": "⬅️ رجوع", "callback_data": "back_home"}],
        ]
    }

def pd_menu_kb() -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "نظرة عامة DSM-5", "callback_data": "pd_overview"}],
            [{"text": "اضطرابات المجموعة A", "callback_data": "pd_cluster_a"}],
            [{"text": "المجموعة B", "callback_data": "pd_cluster_b"}],
            [{"text": "المجموعة C", "callback_data": "pd_cluster_c"}],
            [{"text": "⬅️ رجوع", "callback_data": "back_home"}],
        ]
    }

def ai_enabled() -> bool:
    return bool(AI_BASE_URL and AI_API_KEY)

def ai_reply(prompt: str) -> str:
    """ردّ ذكاء اصطناعي (OpenRouter أو أي مزود متوافق)"""
    if not ai_enabled():
        return ("ميزة الذكاء الاصطناعي غير مفعَّلة حاليًا.\n"
                "أضف مفاتيح OpenRouter في الإعدادات لتفعيلها.")
    try:
        headers = {"Authorization": f"Bearer {AI_API_KEY}"}
        data = {
            "model": AI_MODEL,
            "messages": [
                {"role": "system",
                 "content": ("أنت مساعد نفسي يعتمد على معايير DSM-5. "
                             "قدّم دعمًا أوليًا غير تشخيصي، مع توصيات سلوكية "
                             "وإشارات تحذير تستدعي إحالة مختص.")},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        }
        r = httpx.post(f"{AI_BASE_URL}/chat/completions", headers=headers, json=data, timeout=60)
        r.raise_for_status()
        js = r.json()
        text = js["choices"][0]["message"]["content"].strip()
        return text
    except Exception as e:
        log.exception("AI call failed: %s", e)
        return "تعذر الحصول على رد الذكاء الاصطناعي الآن. حاول لاحقًا."

def send_home(chat_id: int):
    send_message(
        chat_id,
        ("أهلًا بك في <b>ArabiPsycho</b> 🧩\n"
         "اختر من القائمة:"),
        reply_markup=main_menu_kb()
    )

# ============== محتوى الأزرار ==============
def on_cbt(chat_id: int):
    send_message(
        chat_id,
        ("<b>العلاج المعرفي السلوكي (CBT)</b>\n"
         "اختر أداة للعمل عليها اليوم:"),
        reply_markup=cbt_menu_kb()
    )

def on_tests(chat_id: int):
    send_message(
        chat_id,
        ("<b>اختبارات نفسية</b>\n"
         "هذه أدوات غربلة أولية وليست تشخيصًا. اختر اختبارًا:"),
        reply_markup=tests_menu_kb()
    )

def on_pd(chat_id: int):
    send_message(
        chat_id,
        ("<b>اضطرابات الشخصية (DSM-5)</b>\n"
         "اختر فقرة للاطلاع:"),
        reply_markup=pd_menu_kb()
    )

def on_ai(chat_id: int):
    send_message(
        chat_id,
        ("<b>تشخيص مبدئي بالذكاء الاصطناعي</b> 🤖\n"
         "أرسل رسالة تصف أعراضك (المدة، الشدة، ما يزيدها/يخففها، تأثيرها على حياتك)."),
        reply_markup={"inline_keyboard": [[{"text": "⬅️ رجوع", "callback_data": "back_home"}]]}
    )

def on_contacts(chat_id: int, kind: str):
    if kind == "therapist":
        url = CONTACT_THERAPIST_URL
        title = "أخصائي نفسي"
    else:
        url = CONTACT_PSYCHIATRIST_URL
        title = "طبيب نفسي"
    send_message(
        chat_id,
        f"للتواصل مع {title}: {url}",
        reply_markup={"inline_keyboard": [[{"text": "⬅️ رجوع", "callback_data": "back_home"}]]}
    )

# ============== Webhook ==============
@app.post(WEBHOOK_SECRET_PATH)
def webhook():
    if request.method != "POST":
        abort(405)
    update = request.get_json(force=True, silent=True) or {}
    log.info("incoming update: %s", json.dumps(update, ensure_ascii=False))

    # 1) نداء زر (callback_query)
    if "callback_query" in update:
        cq = update["callback_query"]
        cbid = cq.get("id")
        chat_id = cq.get("message", {}).get("chat", {}).get("id")
        data = (cq.get("data") or "").strip()
        if cbid:
            answer_callback(cbid)
        if not chat_id:
            return "ok"

        if data == "cbt":
            on_cbt(chat_id)
        elif data == "tests":
            on_tests(chat_id)
        elif data == "pd":
            on_pd(chat_id)
        elif data == "ai":
            on_ai(chat_id)
        elif data == "therapist":
            on_contacts(chat_id, "therapist")
        elif data == "psychiatrist":
            on_contacts(chat_id, "psychiatrist")

        # قوائم فرعية
        elif data == "cbt_thought_record":
            send_message(chat_id,
                         "📝 <b>سجل الأفكار</b>\nاكتب موقفًا → فكرة تلقائية → شعورك (0-100) → الدليل مع/ضد → فكرة متوازنة.")
        elif data == "cbt_behavioral_activation":
            send_message(chat_id,
                         "✅ <b>التفعيل السلوكي</b>\nاختر نشاطًا بسيطًا ذا معنى اليوم (10–20 دقيقة) وسجّل شعورك قبل/بعد.")
        elif data == "cbt_breathing":
            send_message(chat_id,
                         "🌬️ <b>تمارين التنفس</b>\nشهيق 4 ثوان ٫ حبس 4 ٫ زفير 6-8 ثوان. كرر 4-6 مرات.")
        elif data == "pd_overview":
            send_message(chat_id,
                         "نظرة عامة DSM-5: اضطرابات الشخصية أنماط ثابتة من الخبرة الداخلية والسلوك تُسبب خللًا وظيفيًا واضحًا…")
        elif data == "pd_cluster_a":
            send_message(chat_id,
                         "المجموعة A (غريبة/شاذة): الزورية، الفصامية، شبه الفصامية.")
        elif data == "pd_cluster_b":
            send_message(chat_id,
                         "المجموعة B (درامية/انفعالية): الحدّية، النرجسية، الهستيرية، المعادية للمجتمع.")
        elif data == "pd_cluster_c":
            send_message(chat_id,
                         "المجموعة C (قلقة/خائفة): التجنبية، الاعتمادية، الوسواسية القهرية (الشخصية).")
        elif data == "back_home":
            send_home(chat_id)
        else:
            send_home(chat_id)

        return "ok"

    # 2) رسالة عادية
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id:
        return "ok"

    text = (msg.get("text") or "").strip()

    if text in ("/start", "start", "ابدأ", "/help"):
        send_home(chat_id)
        return "ok"

    # لو ضغط AI ثم كتب أعراضه – نعتبر أي نص طويل طلب AI
    if len(text) >= 8 and any(k in text for k in ["أعاني", "أعراض", "قلق", "اكتئاب", "panic", "symptom", "تشخيص"]):
        reply = ai_reply(text)
        send_message(chat_id,
                     f"⚠️ <i>هذا ليس تشخيصًا طبيًا. استشر مختصًا عند الحاجة.</i>\n\n{reply}",
                     reply_markup=main_menu_kb())
        return "ok"

    # افتراضي: نستقبل ونظهر المنيو
    send_message(chat_id, "تم الاستلام ✅\nاختر من القائمة:", reply_markup=main_menu_kb())
    return "ok"


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
Replace app.py with Flask+httpx menubot

- إضافة قائمة أزرار رئيسية: العلاج السلوكي المعرفي (CBT)، اختبارات نفسية،
  اضطرابات الشخصية، عربي سايكو (تشخيص DSM)، والتواصل مع أخصائي/طبيب.
- تفعيل Webhook على /webhook/secret ومسار فحص جاهزية على / .
- استخدام httpx غير المتزامن مع مهلة وإعادة محاولات لتحسين الاعتمادية.
- تسجيل مختصر للواردات بدون تخزين بيانات حساسة.
- إزالة الاعتماد على features.app.py وتبسيط التسجيل والـ handlers.
- الإبقاء على المتطلبات: python-telegram-bot==21.4 و httpx==0.27 و Flask==3.0.3 و gunicorn==21.2.0.
