# -*- coding: utf-8 -*-
import os
import asyncio
import re
import requests
import time
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# ===== CONFIG =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MY_USER = os.getenv("MY_USER")
MY_PASS = os.getenv("MY_PASS")

TARGET_URL = "http://2.59.169.96/ints/agent/SMSCDRReports"
LOGIN_URL = "http://2.59.169.96/ints/login"

# ✅ Firebase URL (FROM FIRST SCRIPT)
FB_URL = "https://bot-pro-bd-default-rtdb.asia-southeast1.firebasedatabase.app/bot"

ADMIN_LINK = "https://t.me/ftcaiw24"
BOT_LINK = "https://t.me/FTC_SUPER_SMS_BOT"
DV_LINK = "https://t.me/Mhnirob1"
CN_LINK = "https://t.me/saimonearningzon24"

sent_msgs = {}
START_TIME = time.time()

# ===== FIREBASE FUNCTION (ADDED) =====
def update_firebase(num, msg, date_str):
    try:
        url = f"{FB_URL}/sms_logs/{num}.json"
        payload = {
            "number": num,
            "message": msg,
            "time": date_str,
            "paid": False
        }
        requests.put(url, json=payload, timeout=5)
    except:
        pass

# ===== UTILITIES =====
def extract_otp(msg):
    match = re.search(r'\b(\d{3,8}|\d{3}-\d{3}|\d{4}\s\d{4})\b', msg)
    return match.group(0) if match else "N/A"

def send_telegram(date_str, num, sms_text, otp, cli_source, is_update=False):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    masked = num[:4] + "TS" + num[-4:] if len(num) > 8 else num

    header = "🔄🛎️ <b>UPDATED SMS RECEIVED</b>" if is_update else "🛎️ <b>NEW SMS RECEIVED</b>"

    text = f"{header}\n\n" \
           f"📞 <b>Number:</b> <code>{masked}</code>\n" \
           f"🌐 <b>Service:</b> <code>{cli_source}</code>\n\n" \
           f"🔑 <b>OTP:</b> <code>{otp}</code>\n\n" \
           f"📩 <b>Full Message:</b><blockquote>{sms_text}</blockquote>\n"

    keyboard = [
        [
            {"text": "👨‍🦲Admin", "url": ADMIN_LINK},
            {"text": "🔢Number bot", "url": BOT_LINK}
        ],
        [
            {"text": "💥Channel", "url": CN_LINK},
            {"text": "💻 Developer", "url": DV_LINK}
        ]
    ]

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": keyboard}
    }

    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except:
        return False

# ===== MAIN BOT =====
async def start_bot():
    print("🚀 Bot started...")

    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()

        async def login():
            try:
                await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
                await page.evaluate(f"""() => {{
                    const myUser = "{MY_USER}";
                    const myPass = "{MY_PASS}";
                    let userField, passField, ansField;

                    document.querySelectorAll('input').forEach(inp => {{
                        let p = (inp.placeholder || "").toLowerCase();

                        if (inp.type === 'password') passField = inp;
                        else if (p.includes('user') || inp.type === 'text') {{
                            if (!userField && !p.includes('answer')) userField = inp;
                        }}

                        if (p.includes('answer') || (inp.name || "").includes('ans')) ansField = inp;
                    }});

                    let match = document.body.innerText.match(/What is\\s+(\\d+)\\s*\\+\\s*(\\d+)/i);
                    let sum = match ? (parseInt(match[1]) + parseInt(match[2])) : "";

                    if (userField && passField && ansField && sum !== "") {{
                        userField.value = myUser;
                        passField.value = myPass;
                        ansField.value = sum;

                        userField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        passField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        ansField.dispatchEvent(new Event('input', {{ bubbles: true }}));

                        for (let b of document.querySelectorAll('button, input[type="submit"]')) {{
                            if ((b.innerText || b.value || "").toLowerCase().includes('login')) {{
                                b.click();
                                return true;
                            }}
                        }}
                    }}
                }}""")
                return True
            except:
                return False

        await login()
        is_first_scan = True

        while True:
            try:
                await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(2000)

                if "login" in page.url:
                    await login()
                    continue

                valid_rows = []
                rows = await page.query_selector_all("table tbody tr")

                for row in rows:
                    cols = await row.query_selector_all("td")
                    if len(cols) >= 7:
                        d = (await cols[0].inner_text()).strip()
                        n = (await cols[2].inner_text()).strip()
                        s = (await cols[5].inner_text()).strip()
                        cli = (await cols[3].inner_text()).strip()

                        if d and len(re.sub(r'\D', '', n)) >= 8:
                            valid_rows.append({
                                "date": d,
                                "num": n,
                                "sms": s,
                                "cli": cli
                            })

                if valid_rows:
                    latest = valid_rows[0]

                    if is_first_scan:
                        otp = extract_otp(latest['sms'])
                        if send_telegram(latest['date'], latest['num'], latest['sms'], otp, latest['cli']):
                            update_firebase(latest['num'], latest['sms'], latest['date'])

                        sent_msgs[f"{latest['num']}|{latest['sms']}"] = latest['date']
                        is_first_scan = False

                        for item in valid_rows[1:]:
                            sent_msgs[f"{item['num']}|{item['sms']}"] = item['date']

                    else:
                        for item in reversed(valid_rows):
                            uid = f"{item['num']}|{item['sms']}"
                            otp = extract_otp(item['sms'])

                            if uid not in sent_msgs:
                                if send_telegram(item['date'], item['num'], item['sms'], otp, item['cli']):
                                    update_firebase(item['num'], item['sms'], item['date'])

                                sent_msgs[uid] = item['date']

                if len(sent_msgs) > 2000:
                    sent_msgs.clear()

            except Exception:
                pass

            await asyncio.sleep(4)

if __name__ == "__main__":
    asyncio.run(start_bot())
