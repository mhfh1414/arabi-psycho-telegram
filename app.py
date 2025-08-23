# -*- coding: utf-8 -*-
import os
import json
import logging
from typing import Dict, Any, Optional

from flask import Flask, request, abort
import httpx

# ================== إعدادات عامة ==================
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("app")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN مفقود من البيئة")

API = f"https://api.telegram.org/bot{TOKEN}"

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBHOOK_SECRET_PATH = "/webhook/secret"

# الذكاء الاصطناعي (اختياري)
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1")
AI_API_KEY = os.getenv("AI_API_KEY")  # ضع مفتاح OpenRouter هنا
AI_MODEL = os.getenv("AI_MODEL", "openrouter/auto")

# قنوات تواصل (اختياري)
CONTACT_THERAPIST_URL = os.getenv("CONTACT_THERAPIST_URL", "https://t.me/your_therapist")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "https://t.me/your_psychiatrist")

# ذاكرة حالات بسيطة (بالرام)
STATE: Dict[int, Dict[str, Any]] = {}   # لكل chat_id نخزّن حالة الجلسة
TEST_STATE: Dict[int, Dict[str, Any]] = {}  # حالة الاختبارات السريعة

# ================== أدوات Telegram ==================
def tg_send(method: str, payload: Dict[str, Any]) -> Optional[dict]:
    try:
        with httpx.Client(timeout=20) as cli:
            r = cli.post(f"{API}/{method}", json=payload)
        if r.status_code == 200:
            data = r.json()
            if not data.get("ok"):
                LOG.error("Telegram error: %s", data)
            return data
        LOG.error("HTTP error to Telegram %s: %s", method, r.text)
    except Exception as e:
        LOG.exception("tg_send error: %s", e)
    return None

def send_action(chat_id: int, action: str = "typing") -> None:
    tg_send("sendChatAction", {"chat_id": chat_id, "action": action})

def send_message(chat_id: int, text: str, reply_markup: Optional[dict] = None,
                 parse_mode: Optional[str] = "HTML") -> None:
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    tg_send("sendMessage", payload)

def edit_message(chat_id: int, message_id: int, text: str,
                 reply_markup: Optional[dict] = None,
                 parse_mode: Optional[str] = "HTML") -> None:
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    tg_send("editMessageText", payload)

def answer_callback(callback_id: str, text: Optional[str] = None, alert: bool = False) -> None:
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = alert
    tg_send("answerCallbackQuery", payload)

# ================== لوحات الأزرار ==================
def kb_inline(rows: list[list[dict]]) -> dict:
    """توليد InlineKeyboardMarkup"""
    return {"inline_keyboard": rows}

def kb_main_menu() -> dict:
    return kb_inline([
        [
            {"text": "🧠 العلاج السلوكي (CBT)", "callback_data": "menu:cbt"},
            {"text": "🧪 اختبارات نفسية", "callback_data": "menu:tests"},
        ],
        [
            {"text": "📚 اضطرابات الشخصية (DSM-5)", "callback_data": "menu:dsm"},
        ],
        [
            {"text": "🤖 تشخيص بالذكاء الاصطناعي", "callback_data": "ai:start"},
        ],
        [
            {"text": "👤 أخصائي نفسي", "callback_data": "menu:contact_therapist"},
            {"text": "🩺 طبيب نفسي", "callback_data": "menu:contact_psy"},
        ],
        [
            {"text": "🔄 رجوع للقائمة", "callback_data": "menu:home"},
        ],
    ])

def kb_cbt_menu() -> dict:
    return kb_inline([
        [{"text": "📝 جدول ABC", "callback_data": "cbt:abc"}],
        [{"text": "💭 أفكار تلقائية + تحدّي", "callback_data": "cbt:automatic"}],
        [{"text": "📈 تفعيل سلوكي (نشاطات)", "callback_data": "cbt:ba"}],
        [{"text": "⬅️ رجوع", "callback_data": "menu:home"}],
    ])

def kb_tests_menu() -> dict:
    return kb_inline([
        [
            {"text": "PHQ-2 (اكتئاب سريع)", "callback_data": "test:phq2"},
            {"text": "GAD-2 (قلق سريع)", "callback_data": "test:gad2"},
        ],
        [
            {"text": "سمات شخصية (مختصر)", "callback_data": "test:traits"},
            {"text": "فحص اضطرابات شخصية (مؤشر)", "callback_data": "test:pd_screen"},
        ],
        [{"text": "⬅️ رجوع", "callback_data": "menu:home"}],
    ])

def kb_dsm_menu() -> dict:
    return kb_inline([
        [{"text": "Cluster A (غريب/شاذ)", "callback_data": "dsm:clusterA"}],
        [{"text": "Cluster B (درامي/اندفاعي)", "callback_data": "dsm:clusterB"}],
        [{"text": "Cluster C (قلِق/متجنب)", "callback_data": "dsm:clusterC"}],
        [{"text": "⬅️ رجوع", "callback_data": "menu:home"}],
    ])

def kb_contacts() -> dict:
    return kb_inline([
        [{"text": "👤 تواصل مع أخصائي نفسي", "url": CONTACT_THERAPIST_URL}],
        [{"text": "🩺 تواصل مع طبيب نفسي", "url": CONTACT_PSYCHIATRIST_URL}],
        [{"text": "⬅️ رجوع", "callback_data": "menu:home"}],
    ])

# ================== رسائل جاهزة ==================
WELCOME = (
    "<b>مرحبًا بك في عربي سايكو 🤝</b>\n"
    "أنا مساعد نفسي تعليمي. لست بديلاً عن التشخيص الطبي.\n\n"
    "اختر من القائمة:"
)

CBT_ABC = (
    "<b>جدول ABC</b>\n"
    "A = الحدث المُفعِّل\nB = الفكرة/التفسير\nC = الشعور/السلوك\n\n"
    "مثال:\nA: تأخرت عن العمل\nB: \"أنا فاشل\"\nC: حزن وانسحاب\n\n"
    "جرّب كتابة (A, B, C) لحدث مرّ بك اليوم."
)

CBT_AUTO = (
    "<b>الأفكار التلقائية وتحدّيها</b>\n"
    "1) لاحِظ الفكرة السريعة (مثال: \"لن أنجح\").\n"
    "2) الأدلة مع/ضد.\n"
    "3) فكرة متوازنة بديلة.\n\n"
    "اكتب فكرتك الآن وسأساعدك بإطار تحدّي مختصر."
)

CBT_BA = (
    "<b>التفعيل السلوكي</b>\n"
    "اختر نشاطًا بسيطًا ممتعًا/ذي معنى اليوم (10–20 دقيقة):\n"
    "المشي – اتصال بصديق – ترتيب ركن صغير – هواية قصيرة.\n"
    "حدّد الوقت ونفّذ، ثم قيّم مزاجك قبل/بعد (0–10)."
)

DSM_A = (
    "<b>Cluster A</b>\n"
    "البارانويدي، الفُصامي، الفُصامِيّ الوجداني.\n"
    "سمات: غُرابة/انسحاب/أفكار مرجعية.\n"
    "إن كانت السمات مؤثرة بشدة على الوظيفة، راجع أخصائي."
)
DSM_B = (
    "<b>Cluster B</b>\n"
    "الهستيري، الحدّي، النرجسي، المعادي للمجتمع.\n"
    "سمات: اندفاع، تقلب، بحث عن الانتباه، حدود ضعيفة.\n"
    "التشخيص دقيق ويحتاج تقييم سريري."
)
DSM_C = (
    "<b>Cluster C</b>\n"
    "التجنُّبي، الاعتمادي، القهري.\n"
    "سمات: قلق، تجنّب، كمالية/صرامة.\n"
    "العلاج النفسي مفيد جدًا مع CBT والمهارات."
)

# ================== ذكاء اصطناعي ==================
def ai_diagnose(prompt: str) -> str:
    """يرسل وصف الحالة للنموذج ويرجع ملخصًا منظّمًا. إن لم يوجد مفتاح، يرجع ردًا افتراضيًا."""
    if not AI_API_KEY:
        return (
            "<b>تشخيص آلي (تجريبي)</b>\n"
            "لست مفعلًا بمفتاح API الآن، لذا هذا رد توعوي عام:\n"
            "- لاحظ الأعراض (المدة/الشدة/الأثر).\n"
            "- راقب النوم والشهية والطاقة.\n"
            "- لو وُجدت أفكار إيذاء: تواصل فورًا مع الطوارئ.\n"
            "لنتيجة أكثر دقة، وفّر <code>AI_API_KEY</code> في الإعدادات."
        )
    try:
        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "model": AI_MODEL,
            "messages": [
                {"role": "system",
                 "content": (
                     "You are an Arabic mental health assistant. "
                     "Use DSM-5 terminology cautiously and include a disclaimer. "
                     "Structure the reply with headings and bullet points, respond in Arabic."
                 )},
                {"role": "user",
                 "content": f"أعراضي ووصف حالتي: {prompt}\nحلّل بشكل تعليمي، ثم اقترح خطة ذاتية قصيرة (CBT) ومتى أحتاج مختص."},
            ],
            "temperature": 0.4,
        }
        with httpx.Client(timeout=40) as cli:
            r = cli.post(f"{AI_BASE_URL}/chat/completions", headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"].strip()
        # إضافة تنبيه
        content += "\n\n<i>ملاحظة: هذا ليس تشخيصًا طبيًا نهائيًا.</i>"
        return content
    except Exception as e:
        LOG.exception("AI error: %s", e)
        return "تعذر استخدام نموذج الذكاء الاصطناعي حاليًا. جرّب لاحقًا."

# ================== اختبارات سريعة ==================
PHQ2_QS = [
    "خلال آخر أسبوعين: هل شعرت بقلة الاهتمام أو المتعة بالأشياء؟",
    "خلال آخر أسبوعين: هل شعرت بالإحباط أو الاكتئاب أو اليأس؟",
]
GAD2_QS = [
    "خلال آخر أسبوعين: هل شعرت بالتوتر/العصبية/القلق؟",
    "خلال آخر أسبوعين: هل لم تستطع التوقف عن القلق أو التحكم به؟",
]
TRAITS_QS = [
    "أفضل الأنشطة الاجتماعية على العزلة؟",
    "أعتبر نفسي منظمًا ودقيقًا؟",
    "أتضايق بسرعة عند الضغط؟",
]
PD_SCREEN_QS = [
    "هل تكرّر عليك نمط علاقات متوتر/متقلب طويلًا؟",
    "هل لديك اندفاعية أو سلوكيات مخاطرة تسبب مشكلات؟",
    "هل سمعت من مقرّبين أنك \"صارم/متحكم\" أو \"لا مبالي\" بشكل مزمن؟",
]

def start_test(chat_id: int, test_key: str, qs: list[str]) -> None:
    TEST_STATE[chat_id] = {"key": test_key, "qs": qs, "i": 0, "score": 0}
    q = qs[0]
    rows = [[{"text": "نعم", "callback_data": f"t:{test_key}:y"},
             {"text": "لا", "callback_data": f"t:{test_key}:n"}],
            [{"text": "إنهاء", "callback_data": "t:end"}]]
    send_message(chat_id, f"<b>اختبار {test_key.upper()}</b>\n{q}", kb_inline(rows))

def handle_test_step(chat_id: int, ans: Optional[str]) -> None:
    st = TEST_STATE.get(chat_id)
    if not st:
        return
    if ans == "y":
        st["score"] += 1
    st["i"] += 1
    if st["i"] >= len(st["qs"]):
        # النتيجة
        score = st["score"]
        key = st["key"]
        del TEST_STATE[chat_id]
        interpret = ""
        if key in ("phq2", "gad2"):
            interpret = "قد يشير لوجود أعراض ملحوظة، يُستحسن المتابعة." if score >= 3 else "أعراض خفيفة/محدودة على الأرجح."
        elif key == "traits":
            interpret = "هذه مؤشرات عامة لسمات (انبساط/ضمير/عصابية...). ليست تشخيصًا."
        elif key == "pd_screen":
            interpret = "إن كانت الإجابات بنعم متكررة ومع أثر وظيفي مزمن، فكر باستشارة مختص."
        send_message(chat_id, f"<b>النتيجة: {score}/{len(st['qs'])}</b>\n{interpret}", kb_tests_menu())
        return
    # سؤال لاحق
    q = st["qs"][st["i"]]
    rows = [[{"text": "نعم", "callback_data": f"t:{st['key']}:y"},
             {"text": "لا", "callback_data": f"t:{st['key']}:n"}],
            [{"text": "إنهاء", "callback_data": "t:end"}]]
    send_message(chat_id, q, kb_inline(rows))

# ================== Handlers منطقية ==================
def handle_start(chat_id: int) -> None:
    send_message(chat_id, WELCOME, kb_main_menu())

def handle_ai_prompt(chat_id: int) -> None:
    STATE[chat_id] = {"mode": "await_ai"}
    send_message(chat_id, "🚀 اكتب وصف حالتك/أعراضك بتفصيل (المدة، الشدة، المواقف).")

def maybe_handle_text_state(chat_id: int, text: str) -> bool:
    st = STATE.get(chat_id)
    if not st:
        return False
    if st.get("mode") == "await_ai":
        send_action(chat_id, "typing")
        reply = ai_diagnose(text)
        send_message(chat_id, reply, kb_main_menu())
        del STATE[chat_id]
        return True
    return False

def handle_callback(chat_id: int, message_id: int, data: str) -> None:
    if data == "menu:home":
        edit_message(chat_id, message_id, WELCOME, kb_main_menu())
        return

    if data == "menu:cbt":
        edit_message(chat_id, message_id, "اختر أداة من CBT:", kb_cbt_menu())
        return
    if data == "cbt:abc":
        send_message(chat_id, CBT_ABC, kb_cbt_menu())
        return
    if data == "cbt:automatic":
        send_message(chat_id, CBT_AUTO, kb_cbt_menu())
        return
    if data == "cbt:ba":
        send_message(chat_id, CBT_BA, kb_cbt_menu())
        return

    if data == "menu:tests":
        edit_message(chat_id, message_id, "🧪 اختبر نفسك (مؤشرات سريعة):", kb_tests_menu())
        return
    if data == "test:phq2":
        start_test(chat_id, "phq2", PHQ2_QS); return
    if data == "test:gad2":
        start_test(chat_id, "gad2", GAD2_QS); return
    if data == "test:traits":
        start_test(chat_id, "traits", TRAITS_QS); return
    if data == "test:pd_screen":
        start_test(chat_id, "pd_screen", PD_SCREEN_QS); return
    if data.startswith("t:"):
        parts = data.split(":")
        if len(parts) == 3:
            _, key, ans = parts
            handle_test_step(chat_id, ans)
        elif data == "t:end":
            TEST_STATE.pop(chat_id, None)
            send_message(chat_id, "تم إنهاء الاختبار.", kb_tests_menu())
        return

    if data == "menu:dsm":
        edit_message(chat_id, message_id, "📚 اختر مجموعة اضطرابات الشخصية:", kb_dsm_menu()); return
    if data == "dsm:clusterA":
        send_message(chat_id, DSM_A, kb_dsm_menu()); return
    if data == "dsm:clusterB":
        send_message(chat_id, DSM_B, kb_dsm_menu()); return
    if data == "dsm:clusterC":
        send_message(chat_id, DSM_C, kb_dsm_menu()); return

    if data == "ai:start":
        handle_ai_prompt(chat_id); return

    if data == "menu:contact_therapist":
        send_message(chat_id, "اختر وسيلة تواصل:", kb_contacts()); return
    if data == "menu:contact_psy":
        send_message(chat_id, "اختر وسيلة تواصل:", kb_contacts()); return

    # أي شيء آخر يرجّع للقائمة
    send_message(chat_id, "⬅️ رجعناك للقائمة.", kb_main_menu())

# ================== Flask ==================
flask_app = Flask(__name__)

@flask_app.get("/health")
def health():
    return "OK"

@flask_app.post(WEBHOOK_SECRET_PATH)
def webhook():
    if request.method != "POST":
        return abort(405)
    try:
        update = request.get_json(force=True, silent=False)
    except Exception:
        return abort(400)

    LOG.info(">> incoming update: %s", json.dumps({
        "update_id": update.get("update_id"),
        "type": "callback" if "callback_query" in update else "message",
    }, ensure_ascii=False))

    # CallbackQuery (ضغطة زر)
    if "callback_query" in update:
        cq = update["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        msg_id = cq["message"]["message_id"]
        data = cq.get("data", "")
        answer_callback(cq["id"])
        handle_callback(chat_id, msg_id, data)
        return "OK"

    # Message عادي
    if "message" in update:
        msg = update["message"]
        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        text = msg.get("text", "") or ""

        # أولوية حالات الذكاء الاصطناعي/الاختبارات
        if maybe_handle_text_state(chat_id, text):
            return "OK"

        # أوامر
        if text.startswith("/start"):
            handle_start(chat_id)
        elif text.lower() == "ping" or text == "بنق":
            send_message(chat_id, "pong ✅", kb_main_menu())
        else:
            # رد افتراضي + تلميح
            send_message(
                chat_id,
                "📩 تم الاستلام.\n"
                "استخدم /start لفتح القائمة، أو اضغط: <b>تشخيص بالذكاء الاصطناعي</b> ثم اكتب وصف حالتك.",
                kb_main_menu()
            )
        return "OK"

    return "OK"

# ====== تشغيل محلي (اختياري) ======
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    # إن كنت على Render، سيُشغّل عبر gunicorn من Procfile/runtime
    flask_app.run(host="0.0.0.0", port=port)
