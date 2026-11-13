import os, logging, asyncio
from flask import Flask, request, jsonify
import bot as bot_module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = Flask(__name__)

WEBHOOK_PATH     = "/webhook"
WEBHOOK_SECRET   = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_URL      = os.getenv("WEBHOOK_URL", "").rstrip("/")
ADMIN_HTTP_TOKEN = os.getenv("ADMIN_HTTP_TOKEN", "")


@app.before_request
def _ensure_init():
    """Ленивая инициализация при первом запросе (безопасно для gunicorn)."""
    bot_module.init_bot_and_loop(
        webhook_url=WEBHOOK_URL,
        webhook_path=WEBHOOK_PATH,
        webhook_secret=WEBHOOK_SECRET,
    )


@app.get("/")
def root():
    return "Galaxy Rent bot is running", 200


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "orders": len(bot_module.ORDERS),
        "rented": len(bot_module.RENTED),
        "webhook": bool(WEBHOOK_URL),
    }), 200


@app.post(WEBHOOK_PATH)
def webhook():
    if WEBHOOK_SECRET and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
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


@app.get("/admin/stats")
def admin_stats():
    if not ADMIN_HTTP_TOKEN or request.headers.get("X-Admin-Token", "") != ADMIN_HTTP_TOKEN:
        return jsonify({"error": "forbidden"}), 403
    paid = [o for o in bot_module.ORDERS.values() if o["paid"]]
    return jsonify({
        "paid_count": len(paid),
        "income": sum(o["total"] for o in paid),
        "rented": {k: v["until"] for k, v in bot_module.RENTED.items()},
    })


if __name__ == "__main__":
    bot_module.init_bot_and_loop(
        webhook_url=WEBHOOK_URL,
        webhook_path=WEBHOOK_PATH,
        webhook_secret=WEBHOOK_SECRET,
    )
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))