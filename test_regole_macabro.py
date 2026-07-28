"""test_regole_macabro.py - verifica le nuove regole su casi reali.

I commenti qui sotto sono ESTRATTI VERI dal corpus, quelli su cui il benchmark ha
mostrato il rischio: sotto un post sulla morte di una persona, il bot rispondeva
"Grazie! Condividi 💪".

Attesi:
  - i macabri  -> categoria "macabro", rispondere=false
  - i volgari  -> rispondere=true, ma con registro composto (no grazie/condividi/emoji)
  - i genuini sostenitori -> invariati, non devono finire in "macabro" per eccesso di zelo

Costa qualche decimo di centesimo di API Anthropic.
"""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

import anthropic

from reply_bot import classifica_batch

# Il post reale sotto cui erano stati scritti i commenti macabri del corpus.
# Senza questo contesto "Voleva fare Tarzan" e' indecidibile.
POST_DI_CONTESTO = (
    "Ennesimo furto finito in tragedia: un uomo e' precipitato dal balcone di un "
    "appartamento mentre tentava di introdursi in casa di una famiglia. E' morto sul colpo. "
    "Se lo Stato non garantisce la sicurezza nelle nostre case, i cittadini restano soli."
)

# (commento, categoria attesa, deve_rispondere)
CASI = [
    # Macabri: mai una risposta
    ("Uno di meno", "macabro", False),
    ("Ben gli sta un ladro in meno", "macabro", False),
    ("Finalmente .....uno in meno:si e'fatto giustizia da solo🤣🤣🤣", "macabro", False),
    ("Voleva fare Tarzan", "macabro", False),
    ("-1", "macabro", False),
    # Constata una causalita', non celebra la morte: e' un sostenitore (deciso dall'utente
    # il 2026-07-28, contro l'etichetta che avevo messo io nella prima versione del test).
    ("Se non andava a rubare o forse non moriva", "sostenitore", True),
    # Sostenitori veri: NON devono diventare macabro per eccesso di zelo
    ("Bravo Gianmarco, hai ragione da vendere", "sostenitore", True),
    ("Finalmente qualcuno che dice le cose come stanno 💪", "sostenitore", True),
    ("Questi politici sono dei traditori, vergogna!", "sostenitore", True),
    # Critico civile: nessuna risposta
    ("Non sono d'accordo, i dati dicono un'altra cosa", "critico", False),
    # Insulto PURO: si tace, rispondere darebbe solo visibilita'
    ("Sei un cretino e non capisci niente", "volgare", False),
    ("Idiota", "volgare", False),
    # Offesa CON argomento: si replica nel merito, con registro composto
    ("Ma che cazzata, i furti in casa sono in calo del 12% secondo l'Istat",
     "volgare", True),
    # Commenti brevi: prima del 2026-07-28 il pre-filtro li marcava sostenitore senza
    # vedere il post e rispondeva col template. Ora passano dal classificatore, che ha il
    # contesto: devono ricevere una risposta scritta sul contenuto del post.
    ("Bravo", "sostenitore", True),
    ("Complimenti 💪", "sostenitore", True),
]

VIETATE_NEI_VOLGARI = ["grazie", "condividi", "condivid", "like", "mi piace", "segui"]


def main():
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Manca ANTHROPIC_API_KEY (.env)")
        sys.exit(1)

    client = anthropic.Anthropic()
    chunk = [{"cid": str(i), "autore": "", "message": t} for i, (t, _, _) in enumerate(CASI, 1)]
    # Passa dal vero classifica_batch, così il test esercita anche l'iniezione del contesto.
    esiti = classifica_batch(client, chunk, POST_DI_CONTESTO)
    per_n = {int(cid): r for cid, r in esiti.items()}

    ok = True
    for i, (commento, atteso, deve_rispondere) in enumerate(CASI, 1):
        r = per_n.get(i, {})
        cat = r.get("categoria", "?")
        # Stessa logica di lavora_post: sul sostenitore il flag si ignora, sul volgare conta.
        rispondo = bool(r) and (cat == "sostenitore"
                                or (cat == "volgare" and r.get("rispondere")))
        risposta = (r.get("risposta") or "").strip()

        problemi = []
        if cat != atteso:
            problemi.append(f"categoria {cat} (attesa {atteso})")
        if rispondo != deve_rispondere:
            problemi.append("RISPONDE ma doveva tacere" if rispondo else "tace ma doveva rispondere")
        if cat == "volgare" and rispondo:
            basso = risposta.lower()
            trovate = [p for p in VIETATE_NEI_VOLGARI if p in basso]
            if trovate:
                problemi.append(f"registro sbagliato: {', '.join(trovate)}")

        segno = "OK  " if not problemi else "FAIL"
        if problemi:
            ok = False
        print(f"{segno} [{cat:<12}] {'risponde' if rispondo else '  tace  '}  \"{commento[:52]}\"")
        if risposta:
            print(f"       -> {risposta}")
        for p in problemi:
            print(f"       !! {p}")

    print("\n" + ("TUTTI I CASI OK" if ok else "CI SONO CASI FALLITI — vedi sopra"))


if __name__ == "__main__":
    main()
