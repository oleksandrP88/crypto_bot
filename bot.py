import json
import time
import requests
import io
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TOKEN = os.getenv("TG_TOKEN")

# ---------- files ----------

ALERTS_FILE = "alerts.json"
PORTFOLIO_FILE = "portfolio.json"
SETTINGS_FILE = "settings.json"

# ---------- globals ----------

COINS = ["BTC","ETH","SOL","BNB","XRP","TON"]
MAX_ALERTS_PER_USER = 5

alerts = []
portfolio = {}
settings = {}
user_state = {}

# ---------- storage ----------

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

# ---------- fx cache ----------

_fx_cache = {"rate": 1, "ts": 0}
FX_TTL = 600

def fx(cur):
    if cur == "USD":
        return 1

    if time.time() - _fx_cache["ts"] < FX_TTL:
        return _fx_cache["rate"]

    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5).json()
        rate = float(r["rates"][cur])
        _fx_cache["rate"] = rate
        _fx_cache["ts"] = time.time()
        return rate
    except:
        return _fx_cache["rate"]

# ---------- settings ----------

def get_cur(uid):
    return settings.get(uid, {}).get("cur", "USD")

def set_cur(uid, cur):
    settings.setdefault(uid, {})["cur"] = cur
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

ALERT_KB = kb([
    ["➕ Добавить","📋 Мои алерты","❌ Удалить алерты"],
    ["⬅️ Назад"]
])

PORT_KB = kb([
    ["➕ Добавить позицию","📦 Показать"],
    ["⬅️ Назад"]
])

CUR_KB = kb([
    ["USD","EUR","UAH"],
    ["⬅️ Назад"]
])

# ---------- api ----------

CG_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "TON": "the-open-network",
}

_price_cache = {}
_change_cache = {}
_chart_cache = {}
CACHE_TTL = 60

def _cg(sym):
    return CG_IDS[sym]

def _cached_get(cache, key):
    v = cache.get(key)
    if not v:
        return None
    val, ts = v
    if time.time() - ts > CACHE_TTL:
        return None
    return val

def _cached_set(cache, key, val):
    cache[key] = (val, time.time())

def price(sym):
    c = _cached_get(_price_cache, sym)
    if c:
        return c

    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": _cg(sym), "vs_currencies": "usd"},
            timeout=6
        ).json()
        val = float(r[_cg(sym)]["usd"])
        _cached_set(_price_cache, sym, val)
        return val
    except:
        pass

    try:
        r = requests.get(
            f"https://api.binance.com/api/v3/ticker/price?symbol={sym}USDT",
            timeout=5
        ).json()
        val = float(r["price"])
        _cached_set(_price_cache, sym, val)
        return val
    except:
        return None

def change24(sym):
    c = _cached_get(_change_cache, sym)
    if c:
        return c

    try:
        r = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{_cg(sym)}",
            timeout=6
        ).json()
        val = float(r["market_data"]["price_change_percentage_24h"])
        _cached_set(_change_cache, sym, val)
        return val
    except:
        return 0

def top_movers(top=True):
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency":"usd",
                "order":"market_cap_desc",
                "per_page":100,
                "page":1,
                "price_change_percentage":"24h"
            },
            timeout=8
        ).json()

        r.sort(key=lambda x: x["price_change_percentage_24h"] or 0, reverse=top)
        return r[:5]
    except:
        return []

def chart(sym):
    c = _cached_get(_chart_cache, sym)
    if c:
        return c

    try:
        r = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{_cg(sym)}/market_chart",
            params={"vs_currency":"usd","days":2},
            timeout=8
        ).json()

        closes = [p[1] for p in r["prices"]]

        plt.figure()
        plt.plot(closes)
        plt.title(sym)

        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        buf.seek(0)

        _cached_set(_chart_cache, sym, buf)
        return buf
    except:
        return None

# ---------- AI ----------

def ai_market_summary():
    d = top_movers(True)
    if not d:
        return "Нет данных"

    avg = sum((x["price_change_percentage_24h"] or 0) for x in d)/len(d)

    if avg > 5: return "🚀 Сильный рост"
    if avg > 1: return "🙂 Рост"
    if avg > -1: return "😐 Боковик"
    return "⚠️ Давление вниз"

# ---------- start ----------

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid=str(update.effective_chat.id)
    user_state[uid]="onboard_cur"
    await update.message.reply_text("Выбери валюту:", reply_markup=CUR_KB)

# ---------- router ----------

async def router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    uid=str(update.effective_chat.id)
    text=update.message.text
    cur=get_cur(uid)
    rate=fx(cur)

    if user_state.get(uid)=="onboard_cur":
        if text in ["USD","EUR","UAH"]:
            set_cur(uid,text)
            user_state.pop(uid)
            await update.message.reply_text("Готово", reply_markup=MAIN)
        return

    if text=="📈 Цена":
        await update.message.reply_text("Монета:", reply_markup=COIN_KB)
        return

    if text in COINS:
        p=price(text)
        if not p:
            await update.message.reply_text("Нет цены")
            return
        await update.message.reply_text(
            f"{text}\n{p*rate:,.2f} {cur}\n24ч {change24(text):+.2f}%"
        )
        return

    if text=="🔥 Топ рост":
        t=top_movers(True)
        await update.message.reply_text("\n".join(
            f"{x['symbol'].upper()} {x['price_change_percentage_24h']:+.1f}%"
            for x in t))
        return

    if text=="💀 Топ падение":
        t=top_movers(False)
        await update.message.reply_text("\n".join(
            f"{x['symbol'].upper()} {x['price_change_percentage_24h']:+.1f}%"
            for x in t))
        return

    if text=="📉 График":
        user_state[uid]="chart"
        await update.message.reply_text("Монета:", reply_markup=COIN_KB)
        return

    if user_state.get(uid)=="chart" and text in COINS:
        img=chart(text)
        if img:
            await update.message.reply_photo(img)
        user_state.pop(uid)
        return

    if text=="🧠 AI обзор":
        await update.message.reply_text(ai_market_summary())
        return

    if text=="🔔 Алерты":
        await update.message.reply_text("Алерты:", reply_markup=ALERT_KB)
        return

    if text=="➕ Добавить":
        if len([a for a in alerts if a["chat"]==uid])>=MAX_ALERTS_PER_USER:
            await update.message.reply_text("Лимит алертов")
            return
        user_state[uid]="alert_coin"
        await update.message.reply_text("Монета:", reply_markup=COIN_KB)
        return

    if user_state.get(uid)=="alert_coin" and text in COINS:
        user_state[uid]=("alert_price",text)
        await update.message.reply_text("Цена:")
        return

    if isinstance(user_state.get(uid),tuple):
        tag,sym=user_state[uid]
        if tag=="alert_price":
            try:
                target=float(text)
            except:
                await update.message.reply_text("Введи число")
                return
            alerts.append({"chat":uid,"sym":sym,"target":target,"last":0})
            save_json(ALERTS_FILE,alerts)
            user_state.pop(uid)
            await update.message.reply_text("Добавлен", reply_markup=MAIN)
            return

    if text=="⬅️ Назад":
        user_state.pop(uid,None)
        await update.message.reply_text("Меню", reply_markup=MAIN)

# ---------- alerts checker ----------

async def check_alerts(ctx):
    app=ctx.application
    for a in alerts:
        p=price(a["sym"])
        if p and p>=a["target"] and abs(p-a["last"])>1:
            await app.bot.send_message(a["chat"], f"🚀 {a['sym']} → {p}")
            a["last"]=p
    save_json(ALERTS_FILE,alerts)

# ---------- startup ----------

alerts = load_json(ALERTS_FILE, [])
portfolio = load_json(PORTFOLIO_FILE, {})
settings = load_json(SETTINGS_FILE, {})

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, router))
app.job_queue.run_repeating(check_alerts, interval=60, first=10)

print("Bot started")
app.run_polling()
