#!/usr/bin/env python3
"""
dm_bot.py — invia un DM (Private Reply) ai commentatori dei post della Pagina.

Separato da reply_bot.py (bot commenti) di proposito: e' un'azione ad alto rischio
(un DM non si ritira), va accesa/spenta in modo indipendente. Riusa le funzioni Graph
e di fetch di reply_bot.py. NON usa Claude: i testi sono template a rotazione.

Modalita':
  python dm_bot.py --ultimi-post 5                 # PROVA: scrive dm_proposte.csv, non invia
  python dm_bot.py --post <URL|ID> --live --test-uno  # invia UN solo DM e si ferma
  python dm_bot.py --ultimi-post 5 --live --max-giorno 20

Vincolo Meta: la Private Reply raggiunge SOLO chi ha commentato, una volta per commento,
e richiede il permesso pages_messaging (verso il pubblico generico serve Accesso Avanzato).
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
    """Da una lista di commenti (formato get_comments) ricava i destinatari DM:
    salta vuoti, la Pagina stessa, chi ha gia' un DM oggi; deduplica per autore_id."""
    visti_giro = set()
    out = []
    for c in commenti:
        autore_id = c.get("autore_id") or ""
        msg = (c.get("message") or "").strip()
        if not msg:
            continue
        if not autore_id or autore_id == page_id:
            continue
        if dm_inviati.get(autore_id) == oggi:
            continue
        if autore_id in visti_giro:
            continue
        visti_giro.add(autore_id)
        out.append({
            "comment_id": c["id"],
            "autore_id": autore_id,
            "nome": nome_breve(c.get("autore_nome", "")),
        })
    return out


def private_reply(token, comment_id, testo):
    """Invia un messaggio privato (DM) in risposta a un commento.
    Endpoint Meta: POST /{comment_id}/private_replies con message=...
    Usa il graph_post di reply_bot.py (retry/backoff sugli errori temporanei inclusi)."""
    return graph_post(f"{comment_id}/private_replies", token, {"message": testo})
