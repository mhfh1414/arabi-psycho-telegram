# Arabi Psycho (Telegram + Render)

Start command (Render → Settings → Start Command):
gunicorn -w 1 -k gthread -b 0.0.0.0:$PORT app:app

Required env vars:
- TELEGRAM_BOT_TOKEN = <token from @BotFather>
- RENDER_EXTERNAL_URL = https://<your-service>.onrender.com
- AI_API_KEY = <OpenRouter key>
- AI_BASE_URL = https://openrouter.ai/api/v1
- AI_MODEL = openrouter/auto   (or google/gemini-flash-1.5)

After deploy:
1) Make sure logs show: "Webhook set: https://<service>.onrender.com/webhook/secret"
2) In Telegram, send /start to your bot.
