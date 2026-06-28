# Design — DM (Private Reply) ai commentatori della Pagina

Data: 2026-06-28
Stato: approvato dall'utente (in attesa di review dello spec scritto)

## Obiettivo

Inviare un messaggio diretto (DM) di ringraziamento + invito a seguire/mettere like
alla Pagina **Gianmarco Porciani**, a chi ha **commentato** i post. Tono "community":
far leva sullo spirito di gruppo e sul far girare le idee.

## Vincolo Meta (perché il design è questo e non altro)

- **Non si può scrivere in DM a chi solo reagisce/mette like.** Su Messenger Platform un
  utente è contattabile solo se ha scritto per primo alla Pagina (finestra 24h) o tramite
  message tag (vietati per contenuti promozionali). Reazioni e commenti **non** aprono un
  canale di messaggistica.
- **Unica via legittima e proattiva: la Private Reply a un commento.**
  `POST /{comment_id}/private_replies` con `message=...`. Consentita **una volta per commento**,
  perché agganciata a un'interazione reale. Raggiunge quindi **solo i commentatori**.
- **Permesso richiesto:** `pages_messaging`. Verso il pubblico generico serve l'**Accesso
  Avanzato**, che passa per la App Review di Meta. Col token System User attuale potrebbe
  funzionare solo verso admin/tester finché l'Accesso Avanzato non è approvato. **Da verificare
  con un invio singolo controllato prima di qualsiasi invio di massa.**
- **Non esiste API per sapere chi segue già la Pagina** (nessun campo `is_fan`/`is_follower`
  sull'autore del commento). Per questo il testo usa la formula condizionale "se non lo fai già".

## Decisioni del cliente (con rischio messo agli atti)

- **Destinatari:** *tutti* i commentatori, senza esclusione per categoria.
  - ⚠️ Rischio messo agli atti: inviare DM promozionali anche ai **critici** alza molto la
    probabilità di segnalazione "spam" → Meta può limitare la messaggistica o l'intera Pagina.
    La mia raccomandazione era escludere `critico`/`volgare`/`spam`. Scelta del cliente: includere
    tutti. Mitigazione adottata: testo **neutro** che funziona anche per chi non è allineato
    (non dice "grazie del supporto" a un critico), cap stretti, partenza prudente.
- **Frequenza per persona:** **max 1 DM al giorno** alla stessa persona.
- **Tetto globale:** **~150 DM al giorno** totali (configurabile), con partenza più bassa
  consigliata nei primi giorni.
- **Testo:** **10 template a rotazione**, neutri e coinvolgenti, con il nome di battesimo.

## Architettura — script separato `dm_bot.py`

Scelta: **script a sé**, non integrazione in `reply_bot.py`.

Motivazione (isolamento di un'azione hard-to-reverse e ad alto rischio):
- un DM non si ritira; tenerlo separato dal flusso commenti già rodato e in produzione evita
  di rompere ciò che funziona;
- si accende/spegne in modo indipendente (un eventuale blocco Meta sui DM non tocca like/risposte);
- inviando a *tutti* con template, **non serve Claude** → nessuna classificazione, costo API zero,
  meno punti di rottura.

`dm_bot.py` **importa** le funzioni già rodate da `reply_bot.py` invece di duplicarle:
`graph_get`, `graph_post`, `get_comments`, `get_posts`, `get_page_info`, `estrai_post_id`,
e le costanti Graph. (reply_bot.py è importabile: `main()` è sotto `if __name__ == "__main__"`.)

### Nuova funzione Graph

```
private_reply(token, comment_id, testo):
    POST /{comment_id}/private_replies  con data={"message": testo}
```
Usa lo stesso `_graph(...)` con retry/backoff già presente in reply_bot.py.

### Nuovo stato — `dm_inviati.json`

Dizionario `{ autore_id: "YYYY-MM-DD" }` = data dell'ultimo DM per persona.
Serve a:
- saltare chi ha già ricevuto un DM **oggi** (cap "1 al giorno a persona");
- contare i DM **di oggi** (somma delle date == oggi) per il tetto globale.

L'`autore_id` del commento è page-scoped ma stabile per utente sulla Pagina: va bene come chiave
di deduplica anche tra post diversi.

### Selezione candidati (per ogni post lavorato)

Per ogni commento:
1. salta se messaggio vuoto;
2. salta se `autore_id == page_id` (commenti della Pagina stessa);
3. salta se l'autore ha già un DM con data == oggi in `dm_inviati.json`;
4. deduplica per `autore_id` nel giro corrente (un solo candidato per persona per esecuzione);
5. nessuna esclusione per categoria (scelta del cliente) → non serve classificare.

Quando il tetto globale giornaliero è raggiunto, stop.

### Testo — 10 template neutri a rotazione

`{nome}` = solo il nome di battesimo, ricavato da `autore_nome` (prima parola). Se manca, attacco
senza nome (es. "Ciao,") così la frase resta naturale. Rotazione con contatore, come i template
dei commenti. Massimo una emoji per messaggio; 🇮🇹 distribuito "di tanto in tanto".

1. Ciao {nome}, ho letto il tuo commento e mi ha fatto piacere davvero. Siamo in tanti a pensarla così, e più siamo più le nostre idee girano. Se non lo fai già, segui la pagina e lasciale un like: ti aspetto di là 💪
2. {nome}, grazie per esserci. Questa pagina la portiamo avanti insieme, un commento alla volta. Mettile un like e premi "Segui": così non ti perdi niente e diamo più voce a quello in cui crediamo 🙏
3. Senti {nome}, gente come te è esattamente il motivo per cui vale la pena continuare. Aiutami a far crescere la community: un like alla pagina, il tasto Segui, e fai girare il messaggio a chi la pensa come noi. Conta parecchio 🇮🇹
4. Il tuo sostegno non passa inosservato, {nome}. Qui dentro siamo una squadra: più follower vuol dire più persone raggiunte e più idee che viaggiano. Se ti va, segui la pagina e mettile un like 👊
5. {nome}, due secondi: se condividi quello che scrivo, restami vicino. Segui la pagina e lasciale un mi piace. Più siamo, più diventa difficile ignorarci. E a me serve proprio questo.
6. Grazie del commento, {nome}. Lo dico sul serio: ogni persona che si unisce rende questa voce più forte. Premi Segui, metti like alla pagina, e se conosci qualcuno che la pensa come noi tiralo dentro. Le idee si diffondono così.
7. Ciao {nome}, mi piace quando arrivano commenti come il tuo. Vuol dire che non sono solo. Tienimi d'occhio: segui la pagina e mettile un like, così restiamo in contatto e portiamo avanti insieme le nostre battaglie 🇮🇹
8. {nome}, te lo chiedo diretto: seguimi sulla pagina e lasciale un like. Non è una formalità, è quello che ci fa crescere e ci permette di far sentire la nostra di campana. Sei già dei nostri, tanto vale renderlo ufficiale 😉
9. Grazie {nome}. Una community vera si costruisce con le persone che ci mettono la faccia nei commenti, come hai fatto tu. Aiutami: like alla pagina, tasto Segui, e condividi quando qualcosa ti convince. Insieme arriviamo lontano 🇮🇹
10. Contento di averti qui, {nome}. Se vuoi che queste idee continuino a girare, il modo più semplice è restare connessi: segui la pagina, mettile un like, e ogni tanto fai girare un post. Ci conto su di te 💪

### Modalità ed esecuzione (CLI, sul modello di reply_bot.py)

- `--post <URL|ID>` oppure `--ultimi-post N` per scegliere i post da cui pescare i commenti.
- **PROVA (default)**: scrive `dm_proposte.csv` (post_id, autore, comment_id, testo_dm),
  **non invia nulla**.
- `--live`: invia davvero.
- `--test-uno`: invia **un solo** DM e si ferma. Serve a verificare subito se `pages_messaging`
  funziona col token attuale, prima di ogni invio di massa.
- `--max-giorno N` (default 150): tetto globale giornaliero.
- `--max N`: tetto per singolo post.

### Rail anti-ban

- Default = PROVA (nessun invio senza `--live`).
- Pause **30–70s** tra un DM e l'altro (più lente dei commenti: i DM sono più sensibili).
- Blocco **fascia notturna 00–06** (ora italiana), riuso della logica di reply_bot.py.
- **Kill-switch**: 3 errori di fila → stop (come il bot commenti).
- Cap per persona (1/giorno) e globale (default 150/giorno).
- Salvataggio stato dopo ogni invio (idempotenza, ripartenza sicura).

### Rollout

Niente cron all'inizio. Sequenza:
1. `dm_bot.py --ultimi-post 5` (PROVA) → controllo `dm_proposte.csv`.
2. `dm_bot.py --post <recente> --live --test-uno` → verifica permesso `pages_messaging`.
   - Se Meta risponde "permesso mancante / serve Accesso Avanzato" → passo successivo = App Review,
     **prima** di aver inviato un solo DM di massa.
3. Piccolo `--live --max-giorno 20` per qualche giorno, monitorando blocchi/segnalazioni.
4. Solo se Meta non blocca: valutare un workflow GitHub Actions **separato** con cap stretti.

## Compliance (promemoria leggero)

- I DM invitano a *seguire/mettere like*, non a votare → fuori dal perimetro "propaganda di voto".
- A ridosso di una tornata elettorale, nel **giorno di silenzio e nel giorno del voto**, sospendere
  l'invio per prudenza (possibile interruttore dedicato).

## File toccati / creati

- **Nuovo:** `dm_bot.py`
- **Nuovo (stato):** `dm_inviati.json`
- **Nuovo (output prova):** `dm_proposte.csv`
- **Modificato:** `reply_bot.py` solo se servono piccoli aggiustamenti per rendere importabili
  le funzioni condivise (verifica: già importabili, nessuna modifica prevista).
- **Aggiornato:** `DOCUMENTAZIONE.md` / `README.md` con la nuova procedura.
- **Versionato:** `dm_inviati.json` **va committato** (come done.json/visti.json): nel cloud lo
  stato deve persistere tra un'esecuzione e l'altra. Se in futuro arriva un workflow dedicato,
  aggiungerlo alla riga `git add` di quel workflow.

## Rischi residui (espliciti)

- DM ai critici = più alta probabilità di segnalazione e quindi di blocco messaggistica/Pagina.
- `pages_messaging` potrebbe richiedere App Review prima di funzionare sul pubblico generico.
- L'invio di massa di DM è il pattern che Meta sorveglia di più: i cap e le pause riducono il
  rischio ma non lo azzerano. Rilettura/monitoraggio umano indispensabile nei primi giri.
