#!/usr/bin/env python3
"""
dm_bot.py — invia un DM (Private Reply) ai commentatori dei post della Pagina.

Separato da reply_bot.py (bot commenti) di proposito: e' un'azione ad alto rischio
(un DM non si ritira), va accesa/spenta in modo indipendente. Riusa le funzioni Graph
e di fetch di reply_bot.py. NON usa Claude: i testi sono template a rotazione.

Modalita':
  python dm_bot.py --ultimi-post 5                    # PROVA: scrive dm_proposte.csv, non invia
  python dm_bot.py --commento <COMMENT_ID> --live     # invia a UN commento preciso (test mirato)
  python dm_bot.py --post <URL|ID> --live --test-uno  # invia UN solo DM e si ferma
  python dm_bot.py --ultimi-post 5 --live --max-giorno 20

Vincolo Meta: la Private Reply raggiunge SOLO chi ha commentato, una volta per commento,
e richiede il permesso pages_messaging (verso il pubblico generico serve Accesso Avanzato).
Facebook NON espone l'identita' di chi commenta (autore_id/nome vuoti): dedup e cap sono
quindi per COMMENTO (1 DM per commento), e i messaggi usano la versione senza nome.
"""

import argparse
import csv
import json
import os
import random
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from reply_bot import (
    graph_post,
    get_comments,
    get_posts,
    get_page_info,
    estrai_post_id,
)

# --- Config ---
DM_INVIATI_FILE = "dm_inviati.json"
DM_CSV = "dm_proposte.csv"
MAX_GIORNO_DEFAULT = 150
PAUSA_MIN = 30      # secondi tra un DM e l'altro (piu' lente dei commenti)
PAUSA_MAX = 70


def nome_breve(autore_nome):
    """Primo nome di battesimo da 'Mario Rossi' -> 'Mario'. Stringa vuota se assente."""
    if not autore_nome:
        return ""
    parti = autore_nome.strip().split()
    return parti[0] if parti else ""


# 10 template a rotazione, neutri e community-oriented. Una sola emoji per messaggio;
# 🇮🇹 distribuito "di tanto in tanto" (template idx 2, 6, 8).
DM_TEMPLATES = [
    "Ciao {nome}, ho letto il tuo commento e mi ha fatto piacere davvero. Siamo in tanti a pensarla così, e più siamo più le nostre idee girano. Se non lo fai già, segui la pagina e lasciale un like: ti aspetto di là 💪",
    "{nome}, grazie per esserci. Questa pagina la portiamo avanti insieme, un commento alla volta. Mettile un like e premi \"Segui\": così non ti perdi niente e diamo più voce a quello in cui crediamo 🙏",
    "Senti {nome}, gente come te è esattamente il motivo per cui vale la pena continuare. Aiutami a far crescere la community: un like alla pagina, il tasto Segui, e fai girare il messaggio a chi la pensa come noi. Conta parecchio 🇮🇹",
    "Il tuo sostegno non passa inosservato, {nome}. Qui dentro siamo una squadra: più follower vuol dire più persone raggiunte e più idee che viaggiano. Se ti va, segui la pagina e mettile un like 👊",
    "{nome}, due secondi: se condividi quello che scrivo, restami vicino. Segui la pagina e lasciale un mi piace. Più siamo, più diventa difficile ignorarci. E a me serve proprio questo.",
    "Grazie del commento, {nome}. Lo dico sul serio: ogni persona che si unisce rende questa voce più forte. Premi Segui, metti like alla pagina, e se conosci qualcuno che la pensa come noi tiralo dentro. Le idee si diffondono così.",
    "Ciao {nome}, mi piace quando arrivano commenti come il tuo. Vuol dire che non sono solo. Tienimi d'occhio: segui la pagina e mettile un like, così restiamo in contatto e portiamo avanti insieme le nostre battaglie 🇮🇹",
    "{nome}, te lo chiedo diretto: seguimi sulla pagina e lasciale un like. Non è una formalità, è quello che ci fa crescere e ci permette di far sentire la nostra di campana. Sei già dei nostri, tanto vale renderlo ufficiale 😉",
    "Grazie {nome}. Una community vera si costruisce con le persone che ci mettono la faccia nei commenti, come hai fatto tu. Aiutami: like alla pagina, tasto Segui, e condividi quando qualcosa ti convince. Insieme arriviamo lontano 🇮🇹",
    "Contento di averti qui, {nome}. Se vuoi che queste idee continuino a girare, il modo più semplice è restare connessi: segui la pagina, mettile un like, e ogni tanto fai girare un post. Ci conto su di te 💪",
]


def componi_dm(contatore, nome):
    """Sceglie un template a rotazione e inserisce il nome. Se il nome manca, rimuove il
    segnaposto lasciando una frase naturale e pulita."""
    t = DM_TEMPLATES[contatore % len(DM_TEMPLATES)]
    if nome:
        return t.replace("{nome}", nome)
    # Nome assente: sostituzioni ordinate (le piu' specifiche prima).
    t = t.replace("Ciao {nome}, ", "Ciao, ")
    t = t.replace("Senti {nome}, ", "Senti, ")
    t = t.replace(", {nome}.", ".")   # nome a fine frase
    t = t.replace(" {nome}.", ".")    # "Grazie {nome}." -> "Grazie."
    t = t.replace("{nome}, ", "")     # nome a inizio frase
    t = t.replace("{nome}", "")       # residui
    t = t.strip()
    if t:
        t = t[0].upper() + t[1:]
    return t


def carica_dm_inviati(path=DM_INVIATI_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def salva_dm_inviati(stato, path=DM_INVIATI_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stato, f, ensure_ascii=False, indent=0)


def conta_dm_oggi(stato, oggi):
    return sum(1 for data in stato.values() if data == oggi)


def seleziona_candidati(commenti, page_id, dm_inviati, oggi):
    """Da una lista di commenti (formato get_comments) ricava i destinatari DM.
    Facebook NON fornisce l'identita' di chi commenta (autore_id/nome spesso vuoti per
    privacy), quindi dedup e cap sono per COMMENTO, non per persona: salta i commenti
    vuoti, quelli della Pagina stessa e quelli a cui abbiamo gia' inviato un DM (Meta
    consente 1 private reply per commento). 'oggi' non serve qui: un commento riceve un
    DM una volta sola in assoluto (il tetto giornaliero e' applicato a parte in invia_dm)."""
    visti_giro = set()
    out = []
    for c in commenti:
        autore_id = c.get("autore_id") or ""
        cid = c["id"]
        msg = (c.get("message") or "").strip()
        if not msg:
            continue
        if autore_id == page_id:      # commento della Pagina stessa -> mai
            continue
        if cid in dm_inviati:         # a questo commento abbiamo gia' mandato un DM
            continue
        if cid in visti_giro:
            continue
        visti_giro.add(cid)
        out.append({
            "comment_id": cid,
            "autore_id": autore_id,
            "nome": nome_breve(c.get("autore_nome", "")),
        })
    return out


def private_reply(token, comment_id, testo):
    """Invia un messaggio privato (DM) in risposta a un commento.
    Endpoint Meta: POST /{comment_id}/private_replies con message=...
    Usa il graph_post di reply_bot.py (retry/backoff sugli errori temporanei inclusi)."""
    return graph_post(f"{comment_id}/private_replies", token, {"message": testo})


def e_fascia_notturna(ora_it):
    """True tra le 00 e le 06 (escluse) ora italiana: di notte non si invia."""
    return ora_it < 6


def oggi_str():
    """Data odierna 'YYYY-MM-DD' in fuso Europe/Rome (fallback UTC+2)."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Rome")).strftime("%Y-%m-%d")
    except Exception:
        from datetime import datetime, timezone, timedelta
        return datetime.now(timezone(timedelta(hours=2))).strftime("%Y-%m-%d")


def ora_italiana():
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Rome")).hour
    except Exception:
        from datetime import datetime, timezone, timedelta
        return datetime.now(timezone(timedelta(hours=2))).hour


def raccogli_candidati(token, page_id, post_ids, dm_inviati, oggi):
    """Scorre i post indicati, raccoglie i commenti e applica seleziona_candidati.
    Deduplica anche TRA post diversi (una persona = un solo candidato per giro)."""
    tutti = []
    visti_globali = set()
    for pid in post_ids:
        commenti = get_comments(token, pid, page_id)
        print(f"  post {pid}: {len(commenti)} commenti")
        for cand in seleziona_candidati(commenti, page_id, dm_inviati, oggi):
            if cand["comment_id"] in visti_globali:
                continue
            visti_globali.add(cand["comment_id"])
            cand["post_id"] = pid
            tutti.append(cand)
    return tutti


def scrivi_prova_csv(candidati):
    with open(DM_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["post_id", "comment_id", "autore_id", "nome", "dm_proposto"])
        for i, c in enumerate(candidati):
            w.writerow([c.get("post_id", ""), c["comment_id"], c["autore_id"],
                        c["nome"], componi_dm(i, c["nome"])])
    print(f"  scritte {len(candidati)} proposte in {DM_CSV}")


def invia_dm(token, candidati, dm_inviati, oggi, max_giorno, max_per_post, solo_uno=False):
    """Invia i DM con pause, cap globale giornaliero, kill-switch a 3 errori di fila.
    Salva lo stato dopo OGNI invio (idempotenza)."""
    inviati_oggi = conta_dm_oggi(dm_inviati, oggi)
    n = 0
    errori = 0
    for i, cand in enumerate(candidati):
        if inviati_oggi >= max_giorno:
            print(f"  Tetto giornaliero {max_giorno} raggiunto: stop.")
            break
        if max_per_post and n >= max_per_post:
            print(f"  Tetto per sessione {max_per_post} raggiunto: stop.")
            break
        testo = componi_dm(i, cand["nome"])
        try:
            private_reply(token, cand["comment_id"], testo)
            dm_inviati[cand["comment_id"]] = oggi
            salva_dm_inviati(dm_inviati)
            inviati_oggi += 1
            n += 1
            errori = 0
            print(f"  [DM] commento {cand['comment_id']}: {testo}")
        except Exception as e:
            errori += 1
            print(f"  [errore DM su {cand['comment_id']}] {e}")
            if errori >= 3:
                print("  STOP: 3 errori di fila (permesso pages_messaging? blocco Meta?).")
                break
            continue
        if solo_uno:
            print("  --test-uno: inviato 1 DM, mi fermo.")
            break
        pausa = random.uniform(PAUSA_MIN, PAUSA_MAX)
        print(f"    ...pausa {pausa:.0f}s")
        time.sleep(pausa)
    return n


def main():
    ap = argparse.ArgumentParser(description="Invia DM (Private Reply) ai commentatori")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--post", help="ID o URL del post")
    g.add_argument("--ultimi-post", type=int, metavar="N", help="ultimi N post della pagina")
    g.add_argument("--commento", metavar="COMMENT_ID",
                   help="invia a UN solo commento specifico (per test mirati)")
    ap.add_argument("--live", action="store_true", help="invia davvero (senza: solo PROVA->CSV)")
    ap.add_argument("--test-uno", action="store_true", help="in --live, invia UN solo DM e stop")
    ap.add_argument("--max-giorno", type=int, default=MAX_GIORNO_DEFAULT,
                    help=f"tetto globale giornaliero di DM (default {MAX_GIORNO_DEFAULT})")
    ap.add_argument("--max", type=int, default=None, metavar="N",
                    help="tetto di DM per questa sessione")
    args = ap.parse_args()

    if args.live and e_fascia_notturna(ora_italiana()):
        print(f"Ora italiana ~{ora_italiana()}:00 — fascia notturna (00-06): nessun invio.")
        return

    token = os.environ.get("FB_PAGE_TOKEN")
    if not token:
        print("Manca FB_PAGE_TOKEN (.env). Vedi README.md")
        sys.exit(1)

    page_id, page_name = get_page_info(token)
    print(f"Pagina: {page_name} (id {page_id})")
    print(f"Modalita': {'LIVE - invia' if args.live else 'PROVA - solo dm_proposte.csv'}")

    oggi = oggi_str()
    dm_inviati = carica_dm_inviati()
    print(f"  DM gia' inviati oggi ({oggi}): {conta_dm_oggi(dm_inviati, oggi)}")

    if args.commento:
        candidati = [{"comment_id": args.commento, "autore_id": "", "nome": "", "post_id": ""}]
        print(f"  target: singolo commento {args.commento}")
    else:
        if args.post:
            post_ids = [estrai_post_id(args.post, page_id)]
        else:
            post_ids = [p["id"] for p in get_posts(token, page_id, args.ultimi_post)]
        print(f"{len(post_ids)} post da scandire")
        candidati = raccogli_candidati(token, page_id, post_ids, dm_inviati, oggi)
    print(f"  candidati DM (dopo filtri e dedup): {len(candidati)}")

    if not args.live:
        scrivi_prova_csv(candidati)
        print(f"\nPROVA completata. Controlla {DM_CSV}. Per inviare: aggiungi --live")
        return

    n = invia_dm(token, candidati, dm_inviati, oggi, args.max_giorno, args.max,
                 solo_uno=args.test_uno)
    print(f"\nDM inviati in questa sessione: {n}")


if __name__ == "__main__":
    main()
