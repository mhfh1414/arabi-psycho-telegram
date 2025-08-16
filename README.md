# Arabi Psycho Telegram Bot

مساعد نفسي تعليمي (CBT + اختبارات قصيرة) يعمل كويبهوك على Render.

## الإعداد
1) أنشئ بوت تيليجرام من @BotFather وخذ التوكن.
2) ارفع الملفات إلى GitHub (app.py / requirements.txt / render-start.txt / README.md).
3) على Render: New → Web Service → اربط المستودع.
   - Build Command: pip install -r requirements.txt
   - Start Command: contents of render-start.txt (يُقرأ تلقائيًا إذا استخدمتها هناك)
4) Environment Variables:
   - TELEGRAM_BOT_TOKEN = (من BotFather)
   - WEBHOOK_SECRET = (أي قيمة قوية، مثلاً 32 حرفًا)
   - RENDER_EXTERNAL_URL = (يُملأ تلقائيًا من Render)
   - ADMIN_CHAT_ID = (اختياري للتنبيهات)
   - CONTACT_PHONE = (اختياري لظهور رقم التواصل في /help)

## أوامر
/start, /help, /tests, /therapy, /cbt, /whoami
