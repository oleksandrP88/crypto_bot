import requests
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import os

def load_token():
    t = os.getenv("BOT_TOKEN")
    if t:
        return t.strip()

    try:
        with open("/etc/secrets/token.txt") as f:
            return f.read().strip()
    except:
        return None

TOKEN = load_token()
print("TOKEN SOURCE OK:", bool(TOKEN))




# -------- словарь --------

COIN_ALIASES = {
    "биток": "BTC",
    "биткоин": "BTC",
    "btc": "BTC",
    "бтс": "BTC",
    "эфир": "ETH",
    "эфириум": "ETH",
    "ethereum": "ETH",
    "eth": "ETH",
}
 

def normalize_symbol(user_input: str):
    return COIN_ALIASES.get(user_input.lower(), user_input.upper())


# -------- FX --------


def usd_to_eur_rate():
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5)
        data = r.json()
        return float(data["rates"]["EUR"])
    except:
        return None


# -------- price --------


def get_price(symbol):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
    r = requests.get(url)
    if r.status_code != 200:
        return None
    data = r.json()
    if "price" not in data:
        return None
    return float(data["price"])


# -------- alerts --------

alerts = []  # (chat_id, symbol, target_price)


async def alert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Используй: /alert криптовалюта значение")
        return

    sym = normalize_symbol(context.args[0])

    try:
        target = float(context.args[1])
    except:
        await update.message.reply_text("Цена должна быть числом")
        return

    alerts.append((update.effective_chat.id, sym, target))
    await update.message.reply_text(f"🔔 Алерт: {sym} → {target}")


async def check_alerts(app):
    for a in alerts[:]:
        chat_id, sym, target = a
        p = get_price(sym)

        if p and p >= target:
            await app.bot.send_message(
                chat_id,
                f"🚀 {sym} достиг {p}$"
            )
            alerts.remove(a)



# -------- command price --------


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Используй: /price криптовалюта")
        return

    eur_rate = usd_to_eur_rate()
    lines = []

    for arg in context.args:
        sym = normalize_symbol(arg)
        usd_price = get_price(sym)

        if usd_price is None:
            lines.append(f"{sym}: нет на Binance")
            continue

        if eur_rate:
            eur_price = usd_price * eur_rate
            lines.append(f"{sym} — $ {usd_price:,.2f} | € {eur_price:,.2f}")
        else:
            lines.append(f"{sym} — $ {usd_price:,.2f}")

    await update.message.reply_text("\n".join(lines))


# -------- app --------

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("price", price))
app.add_handler(CommandHandler("alert", alert_cmd))

app.job_queue.run_repeating(
    lambda ctx: check_alerts(app),
    interval=60,
    first=5
)


print("Bot started")
app.run_polling()
