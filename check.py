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


def send_notification(image_path, title, message):
    with open(image_path, "rb") as f:
        data = f.read()
    requests.put(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=data,
        headers={
            "Title": title,
            "Filename": "calendar.png",
            "Message": message,
        },
        timeout=30,
    )


def file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


async def dismiss_cookie_banner(page):
    candidates = [
        "#onetrust-accept-btn-handler",
        "text=Accept All Cookies",
        "text=Accept All",
        "text=Accept all",
        "text=I Accept",
        "text=Accept",
    ]
    for sel in candidates:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=2000):
                await btn.click(timeout=2000)
                await page.wait_for_timeout(1000)
                return
        except Exception:
            continue


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        try:
            await page.goto(URL, wait_until="load", timeout=45000)
        except Exception:
            pass

        await page.wait_for_timeout(3000)
        await dismiss_cookie_banner(page)
        await page.wait_for_timeout(1000)

        found_select = False
        debug_info = ""
        try:
            await page.wait_for_selector("select", timeout=20000)
            await page.wait_for_timeout(3000)  # give options time to load in
            selects = page.locator("select")
            count = await selects.count()
            debug_lines = [f"Found {count} dropdown(s) on the page."]
            target_index = None
            for i in range(count):
                option_texts = await selects.nth(i).locator("option").all_inner_texts()
                cleaned = [t.strip() for t in option_texts if t.strip()]
                debug_lines.append(f"Dropdown {i}: {cleaned[:8]}")
                if target_index is None and any(RESORT in t for t in option_texts):
                    target_index = i
            debug_info = " | ".join(debug_lines)
            if target_index is not None:
                await selects.nth(target_index).select_option(label=RESORT)
                await page.wait_for_timeout(3000)
                found_select = True
            else:
                debug_info += " | No dropdown contained 'Skegness' as an option."
        except Exception as e:
            debug_info = f"Error while looking for dropdown: {e}"

        if found_select:
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
        return screenshot_path, found_select, debug_info


def main():
    screenshot_path, found_select, debug_info = asyncio.run(run())
    new_hash = file_hash(screenshot_path)

    old_hash = None
    if os.path.exists("last_hash.txt"):
        with open("last_hash.txt") as f:
            old_hash = f.read().strip()

    if not found_select:
        send_notification(
            screenshot_path,
            "Butlins checker: couldn't select resort",
            f"{debug_info} - send this to Claude to fix.",
        )
        print(f"Could not select resort. Debug info: {debug_info}")
        return

    if new_hash != old_hash:
        send_notification(
            screenshot_path,
            "Butlins Skegness calendar changed",
            "The Skegness day visit calendar looks different - check for open dates!",
        )
        with open("last_hash.txt", "w") as f:
            f.write(new_hash)
        print("Change detected - notification sent.")
    else:
        print("No change since last check.")


if __name__ == "__main__":
    main()
