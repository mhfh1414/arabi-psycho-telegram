# -*- coding: utf-8 -*-
import os, logging, json
from typing import Dict, Any, List, Tuple
import requests
from flask import Flask, request, jsonify

# ========= الإعدادات =========
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Error: Missing TELEGRAM_BOT_TOKEN env var")

BOT_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "secret")
PUBLIC_URL = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("PUBLIC_URL")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")           # اختياري
CONTACT_PHONE = os.environ.get("CONTACT_PHONE")           # اختياري

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho-bot")

# ========= أدوات تيليجرام =========
def tg_call(method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(f"{BOT_API}/{method}", json=payload, timeout=15)
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

# ========= قوائم تعليمية (باستخدام أكواد قصيرة) =========
DX = {
    "anx": {"title": "القلق", "text":
        "توتر مستمر، شد عضلي، أفكار ترقّب. العلاج: CBT والتعرّض وتقنيات الاسترخاء."},
    "soc": {"title": "القلق الاجتماعي", "text":
        "خوف من التقييم السلبي والتجنّب. العلاج: تعرّض اجتماعي وتحدّي الأفكار."},
    "ocd": {"title": "الوسواس القهري", "text":
        "وساوس + أفعال قهرية تُبقي القلق. العلاج: تعرّض ومنع الاستجابة + تقليل الطمأنة."},
    "panic": {"title": "نوبات الهلع", "text":
        "اندفاع قلق شديد مع أعراض جسدية. العلاج: تعرّض للأحاسيس + تصحيح التفسير."},
    "dep": {"title": "الاكتئاب", "text":
        "مزاج منخفض وفقدان المتعة. العلاج: تنشيط سلوكي + إعادة بناء أفكار + روتين نوم."},
    "self": {"title": "الثقة بالنفس", "text":
        "تُبنى بالممارسة التدريجية والإنجازات الصغيرة وصياغات واقعية للذات."},
    "health": {"title": "القلق على الصحة", "text":
        "مراقبة جسدية/طمأنة مفرطة. العلاج: تقليل الفحص، تعرّض للريبة، تحدّي الكارثية."},
    "ptsd": {"title": "كرب ما بعد الصدمة", "text":
        "ذكريات اقتحامية وتجنّب ويقظة. العلاج: تعرّض سردي منضبط + تنظيم الانفعال."},
}

TH = {
    "cd": {"title": "أخطاء التفكير", "text":
        "تهويل/تعميم/قراءة أفكار/كل-أو-لا شيء. لاحظ الفكرة → سمِّ التشوّه → دليل/بديل → صياغة متوازنة."},
    "rum": {"title": "الاجترار والكبت", "text":
        "الاجترار تدوير بلا فعل والكبت يعيدها أقوى. حدّد «وقت قلق» ثم عدْ للحاضر ونفّذ أفعالًا صغيرة."},
    "q10": {"title": "الأسئلة العشرة لتحدي الأفكار", "text":
        "ما الدليل/النقيض؟ هل أعمّم؟ أسوأ/أفضل/الأغلب؟ بدائل؟ لو صديق مكاني؟ ماذا أتجاهل؟ صياغة متوازنة."},
    "relax": {"title": "الاسترخاء", "text":
        "تنفّس 4-4-6 عدة دقائق، إرخاء عضلي تدريجي، تأريض 5-4-3-2-1."},
    "ba": {"title": "التنشيط السلوكي", "text":
        "جدولة ممتع/نافع بخطوات صغيرة (قاعدة الدقيقتين) لرفع المزاج."},
    "mind": {"title": "اليقظة الذهنية", "text":
        "لاحظ اللحظة بلا حكم؛ سمِّ الفكرة «فِكر» وارجع للتنفس/المهمة."},
    "ps": {"title": "حل المشكلات", "text":
        "عرّف المشكلة → اعصف بخيارات → قيّم واختر خطة S.M.A.R.T → جرّب وقيّم."},
    "sa": {"title": "سلوكيات الأمان", "text":
        "مثل الطمأنة/التجنّب الخفي؛ تُبقي القلق. بدّلها بتعرّض تدريجي مع منع الاستجابة."},
}

def edu_home(chat_id: int):
    rows = [
        [("الاختبارات النفسية", "tests:menu"), ("العلاج النفسي", "edu:th")],
        [("الاضطرابات النفسية", "edu:dx")],
        [("مساعدة", "menu:help")],
    ]
    send_kb(chat_id, "اختر من القوائم:", rows)

def edu_dx_list(chat_id: int):
    keys = list(DX.keys())
    rows: List[List[Tuple[str, str]]] = []
    for i in range(0, len(keys), 2):
        part = keys[i:i+2]
        rows.append([(DX[k]["title"], f"dx:{k}") for k in part])
    rows.append([("⟵ القائمة", "edu:home"), ("العلاج النفسي", "edu:th")])
    send_kb(chat_id, "الاضطرابات النفسية:", rows)

def edu_th_list(chat_id: int):
    keys = list(TH.keys())
    rows: List[List[Tuple[str, str]]] = []
    for i in range(0, len(keys), 2):
        part = keys[i:i+2]
        rows.append([(TH[k]["title"], f"th:{k}") for k in part])
    rows.append([("⟵ القائمة", "edu:home"), ("الاضطرابات النفسية", "edu:dx")])
    send_kb(chat_id, "مواضيع العلاج المعرفي السلوكي (CBT):", rows)

def edu_show_dx(chat_id: int, code: str):
    d = DX.get(code)
    if not d:
        edu_dx_list(chat_id); return
    rows = [[("⟵ رجوع", "edu:dx"), ("القائمة الرئيسية", "edu:home")]]
    send_kb(chat_id, f"<b>{d['title']}</b>\n\n{d['text']}", rows)

def edu_show_th(chat_id: int, code: str):
    d = TH.get(code)
    if not d:
        edu_th_list(chat_id); return
    rows = [[("⟵ رجوع", "edu:th"), ("القائمة الرئيسية", "edu:home")], [("ابدأ تمرين /cbt", "noop")]]
    send_kb(chat_id, f"<b>{d['title']}</b>\n\n{d['text']}", rows)

# ========= الاختبارات النفسية =========
CHOICES_0_3 = [("أبدًا", 0), ("عدة أيام", 1), ("أكثر من النصف", 2), ("تقريبًا كل يوم", 3)]
TESTS = {
    "gad2": {
        "title": "قلق (GAD-2)",
        "items": ["العصبية أو القلق أو التوتر", "عدم القدرة على إيقاف القلق أو التحكم فيه"],
        "choices": CHOICES_0_3, "cut": 3,
        "interp": "≥3 يشير لاحتمال قلق مهم؛ استكمل GAD-7 أو راجع مختصًا."
    },
    "phq2": {
        "title": "اكتئاب (PHQ-2)",
        "items": ["قلّة الاهتمام/المتعة", "الشعور بالإحباط أو اليأس"],
        "choices": CHOICES_0_3, "cut": 3,
        "interp": "≥3 يشير لاحتمال اكتئاب؛ استكمل PHQ-9 أو راجع مختصًا."
    },
    "ins2": {
        "title": "أرق (ISI-2 مختصر)",
        "items": ["صعوبة البدء بالنوم", "الاستيقاظ/إجهاد نهاري"],
        "choices": [("لا شيء",0),("خفيف",1),("متوسط",2),("شديد",3)], "cut": 3,
        "interp": "≥3 يشير لمشكلات نوم؛ حسّن العادات واطلب تقييماً عند اللزوم."
    },
}
STATE: Dict[int, Dict[str, Any]] = {}

def tests_menu(chat_id: int):
    rows = [
        [("قلق (GAD-2)", "tests:start:gad2"), ("اكتئاب (PHQ-2)", "tests:start:phq2")],
        [("الأرق (ISI-2)", "tests:start:ins2")],
        [("⟵ القائمة الرئيسية", "edu:home")],
    ]
    send_kb(chat_id, "هذه أدوات فحص أولي وليست تشخيصًا، أجب عن آخر أسبوعين:", rows)

def tests_start(chat_id: int, tkey: str):
    STATE[chat_id] = {"type": tkey, "idx": 0, "score": 0}
    send_question(chat_id)

def send_question(chat_id: int):
    st = STATE.get(chat_id)
    if not st: tests_menu(chat_id); return
    t = TESTS[st["type"]]; idx = st["idx"]; items = t["items"]
    if idx >= len(items):
        score = st["score"]; cut = t["cut"]; badge = "✅" if score < cut else "⚠️"
        send(chat_id, f"<b>{t['title']}</b>\nالنتيجة: <b>{score}</b> / {len(items)*3} {badge}\n"
                      f"{t['interp']}\n\nتنبيه: هذا فحص تعليمي وليس تشخيصًا.")
        STATE.pop(chat_id, None); tests_menu(chat_id); return
    q = items[idx]
    rows = [[(txt, f"tests:ans:{val}")] for (txt, val) in t["choices"]]
    rows.append([("⟵ إلغاء", "tests:cancel")])
    send_kb(chat_id, f"<b>{t['title']}</b>\nس{idx+1}: {q}", rows)

def tests_answer(chat_id: int, val: int):
    st = STATE.get(chat_id)
    if not st: tests_menu(chat_id); return
    st["score"] += int(val); st["idx"] += 1; send_question(chat_id)

# ========= نوايا + أوامر =========
INTENTS = {
    "سلام": "وعليكم السلام ورحمة الله ✨",
    "مرحبا": "أهلًا وسهلًا! كيف أقدر أساعدك؟",
    "تواصل": "تم تسجيل طلب تواصل ✅ سنرجع لك قريبًا.",
    "نوم": "نم 7-8 ساعات وثبّت وقت النوم وقلّل المنبهات مساءً 😴",
    "حزن": "جرّب نشاطًا صغيرًا ممتعًا اليوم ولو 10 دقائق، وشارك أحدًا تثق به.",
    "قلق": "تنفّس 4-4-6 لعدة دقائق ثم واجه مخاوفك بخطوات صغيرة.",
}
def main_menu(chat_id: int): edu_home(chat_id)

def is_cmd(text: str, name: str) -> bool:
    return text.strip().lower().startswith("/" + name.lower())

# ========= الويبهوك =========
@app.route("/", methods=["GET"])
def index():
    info = {"app": "Arabi Psycho Telegram Bot", "public_url": PUBLIC_URL, "status": "ok"}
    info["webhook"] = ("/webhook/" + WEBHOOK_SECRET[:3] + "*****")
    return jsonify(info)

@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    upd = request.get_json(force=True, silent=True) or {}
    # أزرار
    if "callback_query" in upd:
        cb = upd["callback_query"]; data = cb.get("data",""); chat_id = cb["message"]["chat"]["id"]
        answer_cb(cb["id"])

        if data == "edu:home": edu_home(chat_id)
        elif data == "edu:dx":  edu_dx_list(chat_id)
        elif data == "edu:th":  edu_th_list(chat_id)
        elif data.startswith("dx:"):  edu_show_dx(chat_id, data.split(":",1)[1])
        elif data.startswith("th:"):  edu_show_th(chat_id, data.split(":",1)[1])

        elif data == "tests:menu": tests_menu(chat_id)
        elif data.startswith("tests:start:"): tests_start(chat_id, data.split(":",2)[2])
        elif data.startswith("tests:ans:"): tests_answer(chat_id, int(data.split(":",2)[2]))
        elif data == "tests:cancel": STATE.pop(chat_id, None); tests_menu(chat_id)

        elif data == "menu:help": show_help(chat_id)
        return "ok", 200

    # رسائل
    message = upd.get("message") or upd.get("edited_message")
    if not message: return "ok", 200
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()
    low = text.replace("ـ","").lower()

    if is_cmd(text,"start"): main_menu(chat_id); return "ok", 200
    if is_cmd(text,"help"):  show_help(chat_id); return "ok", 200
    if is_cmd(text,"cbt"):
        send(chat_id,
             "جلسة CBT سريعة:\n1) سمِّ الفكرة المزعجة.\n2) ما الدليل/النقيض؟\n"
             "3) ما الخطوة الصغيرة الآن؟\n4) صياغة متوازنة.\n\nجرّب أيضًا «العلاج النفسي».")
        return "ok", 200
    if is_cmd(text,"therapy"): edu_th_list(chat_id); return "ok", 200
    if is_cmd(text,"tests"):   tests_menu(chat_id); return "ok", 200
    if is_cmd(text,"whoami"):
        uid = message.get("from", {}).get("id")
        send(chat_id, f"chat_id: {chat_id}\nuser_id: {uid}")
        return "ok", 200

    # تواصل
    if low in ["تواصل","توصل","اتصال","اتواصل"]:
        user = message.get("from", {})
        username = user.get("username") or (user.get("first_name","")+" "+user.get("last_name","")).strip() or "مستخدم"
        send(chat_id, "تم تسجيل طلب تواصل ✅ سنرجع لك قريبًا.")
        if ADMIN_CHAT_ID:
            info = (f"📩 طلب تواصل\n👤 {username} (user_id={user.get('id')})\n"
                    f"🔗 chat_id={chat_id}\n💬 النص: {text}")
            send(int(ADMIN_CHAT_ID), info)
        return "ok", 200

    for k,v in INTENTS.items():
        if k in low: send(chat_id, v); return "ok", 200

    send(chat_id, f"تمام 👌 وصلتني: “{text}”\nاكتب /help للمساعدة.")
    return "ok", 200

def show_help(chat_id: int):
    phone_line = f"\n📞 للتواصل: {CONTACT_PHONE}" if CONTACT_PHONE else ""
    send(chat_id,
         "الأوامر:\n/start - القائمة الرئيسية\n/help - تعليمات\n"
         "/tests - الاختبارات النفسية\n/therapy - مواضيع CBT\n/cbt - تمرين سريع\n/whoami - معرّفات"
         + phone_line)

def ensure_webhook():
    if not PUBLIC_URL:
        log.warning("No PUBLIC_URL; skipping webhook setup.")
        return
    url = f"{PUBLIC_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
    tg_call("setWebhook", {"url": url})
    log.info("Webhook set to %s", url)

ensure_webhook()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
