# app.py — Arabi Psycho Telegram Bot (Inline + Reply keyboards)
import os, logging, requests
from flask import Flask, request, jsonify

# ========= Config =========
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN env var")

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "secret")
PUBLIC_URL = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("PUBLIC_URL")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # اختياري

BOT_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho-bot")

# ========= Telegram helpers =========
def tg(method: str, payload: dict):
    r = requests.post(f"{BOT_API}/{method}", json=payload, timeout=15)
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
    return {"inline_keyboard": rows}

def kb_reply():  # قائمة سفلية دائمة
    return {
        "keyboard": [
            [{"text": "نوم"}, {"text": "حزن"}],
            [{"text": "تنفس"}, {"text": "تواصل"}],
            [{"text": "مساعدة"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

# ========= Main menu (inline) =========
def main_menu_kb():
    return kb_inline([
        [{"text": "🧠 العلاج السلوكي المعرفي (CBT)", "callback_data": "tx:menu"}],
        [{"text": "ℹ️ مساعدة", "callback_data": "menu:help"}],
        [{"text": "🧪 اختبار الأزرار", "callback_data": "menu:test"}],
    ])

def show_both_menus(chat_id):
    send(chat_id,
         "أنا <b>عربي سايكو</b> 🤝\n"
         "اختر من القائمة أو استخدم الأزرار السفلية.",
         kb=main_menu_kb())
    # رسالة ثانية تفعّل لوحة الأزرار السفلية
    send(chat_id, "لوحة الأزرار السفلية:", kb_reply())

# ========= CBT =========
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
    "tx:te": "أشهر أخطاء التفكير:\n• التعميم\n• قراءة الأفكار\n• التنبؤ السلبي\n• التهويل/التقليل\nاستبدلها بصياغة متوازنة مبنية على أدلة.",
    "tx:rum": "الاجترار تدوير الفكرة بلا فعل، والكبت يزيدها. لاحظها ودعها تمرّ، وانقل انتباهك لنشاط مفيد.",
    "tx:10q": "أسئلة لتحدي الفكرة: الدليل معها/ضدها؟ هل أعمم؟ أسوأ/أفضل/الأغلب؟ ماذا أقول لصديق مكاني؟ ما السلوك المفيد الآن؟",
    "tx:relax": "تنفّس 4-4-6 ×10: شهيق4/حبس4/زفير6. مع إرخاء عضلي تدريجي.",
    "tx:ba": "أضف نشاطات ممتعة/نافعة صغيرة يوميًا وقيّم مزاجك قبل/بعد.",
    "tx:mind": "يقظة ذهنية 3×3×3: 3 أشياء تراها/تسمعها/تلمسها بلا حكم.",
    "tx:ps": "حل المشكلات: عرّف المشكلة → خيارات → خطة SMART → جرّب وقيّم.",
    "tx:safety": "سلوكيات الأمان (تجنّب/طمأنة) تُبقي القلق. قلّلها تدريجيًا مع تعرّض آمن.",
}
def cbt_menu_kb():
    rows = []
    for i in range(0, len(CBT_ITEMS), 2):
        chunk = CBT_ITEMS[i:i+2]
        rows.append([{"text": t, "callback_data": k} for (t, k) in chunk])
    rows.append([{"text": "⬅️ رجوع للقائمة", "callback_data": "tx:back"}])
    return kb_inline(rows)

# ========= Routes =========
@app.get("/")
def root():
    return jsonify({
        "app": "Arabi Psycho Telegram Bot",
        "public_url": (PUBLIC_URL or request.url_root).rstrip("/"),
        "webhook": f"/webhook/{WEBHOOK_SECRET[:3]}*****"
    })

@app.get("/setwebhook")
def setwebhook():
    if not PUBLIC_URL:
        return jsonify({"ok": False, "reason": "No PUBLIC_URL/RENDER_EXTERNAL_URL"}), 400
    url = f"{PUBLIC_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
    return jsonify(tg("setWebhook", {"url": url}))

@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    update = request.get_json(force=True, silent=True) or {}
    log.info("update: %s", update)

    # ==== Callback ====
    if "callback_query" in update:
        cq = update["callback_query"]
        data = cq.get("data", "")
        chat_id = cq.get("message", {}).get("chat", {}).get("id")
        msg_id = cq.get("message", {}).get("message_id")
        answer_cbq(cq.get("id"))

        if data == "menu:help":
            send(chat_id,
                 "الأوامر:\n"
                 "/start — القائمة\n/menu — عرض القوائم\n"
                 "/cbt — قائمة CBT\n/testkb — اختبار الأزرار\n/whoami — المعرّفات")
            return "ok", 200

        if data == "menu:test":
            test_kb = kb_inline([
                [{"text": "زر 1", "callback_data": "z1"}],
                [{"text": "زر 2", "callback_data": "z2"}],
            ])
            edit_msg(chat_id, msg_id, "تجربة الأزرار:", test_kb)
            return "ok", 200

        if data in ["z1", "z2"]:
            edit_msg(chat_id, msg_id, f"✅ اشتغل الزر: {data}", main_menu_kb())
            return "ok", 200

        if data == "tx:menu":
            edit_msg(chat_id, msg_id, "اختر موضوعًا من العلاج السلوكي:", cbt_menu_kb())
            return "ok", 200

        if data == "tx:back":
            edit_msg(chat_id, msg_id, "القائمة الرئيسية:", main_menu_kb())
            return "ok", 200

        if data in CBT_CONTENT:
            title = CBT_TITLES.get(data, "العلاج")
            kb = kb_inline([[{"text": "⬅️ رجوع لقائمة CBT", "callback_data": "tx:menu"}]])
            edit_msg(chat_id, msg_id, f"<b>{title}</b>\n\n{CBT_CONTENT[data]}", kb)
            return "ok", 200

        return "ok", 200

    # ==== Messages ====
    message = update.get("message") or update.get("edited_message") or {}
    if not message:
        return "ok", 200

    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()
    low = text.lower()

    def is_cmd(name): return low.startswith(f"/{name}")

    if is_cmd("start") or is_cmd("menu"):
        show_both_menus(chat_id)
        return "ok", 200

    if is_cmd("cbt") or ("علاج" in low):
        send(chat_id, "اختر موضوعًا من العلاج السلوكي:", cbt_menu_kb())
        return "ok", 200

    if is_cmd("testkb"):
        send(chat_id, "تجربة الأزرار:", kb_inline([
            [{"text": "زر 1", "callback_data": "z1"}],
            [{"text": "زر 2", "callback_data": "z2"}],
        ]))
        send(chat_id, "لوحة الأزرار السفلية:", kb_reply())
        return "ok", 200

    if is_cmd("whoami"):
        uid = message.get("from", {}).get("id")
        send(chat_id, f"chat_id: {chat_id}\nuser_id: {uid}")
        return "ok", 200

    if is_cmd("help"):
        send(chat_id,
             "الأوامر:\n"
             "/start — القائمة\n/menu — عرض القوائم\n"
             "/cbt — قائمة CBT\n/testkb — اختبار الأزرار\n/whoami — المعرّفات")
        return "ok", 200

    # ردود سريعة + تواصل
    intents = {
        "سلام": "وعليكم السلام ورحمة الله ✨",
        "مرحبا": "أهلًا وسهلًا! كيف أقدر أساعدك؟",
        "نوم": "نم 7-8 ساعات وثبّت وقت النوم وقلّل المنبهات مساءً 😴",
        "قلق": "خذ 3 أنفاس بطيئة وركّز على الحاضر. أنت بخير.",
        "حزن": "جرّب نشاطًا ممتعًا قصيرًا اليوم.",
        "تنفس": "تنفّس 4-4-6 ×10: شهيق4/حبس4/زفير6.",
        "مساعدة": "اكتب /menu أو /cbt لعرض القوائم.",
        "تواصل": "تم تسجيل طلب تواصل ✅ سنرجع لك قريبًا.",
    }
    for k, v in intents.items():
        if k in text:
            send(chat_id, v, kb_reply())
            if k == "تواصل" and ADMIN_CHAT_ID:
                user = message.get("from", {})
                username = user.get("username") or (user.get("first_name","") + " " + user.get("last_name","")).strip() or "مستخدم"
                info = (f"📩 طلب تواصل\n"
                        f"👤 {username} (id={user.get('id')})\n"
                        f"🔗 chat_id={chat_id}\n"
                        f"💬 النص: “{text}”")
                try:
                    tg("sendMessage", {"chat_id": int(ADMIN_CHAT_ID), "text": info})
                except Exception:
                    pass
            return "ok", 200

    send(chat_id, f"تمام 👌 وصلتني: “{text}”\nاكتب /menu لعرض الأزرار.", kb_reply())
    return "ok", 200

# ========= Auto set webhook =========
def ensure_webhook():
    if not PUBLIC_URL:
        log.warning("No PUBLIC_URL; skip setWebhook.")
        return
    url = f"{PUBLIC_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
    res = tg("setWebhook", {"url": url})
    log.info("setWebhook -> %s", res)

ensure_webhook()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
