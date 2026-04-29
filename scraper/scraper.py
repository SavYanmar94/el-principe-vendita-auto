"""
scraper.py - El Principe Garage
Usa l'API interna di Subito.it (la stessa che usa il browser)
per ottenere gli annunci del negozio come JSON puro.
Nessun browser headless necessario — più veloce e affidabile.
"""

import json, os, urllib.request, urllib.parse
from datetime import datetime, timezone

# ID negozio Subito (visibile nell'URL: shops/54233-...)
SHOP_ID     = "54233"
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_JSON = os.path.join(BASE_DIR, "cars.json")
IMG_DIR     = os.path.join(BASE_DIR, "img")

# Endpoint API interno di Subito — restituisce JSON con tutti gli annunci del negozio
API_URL = f"https://hades.subito.it/v1/search/classifieds?shp={SHOP_ID}&lim=50&start=0&t=s"

HEADERS = {
    "User-Agent":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept":      "application/json, text/plain, */*",
    "Referer":     "https://impresapiu.subito.it/",
    "Origin":      "https://impresapiu.subito.it",
    "x-client-id": "subito-web",
}


def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def download_image(url: str, car_id: str) -> str:
    if not url:
        return ""
    os.makedirs(IMG_DIR, exist_ok=True)
    filename = f"{car_id}.jpg"
    filepath = os.path.join(IMG_DIR, filename)
    # Salta se già scaricata nelle ultime 24h
    if os.path.exists(filepath):
        age = datetime.now().timestamp() - os.path.getmtime(filepath)
        if age < 86400:
            print(f"    ♻️  {filename} già presente, skip")
            return f"./img/{filename}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer":    "https://www.subito.it/",
            "Accept":     "image/webp,image/apng,image/*,*/*;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        with open(filepath, "wb") as f:
            f.write(data)
        print(f"    ✅ {filename} ({len(data)//1024}KB)")
        return f"./img/{filename}"
    except Exception as e:
        print(f"    ❌ {car_id}: {e}")
        return ""


def parse_date(item):
    """Formatta la data in italiano: Oggi, Ieri, 23 Apr..."""
    date_str = item.get("date", "")
    if not date_str:
        return ""
    try:
        from datetime import date
        dt = datetime.fromisoformat(date_str.replace("Z",""))
        today = date.today()
        d = dt.date()
        if d == today:
            return "Oggi"
        elif (today - d).days == 1:
            return "Ieri"
        else:
            mesi = ["","Gen","Feb","Mar","Apr","Mag","Giu","Lug","Ago","Set","Ott","Nov","Dic"]
            return f"{d.day} {mesi[d.month]}"
    except Exception:
        return date_str[:10]


def extract_feature(features, key):
    """Estrae un valore dalle feature Subito (km, anno, carburante, cambio)"""
    if not features:
        return ""
    for f in features:
        if f.get("uri","").endswith(f"/{key}") or f.get("label","").lower() == key.lower():
            vals = f.get("values", [])
            if vals:
                return vals[0].get("key", vals[0].get("label",""))
    return ""


def scrape():
    print(f"\n{'='*60}")
    print(f"AVVIO: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"API:   {API_URL}")
    print(f"{'='*60}\n")

    # --- Tenta prima con l'API hades ---
    cars_data = []
    try:
        print("→ Chiamata API Subito...")
        data = fetch_json(API_URL)
        ads = data.get("ads", [])
        print(f"→ Annunci ricevuti dall'API: {len(ads)}")
        cars_data = ads
    except Exception as e:
        print(f"⚠️  API hades non disponibile: {e}")
        print("→ Provo endpoint alternativo...")

    # --- Fallback: API di ricerca per venditore ---
    if not cars_data:
        try:
            alt_url = f"https://hades.subito.it/v1/search/classifieds?shp={SHOP_ID}&lim=50&start=0"
            data = fetch_json(alt_url)
            cars_data = data.get("ads", [])
            print(f"→ Annunci (alt): {len(cars_data)}")
        except Exception as e:
            print(f"⚠️  Fallback 1 fallito: {e}")

    # --- Fallback 2: API pubblica di ricerca ---
    if not cars_data:
        try:
            alt2 = f"https://api.subito.it/v1/shop/ads/?shp={SHOP_ID}&lim=50&start=0"
            data = fetch_json(alt2)
            cars_data = data.get("ads", [])
            print(f"→ Annunci (alt2): {len(cars_data)}")
        except Exception as e:
            print(f"⚠️  Fallback 2 fallito: {e}")

    if not cars_data:
        print("❌ Nessun annuncio trovato da nessun endpoint API.")
        print("   Mantengo il cars.json esistente invariato.")
        return 0

    # --- Parsing annunci ---
    cars = []
    for item in cars_data:
        try:
            ad_id   = str(item.get("urn","").split(":")[-1] or item.get("id",""))
            title   = item.get("subject","") or item.get("title","")
            url     = item.get("urls",{}).get("default","") or item.get("url","")
            price_raw = (item.get("features",[]) or [])
            
            # Prezzo
            price = ""
            prices = item.get("prices", {})
            if prices:
                v = prices.get("EUR",{}).get("value") or prices.get("value")
                if v:
                    price = f"{int(v):,}".replace(",",".") + " €"
            if not price:
                for f in (item.get("features") or []):
                    if "price" in f.get("uri","").lower():
                        vals = f.get("values",[])
                        if vals: price = vals[0].get("label","")

            # Immagine (prende la prima disponibile, formato large)
            image_url = ""
            images = item.get("images",[])
            if images:
                img = images[0]
                # Preferisce large, poi medium, poi quello che c'è
                image_url = (img.get("large") or img.get("medium") or
                             img.get("url","")).strip()
                # Normalizza al formato che ci ha dato l'utente
                if image_url and "rule=" not in image_url:
                    image_url += "?rule=large-auto"
                elif image_url:
                    image_url = image_url.replace("bigthumbs-auto","large-auto").replace("thumbs-auto","large-auto")

            # Data
            publish_date = parse_date(item)

            # Feature tecniche auto
            features = item.get("features",[])
            km           = extract_feature(features, "km")
            year         = extract_feature(features, "anno")
            fuel         = extract_feature(features, "carburante")
            transmission = extract_feature(features, "cambio")

            # Fallback feature con labels italiani
            if not km or not year:
                for f in features:
                    label = f.get("label","").lower()
                    vals  = f.get("values",[])
                    val   = vals[0].get("label","") if vals else ""
                    if "chilometri" in label or "km" in label: km = val
                    elif "anno" in label: year = val
                    elif "carburante" in label: fuel = val
                    elif "cambio" in label: transmission = val

            if not ad_id or not title:
                continue

            print(f"  [{ad_id}] {title} — {price}")
            print(f"    img: {image_url[:70] if image_url else '(nessuna)'}")

            local_image = download_image(image_url, ad_id)

            cars.append({
                "id":           ad_id,
                "url":          url,
                "title":        title,
                "price":        price,
                "imageUrl":     image_url,
                "localImage":   local_image,
                "publishDate":  publish_date,
                "km":           km,
                "year":         year,
                "fuel":         fuel,
                "transmission": transmission,
            })

        except Exception as e:
            print(f"  ⚠️  Errore parsing annuncio: {e}")
            continue

    output = {
        "success": True,
        "updated": datetime.now(timezone.utc).isoformat(),
        "count":   len(cars),
        "cars":    cars,
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ COMPLETATO: {len(cars)} auto salvate in cars.json")
    return len(cars)


if __name__ == "__main__":
    scrape()
