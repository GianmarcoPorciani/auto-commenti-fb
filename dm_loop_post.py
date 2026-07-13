#!/usr/bin/env python3
"""dm_loop_post.py — invia i DM-invito a TUTTI i commentatori, POST PER POST.

Parte dal post piu' recente e va all'indietro finche' ci sono post (nessun limite).
Per ogni post:
  1) python dm_targets.py --post <permalink> --tutti   -> scrive ../fb-invite/dm_targets.json
  2) node fb-dm.mjs --live                              -> invia i DM ai target di quel post

Dedup: fb-dm.mjs tiene dm_inviati.json per (post|persona), quindi mai 2 DM alla stessa
persona sullo STESSO post. Una persona che commenta su piu' post riceve 1 DM per post.

Uso:
  python dm_loop_post.py                 # tutti i post
  python dm_loop_post.py --max-post=5    # solo i 5 post piu' recenti
  python dm_loop_post.py --da-post=3     # salta i primi 2, riparte dal 3o (ripresa)

NB: rispetta la guardia oraria di fb-dm.mjs (attivo 08:00-00:00). Di notte gli invii
si fermano da soli. Reel: l'edge /posts potrebbe non elencare i video-reel.
"""
import os
import sys
import json
import time
import subprocess
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()
import requests
import reply_bot as rb

HERE = os.path.dirname(os.path.abspath(__file__))
FBDIR = os.path.abspath(os.path.join(HERE, "..", "fb-invite"))
STATE_FILE = os.path.join(FBDIR, ".fb-dm-state.json")


def _oggi_key():
    """Stesso formato di todayKey() in fb-dm.mjs: 'AAAA-M-G' (senza zero-padding)."""
    d = datetime.now()
    return f"{d.year}-{d.month}-{d.day}"


def conta_oggi():
    """Quanti DM sono gia' stati inviati OGGI (dallo stato condiviso di fb-dm.mjs)."""
    try:
        s = json.load(open(STATE_FILE, encoding="utf-8"))
        return s.get("count", 0) if s.get("date") == _oggi_key() else 0
    except Exception:
        return 0


def attendi_se_cap(cap):
    """Tetto giornaliero raggiunto: NON avanzare tra i post (li salteremmo a vuoto),
    aspetta che scatti il giorno nuovo (il contatore riparte da 0)."""
    while conta_oggi() >= cap:
        print(f"  [tetto {conta_oggi()}/{cap} raggiunto] pausa fino a domani...", flush=True)
        time.sleep(1800)  # ricontrolla ogni 30 min


def attendi_se_notte():
    """Il sender e' attivo 08:00-00:00. Di notte (00:00-08:00) NON avanziamo tra i post
    (li salteremmo a vuoto): aspettiamo le 08:00, ricontrollando ogni 10 minuti."""
    while datetime.now().hour < 8:
        print(f"  [notte {datetime.now():%H:%M}] pausa fino alle 08:00...", flush=True)
        time.sleep(600)


def lista_post(tok, page_id, max_post=None):
    """Tutti i post della Pagina (id + permalink_url), dal piu' recente, paginati."""
    posts = []
    data = rb.graph_get(f"{page_id}/posts", tok, {"fields": "id,permalink_url", "limit": 25})
    while True:
        for p in data.get("data", []):
            posts.append(p)
            if max_post and len(posts) >= max_post:
                return posts
        nxt = (data.get("paging", {}) or {}).get("next")
        if not nxt:
            break
        r = requests.get(nxt, timeout=30)
        if r.status_code != 200:
            break
        data = r.json()
    return posts


def main():
    tok = os.environ.get("FB_PAGE_TOKEN")
    if not tok:
        print("Manca FB_PAGE_TOKEN (.env)."); sys.exit(1)

    max_post = None
    da_post = 1
    cap = 50   # tetto giornaliero (deve combaciare con dailyCap di fb-dm; override con --cap=N)
    for a in sys.argv[1:]:
        if a.startswith("--max-post="):
            max_post = int(a.split("=")[1])
        elif a.startswith("--da-post="):
            da_post = max(1, int(a.split("=")[1]))
        elif a.startswith("--cap="):
            cap = max(1, int(a.split("=")[1]))

    page_id, _ = rb.get_page_info(tok)
    posts = lista_post(tok, page_id, max_post)
    print(f"=== {len(posts)} post trovati (dal piu' recente). Riparto dal #{da_post}. ===", flush=True)

    for i, p in enumerate(posts, 1):
        if i < da_post:
            continue
        attendi_se_cap(cap)   # tetto giornaliero raggiunto: aspetta il giorno nuovo
        attendi_se_notte()    # non avanzare di notte: aspetta le 08:00
        pid = p["id"]
        url = p.get("permalink_url") or f"https://www.facebook.com/{pid}"
        print(f"\n########## POST {i}/{len(posts)} — {pid} (oggi {conta_oggi()}/{cap}) ##########", flush=True)

        # 1) targeting di QUESTO post (tutti i commentatori sostenitori)
        rc = subprocess.run([sys.executable, "dm_targets.py", "--post", url, "--tutti"], cwd=HERE)
        if rc.returncode != 0:
            print(f"  [targeting fallito su {pid}] passo al prossimo post", flush=True)
            continue

        # 2) invio DM ai target di questo post (browser). Cap giornaliero + guardia oraria 08-00.
        rc = subprocess.run(f"node fb-dm.mjs --live --max-day={cap}", cwd=FBDIR, shell=True)
        if rc.returncode != 0:
            print(f"  [invio interrotto/errore su {pid}] passo al prossimo post", flush=True)

    print("\n=== FINE: tutti i post processati. ===", flush=True)


if __name__ == "__main__":
    main()
