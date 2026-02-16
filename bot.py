import json
import requests
import io
import matplotlib.pyplot as plt
import os

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TOKEN = os.getenv("TG_TOKEN")
if not TOKEN:
    raise RuntimeError("TG_TOKEN env variable not set")

# ---------- files ----------

ALERTS_FILE = "alerts.json"
PORTFOLIO_FILE = "portfolio.json"
SETTINGS_FILE = "settings.json"

# ---------- globals ----------

COINS = ["BTC","ETH","SOL","BNB","XRP","TON"]

CG_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "TON": "the-open-network",
}

alerts = []
portfolio = {}
settings = {}
user_state = {}

# ---------- storage ----------

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

# ---------- currency ----------

def get_cur(uid):
    return settings.get(uid, {}).get("cur", "usd").lower()

def set_cur(uid, cur):
    settings.setdefault(uid, {})["cur"] = cur.lower()
    save_json(SETTINGS_FILE, settings)

# ---------- keyboards ----------

def kb(rows):
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

MAIN = kb([
    ["📈 Цена","📊 Рынок"],
    ["🔥 Топ рост","💀 Топ падение"],
    ["📉 График"],
    ["🔔 Алерты","📦 Портфель"],
    ["🧠 AI обзор"],
    ["💱 Валюта"]
])

COIN_KB = kb([
    ["BTC","ETH","SOL"],
    ["BNB","XRP","TON"],
    ["⬅️ Назад"]
])

CUR_KB = kb([
    ["USD","EUR","UAH"],
    ["⬅️ Назад"]
])

ALERT_KB = kb([
    ["➕ Добавить","📋 Мои алерты"],
    ["⬅️ Назад"]
])

PORT_KB = kb([
    ["➕ Добавить позицию","📦 Показать"],
    ["⬅️ Назад"]
])

LANG_KB = kb([
    ["🇷🇺","🇺🇦","🇬🇧"]
])

# ---------- CoinGecko API ----------

def cg_price(sym, cur):
    cid = CG_MAP[sym]
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={cid}&vs_currencies={cur}"
    r = requests.get(url, timeout=10).json()
    return r.get(cid, {}).get(cur)

def cg_change24(sym):
    cid = CG_MAP[sym]
    url = f"https://api.coingecko.com/api/v3/coins/{cid}"
    r = requests.get(url, timeout=10).json()
    return r["market_data"]["price_change_percentage_24h"]

def cg_top(top=True):
    r = requests.get(
        "https://api.coingecko.com/api/v3/coins/markets",
        params={"vs_currency":"usd","order":"market_cap_desc","per_page":50},
        timeout=10
    ).json()

    r.sort(key=lambda x: x["price_change_percentage_24h"] or 0, reverse=top)
    return r[:5]

def cg_chart(sym):
    cid = CG_MAP[sym]
    r = requests.get(
        f"https://api.coingecko.com/api/v3/coins/{cid}/market_chart",
        params={"vs_currency":"usd","days":2},
        timeout=10
    ).json()

    prices = [p[1] for p in r["prices"]]

    plt.figure()
    plt.plot(prices)
    plt.title(sym)
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf

# ---------- AI lite ----------

def ai_summary():
    top = cg_top(True)
    avg = sum(x["price_change_percentage_24h"] or 0 for x in top)/len(top)

    if avg > 5: return "🚀 Рынок перегрет вверх"
    if avg > 1: return "🙂 Рост"
    if avg > -1: return "😐 Боковик"
    return "⚠️ Давление вниз"

# ---------- start ----------

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    user_state[uid] = "lang"
    await update.message.reply_text("🌍 Language:", reply_markup=LANG_KB)

# ---------- router ----------

async def router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    text = update.message.text

    # onboarding
    if user_state.get(uid) == "lang":
        user_state[uid] = "cur"
        await update.message.reply_text("💱 Currency:", reply_markup=CUR_KB)
        return

    if user_state.get(uid) == "cur":
        if text in ["USD","EUR","UAH"]:
            set_cur(uid, text)
            user_state.pop(uid)
            await update.message.reply_text("🤖 Ready", reply_markup=MAIN)
        return

    cur = get_cur(uid)

    # nav
    if text == "📈 Цена":
        await update.message.reply_text("Монета:", reply_markup=COIN_KB)
        return

    if text in COINS:
        p = cg_price(text, cur)
        if not p:
            await update.message.reply_text("Нет цены")
            return
        c = cg_change24(text)
        await update.message.reply_text(f"{text}\n{p:,.2f} {cur.upper()}\n24ч {c:+.2f}%")
        return

    if text == "📊 Рынок":
        lines = [f"{s} {cg_change24(s):+.1f}%" for s in COINS]
        await update.message.reply_text("\n".join(lines))
        return

    if text == "🔥 Топ рост":
        t = cg_top(True)
        await update.message.reply_text("\n".join(
            f"{x['symbol'].upper()} {x['price_change_percentage_24h']:+.1f}%"
            for x in t))
        return

    if text == "💀 Топ падение":
        t = cg_top(False)
        await update.message.reply_text("\n".join(
            f"{x['symbol'].upper()} {x['price_change_percentage_24h']:+.1f}%"
            for x in t))
        return

    if text == "📉 График":
        user_state[uid] = "chart"
        await update.message.reply_text("Монета:", reply_markup=COIN_KB)
        return

    if user_state.get(uid) == "chart" and text in COINS:
        await update.message.reply_photo(cg_chart(text))
        user_state.pop(uid)
        return

    if text == "🧠 AI обзор":
        await update.message.reply_text(ai_summary())
        return

    if text == "💱 Валюта":
        user_state[uid] = "cur"
        await update.message.reply_text("Валюта:", reply_markup=CUR_KB)
        return

    if text == "⬅️ Назад":
        user_state.pop(uid, None)
        await update.message.reply_text("Меню", reply_markup=MAIN)

# ---------- startup ----------

alerts = load_json(ALERTS_FILE, [])
portfolio = load_json(PORTFOLIO_FILE, {})
settings = load_json(SETTINGS_FILE, {})

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, router))

print("Bot started")
app.run_polling()
