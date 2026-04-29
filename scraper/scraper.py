"""
scraper.py - El Principe Garage
Apre Subito.it con Playwright (browser reale), estrae i dati delle auto,
scarica le immagini localmente nella cartella /img/ e salva cars.json.
Le immagini vengono servite da GitHub Pages direttamente — nessun blocco CDN.
"""

import asyncio
import json
import os
import urllib.request
from datetime import datetime, timezone
from playwright.async_api import async_playwright

SHOP_URL    = "https://impresapiu.subito.it/shops/54233-el-principe-di-bavaro-biagio"
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_JSON = os.path.join(BASE_DIR, "cars.json")
IMG_DIR     = os.path.join(BASE_DIR, "img")


def download_image(url: str, car_id: str) -> str:
    """
    Scarica l'immagine da Subito usando gli stessi header del browser.
    Il Referer 'https://www.subito.it/' è la chiave: senza di esso il CDN blocca.
    Salva in /img/<id>.jpg e restituisce il path relativo './img/<id>.jpg'.
    """
    if not url:
        return ""

    os.makedirs(IMG_DIR, exist_ok=True)
    filename = f"{car_id}.jpg"
    filepath = os.path.join(IMG_DIR, filename)

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer":  "https://www.subito.it/",
                "Accept":   "image/webp,image/apng,image/*,*/*;q=0.8",
                "Origin":   "https://www.subito.it",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()

        with open(filepath, "wb") as f:
            f.write(data)

        print(f"    ✅ {filename}  ({len(data)//1024} KB)")
        return f"./img/{filename}"

    except Exception as e:
        print(f"    ❌ Immagine fallita ({car_id}): {e}")
        return ""


async def scrape():
    print(f"\n{'='*50}")
    print(f"Avvio scraping: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"URL: {SHOP_URL}")
    print(f"{'='*50}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="it-IT",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        print("→ Caricamento pagina Subito...")
        await page.goto(SHOP_URL, wait_until="domcontentloaded", timeout=30000)

        print("→ Attendo annunci JS...")
        try:
            await page.wait_for_selector("a[href*='/auto/']", timeout=15000)
        except Exception:
            pass

        # Scroll per lazy loading immagini
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

        cars_raw = await page.evaluate("""
            () => {
                const results = [];
                const seen = new Set();

                document.querySelectorAll('a[href]').forEach(link => {
                    const url = link.href;
                    if (!url || seen.has(url)) return;
                    if (!/subito\\.it\\/auto\\/.+-\\d+\\.htm/.test(url)) return;
                    seen.add(url);

                    // Risali al contenitore della card
                    let card = link;
                    for (let i = 0; i < 8; i++) {
                        if (!card.parentElement) break;
                        card = card.parentElement;
                    }

                    // Titolo
                    let title = link.title || link.getAttribute('title') || '';
                    if (!title) {
                        const h = card.querySelector('h2,h3,[class*="title"],[class*="Title"]');
                        title = h ? h.innerText.trim() : '';
                    }
                    if (!title) title = link.innerText.trim().split('\\n')[0].trim();

                    // Prezzo
                    let price = '';
                    const priceEl = card.querySelector('[class*="price"],[class*="Price"]');
                    if (priceEl) price = priceEl.innerText.trim().replace(/\\s+/g,' ');
                    if (!price) {
                        const m = card.innerText.match(/(\\d{1,3}(?:\\.\\d{3})*)\\s*€/);
                        if (m) price = m[1] + ' €';
                    }

                    // Immagine — prende il src completo da sbito.it (CDN di Subito)
                    let imageUrl = '';
                    card.querySelectorAll('img').forEach(img => {
                        if (!imageUrl) {
                            const src = img.src || img.dataset.src || img.getAttribute('data-original') || '';
                            if (src.includes('sbito.it') || src.includes('subito')) {
                                imageUrl = src
                                    .replace('bigthumbs-auto', 'large-auto')
                                    .replace('thumbs-auto', 'large-auto');
                            }
                        }
                    });

                    // Data pubblicazione
                    let publishDate = '';
                    const m2 = card.innerText.match(/(Oggi|Ieri|\\d{1,2}\\s+[A-Za-z]{3,}),?\\s+\\d{2}:\\d{2}/i);
                    if (m2) publishDate = m2[0];
                    else {
                        const m3 = card.innerText.match(/(Oggi|Ieri|\\d{1,2}\\s+[A-Za-z]{3,})/i);
                        if (m3) publishDate = m3[0];
                    }

                    // Specifiche tecniche
                    let km='', year='', fuel='', transmission='';
                    card.querySelectorAll('li').forEach(li => {
                        const t = li.innerText.trim();
                        if (/\\d{2,3}\\.\\d{3}\\s*km/i.test(t) || /^\\d+\\s*km$/i.test(t)) km = t;
                        else if (/^20\\d{2}$/.test(t)) year = t;
                        else if (/diesel|benzina|gpl|hybrid|elettr/i.test(t)) fuel = t;
                        else if (/manuale|automatico|semi/i.test(t)) transmission = t;
                    });

                    const idM = url.match(/-(\d+)\\.htm$/);
                    const id  = idM ? idM[1] : '';

                    if (title && price && id) {
                        results.push({ id, url, title, price, imageUrl, publishDate, km, year, fuel, transmission });
                    }
                });

                return results;
            }
        """)

        await browser.close()

    print(f"\n→ Trovate {len(cars_raw)} auto. Scarico immagini...\n")

    cars = []
    for car in cars_raw:
        print(f"  [{car['id']}] {car['title']}")
        print(f"    URL img: {car.get('imageUrl','(nessuna)')[:80]}")
        car["localImage"] = download_image(car.get("imageUrl", ""), car["id"])
        cars.append(car)

    output = {
        "success": True,
        "updated": datetime.now(timezone.utc).isoformat(),
        "count":   len(cars),
        "cars":    cars,
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Completato: {len(cars)} auto salvate in cars.json")
    print(f"   Immagini in: {IMG_DIR}\n")
    return len(cars)


if __name__ == "__main__":
    asyncio.run(scrape())
