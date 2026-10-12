# Verifiche della versione 0.2

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
