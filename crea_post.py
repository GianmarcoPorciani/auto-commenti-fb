#!/usr/bin/env python3
"""
crea_post.py — pubblica un post sulla Pagina Facebook e mette subito il primo commento @follower.

Due fasi (l'approvazione resta a te):
  1. GENERA (non pubblica):   python crea_post.py --tema "Mediaset fa fuori Giordano"
     -> Claude scrive il testo nel tuo stile, lo stampa. Non pubblica niente.
  2. PUBBLICA:                python crea_post.py --testo "<testo finale>" --foto img.jpg --pubblica
     -> pubblica il post (con foto se indicata) e mette il primo commento "@follower".

Opzioni utili:
  --quando "2026-06-25 18:00"   programma il post a data/ora (in questo caso il commento @follower
                                 NON viene aggiunto subito: il post non e' ancora online).
  --cta "Condividi se sei d'accordo"   testo aggiunto dopo "@follower" nel primo commento.
  --commento-follower "@follower"      personalizza il primo commento (default: @follower).

Richiede il permesso app 'pages_manage_posts' (oltre a quelli gia' usati).
Setup token/chiave: vedi README.md / .env
"""

import argparse
import datetime
import os
import sys

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import anthropic
except ImportError:
    print("Manca 'anthropic'. Esegui: pip install -r requirements.txt")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GRAPH_VERSION = "v21.0"
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"
MODEL = "claude-opus-4-8"   # per i POST conviene il modello piu' capace (testo curato)

# Stile dei post di Gianmarco Porciani (modificabile).
SYSTEM_POST = """Scrivi un post Facebook per la Pagina di Gianmarco Porciani, creator politico
(area sovranista/identitaria, Futuro Nazionale con Vannacci). Stile: diretto, schietto, senza
ufficio stampa, paragrafi brevi, tono combattivo ma lucido. Struttura tipica:
- un titolo forte tutto maiuscolo nella prima riga
- 2-4 paragrafi brevi che spiegano il punto, con un'inquadratura "noi contro il sistema"
- chiusura con una call to action ("Condividi se...") e qualche hashtag (#FuturoNazionale #Vannacci ecc.)
Niente virgolette attorno al post, niente preamboli: restituisci SOLO il testo del post pronto da pubblicare."""


def genera_testo(tema):
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=900,
        system=SYSTEM_POST,
        messages=[{"role": "user", "content": f"Scrivi il post su questo tema/notizia:\n{tema}"}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()


def get_page_id(token):
    r = requests.get(f"{GRAPH}/me", params={"fields": "id,name", "access_token": token}, timeout=30)
    r.raise_for_status()
    j = r.json()
    return j["id"], j.get("name", "")


def _quando_to_ts(quando):
    dt = datetime.datetime.strptime(quando, "%Y-%m-%d %H:%M")
    return int(dt.timestamp())


def pubblica_post(token, page_id, testo, foto=None, quando=None):
    """Pubblica un post (foto o solo testo), eventualmente programmato. Ritorna l'id del post."""
    programmato = quando is not None
    data = {"access_token": token}
    if programmato:
        data["published"] = "false"
        data["scheduled_publish_time"] = str(_quando_to_ts(quando))

    if foto:
        if not os.path.exists(foto):
            raise FileNotFoundError(f"Foto non trovata: {foto}")
        data["caption"] = testo  # su /photos il testo va in 'caption'
        with open(foto, "rb") as f:
            r = requests.post(f"{GRAPH}/{page_id}/photos", data=data,
                              files={"source": f}, timeout=120)
    else:
        data["message"] = testo
        r = requests.post(f"{GRAPH}/{page_id}/feed", data=data, timeout=60)

    if r.status_code != 200:
        raise RuntimeError(f"Pubblicazione fallita {r.status_code}: {r.text}")
    j = r.json()
    # /photos ritorna {id, post_id}; /feed ritorna {id}
    return j.get("post_id") or j.get("id")


def commenta(token, post_id, testo):
    r = requests.post(f"{GRAPH}/{post_id}/comments",
                      data={"message": testo, "access_token": token}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Commento fallito {r.status_code}: {r.text}")
    return r.json()


def main():
    ap = argparse.ArgumentParser(description="Crea un post sulla Pagina + primo commento @follower")
    ap.add_argument("--tema", help="genera il testo con Claude da questo tema (NON pubblica)")
    ap.add_argument("--testo", help="testo gia' pronto del post")
    ap.add_argument("--foto", help="percorso immagine da allegare")
    ap.add_argument("--quando", help='programma a "AAAA-MM-GG HH:MM"')
    ap.add_argument("--commento-follower", default="@follower",
                    help="primo commento (default: @follower)")
    ap.add_argument("--cta", default="", help="testo aggiunto dopo @follower nel primo commento")
    ap.add_argument("--pubblica", action="store_true",
                    help="pubblica davvero (senza, con --tema, solo genera e stampa)")
    args = ap.parse_args()

    token = os.environ.get("FB_PAGE_TOKEN")
    if not token:
        print("Manca FB_PAGE_TOKEN (.env)")
        sys.exit(1)

    # 1) generazione testo (se richiesto)
    if args.tema and not args.testo:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("Manca ANTHROPIC_API_KEY (.env)")
            sys.exit(1)
        print("Genero il testo con Claude...\n")
        testo = genera_testo(args.tema)
        print("===== BOZZA POST =====\n" + testo + "\n======================")
        if not args.pubblica:
            print("\n(Non pubblicato.) Per pubblicare: rilancia con --testo \"<testo>\" --pubblica")
            return
    else:
        testo = args.testo

    if not testo:
        print("Serve --tema (per generare) oppure --testo (testo pronto).")
        sys.exit(1)

    if not args.pubblica:
        print("Aggiungi --pubblica per pubblicare davvero.")
        return

    page_id, nome = get_page_id(token)
    print(f"Pagina: {nome}")

    post_id = pubblica_post(token, page_id, testo, foto=args.foto, quando=args.quando)
    if args.quando:
        print(f"Post PROGRAMMATO per {args.quando} (id {post_id}).")
        print("Nota: il commento @follower va aggiunto quando il post sara' online (rilancia dopo).")
        return

    print(f"Post PUBBLICATO (id {post_id}).")
    # 2) primo commento @follower
    commento = args.commento_follower
    if args.cta:
        commento = f"{commento} {args.cta}"
    try:
        res = commenta(token, post_id, commento)
        print(f"Primo commento pubblicato: {commento!r} -> {res}")
        print("VERIFICA sul telefono se i follower ricevono la notifica '@follower' "
              "(via API potrebbe non scattare: in tal caso fissa quel commento a mano).")
    except Exception as e:
        print(f"[errore primo commento] {e}")


if __name__ == "__main__":
    main()
