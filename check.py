import asyncio
import hashlib
import os

import requests
from playwright.async_api import async_playwright

# ---- settings you might need to change later ----
NTFY_TOPIC = os.environ["NTFY_TOPIC"]      # set as a GitHub secret, not hardcoded
RESORT = "Skegness"
TARGET_MONTH_YEAR = "August 2026"          # update this if you're still checking in September
# ---------------------------------------------------

URL = "https://passes.butlins.com/DayVisit/Index/#/home"


async def take_screenshot():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(URL, wait_until="networkidle", timeout=60000)

        # pick the resort from the dropdown
        await page.wait_for_selector("select", timeout=30000)
        await page.select_option("select", label=RESORT)
        await page.wait_for_timeout(2000)

        # try to get the calendar to the right month (best effort - up to 6 clicks)
        for _ in range(6):
            try:
                header = await page.locator(
                    "text=/^[A-Za-z]+ 20[0-9]{2}$/"
                ).first.inner_text(timeout=5000)
            except Exception:
                break
            if header.strip() == TARGET_MONTH_YEAR:
                break
            try:
                await page.get_by_role("button", name="Next").first.click(timeout=3000)
            except Exception:
                break
            await page.wait_for_timeout(1000)

        screenshot_path = "calendar.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        await browser.close()
        return screenshot_path


def send_notification(image_path, message):
    with open(image_path, "rb") as f:
        data = f.read()
    requests.put(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=data,
        headers={
            "Title": "Butlins Skegness calendar changed",
            "Filename": "calendar.png",
            "Message": message,
        },
        timeout=30,
    )


def file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    screenshot_path = asyncio.run(take_screenshot())
    new_hash = file_hash(screenshot_path)

    old_hash = None
    if os.path.exists("last_hash.txt"):
        with open("last_hash.txt") as f:
            old_hash = f.read().strip()

    if new_hash != old_hash:
        send_notification(
            screenshot_path,
            "The Skegness day visit calendar looks different - check for open dates!",
        )
        with open("last_hash.txt", "w") as f:
            f.write(new_hash)
        print("Change detected - notification sent.")
    else:
        print("No change since last check.")


if __name__ == "__main__":
    main()
