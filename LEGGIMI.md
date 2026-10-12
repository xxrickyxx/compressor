# Compressione 0.4

Apri **Avvia.cmd** con un doppio clic. Si apre una moderna interfaccia nel browser, servita soltanto su 127.0.0.1. La scheda Compressione permette di selezionare un file e comprimerlo, ricostruirlo o verificarlo. Mostra avanzamento, dimensioni, risparmio e tempo totale; verifica automaticamente ogni archivio appena creato. Il pulsante Annulla interrompe il lavoro al termine del blocco corrente. Se annulli durante la verifica finale, l’archivio già creato resta disponibile e puoi verificarlo successivamente.

La cartella **prove_modelli** contiene gli archivi delle prove reali e il rapporto **RISULTATI.md**. La nuova schermata mostra anche questi risultati. Per il precedente menu testuale puoi eseguire `python avvia.py`; la precedente finestra Tk resta disponibile in `interfaccia.py`.

## Chat dal modello compresso

Il checkpoint Qwen3-1.7B è disponibile come modello aggiuntivo nel menu.
È un modello denso; i pesi ufficiali sono distribuiti in due parti. Il programma
le comprime separatamente e usa un indice JSON per raggiungere i tensori.
Le modalità a strati e cache RAM funzionano anche con questo indice.

Il pannello mostra la memoria del **processo**, distinta dal totale di Windows.
**Libera RAM del modello** scarica i pesi memorizzati senza chiudere il servizio;
non è disponibile durante una generazione. La cache RAM tiene i pesi numerici
residenti per velocizzare le richieste successive. I pesi di embedding e uscita
condividono la stessa copia quando previsto dalla configurazione del modello.

La scheda **API** mostra URL, ID del modello e chiave per integrare la chat
con altri programmi. Il servizio usa normalmente la porta 8765. Gli endpoint
sono descritti in **API.md**, lo schema in **openapi.json**. La chiave persistente
è in api-key.txt e non deve essere condivisa pubblicamente.

L’avvio importa Torch dopo aver preparato esplicitamente le dipendenze Visual
C++ di Windows. La correzione è stata provata con PATH ridotto. Se queste
librerie non sono installate né disponibili nel runtime locale, il messaggio
indica di installare il Redistributable Visual C++ x64 ufficiale.

La scheda Chat locale usa l’archivio compresso Qwen3-0.6B già presente. L’ambiente è ora nella sottocartella .venv di Compressione; Configura.cmd lo crea o ripara e recupera i file di supporto ufficiali del checkpoint. La chat non dipende più da matrix_ia. Il motore supporta Qwen3 safetensors BF16/F16/F32: non supporta ancora BitNet o GGUF per l’inferenza.

- **A strati:** legge gli intervalli dei tensori dall’archivio CMP, verifica i blocchi, decodifica i pesi dello strato, esegue il calcolo e libera i pesi. Non ricostruisce un file completo su disco. Deve rileggere i pesi per ogni token: può essere molto lento.
- **Cache in RAM:** legge i pesi dall’archivio al primo uso e li mantiene in memoria. Richiede più RAM; il programma controlla la disponibilità prima di attivarla.

Le operazioni matematiche usano tensori decodificati, non i byte zlib direttamente. Questo è un motore di inferenza con lettura da archivio, non calcolo su dati ancora compressi. Conserva la cache KV per la generazione e usa una decodifica deterministica. Il campo **Limite di contesto** è regolabile da 128 a 8.192 token, con 1.024 come valore iniziale. Comprende la cronologia, il template e la risposta, che rimane limitata a 128 token e può essere accorciata per rispettare il contesto. “Nuova chat” azzera la conversazione. Contesti lunghi richiedono più memoria e tempo.

Configurazione e tokenizer sono nella sottocartella models/qwen3-0.6b, esclusa da Git. Configura.cmd recupera questi asset dal repository ufficiale Qwen e installa le dipendenze; non riscarica i pesi. Avvia.cmd controlla le dipendenze prima di usare un interprete. `server.log`, `launch-error.log` e `setup.log` contengono eventuali errori.

Il test `test_engine.py` confronta esattamente i logits del motore da archivio con un piccolo Qwen3 di riferimento, sia sul prompt sia sul token successivo con cache KV, nelle due modalità. Le basi per il caricamento a richiesta sono descritte nella [documentazione PyTorch](https://docs.pytorch.org/tutorials/recipes/recipes/module_load_state_dict_tips.html) e nella [documentazione Qwen3](https://huggingface.co/docs/transformers/model_doc/qwen3).

Il programma non modifica il file originale e rifiuta di sovrascrivere destinazioni esistenti. Serve spazio libero per il nuovo archivio. Interrompere una compressione non produce un archivio utilizzabile.

## Cosa fa

Compressione senza perdita, a blocchi da 1 MiB: per ogni blocco sceglie zlib oppure i dati originali se la compressione non conviene. Un indice permette l'accesso diretto ai blocchi. CRC32 controlla ogni blocco; SHA-256 verifica l'intero contenuto ricostruito. La memoria per i dati rimane limitata ai blocchi; l'indice cresce con il numero dei blocchi.

Funziona su file binari, inclusi file di pesi, senza interpretarne i tensori. File già quantizzati o compressi potrebbero ridursi poco o aumentare leggermente a causa dell'indice. Il risultato misura il risparmio su disco, non un aumento dei token al secondo.

## Comandi avanzati

Con Python 3, nella cartella del programma:

```
python compressione.py comprimi modello.gguf modello.cmp
python compressione.py info modello.cmp
python compressione.py verifica modello.cmp
python compressione.py estrai modello.cmp modello_ripristinato.gguf
python compressione.py blocco modello.cmp 0 primo_blocco.bin
python test_compressione.py
```

I numeri dei blocchi partono da zero. `--blocco 262144` imposta blocchi da 256 KiB durante la compressione.

## Passi successivi

Estendere il motore a BitNet/GGUF; confrontare codifiche adatte ai pesi; ottimizzare letture e cache. Questa versione non mappa ancora gli esperti MoE.

Avvia.cmd usa il Python già disponibile sul computer tramite Codex, oppure Python nel PATH. Non richiede pacchetti aggiuntivi.


## v0.5 — chat, loop e confronto

Interfaccia italiano / English / 简体中文. Conversazioni persistenti e recupero lessicale facoltativo delle chat precedenti. Loop per siti statici multipagina con checkpoint, continuazioni, budget e controlli dei link. Vedere [CHAT_AND_TASKS.md](CHAT_AND_TASKS.md).

CMP v2 aggiunge Zstandard; v1 resta leggibile. Qwen3-4B ufficiale: 8.045,0 MB → 6.298,5 MB (−21,71%), integrità verificata. Download: `python download_qwen17.py --size 4 --codec zstd`.

[STUDY.md](STUDY.md) documenta precedenti, algoritmi e limiti dell’esclusività; [CODEC_RESULTS.md](CODEC_RESULTS.md) contiene misure lossless sugli stessi campioni BF16 e quantizzati. Nessun vantaggio token/s rispetto a DwarfStar o llama.cpp dimostrato.

Misure reali del 4B: [QWEN4_RESULTS.md](QWEN4_RESULTS.md).


## v0.6

Scoped file tools, targeted edits, backend API tests and a trusted local gym-management template with SQLite, accounts, lessons and bookings. Optional official llama.cpp + Qwen3-4B Q4 runtime for faster coding loops. See [CHAT_AND_TASKS.md](CHAT_AND_TASKS.md) and [QWEN4_RESULTS.md](QWEN4_RESULTS.md). Quantized inference is separate from lossless CMP inference.
