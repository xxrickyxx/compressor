# Verifiche della versione 0.2

## Riconnessione della pagina dopo un riavvio — 13 ottobre 2026

- Riprodotto “Accesso non autorizzato” nella pagina aperta prima del riavvio:
  il token temporaneo della pagina non coincideva più con quello del servizio.
- Le API dell’interfaccia distinguono ora la sessione scaduta. Il client
  recupera il nuovo token dalla pagina locale senza cache e ripete una sola
  volta la richiesta. Le richieste concorrenti condividono il rinnovo;
  altri errori non avviano tentativi automatici.
- Test JavaScript: rinnovo concorrente, singola esecuzione del POST rifiutato,
  conservazione del token aggiornato, errori estranei e limite dei tentativi.
  Test HTTP: un token scaduto non avvia il lavoro; pagina e script senza cache.
- Verifica nella pagina reale lasciata aperta durante un secondo riavvio:
  testo nel campo messaggio conservato, stato “Pronto” e comando “Libera RAM
  del modello” riuscito senza ricaricare la pagina. Cronologia conservata.

## Correzione avvio llama.cpp — 13 ottobre 2026

- Riprodotto l’errore `0xC0000135` con `llama-server.exe --version` e PATH
  limitato a Windows/System32 e Windows. Le DLL Visual C++ erano presenti nelle
  dipendenze locali ma non venivano cercate dal processo nativo separato.
- Il processo figlio riceve ora le cartelle delle DLL disponibili e la propria
  cartella del runtime. Nessuna modifica al PATH di sistema. Gli errori DLL o
  di architettura hanno un messaggio distinto dall’annullamento dell’utente.
- Ventiquattro test automatici superati, inclusa l’esecuzione del runtime
  ufficiale con PATH Windows minimo. Il test nativo viene saltato quando il
  pacchetto facoltativo non è installato.
- Servizio reale riavviato con PATH Windows minimo; Qwen3-4B Q4_K_M ha
  completato la richiesta “Rispondi esattamente con la parola: PRONTO”.
  Risposta `PRONTO`, 4 token, contesto 1.024; caricamento iniziale 20,14 s e
  generazione 1,57 s. È una verifica dell’avvio, non un benchmark di qualità.

## Modello Qwen3-1.7B e rilascio RAM — 12 ottobre 2026

- Download del checkpoint ufficiale verificato con i SHA-256 upstream; le due
  parti compresse superano la verifica completa CRC32/SHA-256.
- Lettore a più archivi: instradamento dei tensori, rifiuto di indici incoerenti
  e di percorsi fuori dalla cartella verificati automaticamente.
- Tredici test automatici superati; il rilascio RAM è bloccato mentre un lavoro
  è in corso.
- Modello di riferimento: risultati numerici identici su archivio singolo e
  manifest a due parti, sia in modalità direct sia RAM; verificato anche il
  contesto da 600 token e la condivisione effettiva dell’embedding in RAM.
- Risposta di riferimento standard Hugging Face di Qwen0.6 controllata contro
  la risposta del nostro motore, senza differenze nella prova scelta.
- Confronto reale di sei richieste su 0.6B e 1.7B: dettagli in QWEN17_RESULTS.md.

## Aggiornamento 0.4 — 12 ottobre 2026

- Il vecchio progetto matrix_ia non è più presente; creato un ambiente .venv
  dentro Compressione con Torch CPU 2.14.1, Transformers 4.57.6 e psutil 7.2.2.
- Configurazione e tokenizer del checkpoint Qwen3-0.6B recuperati dal repository
  ufficiale alla revisione originaria; l’archivio dei pesi resta quello esistente.
- Avvia.cmd preferisce l’ambiente locale e verifica le dipendenze. Configura.cmd
  consente di ricrearlo/ripararlo senza dipendere da un altro progetto Desktop.
- Dieci test automatici superati: API, compressione, limiti di contesto e scelta
  dell’ambiente. Verificati rifiuto degli ambienti incompleti e contesto condiviso
  fra prompt e risposta.
- Qwen3 di riferimento: logits identici su prefill e token successivo; generazione
  con un prompt sintetico di 600 token accettata con contesto 1.024 e rifiutata
  con 512. Risposta accorciata correttamente al raggiungimento del limite.
  Verificato in modalità direct e RAM.
- Il servizio reale avviato dal CMD segnala tutte le dipendenze disponibili e
  ha completato una generazione di 128 token. La prova HTTP aggiuntiva con prompt
  lungo è stata annullata dall’interfaccia, quindi non viene riportata come passata.
- Contesto ora configurabile da 128 a 8.192 token (default 1.024), nelle API con
  context_window e nell’interfaccia con il campo Limite di contesto.

## Aggiornamento 0.3 — 5 ottobre 2026

- Bootstrap Torch riuscito con PATH limitato a Windows/System32, senza dipendere
  dall’ambiente di una console già configurata.
- Sei test automatici superati: compressione/accesso/corruzione/annullamento e
  autenticazione API, risposta JSON, streaming SSE, job di compressione reale.
- Motore a righe/blocchi: logits del piccolo Qwen3 di riferimento identici con
  tolleranza zero su prefill e token successivo, sia direct sia RAM.
- Server realmente avviato da Avvia.cmd; GET /v1/models e POST
  /v1/chat/completions provati con Qwen completo, autenticazione e streaming.
  Risposta “Ciao.” ricevuta in eventi incrementali e conclusa con [DONE]
  (circa 74,3 secondi nella prova HTTP).
- Misure del processo e relativi limiti descritti in MEMORY.md.

Segue la documentazione delle prove precedenti.

4 ottobre 2026, computer locale Windows.

- Compressione: ricostruzione esatta di dati vuoti, ripetuti, binari e casuali; accesso a blocchi e intervalli che attraversano i blocchi; rifiuto di sovrascrittura; rilevamento di corruzione; pulizia del file temporaneo dopo annullamento.
- Interfaccia Tk: compressione, verifica e ricostruzione tramite i pulsanti.
- Motore Qwen3: su un modello piccolo di riferimento, logits esattamente identici (tolleranza zero) sul prompt e sul token successivo con cache KV. Verificate sia lettura a strati sia cache RAM. In modalità a strati tutti i parametri tornano su dispositivo meta dopo il calcolo.
- Chat web: due generazioni con l’archivio completo di Qwen3-0.6B. La seconda ha prodotto “Ciao.”, 3 token in 64,1 secondi (0,05 token/s), inclusa la lettura ripetuta dei pesi. Questo dimostra l’esecuzione, non misura la qualità generale del modello.
- La modalità RAM ha rifiutato l’attivazione sul modello reale per memoria libera insufficiente; il suo funzionamento numerico è verificato sul modello piccolo.

Le prove di compressione sui modelli completi e le verifiche SHA-256 sono in `prove_modelli/RISULTATI.md` e `prove_modelli/risultati.json`.

Limiti: chat diretta solo Qwen3 safetensors; massimo 512 token di contesto; fino a 128 token di risposta. Nessuna promessa di accelerazione: la modalità a strati riduce la permanenza dei pesi in RAM, ma deve decomprimerli ad ogni passaggio.
