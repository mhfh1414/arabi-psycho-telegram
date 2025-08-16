# app.py  — Arabi Psycho Telegram Bot (CBT menu fixed)
import os, logging, requests
from flask import Flask, request, jsonify

# ========= Config =========
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN env var")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "secret")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # اختياري

BOT_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho-bot")

# ========= Telegram helpers =========
def tg(method: str, payload: dict):
    url = f"{BOT_API}/{method}"
    r = requests.post(url, json=payload, timeout=10)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "text": r.text}

def send(chat_id, text, kb=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if kb:
        payload["reply_markup"] = kb
    return tg("sendMessage", payload)

def edit_msg(chat_id, msg_id, text, kb=None):
    payload = {
        "chat_id": chat_id,
        "message_id": msg_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if kb:
        payload["reply_markup"] = kb
    return tg("editMessageText", payload)

def answer_cbq(cbq_id, text=""):
    return tg("answerCallbackQuery", {"callback_query_id": cbq_id, "text": text})

def kb_inline(rows):
    # rows = [[{"text":"..","callback_data":".."}, ...], ...]
    return {"inline_keyboard": rows}

# ========= CBT content =========
CBT_ITEMS = [
    ("أخطاء التفكير", "tx:te"),
    ("الاجترار والكبت", "tx:rum"),
    ("الأسئلة العشرة لتحدي الأفكار", "tx:10q"),
    ("الاسترخاء", "tx:relax"),
    ("التنشيط السلوكي", "tx:ba"),
    ("اليقظة الذهنية", "tx:mind"),
    ("حل المشكلات", "tx:ps"),
    ("سلوكيات الأمان", "tx:safety"),
]

CBT_TITLES = {
    "tx:te": "أخطاء التفكير",
    "tx:rum": "الاجترار والكبت",
    "tx:10q": "الأسئلة العشرة لتحدي الأفكار",
    "tx:relax": "تقنيات الاسترخاء",
    "tx:ba": "التنشيط السلوكي",
    "tx:mind": "اليقظة الذهنية",
    "tx:ps": "حل المشكلات",
    "tx:safety": "سلوكيات الأمان",
}

CBT_CONTENT = {
    "tx:te": (
        "أشهر أخطاء التفكير:\n"
        "• التعميم: «دايمًا أفشل».\n"
        "• قراءة الأفكار: «أكيد يكرهني».\n"
        "• التنبؤ السلبي: «أكيد بيصير أسوأ».\n"
        "• التهويل/التقليل.\n"
        " جرّب استبدال الفكرة بدليل واقعي ومتوازن."
    ),
    "tx:rum": (
        "الاجترار = إعادة نفس الفكرة المزعجة.\n"
        "الكبت = محاولة طردها بقوة (غالبًا ترجع أقوى).\n"
        "الحل: ملاحظة الفكرة وتركها تعبر، وتحويل الانتباه لنشاط مفيد."
    ),
    "tx:10q": (
        "أسئلة سريعة لتحدي الفكرة:\n"
        "1) ما الدليل معها؟ وما ضدها؟\n"
        "2) هل أعمم؟ هل أقرأ أفكار؟\n"
        "3) ماذا أقول لصديق مكاني؟\n"
        "4) ما أسوأ/أفضل/أغلب ما قد يحدث؟\n"
        "5) ما السلوك المفيد الآن؟"
    ),
    "tx:relax": (
        "تنفّس 4-4-6:\n"
        "اسحب نفسًا 4 ثوانٍ… احبس 4… أخرج 6… ×10 مرات.\n"
        "شدّ واسترخِ للعضلات من أصابع القدم حتى الجبهة."
    ),
    "tx:ba": (
        "لخفض الاكتئاب: أضف نشاطات صغيرة ممتعة/مفيدة يوميًا.\n"
        "ابدأ بخطوات 5–10 دقائق (مشي، ترتيب، تواصل…)\n"
        "سجّلها وقيّم مزاجك قبل/بعد."
    ),
    "tx:mind": (
        "يقظة ذهنية 3×3×3:\n"
        "لاحظ 3 أشياء تراها، 3 تسمعها، 3 تحسّها.\n"
        "ارجع للحظة الحالية بدون حكم."
    ),
    "tx:ps": (
        "حل المشكلات:\n"
        "١) عرّف المشكلة بدقة.\n"
        "٢) اعصف حلولًا ممكنة.\n"
        "٣) اختر الأنسب وجرّبه.\n"
        "٤) قيّم وعدّل."
    ),
    "tx:safety": (
        "سلوكيات الأمان (تجنّب/طمأنة مفرطة) تبقي القلق.\n"
        "قلّلها تدريجيًا مع تعرّض آمن ومخطط، وستلاحظ تحسّن الثقة."
    ),
}

def cbt_menu_kb():
    rows = []
    for i in range(0, len(CBT_ITEMS), 2):
        chunk = CBT_ITEMS[i:i+2]
        row = [{"text": t, "callback_data": k} for (t, k) in chunk]
        rows.append(row)
    return kb_inline(rows)

def back_kb():
    return kb_inline([[{"text": "⬅️ رجوع للقائمة", "callback_data": "tx:menu"}]])

# ========= Webhook =========
@app.route("/", methods=["GET"])
def root():
    return jsonify({"app": "Arabi Psycho Telegram Bot",
                    "public_url": request.url_root.strip("/")})

@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    update = request.get_json(force=True, silent=True) or {}
    log.info("update: %s", update)

    # 1) أزرار (callback_query)
    if "callback_query" in update:
        cq = update["callback_query"]
        data = cq.get("data", "")
        chat_id = cq.get("message", {}).get("chat", {}).get("id")
        msg_id = cq.get("message", {}).get("message_id")
        cbq_id = cq.get("id")

        if data == "tx:menu":
            answer_cbq(cbq_id)
            edit_msg(chat_id, msg_id,
                     "اختر موضوعًا من العلاج السلوكي المعرفي:", cbt_menu_kb())
            return "ok", 200

        if data in CBT_CONTENT:
            title = CBT_TITLES.get(data, "العلاج")
            txt = f"<b>{title}</b>\n\n{CBT_CONTENT[data]}"
            answer_cbq(cbq_id)
            edit_msg(chat_id, msg_id, txt, back_kb())
            return "ok", 200

        answer_cbq(cbq_id, "خيار غير معروف")
        return "ok", 200

    # 2) رسائل عادية
    message = update.get("message") or {}
    if not message:
        return "ok", 200

    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()
    low = text.lower()

    def is_cmd(name):  # /cmd
        return low.startswith(f"/{name}")

    if is_cmd("start"):
        send(chat_id,
             "👋 أهلاً بك! أنا <b>عربي سايكو</b>.\n"
             "اكتب <b>علاج</b> أو <code>/cbt</code> لبدء قائمة العلاج.\n"
             "أو اكتب: نوم، تواصل، سلام…")
        return "ok", 200

    if is_cmd("help"):
        send(chat_id,
             "أرسل كلمة مثل: نوم، تواصل، سلام — وسأرد عليك.\n"
             "للعلاج السلوكي المعرفي: اكتب <b>علاج</b> أو <code>/cbt</code>.")
        return "ok", 200

    if is_cmd("whoami"):
        uid = message.get("from", {}).get("id")
        send(chat_id, f"chat_id: {chat_id}\nuser_id: {uid}")
        return "ok", 200

    if is_cmd("cbt") or ("علاج" in low):
        send(chat_id, "اختر موضوعًا من العلاج السلوكي المعرفي:", cbt_menu_kb())
        return "ok", 200

    intents = {
        "سلام": "وعليكم السلام ورحمة الله ✨",
        "مرحبا": "أهلًا وسهلًا! كيف أقدر أساعدك؟",
        "تواصل": "تم تسجيل طلب تواصل ✅ سنرجع لك قريبًا.",
        "نوم": "جرّب تنام 7-8 ساعات، ونظّم وقت النوم 😴",
        "حزن": "مفهوم أنك حزين. جرّب تكتب مشاعرك وخطوة صغيرة لطّف يومك.",
        "قلق": "خذ 3 أنفاس بطيئة، وركّز على ما حولك الآن. أنت بخير.",
    }
    for k, v in intents.items():
        if k in text:
            send(chat_id, v)
            if k == "تواصل" and ADMIN_CHAT_ID:
                user = message.get("from", {})
                username = user.get("username") or (user.get("first_name","") + " " + user.get("last_name","")).strip() or "مستخدم"
                info = (f"📩 طلب تواصل\n"
                        f"👤 {username} (id={user.get('id')})\n"
                        f"💬 نصّه: “{text}”")
                try:
                    tg("sendMessage", {"chat_id": int(ADMIN_CHAT_ID), "text": info})
                except Exception:
                    pass
            return "ok", 200

    send(chat_id, f"تمام 👌 وصلتني: “{text}”")
    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
