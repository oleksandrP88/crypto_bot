import json
import requests
import io
import matplotlib.pyplot as plt

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import os
TOKEN = os.getenv("TOKEN")


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
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

# ---------- language ----------

def get_lang(uid):
    return settings.get(uid, {}).get("lang", "ru")

def set_lang(uid, lang):
    settings.setdefault(uid, {})["lang"] = lang
    save_json(SETTINGS_FILE, settings)

def tr(uid, text):
    L = get_lang(uid)

    table = {
        "🚀 Crypto Helper":"🚀 Crypto Helper",
        "Выбери валюту:":"Выбери валюту:",
        "👇 Главное меню":"👇 Главное меню",
    }

    return table.get(text, text)

# ---------- currency ----------

def get_cur(uid):
    return settings.get(uid, {}).get("cur", "USD")

def set_cur(uid, cur):
    settings.setdefault(uid, {})["cur"] = cur
    save_json(SETTINGS_FILE, settings)

def fx(cur):
    if cur == "USD":
        return 1
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5).json()
        return float(r["rates"][cur])
    except:
        return 1

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
    ["❌ Удалить позицию"],
    ["⬅️ Назад"]
])

CUR_KB = kb([
    ["USD","EUR","UAH"],
    ["⬅️ Назад"]
])

LANG_KB = kb([
    ["🇷🇺","🇺🇦","🇬🇧"]
])

# ---------- api ----------

def price(sym):
    try:
        return float(requests.get(
            f"https://api.binance.com/api/v3/ticker/price?symbol={sym}USDT",
            timeout=5).json()["price"])
    except:
        return None

def change24(sym):
    try:
        return float(requests.get(
            f"https://api.binance.com/api/v3/ticker/24hr?symbol={sym}USDT",
            timeout=5).json()["priceChangePercent"])
    except:
        return 0

def top_movers(top=True):
    data = requests.get(
        "https://api.binance.com/api/v3/ticker/24hr",
        timeout=8).json()

    filt = [d for d in data if d["symbol"].endswith("USDT") and len(d["symbol"]) < 12]
    filt.sort(key=lambda x: float(x["priceChangePercent"]), reverse=top)
    return filt[:5]

def chart(sym):
    k = requests.get(
        f"https://api.binance.com/api/v3/klines?symbol={sym}USDT&interval=1h&limit=48",
        timeout=8).json()

    closes = [float(x[4]) for x in k]

    plt.figure()
    plt.plot(closes)
    plt.title(sym)
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf

# ---------- AI block (lightweight local) ----------

def ai_market_summary():
    data = top_movers(True)
    avg = sum(float(x["priceChangePercent"]) for x in data)/len(data)

    if avg > 5:
        mood = "🚀 Рынок сильно бычий"
    elif avg > 1:
        mood = "🙂 Умеренный рост"
    elif avg > -1:
        mood = "😐 Боковик"
    else:
        mood = "⚠️ Давление вниз"

    return mood

# ---------- start ----------

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    user_state[uid] = "onboard_lang"

    await update.message.reply_text(
        "🌍 Choose language:",
        reply_markup=LANG_KB
    )

# ---------- router ----------

async def router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    text = update.message.text
    cur = get_cur(uid)
    rate = fx(cur)

    # ===== ONBOARD =====

    if user_state.get(uid) == "onboard_lang":
        m = {"🇷🇺":"ru","🇺🇦":"uk","🇬🇧":"en"}
        if text in m:
            set_lang(uid, m[text])
            user_state[uid] = "onboard_cur"
            await update.message.reply_text("💱 Валюта:", reply_markup=CUR_KB)
        return

    if user_state.get(uid) == "onboard_cur":
        if text in ["USD","EUR","UAH"]:
            set_cur(uid, text)
            user_state.pop(uid)
            await update.message.reply_text(
                "🤖 Бот умеет: цены, портфель, алерты, графики, рынок, AI обзор",
                reply_markup=MAIN
            )
        return

    # ===== NAV =====

    if text == "📈 Цена":
        await update.message.reply_text("Монета:", reply_markup=COIN_KB)
        return

    if text in COINS:
        p = price(text)
        if not p:
            await update.message.reply_text("Нет цены")
            return
        p *= rate
        c = change24(text)
        await update.message.reply_text(f"{text}\n{p:,.2f} {cur}\n24ч {c:+.2f}%")
        return

    if text == "📊 Рынок":
        lines=[f"{s} {change24(s):+.1f}%" for s in COINS]
        await update.message.reply_text("\n".join(lines))
        return

    if text == "🔥 Топ рост":
        t = top_movers(True)
        await update.message.reply_text("\n".join(
            f"{x['symbol']} {float(x['priceChangePercent']):+.1f}%"
            for x in t))
        return

    if text == "💀 Топ падение":
        t = top_movers(False)
        await update.message.reply_text("\n".join(
            f"{x['symbol']} {float(x['priceChangePercent']):+.1f}%"
            for x in t))
        return

    if text == "📉 График":
        user_state[uid] = "chart"
        await update.message.reply_text("Монета:", reply_markup=COIN_KB)
        return

    if user_state.get(uid) == "chart" and text in COINS:
        await update.message.reply_photo(chart(text))
        user_state.pop(uid)
        return

    # ===== AI =====

    if text == "🧠 AI обзор":
        await update.message.reply_text(ai_market_summary())
        return

    # ===== alerts =====

    if text == "🔔 Алерты":
        await update.message.reply_text("Алерты:", reply_markup=ALERT_KB)
        return

    if text == "➕ Добавить":
        user_state[uid] = "alert_coin"
        await update.message.reply_text("Монета:", reply_markup=COIN_KB)
        return

    if user_state.get(uid) == "alert_coin" and text in COINS:
        user_state[uid] = ("alert_price", text)
        await update.message.reply_text("Цена:")
        return

    if isinstance(user_state.get(uid), tuple) and user_state[uid][0] == "alert_price":
        sym = user_state[uid][1]
        target = float(text)
        alerts.append({"chat":uid,"sym":sym,"target":target,"last":0})
        save_json(ALERTS_FILE, alerts)
        user_state.pop(uid)
        await update.message.reply_text("🔔 Добавлен", reply_markup=MAIN)
        return

    if text == "📋 Мои алерты":
        ua=[a for a in alerts if a["chat"]==uid]
        await update.message.reply_text("\n".join(
            f"{a['sym']} → {a['target']}" for a in ua) or "Пусто")
        return

    if text == "❌ Удалить алерты":
        alerts[:] = [a for a in alerts if a["chat"]!=uid]
        save_json(ALERTS_FILE, alerts)
        await update.message.reply_text("Удалены")
        return

    # ===== portfolio =====

    if text == "📦 Портфель":
        await update.message.reply_text("Портфель:", reply_markup=PORT_KB)
        return

    if text == "➕ Добавить позицию":
        user_state[uid] = "pf_coin"
        await update.message.reply_text("Монета:", reply_markup=COIN_KB)
        return

    if user_state.get(uid) == "pf_coin" and text in COINS:
        user_state[uid] = ("pf_amt", text)
        await update.message.reply_text("Количество:")
        return

    if isinstance(user_state.get(uid), tuple) and user_state[uid][0] == "pf_amt":
        sym = user_state[uid][1]
        amt = float(text)
        p = price(sym) or 0
        portfolio.setdefault(uid,{})
        portfolio[uid][sym] = {"amt":amt,"entry":p}
        save_json(PORTFOLIO_FILE, portfolio)
        user_state.pop(uid)
        await update.message.reply_text("Добавлено", reply_markup=MAIN)
        return

    if text == "📦 Показать":
        pf = portfolio.get(uid,{})
        lines=[]
        total=0
        for s,d in pf.items():
            curp = price(s) or 0
            v = curp*d["amt"]*rate
            total+=v
            lines.append(f"{s} → {v:,.2f} {cur}")
        await update.message.reply_text("\n".join(lines)+f"\n💰 {total:,.2f}")
        return

    if text == "💱 Валюта":
        user_state[uid]="onboard_cur"
        await update.message.reply_text("Валюта:", reply_markup=CUR_KB)
        return

    if text == "⬅️ Назад":
        user_state.pop(uid,None)
        await update.message.reply_text("Главное меню", reply_markup=MAIN)

# ---------- alerts checker ----------

async def check_alerts(ctx):
    app=ctx.application
    for a in alerts:
        p=price(a["sym"])
        if p and p>=a["target"] and abs(p-a["last"])>1:
            await app.bot.send_message(a["chat"],f"🚀 {a['sym']} → {p}")
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
