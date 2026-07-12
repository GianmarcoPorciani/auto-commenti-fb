#!/usr/bin/env python3
"""
dm_targets.py — genera dm_targets.json: i commenti SOSTENITORI entro N ore dalla pubblicazione
di un post/reel, letti via API (veloce, paginato) e classificati con Claude.

Il browser (fb-invite/fb-dm.mjs) legge questo file e invia i DM SOLO ai comment_id elencati,
senza dover scrollare/classificare a mano nel browser.

Uso:
  python dm_targets.py --post "<URL_o_ID_del_post_o_reel>"
  python dm_targets.py --post 1347672464235801 --ore 24
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv()

import requests
import anthropic
import reply_bot as rb

OUT_DEFAULT = os.path.join("..", "fb-invite", "dm_targets.json")


def obj_id_from_arg(arg):
    """Ricava l'ID oggetto (reel/video/post) da un URL o da un id nudo."""
    arg = arg.strip()
    for pat in (r"/reel/(\d+)", r"/videos/(\d+)", r"/posts/(\d+)", r"story_fbid=(\d+)", r"/(\d{6,})"):
        m = re.search(pat, arg)
        if m:
            return m.group(1)
    if re.fullmatch(r"\d+", arg):
        return arg
    return arg


# Prompt LEGGERO: solo categoria, niente risposta (i DM usano un template fisso).
CLASSIFY_SYS = (
    "Classifichi i commenti sotto un post di un creator politico (area sovranista/identitaria). "
    "Per OGNI commento numerato dai SOLO la categoria: sostenitore | critico | neutro | volgare | spam. "
    "Un commento di SOSTEGNO che usa parole forti verso avversari/sistema (es. 'traditori', 'vergogna', "
    "'schifo') è 'sostenitore', NON volgare. Rispondi SOLO col JSON richiesto."
)
CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {"risultati": {"type": "array", "items": {"type": "object", "properties": {
        "n": {"type": "integer"},
        "categoria": {"type": "string", "enum": ["sostenitore", "critico", "neutro", "volgare", "spam"]},
    }, "required": ["n", "categoria"], "additionalProperties": False}}},
    "required": ["risultati"], "additionalProperties": False,
}


def classifica_solo_categoria(client, items, batch=18):
    """items = lista di (num, message). Ritorna dict {num: categoria}. Solo categoria, niente risposta."""
    out = {}
    for i in range(0, len(items), batch):
        chunk = items[i:i + batch]
        righe = "\n".join(f'[{k + 1}] "{(msg or "")[:200]}"' for k, (num, msg) in enumerate(chunk))
        try:
            resp = client.messages.create(
                model=rb.MODEL, max_tokens=len(chunk) * 12 + 100, system=CLASSIFY_SYS,
                output_config={"format": {"type": "json_schema", "schema": CLASSIFY_SCHEMA}},
                messages=[{"role": "user", "content": "Commenti:\n" + righe}])
            testo = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            for r in json.loads(testo).get("risultati", []):
                n = r.get("n")
                if isinstance(n, int) and 1 <= n <= len(chunk):
                    out[chunk[n - 1][0]] = r.get("categoria")
            print(f"  classificati {min(i + batch, len(items))}/{len(items)}")
        except Exception as e:
            print(f"  [errore classificazione batch] {e}")
    return out


def fetch_all_comments(tok, oid):
    out = []
    data = rb.graph_get(f"{oid}/comments", tok,
                        {"fields": "id,message,created_time,from{id,name}", "limit": 100, "filter": "stream"})
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
    ap = argparse.ArgumentParser(description="Genera dm_targets.json (sostenitori entro 24h)")
    ap.add_argument("--post", required=True, help="URL o ID del post/reel")
    ap.add_argument("--ore", type=float, default=24.0, help="finestra ore dalla pubblicazione (default 24)")
    ap.add_argument("--out", default=OUT_DEFAULT, help="file di output (default ../fb-invite/dm_targets.json)")
    args = ap.parse_args()

    tok = os.environ.get("FB_PAGE_TOKEN")
    if not tok:
        print("Manca FB_PAGE_TOKEN (.env)."); sys.exit(1)

    page_id, _ = rb.get_page_info(tok)   # per escludere i commenti della Pagina stessa
    oid = obj_id_from_arg(args.post)
    print(f"Oggetto: {oid}")

    # created_time del post/reel → finestra 24h
    try:
        meta = rb.graph_get(oid, tok, {"fields": "created_time"})
        pub = datetime.strptime(meta["created_time"], "%Y-%m-%dT%H:%M:%S%z")
    except Exception as e:
        print(f"Impossibile leggere created_time del post: {e}"); sys.exit(1)
    limite = pub + timedelta(hours=args.ore)
    print(f"Pubblicato: {pub.isoformat()}  →  finestra fino a: {limite.isoformat()}")

    comments = fetch_all_comments(tok, oid)
    print(f"{len(comments)} commenti totali dall'API")

    entro = []
    n_pagina = 0
    for c in comments:
        msg = (c.get("message") or "").strip()
        if not msg:
            continue
        frm = c.get("from") or {}
        if frm.get("id") == page_id:   # commento/risposta della Pagina stessa: mai
            n_pagina += 1
            continue
        try:
            t = datetime.strptime(c["created_time"], "%Y-%m-%dT%H:%M:%S%z")
        except Exception:
            continue
        if pub <= t <= limite:
            entro.append(c)
    print(f"{len(entro)} entro {args.ore}h dalla pubblicazione (esclusi {n_pagina} commenti della Pagina)")

    if not entro:
        _scrivi(args.out, args.post, [])
        print("Nessun commento nella finestra. Fine.")
        return

    # Classificazione CONDIVISA: riusa la cache scritta dal bot commenti, pre-filtra i banali,
    # e manda a Claude (SOLO-categoria) solo i commenti non ancora classificati e non banali.
    classificati = rb._carica_dict(rb.CLASSIFICATI_FILE)
    cat_di = {}          # num -> categoria
    da_claude = []       # (num, msg) ancora da classificare
    n_cache = n_banali = 0
    for c in entro:
        num = c["id"].split("_")[-1]
        msg = (c.get("message") or "").strip()
        if num in classificati:
            cat_di[num] = classificati[num]; n_cache += 1
        elif rb.e_banale_positivo(msg):
            cat_di[num] = "sostenitore"; classificati[num] = "sostenitore"; n_banali += 1
        else:
            da_claude.append((num, msg))
    print(f"  da cache condivisa: {n_cache} | banali (0 Claude): {n_banali} | a Claude: {len(da_claude)}")

    if da_claude:
        client = anthropic.Anthropic()
        for num, cat in classifica_solo_categoria(client, da_claude).items():
            cat_di[num] = cat
            classificati[num] = cat

    rb._salva_dict(rb.CLASSIFICATI_FILE, classificati)   # aggiorna la cache condivisa

    targets = []
    for c in entro:
        num = c["id"].split("_")[-1]
        if cat_di.get(num) == "sostenitore":
            targets.append({"comment_id": num, "full_id": c["id"],
                            "message": (c.get("message") or "")[:120]})
    print(f"{len(targets)} sostenitori → target")

    _scrivi(args.out, args.post, targets)
    print(f"Scritto {os.path.abspath(args.out)}")
    for t in targets[:5]:
        print(f"   • {t['comment_id']}  ::  {t['message'][:50]!r}")


def _scrivi(out, post, targets):
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "post": post,
            "ids": [t["comment_id"] for t in targets],
            "targets": targets,
        }, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
