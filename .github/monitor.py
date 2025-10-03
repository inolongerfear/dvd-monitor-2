import os
import json
import smtplib
import requests
from bs4 import BeautifulSoup
from email.message import EmailMessage
from urllib.parse import urljoin

# --- CONFIG via environment variables ---
URL = os.getenv("MONITOR_URL")
SELECTOR = os.getenv("CSS_SELECTOR") or 'a[href*="/products/"]'
STATE_FILE = "products.json"

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMS_TARGET = os.getenv("SMS_TARGET")

MAX_NOTIFICATIONS_PER_RUN = int(os.getenv("MAX_NOTIFICATIONS_PER_RUN") or 5)

# --- FUNCTIONS ---
def fetch_products():
    resp = requests.get(URL, timeout=20, headers={"User-Agent": "product-monitor-bot/1.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    nodes = soup.select(SELECTOR)
    products = []
    for n in nodes:
        a = n if n.name == "a" else n.find("a", href=True)
        if a is None:
            title = (n.get_text() or "").strip()
            if title:
                products.append({"title": title, "url": ""})
            continue
        title = (a.get_text() or "").strip()
        href = a.get("href") or ""
        if href and not href.startswith("http"):
            href = urljoin(URL, href)
        products.append({"title": title or href, "url": href})
    # remove duplicates
    seen = set()
    uniq = []
    for p in products:
        key = (p.get("title","").strip(), p.get("url","").strip())
        if key not in seen and key != ("",""):
            seen.add(key)
            uniq.append({"title": key[0], "url": key[1]})
    return uniq

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_state(data):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def send_sms_via_email(subject, body):
    if not (SMTP_USER and SMTP_PASS and SMS_TARGET):
        print("SMTP_USER, SMTP_PASS or SMS_TARGET not set — skipping notification.")
        return
    msg = EmailMessage()
    msg["From"] = SMTP_USER
    msg["To"] = SMS_TARGET
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)
    print("Sent SMS via", SMS_TARGET)

# --- MAIN ---
def main():
    if not URL:
        raise SystemExit("MONITOR_URL must be set")

    old = load_state()
    old_keys = {(p.get("title",""), p.get("url","")) for p in old}
    print("Loaded", len(old_keys), "old products")

    new = fetch_products()
    new_keys = {(p.get("title",""), p.get("url","")) for p in new}
    added_keys = new_keys - old_keys

    added = [p for p in new if (p.get("title",""), p.get("url","")) in added_keys]

    if added:
        print(f"Found {len(added)} new product(s).")
        notifications = 0
        for p in added:
            if notifications >= MAX_NOTIFICATIONS_PER_RUN:
                print("Reached max notifications for this run.")
                break
            title = p.get("title", "New product")
            url = p.get("url", "")
            message = f"{title}\n{url}" if url else title
            if len(message) > 300:
                message = message[:290] + "…"
            send_sms_via_email("New product", message)
            print("Notified:", title)
            notifications += 1
    else:
        print("No new products.")

    save_state(new)

if __name__ == "__main__":
    main()
