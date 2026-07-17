#!/usr/bin/env python3
"""report_offensivi.py — REPORT dei commenti OFFENSIVI (categoria 'volgare') diretti alla Pagina.

Per ogni commento offensivo: testo, data, POST di riferimento e LINK DIRETTO al commento
(cliccando si apre il commento su Facebook e si vede CHI l'ha scritto — l'autore NON e'
esposto via API per gli utenti normali).

- Ambito: tutti i post del 2026 (filtro created_time).
- Categoria: 'volgare' (offensivi/insulti). Classificazione RIUSATA da classificati.json
  (cache del bot commenti); i pochi non ancora classificati vengono classificati al volo
  (SOLO in memoria, NON riscrive la cache per non dare fastidio ai giri in corso).
- Output: report_offensivi.html + report_offensivi.csv sul Desktop.

Uso:  python report_offensivi.py            # tutti i post 2026
      python report_offensivi.py --anno 2026 --categorie volgare,critico
"""
import os
import sys
import csv
import json
import html
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv()

import requests
import anthropic
import reply_bot as rb
import dm_targets as dt

CACHE = "classificati.json"
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")


def _num(cid):
    return str(cid).split("_")[-1]


def lista_post_anno(tok, page_id, anno):
    """Post della Pagina con created_time nell'anno dato (reverse-chrono, si ferma prima)."""
    posts = []
    data = rb.graph_get(f"{page_id}/posts", tok, {"fields": "id,permalink_url,created_time", "limit": 25})
    while True:
        dd = data.get("data", [])
        for p in dd:
            ct = p.get("created_time", "")
            if ct[:4] == anno:
                posts.append(p)
        if dd and dd[-1].get("created_time", "")[:4] < anno:
            break  # superato l'anno, i successivi sono piu' vecchi
        nxt = (data.get("paging", {}) or {}).get("next")
        if not nxt:
            break
        r = requests.get(nxt, timeout=30)
        if r.status_code != 200:
            break
        data = r.json()
    return posts


def link_commento(permalink, cid):
    num = _num(cid)
    sep = "&" if "?" in permalink else "?"
    return f"{permalink}{sep}comment_id={num}"


def main():
    anno = "2026"
    categorie = {"volgare"}
    classifica = False   # DEFAULT: cache-only, ZERO Claude. --classifica per classificare i non-cache (a pagamento).
    for a in sys.argv[1:]:
        if a.startswith("--anno="):
            anno = a.split("=")[1]
        elif a.startswith("--categorie="):
            categorie = {c.strip() for c in a.split("=")[1].split(",") if c.strip()}
        elif a == "--classifica":
            classifica = True

    tok = os.environ.get("FB_PAGE_TOKEN")
    if not tok:
        print("Manca FB_PAGE_TOKEN (.env)."); sys.exit(1)
    client = anthropic.Anthropic() if classifica else None  # niente Claude di default

    page_id, _ = rb.get_page_info(tok)
    cache = {}
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        pass

    posts = lista_post_anno(tok, page_id, anno)
    print(f"{len(posts)} post del {anno} da scandire. Categorie: {sorted(categorie)}")

    offensivi = []       # {data, testo, post_url, link, categoria}
    n_classificati_nuovi = 0
    tot_commenti = 0

    for i, p in enumerate(posts, 1):
        permalink = p.get("permalink_url") or f"https://www.facebook.com/{p['id']}"
        candidati = [p["id"], dt.obj_id_from_arg(permalink)]
        try:
            comments, _oid = dt.fetch_all_comments(tok, candidati)
        except Exception as e:
            print(f"  [{i}/{len(posts)}] commenti non letti ({str(e)[:50]}) — salto")
            continue
        tot_commenti += len(comments)

        # commenti non della Pagina, con testo
        da_classificare = []   # (indice, num, message)
        righe_post = []        # (comment, num)
        for c in comments:
            msg = (c.get("message") or "").strip()
            if not msg:
                continue
            frm = c.get("from") or {}
            if frm.get("id") == page_id:   # commenti della Pagina stessa: mai
                continue
            num = _num(c["id"])
            righe_post.append((c, num))
            if num not in cache:
                da_classificare.append((num, msg))

        # classifica al volo i non-cache SOLO se --classifica (a pagamento); altrimenti cache-only
        if classifica and da_classificare:
            items = [(num, msg) for (num, msg) in da_classificare]
            nuovi = dt.classifica_solo_categoria(client, items)
            for num, cat in nuovi.items():
                cache[num] = cat
                n_classificati_nuovi += 1

        for c, num in righe_post:
            cat = cache.get(num)
            if cat in categorie:
                offensivi.append({
                    "data": (c.get("created_time") or "")[:19].replace("T", " "),
                    "testo": (c.get("message") or "").strip(),
                    "categoria": cat,
                    "post_url": permalink,
                    "link": link_commento(permalink, c["id"]),
                })
        print(f"  [{i}/{len(posts)}] {len(comments)} commenti — offensivi finora: {len(offensivi)}")

    # ordina per data desc
    offensivi.sort(key=lambda x: x["data"], reverse=True)

    # ---- CSV ----
    csv_path = os.path.join(DESKTOP, "report_offensivi_porciani.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Data", "Categoria", "Commento offensivo", "Post", "Link al commento (mostra autore)"])
        for o in offensivi:
            w.writerow([o["data"], o["categoria"], o["testo"], o["post_url"], o["link"]])

    # ---- HTML ----
    righe_html = []
    for n, o in enumerate(offensivi, 1):
        righe_html.append(
            f"<tr><td class='n'>{n}</td>"
            f"<td class='data'>{html.escape(o['data'])}</td>"
            f"<td class='testo'>{html.escape(o['testo'])}</td>"
            f"<td><a href='{html.escape(o['post_url'])}' target='_blank'>post</a></td>"
            f"<td><a class='autore' href='{html.escape(o['link'])}' target='_blank'>apri &amp; vedi autore →</a></td></tr>"
        )
    generato = datetime.now().strftime("%d/%m/%Y %H:%M")
    html_doc = f"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<title>Report commenti offensivi — Gianmarco Porciani</title>
<style>
:root{{--bg:#020D1A;--bg2:#071828;--accent:#50C0E8;--text:#F0F8FF;--err:#e05c5c;--muted:#7c93a8}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,Arial,sans-serif;padding:28px}}
h1{{font-family:Syne,Inter,sans-serif;font-size:22px;margin:0 0 4px}}
.sub{{color:var(--muted);font-size:13px;margin-bottom:18px}}
.badge{{display:inline-block;background:var(--err);color:#fff;border-radius:12px;padding:2px 10px;font-weight:700;font-size:13px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid #12314a;vertical-align:top}}
th{{color:var(--accent);font-size:12px;text-transform:uppercase;letter-spacing:.4px;position:sticky;top:0;background:var(--bg)}}
td.n{{color:var(--muted);width:34px}} td.data{{color:var(--muted);white-space:nowrap;width:150px;font-variant-numeric:tabular-nums}}
td.testo{{max-width:640px}} a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}}
a.autore{{white-space:nowrap;font-weight:600}}
tr:hover{{background:#0a1f33}}
.empty{{color:var(--muted);padding:30px 0}}
</style></head><body>
<h1>Commenti offensivi diretti alla Pagina</h1>
<div class="sub">Gianmarco Porciani · post del {anno} · <span class="badge">{len(offensivi)} offensivi</span>
 · {tot_commenti} commenti scanditi · generato il {generato}<br>
L'autore non è esposto da Facebook via API: clicca <b>"apri &amp; vedi autore"</b> per aprire il commento e vedere chi l'ha scritto.</div>
{"<table><thead><tr><th>#</th><th>Data</th><th>Commento</th><th>Post</th><th>Autore (link)</th></tr></thead><tbody>" + "".join(righe_html) + "</tbody></table>" if offensivi else "<div class='empty'>Nessun commento offensivo trovato.</div>"}
</body></html>"""
    html_path = os.path.join(DESKTOP, "report_offensivi_porciani.html")
    open(html_path, "w", encoding="utf-8").write(html_doc)

    print(f"\n=== FATTO ===")
    print(f"Offensivi trovati: {len(offensivi)} (su {tot_commenti} commenti, {len(posts)} post)")
    print(f"Nuove classificazioni Claude: {n_classificati_nuovi}")
    print(f"HTML: {html_path}")
    print(f"CSV : {csv_path}")


if __name__ == "__main__":
    main()
