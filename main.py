import os
import asyncio
import re
import requests
import time
from datetime import datetime
from playwright.async_api import async_playwright

# ===== GitHub Secrets থেকে কনফিগারেশন নেওয়া =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MY_USER = os.getenv("MY_USER")
MY_PASS = os.getenv("MY_PASS")

TARGET_URL = "http://185.2.83.39/ints/agent/SMSCDRReports"
LOGIN_URL = "http://185.2.83.39/login"

sent_cache = set()
START_TIME = time.time()

def get_now():
    return datetime.now().strftime('%H:%M:%S')

# ===== টেলিগ্রামে মেসেজ পাঠানোর ফাংশন =====
def send_telegram(num, msg):
    masked = num[:4] + "XXX" + num[-4:] if len(num) > 8 else num
    otp_match = re.search(r'\b(\d{4,8}|\d{3}-\d{3}|\d{4}\s\d{4})\b', msg)
    otp = otp_match.group(1) if otp_match else ""

    text = f"🆕 <b>NEW SMS RECEIVED</b>\n\n" \
           f"📱 <b>Number:</b> <code>{masked}</code>\n"
    if otp:
        text += f"🔑 <b>OTP Code:</b> <code>{otp}</code>\n"
    text += f"\n💬 <b>Message:</b>\n<code>{msg}</code>"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": [[{"text": "🤖 FTC SUPER SMS BOT", "url": "https://t.me/FTC_SUPER_SMS_BOT"}]]}
    }
    try:
        requests.post(url, json=payload, timeout=10)
        return True
    except Exception as e: 
        print(f"[{get_now()}] ❌ টেলিগ্রাম এরর: {e}")
        return False

# ===== মূল বট ফাংশন =====
async def start_bot():
    print(f"[{get_now()}] 🚀 FTC PRO GitHub Actions-এ চালু হচ্ছে...")
    async with async_playwright() as p:
        print(f"[{get_now()}] 🌐 ব্রাউজার লঞ্চ করা হচ্ছে...")
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print(f"[{get_now()}] ✅ ব্রাউজার রেডি!")

        async def login():
            print(f"[{get_now()}] 🔑 লগিন করার চেষ্টা করছি...")
            try:
                await page.goto(LOGIN_URL, timeout=60000)
                # পেজ পুরোপুরি লোড হওয়ার জন্য অপেক্ষা
                await page.wait_for_load_state("domcontentloaded") 
                print(f"[{get_now()}] 📄 পেজ লোড হয়েছে, ক্রেডেনশিয়াল দেওয়া হচ্ছে...")
                
                # JS কোডের মতো স্মার্ট সিলেক্টর দিয়ে ফিল্ড পূরণ
                await page.locator('input[type="text"]').first.fill(MY_USER)
                await page.locator('input[type="password"]').first.fill(MY_PASS)
                
                # ক্যাপচা সলভ করা
                content = await page.content()
                match = re.search(r'What is\s+(\d+)\s*\+\s*(\d+)', content, re.IGNORECASE)
                if match:
                    ans_val = str(int(match[1]) + int(match[2]))
                    # Answer ফিল্ডটি নাম বা প্লেসহোল্ডার দিয়ে খোঁজা
                    await page.locator('input[name="ans"], input[placeholder*="ans" i], input[placeholder*="answer" i]').first.fill(ans_val)
                    print(f"[{get_now()}] ✅ ক্যাপচা সলভড: {ans_val}")
                
                # লগিন বাটন ক্লিক
                await page.locator('button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("login")').first.click()
                
                await page.wait_for_timeout(5000)
                print(f"[{get_now()}] 🎉 লগিন সফল!")
            except Exception as e:
                print(f"[{get_now()}] ❌ লগিন এরর: {str(e)}")

        # প্রথমবার লগিন ফাংশন কল
        await login()

        while True:
            # ৫ ঘণ্টা (১৮০০০ সেকেন্ড) হয়ে গেলে বট বন্ধ হবে যাতে গিটহাব নতুন শিডিউল শুরু করতে পারে
            if time.time() - START_TIME > 18000:
                print(f"[{get_now()}] 🔄 সেশন রিস্টার্টের জন্য বন্ধ হচ্ছে...")
                break

            try:
                # যদি সেশন আউট হয়ে যায় বা ভুল করে লগিন পেজে চলে যায়
                if "login" in page.url: 
                    await login()
                
                # মূল পেজে যাওয়া
                await page.goto(TARGET_URL, timeout=60000)
                await page.wait_for_selector("table tbody tr", timeout=20000)
                
                rows = await page.query_selector_all("table tbody tr")
                found_new = False
                
                for row in rows:
                    cols = await row.query_selector_all("td")
                    if len(cols) >= 6:
                        num = (await cols[2].inner_text()).strip()
                        sms = (await cols[5].inner_text()).strip()
                        uid = f"{num}|{sms}"
                        
                        if uid not in sent_cache:
                            if send_telegram(num, sms):
                                sent_cache.add(uid)
                                found_new = True
                                # ক্যাশ লিমিট (মেমোরি বাঁচাতে)
                                if len(sent_cache) > 500: 
                                    sent_cache.pop()
                                    
                if found_new:
                    print(f"[{get_now()}] 📥 নতুন মেসেজ টেলিগ্রামে পাঠানো হয়েছে!")
                else:
                    print(f"[{get_now()}] ⏳ স্ক্যানিং সম্পন্ন। নতুন কোনো ডেটা নেই।")
                    
            except Exception as e:
                print(f"[{get_now()}] ⚠️ লুপ এরর (পুনরায় চেষ্টা চলছে): {str(e)}")
                try:
                    await page.reload()
                except:
                    pass
            
            # ৫ সেকেন্ড পর পর চেক করবে (আপনি চাইলে সময় কমাতে বা বাড়াতে পারেন)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(start_bot())
