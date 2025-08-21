تشغيل عربي سايكو على Render:

1) ارفع الملفات كما هي.
2) Environment:
   - TELEGRAM_BOT_TOKEN=...
   - RENDER_EXTERNAL_URL=https://<اسم-خدمتك>.onrender.com
   - AI_BASE_URL=https://openrouter.ai/api/v1
   - AI_API_KEY=sk-or-...
   - AI_MODEL=openrouter/auto (أو google/gemini-flash-1.5 عبر OpenRouter)
   - CONTACT_THERAPIST_URL=... | CONTACT_PSYCHIATRIST_URL=...
3) Start Command:
   gunicorn -w 1 -k gthread -b 0.0.0.0:$PORT app:app
4) بعد النشر أرسل في تيليجرام: /ai_diag
