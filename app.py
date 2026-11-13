import os, logging, asyncio
from flask import Flask, request, jsonify
import bot as bot_module

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# Инициализируем бота при старте
bot_module.init_bot_and_loop()

@app.get("/")
def root():
    return "Galaxy Rent bot is running", 200

@app.get("/health")
def health():
    return jsonify({"status": "ok", "orders": len(bot_module.ORDERS)}), 200

@app.post("/webhook")
def webhook():
    # Проверка безопасности от Telegram
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != "mysecret123":
        return "", 403
        
    data = request.get_json(force=True, silent=True) or {}
    if not data:
        return "", 400
        
    fut = asyncio.run_coroutine_threadsafe(bot_module.process_update(data), bot_module._loop)
    try:
        fut.result(timeout=60)
    except Exception:
        logging.exception("process_update failed")
    return "", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
