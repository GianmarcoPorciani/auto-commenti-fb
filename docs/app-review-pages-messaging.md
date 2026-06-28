# App Review — Accesso Avanzato `pages_messaging`

App: **Risposte Commenti** (App ID 1529398511958436) · Pagina: Gianmarco Porciani (504760203329428)
Obiettivo: ottenere l'**Accesso Avanzato** di `pages_messaging` per inviare **Private Reply**
(`POST /{comment_id}/private_replies`) ai follower che commentano i post della Pagina.

Taglio della richiesta: **assistenza / cura della relazione con chi commenta** (uso consentito delle
Private Reply), NON invio promozionale di massa.

---

## ⚠️ Prerequisito di onestà (leggere)

Meta verifica che l'uso reale corrisponda alla descrizione. Perché la richiesta sia veritiera e
abbia chance di approvazione, il DM deve **rispondere/ringraziare** il commento; l'invito a
seguire/like va tenuto come elemento **secondario e morbido**, non come scopo del messaggio.
Vedi "Ritocco consigliato ai testi" in fondo: conviene adottarlo prima di sottomettere e di girare
lo screencast (lo screencast deve mostrare ciò che descrivi).

---

## 1. Requisiti da soddisfare PRIMA di poter sottomettere

- [ ] **App pubblicata (Live)**: oggi è "Non pubblicata". In Dashboard → Pubblicazione, completa i
      requisiti e porta l'app in modalità Live.
- [ ] **Informativa sulla privacy (URL)**: serve un URL pubblico a una privacy policy. Impostazioni
      app → Di base → "URL dell'informativa sulla privacy".
- [ ] **Verifica del business** (Business Verification) del portfolio ZanzOut, se non già fatta.
- [ ] **Screencast** che dimostra il permesso in uso (vedi sezione 4).
- [ ] **Caso d'uso Messenger** già aggiunto all'app ✅ (fatto il 2026-06-28).
- [ ] `pages_messaging` presente sul token ✅ (Accesso Standard, fatto il 2026-06-28).

---

## 2. Descrizione d'uso del permesso (campo "How will you use pages_messaging?")

> Meta richiede la descrizione **in inglese**. Sotto trovi la versione EN da incollare e la
> traduzione IT per tua comprensione.

### EN (da incollare nel form)

We use `pages_messaging` to send a **private reply** to followers who comment on our Page's public
posts. Our Page (a public figure / content creator) receives a high volume of comments — questions,
feedback, and messages of support. Replying to each one publicly is not practical and clutters the
comment threads.

With `pages_messaging`, when a follower leaves a comment, the Page sends them **one private reply in
Messenger** that personally acknowledges and responds to their comment, thanks them for engaging, and
keeps the relationship going. This is a customer-care style interaction: each follower gets a direct,
personal response in their inbox instead of being lost in a long public thread. We send at most one
private reply per comment, we never message people who have not commented, and we respect Messenger
policies (no spam, conservative pacing, the user can block/stop at any time).

We do **not** use this permission for bulk promotional broadcasts or to message users who did not
interact with the Page.

### IT (per te, non per il form)

Usiamo `pages_messaging` per inviare una **risposta privata** ai follower che commentano i post
pubblici della Pagina. La Pagina (figura pubblica / creator) riceve molti commenti — domande,
riscontri, messaggi di sostegno. Rispondere a tutti pubblicamente è impraticabile e intasa i thread.
Con `pages_messaging`, quando un follower commenta, la Pagina gli invia **una sola risposta privata
in Messenger** che riconosce e risponde personalmente al suo commento, lo ringrazia e cura la
relazione. È un'interazione in stile assistenza clienti: ogni follower riceve una risposta diretta e
personale, invece di perdersi in un thread lungo. Una sola private reply per commento, mai a chi non
ha commentato, nel rispetto delle policy di Messenger (niente spam, ritmo prudente, l'utente può
bloccare/fermare quando vuole). NON usiamo il permesso per invii promozionali di massa.

---

## 3. Istruzioni passo-passo per i reviewer (campo "Tell us how to test")

### EN (da incollare)

1. Open our Facebook Page: https://www.facebook.com/GianmarcoPorciani1991
2. Open any recent public post and leave a comment (e.g. "Great video, thanks!").
3. Within a few minutes, the Page sends you a **private reply in Messenger** that acknowledges your
   comment and thanks you personally. Open Messenger to see the message from the Page.
4. The reply is sent only in response to your comment, one time, via
   `POST /{comment_id}/private_replies`.

(If testing in development mode, the reviewer can use a test user with a role on the app; the same
flow applies.)

---

## 4. Note per lo SCREENCAST (obbligatorio)

Registra uno schermo (anche col telefono) che mostra **l'intero flusso**:

1. Mostra la Pagina e un post pubblico.
2. Da un account follower, **scrivi un commento** sul post.
3. Passa a **Messenger** dell'account follower e mostra **la risposta privata** arrivata dalla Pagina,
   che ringrazia/risponde al commento.
4. (Facoltativo ma utile) mostra a schermo, anche brevemente, la chiamata API
   `POST /{comment_id}/private_replies` che genera quel messaggio (es. log del bot `dm_bot.py`).

Durata 1–2 minuti, senza tagli sospetti: deve vedersi causa→effetto (commento → DM).

---

## 5. Ritocco consigliato ai testi dei DM (per coerenza con la descrizione)

Per allineare l'uso reale alla descrizione "assistenza/relazione", conviene che i 10 template
mettano davanti il **riconoscimento del commento** e tengano l'invito a seguire come chiusura
morbida e non sempre presente. Esempi di taglio corretto:

- "Ciao {nome}, grazie per il tuo commento — l'ho letto davvero. Se ti va di restare in contatto, mi
  trovi sulla pagina; per qualsiasi cosa, scrivimi pure qui."
- "Grazie {nome} per essere passato a commentare. Volevo risponderti personalmente: se hai domande o
  vuoi dirmi la tua, sono qui. E se ti fa piacere seguire la pagina, ne sono felice 🙏"

Posso riscrivere tutti e 10 i template in questa chiave (assistenza-first) quando vuoi: riduce il
rischio di rifiuto e rende la descrizione veritiera.

---

## 6. Dove si sottomette

Dashboard app → (sidebar) **Revisione dell'app** / nella riga `pages_messaging` del caso d'uso
Messenger → "Richiedi Accesso Avanzato" → compila descrizione (sez. 2), istruzioni test (sez. 3),
allega screencast (sez. 4), conferma privacy policy e business verification, invia.
