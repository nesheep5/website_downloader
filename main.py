import argparse
import asyncio
import os
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse

import requests
from playwright.async_api import async_playwright
from tqdm.asyncio import tqdm

OUTPUT_DIR = "output"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


# ログを記録する関数
def log_message(message):
    with open("scraping_log.txt", "a", encoding="utf-8") as log_file:
        log_file.write(f"{datetime.now()}: {message}\n")


# ファイル名を変換する関数
def convert_filename(url: str) -> str:
    file_name = urlparse(url).path.rstrip("/").split("/")[-1] + ".html"
    file_name = urllib.parse.unquote(file_name)
    return file_name


# HTMLを保存する関数
async def save_html(playwright, url, semaphore):
    async with semaphore:  # セマフォを使用して同時実行数を制限
        # 出力ディレクトリを作成
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.rstrip("/").split("/")[:-1]
        output_dir = os.path.join(OUTPUT_DIR, parsed_url.netloc, *path_parts)
        os.makedirs(output_dir, exist_ok=True)

        # HTMLをダウンロード
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()
        try:
            await page.goto(url, timeout=30000)
            await page.wait_for_selector("body", timeout=10000)
            content = await page.content()
            file_name = convert_filename(url)
            file_path = os.path.join(output_dir, file_name)

            with open(file_path, "w", encoding="utf-8") as file:
                file.write(content)

            return True
        except Exception as e:
            log_message(f"[ERROR] Failed to download. url:{url}, \n error: {e}")
            return False
        finally:
            await browser.close()


# sitemap.xmlを解析して対象のURLリストを取得する関数
def parse_sitemap(sitemap_url):
    try:
        response = requests.get(sitemap_url, timeout=10)
        response.raise_for_status()

        # sitemap.xmlをパース
        root = ET.fromstring(response.content)
        urls = [
            elem.text
            for elem in root.findall(
                ".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
            )
        ]

        return urls
    except requests.exceptions.RequestException as e:
        log_message(f"ERROR: Failed to fetch sitemap: {e}")
        raise e


async def main(sitemap_url):
    # sitemap.xmlを解析してURLリストを取得
    urls = parse_sitemap(sitemap_url)
    if not urls:
        print("No URLs found in the sitemap.")
        return

    print(f"Found {len(urls)} URLs in the sitemap.")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Playwrightを使用したスクレイピング
    semaphore = asyncio.Semaphore(5)
    async with async_playwright() as playwright:
        tasks = [save_html(playwright, url, semaphore) for url in urls]
        await tqdm.gather(
            *tasks,
            desc="Downloading HTML",
            bar_format="{desc:<5.5}{percentage:3.0f}%|{bar:100}{r_bar}",
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape and download HTML from a sitemap.xml using Playwright."
    )
    parser.add_argument("sitemap_url", type=str, help="The URL of the sitemap.xml")
    args = parser.parse_args()
    asyncio.run(main(args.sitemap_url))

