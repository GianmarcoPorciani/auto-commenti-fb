#!/usr/bin/env python3
"""stato_cloud.py — stato del bot CIFRATO su un branch separato del repo (pubblico).

Perche': il repo e' pubblico (Actions gratis e senza limiti), ma i file di stato
(done/visti/likati/coda/classificati.json) collegano gli ID dei commenti alla loro
classificazione (critico, volgare...). In chiaro sarebbero leggibili da chiunque.

Come funziona:
  - i 5 file JSON restano SOLO in locale (runner GitHub o PC) e sono in .gitignore;
  - nel repo c'e' solo `stato.enc` (JSON compresso + cifrato con Fernet/AES), sul
    branch `stato`, che contiene SEMPRE UN SOLO commit (force-push a ogni salvataggio):
    niente storia che cresce, le versioni vecchie diventano irraggiungibili;
  - la chiave e' STATO_KEY: GitHub Secret per il cloud, .env sul PC. SENZA LA CHIAVE
    LO STATO NON SI RECUPERA: tenerne una copia sicura.

Uso:
  python stato_cloud.py scarica   # scarica e decifra lo stato remoto nei 5 file locali
  python stato_cloud.py salva     # unisce locale + remoto (unione, mai perdite), cifra, pubblica
  python stato_cloud.py genera-chiave   # stampa una nuova chiave (solo al primo setup)

Sul PC serve solo `scarica` (aggiorna la cache locale usata da dm_targets/report). Il
`salva` lo fa il cloud: non lanciarlo dal PC mentre gira il bot in cloud.

Sicurezza: se lo stato remoto esiste ma non si decifra (chiave sbagliata o assente) lo
script ESCE CON ERRORE e il bot non parte: meglio fermarsi che ripartire da stato vuoto.
"""
import os
import re
import sys
import json
import gzip
import tempfile
import subprocess
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

FILES = ["done.json", "visti.json", "likati.json", "coda.json", "classificati.json"]
BRANCH = "stato"
ENC_NAME = "stato.enc"
REMOTE = "origin"


def _fernet():
    from cryptography.fernet import Fernet
    key = (os.environ.get("STATO_KEY") or "").strip()
    # tolleranza agli errori di incolla: riga intera "STATO_KEY=...", virgolette, spazi/a capo
    if key.upper().startswith("STATO_KEY="):
        key = key[len("STATO_KEY="):]
    key = key.strip().strip('"').strip("'").strip()
    if not key:
        sys.exit("ERRORE: manca STATO_KEY (GitHub Secret in cloud, .env sul PC).")
    try:
        return Fernet(key.encode())
    except Exception:
        # diagnostica SENZA rivelare la chiave: solo lunghezza e tipo di caratteri
        import string
        ok = set(string.ascii_letters + string.digits + "-_=")
        estranei = sum(1 for ch in key if ch not in ok)
        sys.exit(f"ERRORE: STATO_KEY non valida (deve essere una chiave Fernet base64 da 44 caratteri; "
                 f"ricevuti {len(key)} caratteri, di cui {estranei} non ammessi).")


def _git(*args, input_bytes=None, check=True):
    r = subprocess.run(["git", *args], input=input_bytes, capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode(errors='replace').strip()}")
    return r


# ---------------------------------------------------------------------------
# cifratura
# ---------------------------------------------------------------------------

def cifra(files_txt):
    raw = json.dumps({"versione": 1, "files": files_txt}, ensure_ascii=False).encode("utf-8")
    return _fernet().encrypt(gzip.compress(raw, 9))


def decifra(blob):
    from cryptography.fernet import InvalidToken
    try:
        raw = gzip.decompress(_fernet().decrypt(blob.strip()))
    except InvalidToken:
        sys.exit("ERRORE: lo stato remoto non si decifra con questa STATO_KEY. Mi fermo "
                 "(il bot non deve ripartire da stato vuoto).")
    return json.loads(raw.decode("utf-8"))["files"]


# ---------------------------------------------------------------------------
# remoto (branch `stato`)
# ---------------------------------------------------------------------------

def leggi_remoto():
    """(sha, {file: testo}) dello stato remoto, oppure ('', None) se il branch non esiste."""
    r = _git("fetch", "--quiet", REMOTE, f"+refs/heads/{BRANCH}:refs/remotes/{REMOTE}/{BRANCH}", check=False)
    if r.returncode != 0:
        err = r.stderr.decode(errors="replace")
        if "couldn't find remote ref" in err or "could not find remote ref" in err.lower():
            return "", None
        raise RuntimeError(f"fetch dello stato fallito: {err.strip()}")
    sha = _git("rev-parse", f"refs/remotes/{REMOTE}/{BRANCH}").stdout.decode().strip()
    blob = _git("show", f"{sha}:{ENC_NAME}").stdout
    return sha, decifra(blob)


def pubblica(enc_bytes, sha_atteso):
    """Commit ORFANO con il solo stato.enc, force-push con lease (fallisce se qualcuno ha
    aggiornato il branch nel frattempo -> si riprova con un nuovo merge)."""
    env = dict(os.environ,
               GIT_AUTHOR_NAME="auto-commenti-bot", GIT_AUTHOR_EMAIL="bot@users.noreply.github.com",
               GIT_COMMITTER_NAME="auto-commenti-bot", GIT_COMMITTER_EMAIL="bot@users.noreply.github.com")
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(enc_bytes)
        tmp = f.name
    try:
        blob = _git("hash-object", "-w", tmp).stdout.decode().strip()
    finally:
        os.unlink(tmp)
    tree = _git("mktree", input_bytes=f"100644 blob {blob}\t{ENC_NAME}\n".encode()).stdout.decode().strip()
    msg = f"stato cifrato {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    r = subprocess.run(["git", "commit-tree", tree, "-m", msg], capture_output=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="replace"))
    commit = r.stdout.decode().strip()
    lease = f"--force-with-lease=refs/heads/{BRANCH}:{sha_atteso}"
    r = _git("push", "--quiet", lease, REMOTE, f"{commit}:refs/heads/{BRANCH}", check=False)
    return r.returncode == 0, r.stderr.decode(errors="replace").strip()


# ---------------------------------------------------------------------------
# unione locale + remoto (stessa logica del vecchio merge_stato.py)
# ---------------------------------------------------------------------------

def _ids(testo):
    return set(re.findall(r"\d+_\d+", testo or ""))


def _dict(testo):
    try:
        d = json.loads(testo or "")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def unisci(locali, remoti):
    """Lo stato e' fatto di INSIEMI (done/visti/likati) e di DIZIONARI (coda, classificati):
    la fusione corretta e' sempre l'unione. La coda perde le voci gia' in done."""
    done_union = _ids(locali.get("done.json")) | _ids(remoti.get("done.json"))
    out = {}
    for path in FILES:
        loc, rem = locali.get(path, ""), remoti.get(path, "")
        if path == "coda.json":
            unito = {**_dict(rem), **_dict(loc)}
            unito = {k: v for k, v in unito.items() if k not in done_union}
        elif path == "classificati.json":
            unito = {**_dict(rem), **_dict(loc)}
        else:
            unito = sorted(_ids(loc) | _ids(rem))
        out[path] = json.dumps(unito, ensure_ascii=False, indent=0)
    return out


def _leggi_locali():
    out = {}
    for p in FILES:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                out[p] = f.read()
    return out


def _scrivi_locali(files_txt):
    for p, txt in files_txt.items():
        if p in FILES:
            with open(p, "w", encoding="utf-8") as f:
                f.write(txt)


# ---------------------------------------------------------------------------
# comandi
# ---------------------------------------------------------------------------

def cmd_scarica():
    _fernet()   # verifica subito la chiave
    sha, remoto = leggi_remoto()
    if remoto is None:
        locali = _leggi_locali()
        if "done.json" not in locali:
            sys.exit("ERRORE: nessuno stato remoto e nessun done.json locale. Mi fermo per non "
                     "ripartire da zero (il bot risponderebbe di nuovo a commenti gia' gestiti).")
        print(f"Nessuno stato cifrato remoto: uso i file locali ({len(locali)} file). "
              f"Il primo 'salva' creera' il branch '{BRANCH}'.")
        return
    _scrivi_locali(remoto)
    print(f"Stato scaricato e decifrato ({sha[:7]}): " +
          ", ".join(f"{p} {len(_ids(t)) if p not in ('coda.json', 'classificati.json') else len(_dict(t))}"
                    for p, t in remoto.items()))


def cmd_salva():
    _fernet()
    for tentativo in range(1, 6):
        sha, remoto = leggi_remoto()
        unito = unisci(_leggi_locali(), remoto or {})
        _scrivi_locali(unito)
        if remoto is not None and unito == unisci(remoto, {}):
            print("Stato invariato rispetto al remoto: niente da salvare.")
            return
        ok, err = pubblica(cifra(unito), sha)
        if ok:
            print(f"Stato cifrato salvato sul branch '{BRANCH}' (tentativo {tentativo}).")
            return
        print(f"Push rifiutato (aggiornato da un altro giro?), riprovo ({tentativo}): {err[:200]}")
    sys.exit("ERRORE: stato non salvato dopo 5 tentativi (riprovera' al giro successivo).")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "scarica":
        cmd_scarica()
    elif cmd == "salva":
        cmd_salva()
    elif cmd == "genera-chiave":
        from cryptography.fernet import Fernet
        print(Fernet.generate_key().decode())
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
