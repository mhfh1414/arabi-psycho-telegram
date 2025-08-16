# -*- coding: utf-8 -*-
import os, logging, json, random, string
from typing import Dict, Any, List, Tuple
import requests
from flask import Flask, request, jsonify

# ========= الإعدادات =========
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Error: Missing TELEGRAM_BOT_TOKEN env var")

BOT_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "secret")
PUBLIC_URL = (
    os.environ.get("RENDER_EXTERNAL_URL")
    or os.environ.get("PUBLIC_URL")
)
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # اختياري: رقم محادثة المدير
CONTACT_PHONE = os.environ.get("CONTACT_PHONE")  # اختياري: يظهر في /help

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho-bot")

# ========= أدوات تيليجرام =========
def tg_call(method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(f"{BOT_API}/{method}", json=payload, timeout=15)
    if r.status_code != 200:
        log.warning("TG %s %s -> %s %s", method, payload, r.status_code, r.text[:200])
    try:
        return r.json()
    except Exception:
        return {"ok": False, "err": r.text}

def send(chat_id: int, text: str, **kw) -> None:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    payload.update(kw)
    tg_call("sendMessage", payload)

def send_kb(chat_id: int, text: str, rows: List[List[Tuple[str, str]]]) -> None:
    kb = {"inline_keyboard": [[{"text": t, "callback_data": d} for (t, d) in row] for row in rows]}
    send(chat_id, text, reply_markup=kb)

def answer_cb(cb_id: str) -> None:
    tg_call("answerCallbackQuery", {"callback_query_id": cb_id})

# ========= قوائم تعليمية مختصرة =========
DX_TOPICS = {
    "القلق": "أعراضه توتر مستمر، شد عضلي، أفكار ترقب. العلاج: CBT والتعرّض التدريجي وتقنيات الاسترخاء.",
    "القلق الاجتماعي": "خوف من التقييم السلبي والتجنب. العلاج: تعرّض اجتماعي وتحدي أفكار (أنا محط أنظار الجميع).",
    "الوسواس القهري": "وساوس + أفعال قهرية تُبقي القلق. العلاج: تعرّض ومنع الاستجابة + تحدي التطمين.",
    "نوبات الهلع": "اندفاع قلق شديد مع أعراض جسدية. العلاج: تعرّض للأحاسيس الجسدية + تصحيح التفسير الكارثي.",
    "الاكتئاب": "مزاج منخفض وفقدان المتعة. العلاج: تنشيط سلوكي + إعادة بناء أفكار + روتين نوم وحركة.",
    "الثقة بالنفس": "تُبنى بالممارسة التدريجية والإنجازات الصغيرة وصياغات واقعية للذات.",
    "القلق على الصحة": "مراقبة جسدية/طمأنة مفرطة. العلاج: تقليل الفحص، تعرّض للريبة، تحدي الأفكار الكارثية.",
    "كرب ما بعد الصدمة": "ذكريات اقتحامية وتجنب ويقظة. العلاج: تعرّض سردي منضبط + مهارات تنظيم انفعال.",
}
def edu_dx_list(chat_id: int):
    names = list(DX_TOPICS.keys())
    rows = []
    for i in range(0, len(names), 2):
        rows.append([(n, f"edu:dx:{n}") for n in names[i:i+2]])
    rows.append([("⟵ القائمة", "edu:home"), ("العلاج النفسي", "edu:cat:therapy")])
    send_kb(chat_id, "الاضطرابات النفسية (ملخصات سريعة):", rows)

def edu_show_dx(chat_id: int, name: str):
    text = DX_TOPICS.get(name, "غير متوفر.")
    rows = [[("⟵ الرجوع", "edu:cat:dx"), ("القائمة الرئيسية", "edu:home")]]
    send_kb(chat_id, f"<b>{name}</b>\n\n{text}", rows)

THERAPY_TOPICS = {
    "أخطاء التفكير": (
        "الأشيع: التهويل، التعميم، قراءة الأفكار، كل-أو-لا شيء.\n"
        "لاحظ الفكرة → سمِّ التشوه → اسأل: ما الدليل/البديل؟ → اكتب صياغة متوازنة."
    ),
    "الاجترار والكبت": (
        "الاجترار تدوير للفكرة بلا فعل؛ الكبت يعيدها أقوى.\n"
        "حدد «وقت قلق» 15د ثم عُدْ للحاضر؛ نفّذ أفعالًا صغيرة نافعة."
    ),
    "الأسئلة العشرة لتحدي الأفكار": (
        "ما الدليل/النقيض؟ هل أعمّم؟ أسوأ/أفضل/الأغلب؟ بدائل؟ لو صديق مكاني؟ "
        "كيف سأرى الموقف بعد أسبوع؟ ما الذي أتجاهله؟ ما العبارة المتوازنة؟"
    ),
    "الاسترخاء": (
        "تنفّس 4-4-6 ×3–5 دقائق؛ إرخاء عضلي تدريجي؛ تأريض 5-4-3-2-1 للحواس."
    ),
    "التنشيط السلوكي": (
        "للاكتئاب: جدولة ممتع/نافع بخطوات صغيرة؛ قاعدة الدقيقتين لبدء المهمة."
    ),
    "اليقظة الذهنية": (
        "لاحظ اللحظة بلا حكم؛ سمِّ الفكرة «فِكر» ثم ارجع للتنفس أو المهمة."
    ),
    "حل المشكلات": (
        "عرّف المشكلة → اعصف بخيارات → قيّم واختر خطة S.M.A.R.T → جرّب وقيّم."
    ),
    "سلوكيات الأمان": (
        "مثل الطمأنة/التجنب الخفي؛ تُبقي القلق. بدّلها بتعرّض تدريجي مع منع الاستجابة."
    ),
}
def edu_therapy_list(chat_id: int):
    names = list(THERAPY_TOPICS.keys())
    rows = []
    for i in range(0, len(names), 2):
        rows.append([(n, f"edu:therapy:{n}") for n in names[i:i+2]])
    rows.append([("⟵ القائمة", "edu:home"), ("الاضطرابات النفسية", "edu:cat:dx")])
    send_kb(chat_id, "مواضيع العلاج المعرفي السلوكي (CBT):", rows)

def edu_show_therapy_topic(chat_id: int, name: str):
    text = THERAPY_TOPICS.get(name, "غير متوفر.")
    rows = [
        [("⟵ الرجوع", "edu:cat:therapy"), ("القائمة الرئيسية", "edu:home")],
        [("ابدأ تمرين /cbt", "edu:noop")]
    ]
    send_kb(chat_id, f"<b>{name}</b>\n\n{text}", rows)

# ========= الاختبارات النفسية (نسخ قصيرة) =========
CHOICES_0_3 = [
    ("أبدًا", 0), ("عدة أيام", 1), ("أكثر من النصف", 2), ("تقريبًا كل يوم", 3),
]
TESTS = {
    "gad2": {
        "title": "قلق (GAD-2)",
        "items": [
            "الشعور بالعصبية أو القلق أو التوتر",
            "عدم القدرة على التوقف عن القلق أو التحكم فيه",
        ],
        "choices": CHOICES_0_3,
        "cut": 3,
        "interp": "≥3 يشير لاحتمال قلق مهم؛ استكمل GAD-7 أو راجع مختصًا.",
    },
    "phq2": {
        "title": "اكتئاب (PHQ-2)",
        "items": [
            "قلّة الاهتمام أو المتعة بالقيام بالأشياء",
            "الشعور بالإحباط أو الاكتئاب أو اليأس",
        ],
        "choices": CHOICES_0_3,
        "cut": 3,
        "interp": "≥3 يشير لاحتمال اكتئاب؛ استكمل PHQ-9 أو راجع مختصًا.",
    },
    "ins2": {
        "title": "أرق (ISI-2 مختصر)",
        "items": [
            "صعوبة البدء بالنوم",
            "الاستيقاظ المتكرر/المبكر وإجهاد نهاري",
        ],
        "choices": [
            ("لا شيء", 0), ("خفيف", 1), ("متوسط", 2), ("شديد", 3),
        ],
        "cut": 3,
        "interp": "≥3 يشير لمشكلات نوم ملحوظة؛ حسن العادات واطلب تقييماً عند اللزوم.",
    },
}
STATE: Dict[int, Dict[str, Any]] = {}  # {chat_id: {type, idx, score}}

def tests_menu(chat_id: int):
    rows = [
        [("قلق (GAD-2)", "tests:start:gad2"), ("اكتئاب (PHQ-2)", "tests:start:phq2")],
        [("الأرق (ISI-2)", "tests:start:ins2")],
        [("⟵ القائمة الرئيسية", "edu:home")],
    ]
    msg = ("هذه أدوات فحص أولي وليست تشخيصًا. أجب عن الأسئلة حسب آخر أسبوعين.")
    send_kb(chat_id, msg, rows)

def tests_start(chat_id: int, tkey: str):
    t = TESTS[tkey]
    STATE[chat_id] = {"type": tkey, "idx": 0, "score": 0}
    send_question(chat_id)

def send_question(chat_id: int):
    st = STATE.get(chat_id)
    if not st: 
        tests_menu(chat_id); 
        return
    t = TESTS[st["type"]]
    idx = st["idx"]
    items = t["items"]
    if idx >= len(items):
        # نهاية الاختبار
        score = st["score"]
        cut = t["cut"]
        badge = "✅" if score < cut else "⚠️"
        send(chat_id,
             f"<b>{t['title']}</b>\nالنتيجة: <b>{score}</b> / {len(items)*3} {badge}\n"
             f"{t['interp']}\n\nتنبيه: هذا فحص تعليمي وليس تشخيصًا.")
        STATE.pop(chat_id, None)
        tests_menu(chat_id)
        return
    q = items[idx]
    # أزرار الخيارات
    choices = t["choices"]
    rows = [[(txt, f"tests:ans:{val}")] for (txt, val) in choices]
    rows.append([("⟵ إلغاء", "tests:cancel")])
    send_kb(chat_id, f"<b>{t['title']}</b>\nس{idx+1}: {q}", rows)

def tests_answer(chat_id: int, val: int):
    st = STATE.get(chat_id)
    if not st: 
        tests_menu(chat_id); 
        return
    st["score"] += int(val)
    st["idx"] += 1
    send_question(chat_id)

# ========= نوايا بسيطة + أوامر =========
INTENTS = {
    "سلام": "وعليكم السلام ورحمة الله ✨",
    "مرحبا": "أهلًا وسهلًا! كيف أقدر أساعدك؟",
    "تواصل": "تم تسجيل طلب تواصل ✅ سنرجع لك قريبًا.",
    "نوم": "جرّب تنام 7-8 ساعات، وثبّت وقت النوم، وابتعد عن المنبهات مساءً 😴",
    "حزن": "مفهوم.. جرّب نشاطًا صغيرًا ممتعًا اليوم ولو لـ10 دقائق، وشارك أحدًا تثق به.",
    "قلق": "تنفّس 4-4-6 لعدة دقائق، ثم واجه مخاوفك بخطوات صغيرة.",
}

def main_menu(chat_id: int):
    rows = [
        [("الاختبارات النفسية", "tests:menu"), ("العلاج النفسي", "edu:cat:therapy")],
        [("الاضطرابات النفسية", "edu:cat:dx")],
        [("مساعدة", "menu:help")],
    ]
    send_kb(chat_id,
            "أنا <b>عربي سايكو</b> 🤝 مساعد نفسي تعليمي.\nاختر من القوائم أو أرسل كلمة مثل: قلق، نوم، تواصل…",
            rows)

def is_cmd(text: str, name: str) -> bool:
    return text.strip().lower().startswith("/" + name.lower())

# ========= الويبهوك =========
@app.route("/", methods=["GET"])
def index():
    info = {"app": "Arabi Psycho Telegram Bot", "public_url": PUBLIC_URL, "status": "ok"}
    # أظهر مسار الويبهوك مقنّعًا
    info["webhook"] = ("/webhook/" + WEBHOOK_SECRET[:3] + "*****")
    return jsonify(info)

@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    upd = request.get_json(force=True, silent=True) or {}
    # تعامل مع الضغط على الأزرار
    if "callback_query" in upd:
        cb = upd["callback_query"]
        data_str = cb.get("data", "")
        chat_id = cb["message"]["chat"]["id"]
        answer_cb(cb["id"])

        # قوائم تعليمية
        if data_str == "edu:home":
            main_menu(chat_id)
        elif data_str == "edu:cat:dx":
            edu_dx_list(chat_id)
        elif data_str.startswith("edu:dx:"):
            edu_show_dx(chat_id, data_str.split("edu:dx:", 1)[1])
        elif data_str == "edu:cat:therapy":
            edu_therapy_list(chat_id)
        elif data_str.startswith("edu:therapy:"):
            edu_show_therapy_topic(chat_id, data_str.split("edu:therapy:", 1)[1])

        # الاختبارات
        elif data_str == "tests:menu":
            tests_menu(chat_id)
        elif data_str.startswith("tests:start:"):
            tests_start(chat_id, data_str.split("tests:start:", 1)[1])
        elif data_str.startswith("tests:ans:"):
            tests_answer(chat_id, int(data_str.split("tests:ans:", 1)[1]))
        elif data_str == "tests:cancel":
            STATE.pop(chat_id, None)
            tests_menu(chat_id)

        elif data_str == "menu:help":
            show_help(chat_id)
        return "ok", 200

    # رسائل نصيّة
    message = upd.get("message") or upd.get("edited_message")
    if not message:
        return "ok", 200

    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()
    low = text.replace("ـ", "").lower()

    # أوامر
    if is_cmd(text, "start"):
        main_menu(chat_id)
        return "ok", 200

    if is_cmd(text, "help"):
        show_help(chat_id)
        return "ok", 200

    if is_cmd(text, "cbt"):
        send(chat_id,
             "جلسة CBT سريعة:\n1) سمِّ الفكرة المزعجة.\n2) ما الدليل/النقيض؟\n"
             "3) ماذا أستطيع فعله الآن خطوة صغيرة؟\n4) اكتب صياغة متوازنة.\n\n"
             "جرب أيضًا قائمة «العلاج النفسي».")
        return "ok", 200

    if is_cmd(text, "therapy"):
        edu_therapy_list(chat_id)
        return "ok", 200

    if is_cmd(text, "tests"):
        tests_menu(chat_id)
        return "ok", 200

    if is_cmd(text, "whoami"):
        uid = message.get("from", {}).get("id")
        send(chat_id, f"chat_id: {chat_id}\nuser_id: {uid}")
        return "ok", 200

    # طلب تواصل (تنبيه للأدمن)
    if low in ["تواصل", "توصل", "اتصال", "اتواصل"]:
        user = message.get("from", {})
        username = user.get("username") or (user.get("first_name", "") + " " + user.get("last_name","")).strip() or "مستخدم"
        send(chat_id, "تم تسجيل طلب تواصل ✅ سنرجع لك قريبًا.")
        if ADMIN_CHAT_ID:
            info = (
                f"📩 طلب تواصل\n"
                f"👤 من: {username} (user_id={user.get('id')})\n"
                f"💬 نصّه: {text}\n"
                f"🔗 chat_id={chat_id}"
            )
            send(int(ADMIN_CHAT_ID), info)
        return "ok", 200

    # نوايا سريعة
    for k, v in INTENTS.items():
        if k in low:
            send(chat_id, v)
            return "ok", 200

    # افتراضي
    send(chat_id, f"تمام 👌 وصلتني: “{text}”\nاكتب /help للمساعدة.")
    return "ok", 200

def show_help(chat_id: int):
    phone_line = f"\n📞 للتواصل: {CONTACT_PHONE}" if CONTACT_PHONE else ""
    send(chat_id,
         "الأوامر:\n"
         "/start - القائمة الرئيسية\n"
         "/help - تعليمات سريعة\n"
         "/tests - الاختبارات النفسية\n"
         "/therapy - مواضيع CBT\n"
         "/cbt - تمرين سريع CBT\n"
         "/whoami - عرض المعرّفات"
         + phone_line)

# ========= إعداد الويبهوك عند الإقلاع =========
def ensure_webhook():
    if not PUBLIC_URL:
        log.warning("No PUBLIC_URL/RENDER_EXTERNAL_URL set; skipping webhook setup.")
        return
    url = f"{PUBLIC_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
    tg_call("setWebhook", {"url": url})
    log.info("Webhook set to %s", url)

ensure_webhook()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
