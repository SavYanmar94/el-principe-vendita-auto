"""
scraper.py - El Principe Garage
Strategia crediti ottimizzata:
1. Ogni giorno controlla SE ci sono nuove auto (1 chiamata = 25 crediti)
2. Solo se ci sono auto nuove → scarica i dettagli (25 crediti per auto nuova)
3. Ruota automaticamente tra 6 account ScrapingBot (3.000 crediti/mese totali)
4. Le auto già presenti con immagine non vengono mai ri-scaricate
"""

import json, os, time, urllib.request, base64, re
from datetime import datetime, timezone

# ── ACCOUNT SCRAPINGBOT (rotazione automatica) ───────────────
ACCOUNTS = [
    ("SavYanmar94",  "Yl5MgMO0oULolQpbXSl4IOoz1"),
    ("Domi28",       "tEBA2RkLkIzi0I6mFn3yhE80D"),
    ("Genny23",      "TDQZbqp0jLJxcvRn8hAKCrDxx"),
    ("Nasoni23",     "aR50QSv23t5nLzS1GU2ofGCVA"),
    ("LamacMak92",   "18uZGwmI8rIPXBd0w3UyPQVPd"),
    ("Lidwef32",     "w6Ns04tg2aYcIEONc50h93UUF"),
]

API_URL  = "http://api.scraping-bot.io/scrape/retail"
SHOP_URL = "https://impresapiu.subito.it/shops/54233-el-principe-di-bavaro-biagio"

BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_FILE     = os.path.join(BASE_DIR, "cars.json")
STATE_FILE    = os.path.join(BASE_DIR, "scraper", "state.json")  # traccia account e crediti
IMG_DIR       = os.path.join(BASE_DIR, "img")
# ─────────────────────────────────────────────────────────────


# ── Gestione stato account ────────────────────────────────────

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"account_index": 0, "credits_used": {a[0]: 0 for a in ACCOUNTS}}

def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def get_account(state):
    """Restituisce (user, pass) dell'account corrente, ruotando se necessario."""
    idx = state.get("account_index", 0)
    # Se l'account corrente ha quasi esaurito i crediti (>450), passa al prossimo
    current_user = ACCOUNTS[idx][0]
    if state["credits_used"].get(current_user, 0) >= 450:
        idx = (idx + 1) % len(ACCOUNTS)
        state["account_index"] = idx
        print(f"  🔄 Rotazione account → {ACCOUNTS[idx][0]}")
    return ACCOUNTS[idx], state

# ── Chiamata API ──────────────────────────────────────────────

def scraping_bot_call(url, account, use_chrome=False):
    user, pwd = account
    auth = base64.b64encode(f"{user}:{pwd}".encode()).decode()
    payload = json.dumps({
        "url": url,
        "options": {
            "useChrome":              use_chrome,
            "premiumProxy":           True,
            "proxyCountry":           "IT",
            "waitForNetworkRequests": use_chrome,
        }
    }).encode()
    req = urllib.request.Request(
        API_URL, data=payload,
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

# ── Utilità ───────────────────────────────────────────────────

def extract_id(url):
    m = re.search(r'-(\d+)\.htm', url)
    return m.group(1) if m else ""

def load_cars():
    try:
        with open(JSON_FILE) as f:
            return json.load(f)
    except Exception:
        return {"success": True, "cars": []}

def download_image(url, car_id):
    """Scarica immagine con Referer subito.it — bypassa il blocco CDN."""
    if not url:
        return ""
    os.makedirs(IMG_DIR, exist_ok=True)
    filename = f"{car_id}.jpg"
    filepath = os.path.join(IMG_DIR, filename)
    if os.path.exists(filepath):
        print(f"    ♻️  {filename} già presente")
        return f"./img/{filename}"
    try:
        dl_url = url.replace("fullscreen-1x-auto", "large-auto").replace("bigthumbs-auto", "large-auto")
        req = urllib.request.Request(dl_url, headers={
            "User-Agent": "Mozilla/5.0 Chrome/120.0.0.0",
            "Referer":    "https://www.subito.it/",
            "Accept":     "image/webp,image/apng,image/*,*/*",
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        with open(filepath, "wb") as f:
            f.write(data)
        print(f"    ✅ {filename} ({len(data)//1024}KB)")
        return f"./img/{filename}"
    except Exception as e:
        print(f"    ❌ Download fallito ({car_id}): {e}")
        return ""

def format_price(value):
    try:
        return f"{int(float(value)):,}".replace(",", ".") + " €"
    except Exception:
        return str(value)

def format_date(date_str):
    if not date_str:
        return ""
    try:
        from datetime import date
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        today = datetime.now(timezone.utc).date()
        d = dt.date()
        diff = (today - d).days
        if diff == 0: return "Oggi"
        if diff == 1: return "Ieri"
        mesi = ["","Gen","Feb","Mar","Apr","Mag","Giu","Lug","Ago","Set","Ott","Nov","Dic"]
        return f"{d.day} {mesi[d.month]}"
    except Exception:
        return date_str[:10]

# ── Estrai URL annunci dalla risposta della pagina negozio ────

def extract_ad_urls(shop_response):
    d = shop_response.get("data", shop_response)
    urls = []

    # Caso A: lista "products" con siteURL
    if isinstance(d.get("products"), list):
        for p in d["products"]:
            u = p.get("siteURL") or p.get("url","")
            if u and re.search(r'subito\.it/auto/.+-\d+\.htm', u):
                urls.append(u)

    # Caso B: lista "links"
    if not urls and isinstance(d.get("links"), list):
        for lnk in d["links"]:
            href = lnk.get("href","") if isinstance(lnk, dict) else str(lnk)
            if re.search(r'subito\.it/auto/.+-\d+\.htm', href):
                urls.append(href)

    # Caso C: parsing HTML grezzo
    if not urls:
        html = d.get("siteHtml","") or d.get("html","") or ""
        if html:
            found = re.findall(r'https://www\.subito\.it/auto/[^\s"\'<>]+\.htm', html)
            urls = list(dict.fromkeys(found))

    # Dedup
    return list(dict.fromkeys(urls))


# ── MAIN ──────────────────────────────────────────────────────

def scrape():
    print(f"\n{'='*60}")
    print(f"AVVIO: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'='*60}\n")

    state    = load_state()
    existing = load_cars()
    existing_map = {c["url"]: c for c in existing.get("cars", [])}
    existing_urls = set(existing_map.keys())

    # ── STEP 1: Pagina negozio → lista URL annunci (25 crediti) ──
    account, state = get_account(state)
    print(f"→ [STEP 1] Account: {account[0]} | Pagina negozio (25 crediti)...")
    try:
        shop_resp = scraping_bot_call(SHOP_URL, account, use_chrome=True)
        state["credits_used"][account[0]] = state["credits_used"].get(account[0], 0) + 25
        save_state(state)
    except Exception as e:
        print(f"❌ Errore pagina negozio: {e}")
        print("   Mantengo cars.json invariato.")
        return 0

    live_urls = extract_ad_urls(shop_resp)
    print(f"   URL annunci trovati: {len(live_urls)}")

    if not live_urls:
        # Fallback: usa gli URL esistenti per almeno aggiornare le immagini mancanti
        live_urls = list(existing_urls)
        print(f"   ⚠️  Nessun URL dalla pagina, uso {len(live_urls)} URL esistenti")

    # ── Confronto: quali sono nuove? quali sono sparite? ──
    live_set    = set(live_urls)
    new_urls    = live_set - existing_urls          # auto nuove → da scaricare
    removed_urls = existing_urls - live_set         # auto vendute → da rimuovere
    same_urls   = live_set & existing_urls          # invariate → mantieni

    print(f"\n   📊 Stato annunci:")
    print(f"      Nuove:    {len(new_urls)}")
    print(f"      Invariate:{len(same_urls)}")
    print(f"      Rimosse:  {len(removed_urls)}")

    if removed_urls:
        print(f"\n   🗑️  Auto vendute/rimosse:")
        for u in removed_urls:
            print(f"      - {existing_map[u].get('title','?')}")

    # ── STEP 2: Scarica dati solo per le auto NUOVE ──
    new_cars = []
    if new_urls:
        print(f"\n→ [STEP 2] Scarico {len(new_urls)} auto nuove...")
        for url in new_urls:
            car_id = extract_id(url)
            if not car_id:
                continue

            # Ruota account se necessario
            account, state = get_account(state)
            print(f"\n  Auto: {url}")
            print(f"  Account: {account[0]} ({state['credits_used'].get(account[0],0)} crediti usati)")

            try:
                resp = scraping_bot_call(url, account, use_chrome=False)
                state["credits_used"][account[0]] = state["credits_used"].get(account[0], 0) + 25
                save_state(state)
                time.sleep(1)
            except Exception as e:
                print(f"  ❌ Errore: {e}")
                continue

            ad = resp.get("data", resp)

            title   = ad.get("title","") or ad.get("subject","")
            price_v = ad.get("price", 0)
            price   = format_price(price_v) if price_v else ""
            img_url = ad.get("image","")
            if not img_url and ad.get("images"):
                img_url = ad["images"][0]

            local_img = download_image(img_url, car_id)

            # Dati tecnici dalla description se non disponibili direttamente
            km = fuel = transmission = year = ""
            desc = (ad.get("description","") or "").lower()
            m = re.search(r'(\d{1,3}(?:[.,]\d{3})*)\s*km', desc)
            if m: km = m.group(0).strip()
            m = re.search(r'\b(20\d{2})\b', desc)
            if m: year = m.group(1)
            for f_word in ["diesel","benzina","gpl","ibrido","elettrico","hybrid"]:
                if f_word in desc: fuel = f_word.capitalize(); break
            for t_word in ["automatico","manuale"]:
                if t_word in desc: transmission = t_word.capitalize(); break

            print(f"  ✔ {title} | {price} | km:{km} | {year} | {fuel} | {transmission}")

            new_cars.append({
                "id": car_id, "url": url, "title": title,
                "price": price, "imageUrl": img_url, "localImage": local_img,
                "publishDate": "Oggi", "km": km, "year": year,
                "fuel": fuel, "transmission": transmission,
            })
    else:
        print("\n→ Nessuna auto nuova. Zero crediti aggiuntivi spesi. ✨")

    # ── STEP 3: Controlla immagini mancanti nelle auto esistenti ──
    # (succede se la run precedente ha fallito il download)
    fixed = 0
    for url in same_urls:
        car = existing_map[url]
        local = car.get("localImage","")
        if not local or not os.path.exists(os.path.join(BASE_DIR, local.lstrip("./"))):
            car_id = extract_id(url)
            print(f"\n→ Immagine mancante per {car.get('title','?')}, scarico...")
            car["localImage"] = download_image(car.get("imageUrl",""), car_id)
            fixed += 1
    if fixed:
        print(f"   ✅ Recuperate {fixed} immagini mancanti")

    # ── Assembla lista finale (nuove + invariate, senza le rimosse) ──
    final_cars = new_cars + [existing_map[u] for u in same_urls]

    # Ordina per publishDate (Oggi prima, poi le altre)
    def sort_key(c):
        pd = c.get("publishDate","")
        if pd == "Oggi": return "0"
        if pd == "Ieri": return "1"
        return pd
    final_cars.sort(key=sort_key)

    output = {
        "success": True,
        "updated": datetime.now(timezone.utc).isoformat(),
        "count":   len(final_cars),
        "cars":    final_cars,
    }
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Riepilogo crediti
    print(f"\n{'='*60}")
    print(f"✅ COMPLETATO: {len(final_cars)} auto nel sito")
    print(f"💳 Crediti usati per account:")
    for user, pwd in ACCOUNTS:
        used = state["credits_used"].get(user, 0)
        remaining = 500 - used
        bar = "█" * (used // 50) + "░" * ((500 - used) // 50)
        print(f"   {user:15s} {bar} {used:3d}/500 (rimasti: {remaining})")
    print(f"{'='*60}\n")
    return len(final_cars)


if __name__ == "__main__":
    scrape()
