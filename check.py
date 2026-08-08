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


def sanitize_header(text, max_length=800):
    cleaned = text.replace("\n", " ").replace("\r", " ")
    cleaned = " ".join(cleaned.split())
    return cleaned[:max_length]


def send_notification(image_path, title, message):
    with open(image_path, "rb") as f:
        data = f.read()
    requests.put(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=data,
        headers={
            "Title": sanitize_header(title),
            "Filename": "calendar.png",
            "Message": sanitize_header(message),
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


async def open_resort_dropdown(page):
    strategies = [
        ("combobox role", lambda: page.get_by_role("combobox").first),
        ("role=combobox css", lambda: page.locator("[role='combobox']").first),
        ("last 'Please select resort' match", lambda: page.get_by_text("Please select resort", exact=False).last),
        ("first 'Please select resort' match", lambda: page.get_by_text("Please select resort", exact=False).first),
        ("div containing 'Please select resort'", lambda: page.locator("div:has-text('Please select resort')").last),
    ]
    for label, strat in strategies:
        try:
            el = strat()
            if await el.count() == 0:
                continue
            await el.scroll_into_view_if_needed(timeout=3000)
            await el.click(timeout=6000, force=True)
            await page.wait_for_timeout(1200)
            option_count = await page.get_by_role("option").count()
            skeg_count = await page.get_by_text("Skegness", exact=True).count()
            if option_count > 0 or skeg_count > 1:
                return True, f"Opened dropdown using: {label}."
        except Exception:
            continue
    return False, "Tried several ways to click the resort box, none opened it."


async def select_resort(page):
    opened, open_debug = await open_resort_dropdown(page)
    if not opened:
        return False, open_debug

    await page.wait_for_timeout(1000)

    try:
        option = page.get_by_role("option", name=RESORT, exact=True)
        if await option.count() > 0:
            await option.first.click(timeout=5000, force=True)
            await page.wait_for_timeout(2500)
            return True, f"{open_debug} Selected Skegness via role=option."
    except Exception:
        pass

    try:
        matches = page.get_by_text(RESORT, exact=True)
        count = await matches.count()
        if count > 0:
            await matches.last.click(timeout=5000, force=True)
            await page.wait_for_timeout(2500)
            return True, f"{open_debug} Selected Skegness via text match (option {count} of {count})."
    except Exception:
        pass

    return False, f"{open_debug} Opened the dropdown but could not find/click the Skegness option inside it."


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        try:
            await page.goto(URL, wait_until="load", timeout=60000)
        except Exception:
            pass

        await page.wait_for_timeout(5000)
        await dismiss_cookie_banner(page)
        await page.wait_for_timeout(2000)

        found_select, debug_info = await select_resort(page)

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
