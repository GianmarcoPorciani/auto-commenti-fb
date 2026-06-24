#!/usr/bin/env python3
"""
get_token.py — genera un TOKEN PAGINA A LUNGA DURATA (~60 giorni) per usarlo in reply_bot.py.

Ti serve:
  - APP_ID e APP_SECRET della tua app (Meta for Developers -> la tua app -> Impostazioni -> Basic)
  - un TOKEN UTENTE A BREVE DURATA, preso dal Graph API Explorer con i permessi:
      pages_show_list, pages_read_engagement, pages_manage_engagement

Uso:
  python get_token.py --app-id 123... --app-secret abc... --short-token EAAB...

Lo script:
  1. scambia il token utente breve -> token utente a lunga durata
  2. chiama /me/accounts -> stampa il TOKEN PAGINA a lunga durata per ogni tua Pagina
Copia il token della pagina giusta in .env alla voce FB_PAGE_TOKEN.
"""

import argparse
import sys
import requests

GRAPH = "https://graph.facebook.com/v21.0"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-id", required=True)
    ap.add_argument("--app-secret", required=True)
    ap.add_argument("--short-token", required=True,
                    help="token utente a breve durata dal Graph API Explorer")
    args = ap.parse_args()

    # 1) token utente breve -> token utente a lunga durata
    r = requests.get(f"{GRAPH}/oauth/access_token", params={
        "grant_type": "fb_exchange_token",
        "client_id": args.app_id,
        "client_secret": args.app_secret,
        "fb_exchange_token": args.short_token,
    }, timeout=30)
    if r.status_code != 200:
        print("Errore nello scambio del token:", r.text)
        sys.exit(1)
    long_user_token = r.json()["access_token"]
    print("OK: token utente a lunga durata ottenuto.\n")

    # 2) elenco Pagine + relativi token Pagina (a lunga durata)
    r = requests.get(f"{GRAPH}/me/accounts", params={
        "access_token": long_user_token,
        "fields": "name,id,access_token",
    }, timeout=30)
    if r.status_code != 200:
        print("Errore nel recupero delle Pagine:", r.text)
        sys.exit(1)

    pagine = r.json().get("data", [])
    if not pagine:
        print("Nessuna Pagina trovata per questo utente/permessi.")
        sys.exit(1)

    print("=== Token Pagina a lunga durata ===")
    for p in pagine:
        print(f"\nPagina: {p['name']}  (id {p['id']})")
        print(f"FB_PAGE_TOKEN={p['access_token']}")
    print("\nCopia il FB_PAGE_TOKEN della pagina giusta nel file .env")


if __name__ == "__main__":
    main()
