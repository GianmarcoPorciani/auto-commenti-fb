#!/usr/bin/env python3
"""report_diretti.py — REPORT dei commenti offensivi DIRETTI A GIANMARCO / alla Pagina.

Due filtri combinati per isolare SOLO gli attacchi a lui (non le risse tra utenti):
  1) STRUTTURA (gratis): tiene solo i commenti VOLGARI che sono top-level sul post
     o risposte a un commento DELLA PAGINA. Scarta le risposte ad altri utenti.
  2) CONFERMA CLAUDE: sui superstiti verifica che l'offesa bersagli LUI/la Pagina
     (non un altro utente, non un politico/partito terzo, non uno sfogo generico).

Autore non esposto via API -> nel report c'e' il LINK al commento (mostra l'autore al clic).
Output: report_diretti_porciani.html + .csv sul Desktop.

Uso:  python report_diretti.py            # tutti i post 2026
      python report_diretti.py --anno 2026
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

DIRETTO_SYS = (
    "Sei un moderatore. Ricevi commenti pubblicati sotto i post di GIANMARCO PORCIANI, "
    "creator politico (area sovranista/identitaria). Per OGNI commento numerato indica se e' "
    "un'OFFESA, INSULTO o ATTACCO PERSONALE rivolto a GIANMARCO o alla sua PAGINA. "
    "Metti diretto=false se il commento: e' rivolto a un ALTRO utente, bersaglia un politico/partito/"
    "categoria TERZI (PD, M5S, sinistra, immigrati, governo, ecc.), o e' uno sfogo generico non contro di lui. "
    "Metti diretto=true SOLO se il bersaglio e' lui o la Pagina (es. 'sei un fascista di merda', "
    "'Porciani pagliaccio', 'leone da tastiera', 'fai schifo tu'). Rispondi SOLO col JSON richiesto."
)
DIRETTO_SCHEMA = {
    "type": "object",
    "properties": {"risultati": {"type": "array", "items": {"type": "object", "properties": {
        "n": {"type": "integer"},
        "diretto": {"type": "boolean"},
    }, "required": ["n", "diretto"], "additionalProperties": False}}},
    "required": ["risultati"], "additionalProperties": False,
}


def _num(cid):
    return str(cid).split("_")[-1]


def lista_post_anno(tok, page_id, anno):
    posts = []
    data = rb.graph_get(f"{page_id}/posts", tok, {"fields": "id,permalink_url,created_time", "limit": 25})
    while True:
        dd = data.get("data", [])
        for p in dd:
            if p.get("created_time", "")[:4] == anno:
                posts.append(p)
        if dd and dd[-1].get("created_time", "")[:4] < anno:
            break
        nxt = (data.get("paging", {}) or {}).get("next")
        if not nxt:
            break
        r = requests.get(nxt, timeout=30)
        if r.status_code != 200:
            break
        data = r.json()
    return posts


def fetch_comments_parent(tok, oids):
    """Come dt.fetch_all_comments ma con il campo parent (per top-level vs reply). Ritorna (comments, oid)."""
    if isinstance(oids, str):
        oids = [oids]
    last_err = None
    for oid in oids:
        if not oid:
            continue
        try:
            data = rb.graph_get(f"{oid}/comments", tok,
                                {"fields": "id,message,created_time,from{id},parent{id,from{id}}",
                                 "limit": 100, "filter": "stream"})
        except Exception as e:
            last_err = e
            continue
        out = []
        while True:
            out.extend(data.get("data", []))
            nxt = (data.get("paging", {}) or {}).get("next")
            if not nxt:
                break
            r = requests.get(nxt, timeout=30)
            if r.status_code != 200:
                break
            data = r.json()
        return out, oid
    raise RuntimeError(f"nessun id valido (provati {oids}): {last_err}")


def classifica_diretti(client, items, batch=25):
    """items = list di (idx, testo). Ritorna set degli idx che sono offese DIRETTE a lui."""
    out = set()
    for i in range(0, len(items), batch):
        chunk = items[i:i + batch]
        righe = "\n".join(f'[{k + 1}] "{(t or "")[:200]}"' for k, (idx, t) in enumerate(chunk))
        try:
            resp = client.messages.create(
                model=rb.MODEL, max_tokens=len(chunk) * 8 + 300, system=DIRETTO_SYS,
                output_config={"format": {"type": "json_schema", "schema": DIRETTO_SCHEMA}},
                messages=[{"role": "user", "content": "Commenti:\n" + righe}])
            testo = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            for r in json.loads(testo).get("risultati", []):
                n = r.get("n")
                if isinstance(n, int) and 1 <= n <= len(chunk) and r.get("diretto") is True:
                    out.add(chunk[n - 1][0])
            print(f"  conferma diretti {min(i + batch, len(items))}/{len(items)}")
        except Exception as e:
            print(f"  [errore conferma diretti] {e}")
    return out


def link_commento(permalink, cid):
    sep = "&" if "?" in permalink else "?"
    return f"{permalink}{sep}comment_id={_num(cid)}"


def main():
    anno = "2026"
    for a in sys.argv[1:]:
        if a.startswith("--anno="):
            anno = a.split("=")[1]

    tok = os.environ.get("FB_PAGE_TOKEN")
    if not tok:
        print("Manca FB_PAGE_TOKEN (.env)."); sys.exit(1)
    client = anthropic.Anthropic()

    page_id, _ = rb.get_page_info(tok)
    cache = {}
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        pass

    posts = lista_post_anno(tok, page_id, anno)
    print(f"{len(posts)} post del {anno}. Filtro: volgare + (top-level o risposta alla Pagina) + conferma Claude.")

    candidati = []   # {data, testo, post_url, link, cid}
    tot_commenti = 0
    for i, p in enumerate(posts, 1):
        permalink = p.get("permalink_url") or f"https://www.facebook.com/{p['id']}"
        try:
            comments, _oid = fetch_comments_parent(tok, [p["id"], dt.obj_id_from_arg(permalink)])
        except Exception as e:
            print(f"  [{i}/{len(posts)}] non letto ({str(e)[:40]}) — salto")
            continue
        tot_commenti += len(comments)

        da_classificare = []
        for c in comments:
            msg = (c.get("message") or "").strip()
            if not msg:
                continue
            frm = c.get("from") or {}
            if frm.get("id") == page_id:
                continue
            num = _num(c["id"])
            if num not in cache:
                da_classificare.append((num, msg))
        if da_classificare:
            nuovi = dt.classifica_solo_categoria(client, da_classificare)
            cache.update(nuovi)

        for c in comments:
            msg = (c.get("message") or "").strip()
            if not msg:
                continue
            frm = c.get("from") or {}
            if frm.get("id") == page_id:
                continue
            num = _num(c["id"])
            if cache.get(num) != "volgare":
                continue
            # FILTRO STRUTTURA: solo top-level o risposta alla PAGINA
            par = c.get("parent")
            if par is not None and (par.get("from") or {}).get("id") != page_id:
                continue  # risposta a un altro utente -> rissa tra utenti, scarto
            candidati.append({
                "data": (c.get("created_time") or "")[:19].replace("T", " "),
                "testo": msg,
                "post_url": permalink,
                "link": link_commento(permalink, c["id"]),
            })
        print(f"  [{i}/{len(posts)}] {len(comments)} commenti — candidati (volgare+struttura): {len(candidati)}")

    # CONFERMA CLAUDE: bersaglio = lui/la Pagina?
    print(f"\nConferma Claude su {len(candidati)} candidati...")
    idx_items = [(k, c["testo"]) for k, c in enumerate(candidati)]
    diretti_idx = classifica_diretti(client, idx_items)
    diretti = [candidati[k] for k in sorted(diretti_idx)]
    diretti.sort(key=lambda x: x["data"], reverse=True)

    # ---- CSV ----
    csv_path = os.path.join(DESKTOP, "report_diretti_porciani.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Data", "Commento offensivo (diretto a te)", "Post", "Link al commento (mostra autore)"])
        for o in diretti:
            w.writerow([o["data"], o["testo"], o["post_url"], o["link"]])

    # ---- HTML ----
    righe_html = []
    for n, o in enumerate(diretti, 1):
        righe_html.append(
            f"<tr><td class='n'>{n}</td><td class='data'>{html.escape(o['data'])}</td>"
            f"<td class='testo'>{html.escape(o['testo'])}</td>"
            f"<td><a href='{html.escape(o['post_url'])}' target='_blank'>post</a></td>"
            f"<td><a class='autore' href='{html.escape(o['link'])}' target='_blank'>apri &amp; vedi autore →</a></td></tr>"
        )
    generato = datetime.now().strftime("%d/%m/%Y %H:%M")
    html_doc = f"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<title>Offese dirette — Gianmarco Porciani</title>
<style>
:root{{--bg:#020D1A;--bg2:#071828;--accent:#50C0E8;--text:#F0F8FF;--err:#e05c5c;--muted:#7c93a8}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,Arial,sans-serif;padding:28px}}
h1{{font-family:Syne,Inter,sans-serif;font-size:22px;margin:0 0 4px}}
.sub{{color:var(--muted);font-size:13px;margin-bottom:18px;line-height:1.5}}
.badge{{display:inline-block;background:var(--err);color:#fff;border-radius:12px;padding:2px 10px;font-weight:700;font-size:13px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid #12314a;vertical-align:top}}
th{{color:var(--accent);font-size:12px;text-transform:uppercase;letter-spacing:.4px;position:sticky;top:0;background:var(--bg)}}
td.n{{color:var(--muted);width:34px}} td.data{{color:var(--muted);white-space:nowrap;width:150px;font-variant-numeric:tabular-nums}}
td.testo{{max-width:640px}} a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}}
a.autore{{white-space:nowrap;font-weight:600}} tr:hover{{background:#0a1f33}} .empty{{color:var(--muted);padding:30px 0}}
</style></head><body>
<h1>Offese dirette a te</h1>
<div class="sub">Gianmarco Porciani · post del {anno} · <span class="badge">{len(diretti)} offese dirette</span>
 · {tot_commenti} commenti scanditi · generato il {generato}<br>
Filtrati: solo commenti volgari <b>rivolti a te / alla Pagina</b> (esclusi litigi tra utenti e attacchi a terzi).
Clicca <b>"apri &amp; vedi autore"</b> per aprire il commento e vedere chi l'ha scritto.</div>
{"<table><thead><tr><th>#</th><th>Data</th><th>Commento</th><th>Post</th><th>Autore (link)</th></tr></thead><tbody>" + "".join(righe_html) + "</tbody></table>" if diretti else "<div class='empty'>Nessuna offesa diretta trovata.</div>"}
</body></html>"""
    html_path = os.path.join(DESKTOP, "report_diretti_porciani.html")
    open(html_path, "w", encoding="utf-8").write(html_doc)

    print(f"\n=== FATTO ===")
    print(f"Offese DIRETTE a te: {len(diretti)} (candidati struttura: {len(candidati)}, commenti totali: {tot_commenti})")
    print(f"HTML: {html_path}")
    print(f"CSV : {csv_path}")


if __name__ == "__main__":
    main()
