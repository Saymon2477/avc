import os
import asyncio
import re
import requests
import time
import traceback
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# ===== কনফিগারেশন (আপনার সিক্রেট কি গুলো আগের মতোই থাকবে) =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MY_USER = os.getenv("MY_USER")
MY_PASS = os.getenv("MY_PASS")

TARGET_URL = "http://185.2.83.39/ints/agent/SMSCDRReports"
LOGIN_URL = "http://185.2.83.39/ints/login"
FB_URL = "https://otp-manager-511ec-default-rtdb.asia-southeast1.firebasedatabase.app/bot"

sent_cache = set()
START_TIME = time.time()
last_heartbeat = time.time()

def get_now():
    return datetime.now().strftime('%I:%M:%S %p')

# ===== গ্রুপে রিপোর্ট বা এরর পাঠানোর ফাংশন =====
def report_to_group(msg, is_error=False):
    icon = "❌ ERROR" if is_error else "📢 STATUS"
    final_text = f"<b>[{icon}]</b>\n{msg}\n\n🕒 <code>{get_now()}</code>"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": final_text, "parse_mode": "HTML"}, timeout=10)
    except:
        pass

# ===== ডাটাবেজ থেকে ডেটা নিয়ে ক্যাশ মেমোরি তৈরি (রিস্টার্টের জন্য) =====
def initialize_from_db():
    print(f"[{get_now()}] 🔄 ডাটাবেজ চেক করা হচ্ছে...")
    latest_db_msg = None
    latest_time_val = ""
    try:
        res = requests.get(f"{FB_URL}/sms_logs.json", timeout=10)
        data = res.json()
        if data and isinstance(data, dict):
            for num, info in data.items():
                if isinstance(info, dict):
                    db_time = info.get("time", "")
                    db_msg = info.get("message", "")
                    db_num = info.get("number", num)
                    if db_time and db_msg:
                        uid = f"{db_time}|{db_num}|{db_msg}"
                        sent_cache.add(uid)
                        if db_time > latest_time_val:
                            latest_time_val = db_time
                            latest_db_msg = {"num": db_num, "sms": db_msg, "time": db_time}
        else:
            print(f"[{get_now()}] ডাটাবেজ খালি।")
    except Exception as e:
        report_to_group(f"⚠️ ডাটাবেজ সিঙ্ক এরর: {str(e)}", is_error=True)
    return latest_db_msg

# ===== ফায়ারবেজ আপডেট ফাংশন =====
def update_firebase(num, msg, date_str):
    try:
        url = f"{FB_URL}/sms_logs/{num}.json"
        payload = {"number": num, "message": msg, "time": date_str, "paid": False}
        res = requests.put(url, json=payload, timeout=7)
        if res.status_code != 200:
            report_to_group(f"❌ ডাটাবেজে তথ্য সেভ হয়নি! Status: {res.status_code}", is_error=True)
    except Exception as e:
        report_to_group(f"❌ ডাটাবেজ কানেকশন ফেলড: {str(e)}", is_error=True)

# ===== টেলিগ্রাম এসএমএস ফাংশন =====
def send_telegram_sms(date_str, num, msg, prefix="🆕"):
    masked = num[:4] + "XXX" + num[-4:] if len(num) > 8 else num
    otp_match = re.search(r'\b(\d{4,8}|\d{3}-\d{3}|\d{4}\s\d{4})\b', msg)
    otp = otp_match.group(1) if otp_match else ""

    text = f"{prefix} <b>NEW SMS RECEIVED</b>\n\n" \
           f"🕒 <b>Time:</b> <code>{date_str}</code>\n" \
           f"📱 <b>Number:</b> <code>{masked}</code>\n"
    if otp: text += f"🔑 <b>OTP Code:</b> <code>{otp}</code>\n"
    text += f"\n💬 <b>Message:</b>\n<code>{msg}</code>"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": [[{"text": "🤖 FTC BOT", "url": "https://t.me/FTC_SUPER_SMS_BOT"}]]}
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except:
        return False

# ===== মূল বট ফাংশন =====
async def start_bot():
    global last_heartbeat
    print(f"[{get_now()}] 🚀 FTC PRO (Full Monitor) চালু হচ্ছে...")
    
    # ১. ডাটাবেজ সিঙ্ক
    latest_db = initialize_from_db()
    report_to_group(f"🟢 <b>BOT RESTARTED</b>\nবট চালু হয়েছে এবং সিঙ্ক সম্পন্ন।")

    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(user_agent="Mozilla/5.0 Chrome/120.0.0.0")
        page = await context.new_page()

        async def login():
            print(f"[{get_now()}] 🔑 লগিন করা হচ্ছে...")
            try:
                await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
                await page.evaluate(f"""() => {{
                    let u = "{MY_USER}", p = "{MY_PASS}";
                    let inputs = document.querySelectorAll('input');
                    let uf, pf, af;
                    inputs.forEach(i => {{
                        let h = (i.placeholder || "").toLowerCase();
                        if (i.type === 'password') pf = i;
                        else if (h.includes('user') || i.type === 'text') {{ if(!uf && !h.includes('ans')) uf = i; }}
                        if (h.includes('ans') || i.name.includes('ans')) af = i;
                    }});
                    let m = document.body.innerText.match(/What is\\s+(\\d+)\\s*\\+\\s*(\\d+)/i);
                    if (uf && pf && af && m) {{
                        uf.value = u; pf.value = p; af.value = parseInt(m[1]) + parseInt(m[2]);
                        uf.dispatchEvent(new Event('input', {{bubbles:true}}));
                        pf.dispatchEvent(new Event('input', {{bubbles:true}}));
                        af.dispatchEvent(new Event('input', {{bubbles:true}}));
                        document.querySelectorAll('button, input[type="submit"]').forEach(b => {{
                            if((b.innerText || b.value || "").toLowerCase().includes('login')) b.click();
                        }});
                    }}
                }}""")
                await page.wait_for_timeout(5000)
            except Exception as e:
                report_to_group(f"❌ লগিন এরর: {str(e)}", is_error=True)

        await login()
        is_first_scan = True

        while True:
            # ৫ ঘণ্টা পর পর গিটহাব অ্যাকশন রিস্টার্ট হবে
            if time.time() - START_TIME > 18000: break
            
            try:
                if "login" in page.url or "Account Login" in await page.content():
                    report_to_group("⚠️ সেশন আউট! পুনরায় লগিন করা হচ্ছে...")
                    await login()
                    continue

                await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
                
                # টেবিল ডেটা আসার জন্য স্মার্ট ওয়েটার
                valid_rows = []
                for _ in range(15): # ১৫ সেকেন্ড অপেক্ষা করবে
                    rows = await page.query_selector_all("table tbody tr")
                    for row in rows:
                        cols = await row.query_selector_all("td")
                        if len(cols) >= 6:
                            d = (await cols[0].inner_text()).strip()
                            n = (await cols[2].inner_text()).strip()
                            s = (await cols[5].inner_text()).strip()
                            # টাইম, নাম্বার এবং মেসেজ থাকলে ভ্যালিড ধরবে
                            if d and len(re.sub(r'\D','',n)) >= 8 and "Loading" not in d:
                                valid_rows.append({"date": d, "num": n, "sms": s})
                    if valid_rows: break
                    await asyncio.sleep(1)
                
                if valid_rows:
                    latest_p_msg = valid_rows[0]
                    
                    # হার্টবিট: প্রতি ২০ মিনিট পর পর স্ট্যাটাস দিবে
                    if time.time() - last_heartbeat > 1200:
                        report_to_group(f"💓 <b>HEARTBEAT: BOT ACTIVE</b>\nপ্যানেলে সর্বশেষ মেসেজ: <code>{latest_p_msg['date']}</code>")
                        last_heartbeat = time.time()

                    # প্রথম স্ক্যান: টপ ৩টি মেসেজ গ্রুপে পাঠিয়ে কনফার্ম করবে
                    if is_first_scan:
                        report_to_group(f"📥 <b>INITIAL SYNC COMPLETE</b>\nপ্যানেলের টপ ৩টি মেসেজ পাঠানো হচ্ছে...")
                        for item in reversed(valid_rows[:3]):
                            send_telegram_sms(item['date'], item['num'], item['sms'], prefix="📌 [SYNC]")
                            uid = f"{item['date']}|{item['num']}|{item['sms']}"
                            sent_cache.add(uid)
                        is_first_scan = False

                    # সাধারণ স্ক্যানিং
                    found_new = False
                    for item in reversed(valid_rows):
                        uid = f"{item['date']}|{item['num']}|{item['sms']}"
                        if uid not in sent_cache:
                            if send_telegram_sms(item['date'], item['num'], item['sms']):
                                update_firebase(item['num'], item['sms'], item['date'])
                                sent_cache.add(uid)
                                found_new = True
                                if len(sent_cache) > 2000: sent_cache.pop()
                    
                    if found_new:
                        print(f"[{get_now()}] নতুন মেসেজ পাঠানো হয়েছে।")
                else:
                    print(f"[{get_now()}] ⏳ টেবিল খালি বা লোড হচ্ছে...")

            except Exception as e:
                if "Target page, context or browser has been closed" not in str(e):
                    report_to_group(f"⚠️ স্ক্যানিং লুপ এরর: {str(e)}", is_error=True)
                await page.reload()
            
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(start_bot())
