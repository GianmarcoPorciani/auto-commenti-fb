#!/usr/bin/env python3
"""
insights.py — report sintetico della Pagina: follower e rendimento degli ultimi post.

Uso:
  python insights.py                 # ultimi 10 post
  python insights.py --post 20       # ultimi 20 post

Follower e like/commenti/condivisioni per post funzionano con i permessi gia' in uso.
Reach/impression (copertura) richiedono in piu' il permesso 'read_insights': se manca,
quella colonna viene saltata in silenzio.
"""

import argparse
import os
import sys

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GRAPH_VERSION = "v21.0"
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"


def g(path, token, params=None):
    p = {"access_token": token}
    if params:
        p.update(params)
    r = requests.get(f"{GRAPH}/{path}", params=p, timeout=30)
    if r.status_code != 200:
        return {"_err": r.status_code, "_body": r.text}
    return r.json()


def metriche_post(post_id, token):
    """Reazioni per tipo + click del post (richiede read_insights). Ritorna dict."""
    out = {"reazioni": 0, "anger": 0, "click": 0}
    d = g(f"{post_id}/insights", token,
          {"metric": "post_reactions_by_type_total,post_clicks"})
    for item in d.get("data", []):
        try:
            val = item["values"][0]["value"]
        except Exception:
            continue
        if item.get("name") == "post_reactions_by_type_total":
            out["reazioni"] = sum(val.values()) if isinstance(val, dict) else 0
            out["anger"] = val.get("anger", 0) if isinstance(val, dict) else 0
        elif item.get("name") == "post_clicks":
            out["click"] = val
    return out


def main():
    ap = argparse.ArgumentParser(description="Report Pagina Facebook")
    ap.add_argument("--post", type=int, default=10, help="quanti ultimi post analizzare (default 10)")
    args = ap.parse_args()

    token = os.environ.get("FB_PAGE_TOKEN")
    if not token:
        print("Manca FB_PAGE_TOKEN (.env)")
        sys.exit(1)

    me = g("me", token, {"fields": "name,fan_count,followers_count"})
    if "_err" in me:
        print("Errore:", me)
        sys.exit(1)
    print(f"=== {me.get('name')} ===")
    print(f"Follower: {me.get('followers_count', me.get('fan_count', '?'))}  "
          f"(fan_count: {me.get('fan_count', '?')})\n")

    page_id = g("me", token, {"fields": "id"}).get("id")
    posts = g(f"{page_id}/posts", token, {
        "fields": "id,created_time,message,"
                  "likes.summary(true).limit(0),"
                  "comments.summary(true).limit(0),"
                  "shares",
        "limit": args.post,
    })
    if "_err" in posts:
        print("Errore lettura post:", posts)
        sys.exit(1)

    print(f"{'data':10} {'reaz.':>6} {'😡':>4} {'commenti':>9} {'cond.':>6} {'click':>6}  testo")
    print("-" * 86)
    for p in posts.get("data", []):
        data = (p.get("created_time") or "")[:10]
        com = p.get("comments", {}).get("summary", {}).get("total_count", 0)
        sh = (p.get("shares") or {}).get("count", 0)
        m = metriche_post(p["id"], token)
        msg = (p.get("message") or "(senza testo)").replace("\n", " ")[:40]
        print(f"{data:10} {m['reazioni']:>6} {m['anger']:>4} {com:>9} {sh:>6} {m['click']:>6}  {msg}")
    print("\n('reaz.' = reazioni totali, '😡' = arrabbiati. Le impression/reach non sono "
          "piu' esposte dall'API Facebook in questa versione.)")


if __name__ == "__main__":
    main()
