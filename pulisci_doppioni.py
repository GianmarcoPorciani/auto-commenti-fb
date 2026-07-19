#!/usr/bin/env python3
"""pulisci_doppioni.py — trova i commenti PRINCIPALI su cui la Pagina ha risposto PIU' di una volta
e cancella le risposte in eccesso, tenendo la piu' VECCHIA (una sola risposta per commento).

Uso:
  python pulisci_doppioni.py --posts 10           # DRY: conta soltanto, non cancella
  python pulisci_doppioni.py --posts 10 --elimina # cancella davvero le extra
  python pulisci_doppioni.py --anno 2026 --elimina

NB: cancella SOLO le risposte della Pagina in eccesso (mai i commenti degli utenti).
"""
import os
import sys
import time

from dotenv import load_dotenv
load_dotenv()
import requests
import reply_bot as rb

GRAPH = rb.GRAPH


def _all_top_comments(tok, oid):
    """Tutti i commenti di primo livello con le risposte della Pagina (id, from, created_time)."""
    out = []
    fields = "id,created_time,comments.limit(100){id,from{id},created_time,message}"
    try:
        data = rb.graph_get(f"{oid}/comments", tok, {"fields": fields, "limit": 50, "filter": "toplevel"})
    except Exception as e:
        print(f"  [commenti non letti: {str(e)[:50]}]")
        return out
    while True:
        out.extend(data.get("data", []))
        nxt = (data.get("paging", {}) or {}).get("next")
        if not nxt:
            break
        r = requests.get(nxt, timeout=30)
        if r.status_code != 200:
            break
        data = r.json()
    return out


def main():
    posts_n = 10
    anno = None
    elimina = "--elimina" in sys.argv
    for a in sys.argv[1:]:
        if a.startswith("--posts="):
            posts_n = int(a.split("=")[1])
        elif a.startswith("--anno="):
            anno = a.split("=")[1]

    tok = os.environ.get("FB_PAGE_TOKEN")
    if not tok:
        print("Manca FB_PAGE_TOKEN (.env)."); sys.exit(1)
    page_id, _ = rb.get_page_info(tok)

    # lista post
    posts = []
    data = rb.graph_get(f"{page_id}/posts", tok, {"fields": "id,permalink_url,created_time,message", "limit": 25})
    while True:
        for p in data.get("data", []):
            if anno:
                if p.get("created_time", "")[:4] == anno:
                    posts.append(p)
            else:
                posts.append(p)
                if len(posts) >= posts_n:
                    break
        if not anno and len(posts) >= posts_n:
            break
        if anno and data.get("data") and data["data"][-1].get("created_time", "")[:4] < anno:
            break
        nxt = (data.get("paging", {}) or {}).get("next")
        if not nxt:
            break
        r = requests.get(nxt, timeout=30)
        if r.status_code != 200:
            break
        data = r.json()

    modo = "ELIMINA" if elimina else "DRY (solo conteggio)"
    print(f"=== {len(posts)} post da scandire | modalita': {modo} ===")

    tot_commenti_doppi = 0
    tot_da_eliminare = 0
    tot_eliminate = 0
    tot_errori = 0
    rate_limited = False

    for i, p in enumerate(posts, 1):
        if rate_limited:
            break
        oid = p["id"]
        ptxt = (p.get("message") or "(media)")[:35].replace("\n", " ")
        comments = _all_top_comments(tok, oid)
        doppi_post = 0
        for c in comments:
            reps = (c.get("comments", {}) or {}).get("data", [])
            pag = [r for r in reps if (r.get("from") or {}).get("id") == page_id]
            if len(pag) <= 1:
                continue
            # tieni la piu' VECCHIA, elimina le altre
            pag.sort(key=lambda r: r.get("created_time", ""))
            extra = pag[1:]
            doppi_post += 1
            tot_commenti_doppi += 1
            tot_da_eliminare += len(extra)
            if elimina:
                for r in extra:
                    rid = r["id"]
                    try:
                        resp = requests.delete(f"{GRAPH}/{rid}", params={"access_token": tok}, timeout=30)
                        if resp.status_code == 200:
                            tot_eliminate += 1
                        else:
                            tot_errori += 1
                            txt = resp.text[:120]
                            # Limite chiamate app di Facebook: inutile insistere, FERMATI (rientra in ~1h).
                            if "request limit reached" in txt or '"code":4' in txt or '(#4)' in txt:
                                print(f"    STOP: limite chiamate app di Facebook (#4). Riprova tra ~1 ora.")
                                rate_limited = True
                                break
                            print(f"    [errore delete {rid}] {resp.status_code}: {txt[:80]}")
                    except Exception as e:
                        tot_errori += 1
                        print(f"    [errore delete {rid}] {str(e)[:60]}")
                    time.sleep(1.5)
            if rate_limited:
                break
        print(f"  [{i}/{len(posts)}] {ptxt!r}: {len(comments)} commenti, {doppi_post} con risposte doppie")

    print(f"\n=== RISULTATO ===")
    print(f"Commenti con risposta doppia: {tot_commenti_doppi}")
    print(f"Risposte in eccesso da eliminare: {tot_da_eliminare}")
    if elimina:
        print(f"Eliminate: {tot_eliminate} | errori: {tot_errori}")
    else:
        print("(DRY: niente eliminato. Rilancia con --elimina per cancellare.)")


if __name__ == "__main__":
    main()
