# Arabi Psycho – Telegram Bot (CBT + Menu)

نشر على Render:
- Build: pip install -r requirements.txt
- Start: gunicorn -w 1 -k gthread -b 0.0.0.0:$PORT app:app
- Env Vars: TELEGRAM_BOT_TOKEN (+ WEBHOOK_SECRET اختياري)
- بعد ما تصير Live: افتح /setwebhook ثم جرّب /start و /cbt.
