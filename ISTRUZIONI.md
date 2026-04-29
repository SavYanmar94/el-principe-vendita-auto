# Istruzioni complete El Principe Garage

## FILE DA CARICARE SU GITHUB

Vai sul tuo repository GitHub (elprincipe-auto) e carica questi file:

### File normali (trascinali direttamente):
- index.html
- cars.json
- netlify.toml
- update-cars.yml  ← IMPORTANTE: vedi sotto come caricarlo
- scraper/scraper.py
- scraper/requirements.txt

---

## COME CARICARE IL WORKFLOW (update-cars.yml)

Il file workflow va in una cartella speciale chiamata `.github/workflows/`.
GitHub ti permette di crearla direttamente dal browser:

1. Nel tuo repository, clicca **"Add file"** → **"Create new file"**
2. Nel campo nome file scrivi esattamente:
   `.github/workflows/update-cars.yml`
   (GitHub creerà le cartelle automaticamente mentre digiti)
3. Copia e incolla il contenuto del file `update-cars.yml`
4. Clicca **"Commit changes"**

---

## PERMESSI GITHUB ACTIONS (obbligatorio)

Dopo aver caricato il workflow:

1. Nel repository → **Settings** (tab in alto)
2. Nel menu a sinistra → **Actions** → **General**
3. Scorrere fino a **"Workflow permissions"**
4. Seleziona **"Read and write permissions"**
5. Clicca **Save**

Poi vai su **Actions** → **"Aggiorna annunci auto"** → **"Run workflow"** per testare.

---

## COME FUNZIONA IL SITO

Il sito legge il file `cars.json` che viene aggiornato ogni notte alle 7:00
dallo scraper Python (GitHub Actions). Le immagini vengono servite tramite
un proxy CDN gratuito (weserv.nl) che bypassa il blocco di Subito.

---

## NETLIFY

- Publish directory: `.`
- Build command: (vuoto)
- Il deploy avviene automaticamente ad ogni push su GitHub

## USERNAME GITHUB

ATTENZIONE: Nel file index.html il logo e il background vengono caricati da:
  https://raw.githubusercontent.com/TONOMIO/elprincipe-auto/main/logo.png

Se il tuo username GitHub NON è "TONOMIO", sostituiscilo nel file index.html
cercando "TONOMIO" e mettendo il tuo username corretto.
