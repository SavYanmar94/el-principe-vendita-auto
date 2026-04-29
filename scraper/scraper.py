"""
scraper.py - El Principe Garage

LOGICA:
1. Playwright (browser reale) → legge la pagina negozio, estrae tutti i dati delle auto
   Questo funzionava già prima - lo rimettiamo.
2. ScrapingBot → usato SOLO per scaricare l'immagine delle auto NUOVE
   (25 crediti per auto nuova, 0 crediti se l'auto esiste già)
3. Le auto già presenti con immagine non vengono mai ri-toccate
"""

import asyncio, json, os, time, urllib.request, base64, re
from datetime import datetime, timezone
from playwright.async_api import async_playwright

# ── CONFIG ───────────────────────────────────────────────────
ACCOUNTS = [
    ("SavYanmar94",  "Yl5MgMO0oULolQpbXSl4IOoz1"),
    ("Domi28",       "tEBA2RkLkIzi0I6mFn3yhE80D"),
    ("Genny23",      "TDQZbqp0jLJxcvRn8hAKCrDxx"),
    ("Nasoni23",     "aR50QSv23t5nLzS1GU2ofGCVA"),
    ("LamacMak92",   "18uZGwmI8rIPXBd0w3UyPQVPd"),
    ("Lidwef32",     "w6Ns04tg2aYcIEONc50h93UUF"),
]
SCRAPING_BOT_API = "http://api.scraping-bot.io/scrape/retail"
SHOP_URL  = "https://impresapiu.subito.it/shops/54233-el-principe-di-bavaro-biagio"
BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_FILE = os.path.join(BASE_DIR, "cars.json")
STATE_FILE= os.path.join(BASE_DIR, "scraper", "state.json")
IMG_DIR   = os.path.join(BASE_DIR, "img")
# ─────────────────────────────────────────────────────────────

def load_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except: return {"account_index": 0, "credits_used": {a[0]: 0 for a in ACCOUNTS}}

def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f: json.dump(state, f, indent=2)

def get_account(state):
    idx = state.get("account_index", 0)
    if state["credits_used"].get(ACCOUNTS[idx][0], 0) >= 450:
        idx = (idx + 1) % len(ACCOUNTS)
        state["account_index"] = idx
        print(f"  🔄 Rotazione account → {ACCOUNTS[idx][0]}")
    return ACCOUNTS[idx], state

def load_cars():
    try:
        with open(JSON_FILE) as f: return json.load(f)
    except: return {"success": True, "cars": []}

def extract_id(url):
    m = re.search(r'-(\d+)\.htm', url)
    return m.group(1) if m else ""

def format_price(v):
    try: return f"{int(float(v)):,}".replace(",", ".") + " €"
    except: return str(v)

def download_image_direct(url, car_id):
    """Scarica immagine direttamente con Referer subito.it (gratis, no crediti)."""
    if not url: return ""
    os.makedirs(IMG_DIR, exist_ok=True)
    filename = f"{car_id}.jpg"
    filepath = os.path.join(IMG_DIR, filename)
    if os.path.exists(filepath):
        print(f"    ♻️  {filename} già presente")
        return f"./img/{filename}"
    try:
        dl_url = url.replace("fullscreen-1x-auto","large-auto").replace("bigthumbs-auto","large-auto")
        req = urllib.request.Request(dl_url, headers={
            "User-Agent": "Mozilla/5.0 Chrome/120.0.0.0",
            "Referer":    "https://www.subito.it/",
            "Accept":     "image/webp,image/apng,image/*,*/*",
        })
        with urllib.request.urlopen(req, timeout=20) as r: data = r.read()
        with open(filepath, "wb") as f: f.write(data)
        print(f"    ✅ {filename} ({len(data)//1024}KB) — scaricata direttamente")
        return f"./img/{filename}"
    except Exception as e:
        print(f"    ⚠️  Download diretto fallito: {e} — provo ScrapingBot...")
        return ""

def download_image_scrapingbot(img_url, car_ad_url, car_id, state):
    """
    Usa ScrapingBot per ottenere l'immagine quando il download diretto fallisce.
    Costa 25 crediti. Usato solo come fallback.
    """
    account, state = get_account(state)
    print(f"    📡 ScrapingBot ({account[0]}, 25 crediti)...")
    auth = base64.b64encode(f"{account[0]}:{account[1]}".encode()).decode()
    payload = json.dumps({
        "url": car_ad_url,
        "options": {"useChrome": False, "premiumProxy": True, "proxyCountry": "IT"}
    }).encode()
    try:
        req = urllib.request.Request(SCRAPING_BOT_API, data=payload, method="POST",
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read().decode())
        state["credits_used"][account[0]] = state["credits_used"].get(account[0], 0) + 25
        save_state(state)
        ad = resp.get("data", resp)
        new_img_url = ad.get("image","")
        if not new_img_url and ad.get("images"): new_img_url = ad["images"][0]
        if new_img_url:
            # Riprova download diretto con il nuovo URL
            result = download_image_direct(new_img_url, car_id)
            if result: return result, new_img_url, state
    except Exception as e:
        print(f"    ❌ ScrapingBot fallito: {e}")
    return "", img_url, state


async def scrape_with_playwright():
    """
    Usa Playwright per leggere la pagina negozio e estrarre TUTTI i dati.
    Questo funzionava già prima — è il metodo principale.
    """
    print("→ Avvio Playwright (browser reale)...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--no-sandbox","--disable-setuid-sandbox",
            "--disable-dev-shm-usage","--disable-gpu"
        ])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            locale="it-IT", viewport={"width": 1280, "height": 900}
        )
        page = await context.new_page()
        print(f"→ Caricamento {SHOP_URL}...")
        await page.goto(SHOP_URL, wait_until="networkidle", timeout=40000)
        await asyncio.sleep(3)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

        count = await page.evaluate("() => document.querySelectorAll('a[href*=\"/auto/\"]').length")
        print(f"→ Link /auto/ trovati: {count}")

        cars_raw = await page.evaluate("""
            () => {
                const results = [], seen = new Set();
                document.querySelectorAll('a[href]').forEach(link => {
                    const url = link.href;
                    if (!url || seen.has(url)) return;
                    if (!/subito\\.it\\/auto\\/.+-\\d+\\.htm/.test(url)) return;
                    seen.add(url);
                    let card = link;
                    for (let i=0; i<8; i++) { if (!card.parentElement) break; card=card.parentElement; }
                    let title = link.title || link.getAttribute('title') || '';
                    if (!title) { const h=card.querySelector('h2,h3,[class*="title"]'); title=h?h.innerText.trim():''; }
                    if (!title) title = link.innerText.trim().split('\\n')[0].trim();
                    let price='';
                    const pe=card.querySelector('[class*="price"],[class*="Price"]');
                    if (pe) price=pe.innerText.trim().replace(/\\s+/g,' ');
                    if (!price) { const m=card.innerText.match(/(\\d{1,3}(?:\\.\\d{3})*)\\s*€/); if(m) price=m[1]+' €'; }
                    let imageUrl='';
                    card.querySelectorAll('img').forEach(img => {
                        if (!imageUrl) {
                            const src=img.src||img.dataset.src||'';
                            if (src && (src.includes('sbito.it')||src.includes('subito'))) {
                                imageUrl=src.replace('bigthumbs-auto','large-auto').replace('thumbs-auto','large-auto');
                            }
                        }
                    });
                    let publishDate='';
                    const m2=card.innerText.match(/(Oggi|Ieri|\\d{1,2}\\s+[A-Za-z]{3,}),?\\s+\\d{2}:\\d{2}/i);
                    if (m2) publishDate=m2[0];
                    else { const m3=card.innerText.match(/(Oggi|Ieri|\\d{1,2}\\s+[A-Za-z]{3,})/i); if(m3) publishDate=m3[0]; }
                    let km='',year='',fuel='',transmission='';
                    card.querySelectorAll('li').forEach(li => {
                        const t=li.innerText.trim();
                        if (/\\d{2,3}\\.\\d{3}\\s*km/i.test(t)||/^\\d+\\s*km$/i.test(t)) km=t;
                        else if (/^20\\d{2}$/.test(t)) year=t;
                        else if (/diesel|benzina|gpl|hybrid|elettr/i.test(t)) fuel=t;
                        else if (/manuale|automatico|semi/i.test(t)) transmission=t;
                    });
                    const idM=url.match(/-(\d+)\\.htm$/);
                    const id=idM?idM[1]:'';
                    if (title && price && id) results.push({id,url,title,price,imageUrl,publishDate,km,year,fuel,transmission});
                });
                return results;
            }
        """)
        await browser.close()
    print(f"→ Auto estratte da Playwright: {len(cars_raw)}")
    return cars_raw


def scrape():
    print(f"\n{'='*60}")
    print(f"AVVIO: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'='*60}\n")

    state    = load_state()
    existing = load_cars()
    existing_map = {c["url"]: c for c in existing.get("cars", [])}

    # ── STEP 1: Playwright legge tutte le auto dalla pagina ──
    cars_raw = asyncio.run(scrape_with_playwright())

    if not cars_raw:
        print("❌ Playwright ha trovato 0 auto. Mantengo cars.json invariato.")
        return 0

    # ── STEP 2: Per ogni auto, gestisci immagine ──
    final_cars = []
    for car in cars_raw:
        url    = car["url"]
        car_id = car["id"]
        ex     = existing_map.get(url, {})

        # Se l'auto esisteva già e ha già l'immagine → tienila, non sprecare crediti
        if ex.get("localImage") and os.path.exists(
            os.path.join(BASE_DIR, ex["localImage"].lstrip("./"))
        ):
            # Aggiorna solo prezzo e publishDate (potrebbero essere cambiati)
            ex["price"]       = car["price"] or ex.get("price","")
            ex["publishDate"] = car["publishDate"] or ex.get("publishDate","")
            final_cars.append(ex)
            print(f"  ♻️  {car['title']} — immagine già OK")
            continue

        # Auto nuova o senza immagine → prova prima download diretto (gratis)
        print(f"\n  🚗 {car['title']} ({car_id})")
        local_img = download_image_direct(car.get("imageUrl",""), car_id)

        # Se il download diretto fallisce → usa ScrapingBot (25 crediti)
        if not local_img:
            local_img, new_img_url, state = download_image_scrapingbot(
                car.get("imageUrl",""), url, car_id, state
            )
            if new_img_url: car["imageUrl"] = new_img_url

        car["localImage"] = local_img
        final_cars.append(car)

    # ── STEP 3: Riepilogo crediti ──
    print(f"\n{'='*60}")
    print(f"✅ COMPLETATO: {len(final_cars)} auto nel sito")
    print(f"💳 Crediti ScrapingBot:")
    for user, _ in ACCOUNTS:
        used = state["credits_used"].get(user, 0)
        bar  = "█"*(used//50) + "░"*((500-used)//50)
        print(f"   {user:15s} {bar} {used:3d}/500 (rimasti: {500-used})")
    print(f"{'='*60}\n")

    output = {
        "success": True,
        "updated": datetime.now(timezone.utc).isoformat(),
        "count":   len(final_cars),
        "cars":    final_cars,
    }
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    save_state(state)
    return len(final_cars)


if __name__ == "__main__":
    scrape()
