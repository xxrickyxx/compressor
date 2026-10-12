# Conversazioni e progetti locali — v0.6

La lingua dell'interfaccia è selezionabile fra italiano, inglese e cinese semplificato, e viene ricordata dal browser. Non cambia automaticamente la lingua delle risposte del modello: chiedila nel messaggio. Le risposte e i contenuti prodotti restano testo del modello; gli errori tecnici upstream possono restare nella lingua originale.

Le chat sono salvate in `data/chats.sqlite3` nella cartella del programma e sopravvivono a chiusura, ricaricamento e riavvio. Il selettore apre le conversazioni precedenti con i relativi messaggi e impostazioni. Una nuova chat mantiene separate le discussioni. I dati non vengono inviati a servizi cloud e sono esclusi da Git. Il database contiene testo in chiaro: un backup della cartella data ne conserva una copia.

La conversazione completa viene conservata, ma solo una parte entra nel contesto del modello. Il programma conta i token reali del template e conserva gli scambi recenti, rimuovendo gli scambi più vecchi dal prompt quando necessario. Il messaggio corrente non viene troncato: se è troppo lungo, viene richiesto un contesto maggiore. L'interfaccia riporta quanti messaggi precedenti sono rimasti fuori contesto.

“Richiama altre chat pertinenti” aggiunge fino a tre estratti con parole in comune alla domanda. È un recupero lessicale locale, non un riassunto affidabile di tutte le chat e non una memoria semantica. Gli estratti sono limitati e identificati nel risultato; vengono esclusi se non entrano nel budget. Istruzioni contenute negli estratti non hanno precedenza sulla richiesta corrente. “Archivia questa chat” nasconde la conversazione e la esclude dal recupero di memoria; i messaggi restano conservati. “Ripristina ultima chat archiviata” permette di annullare l’archiviazione più recente.

## Loop per un sito con più pagine

1. In Chat scegli modello, modalità dei pesi e contesto. Per il loop inizia con 4.096 token di contesto e modalità RAM se disponibile.
2. Apri “Progetti e loop”, descrivi l'obiettivo e indica tutti i file attesi, uno per riga: per esempio index.html, about.html, contact.html, style.css e script.js.
3. Imposta massimo di passaggi per questa esecuzione e budget totale cumulativo di token. Ogni passaggio genera fino a 1.024 token.
4. Avvia. Il ciclo genera un file per volta, conserva una risposta troncata e chiede di proseguire il file al passaggio successivo.
5. I risultati restano in `outputs/<id>/site`; il checkpoint è `outputs/<id>/task.json`. “Riprendi” continua dal checkpoint. Per un budget totale già esaurito, aumentalo prima di riprendere.

Il loop verifica file attesi non vuoti, struttura HTML e chiusura, navigazione fra tutte le pagine HTML, assenza di marcatori Markdown nel codice, JSON valido e destinazioni dei riferimenti href/src locali. Se Node è disponibile, controlla anche la sintassi JavaScript senza eseguirlo. Il programma estrae il file richiesto anche quando il modello aggiunge altri file alla risposta e collega automaticamente pagine, CSS e JavaScript condivisi. Questa riparazione di struttura è deterministica. Per gli altri problemi prova a riscrivere il file responsabile entro il budget. Mostra “completed” soltanto se la lista di file è completa e i controlli passano; altrimenti si sospende senza dichiarare successo. Può essere fermato e ripreso. Se il processo viene chiuso durante una generazione, riprende dall'ultimo passaggio salvato.

Il percorso statico lavora su HTML/CSS/JS/JSON/Markdown/SVG/testo dentro la propria cartella. Non esegue comandi arbitrari del modello, non installa pacchetti e non pubblica siti. Il backend palestra gestito della v0.6 è descritto più avanti; altri backend, pagamenti e account di terze parti richiedono ulteriori integrazioni. Il controllo di un link non certifica la correttezza funzionale del JavaScript, l'accessibilità o la qualità grafica. Per richieste complesse un modello piccolo può fallire e richiedere correzioni.

Le API Chat Completions restano senza stato per compatibilità: il client passa i messaggi. La memoria applicativa è nelle API locali `/api/chats`, `/api/chat?id=...`, `/api/chats/create` e `/api/chats/delete`, protette dal token dell'interfaccia. Il loop usa `/api/run` con `action: agent`; non è esposto come esecuzione di tool remoti nel protocollo OpenAI.

“Anteprima” apre index.html su un server locale separato dall’origine delle API e della chat. Non pubblica il progetto su Internet e non dà al sito accesso al token dell’interfaccia.


## Backend e strumenti v0.6

Il tipo Automatico riconosce un gestionale palestra con backend; si può selezionarlo esplicitamente. Il programma aggiunge `gestionale.html`, `backend.py` e README, crea una base funzionale da un runtime e un’interfaccia verificati e collega le pagine. La base del backend è un template gestito dal programma: non viene inventata né eseguita come codice arbitrario del modello. I passaggi del modello possono essere zero quando il template soddisfa già il progetto.

Gli strumenti del loop sono `list_files`, `read_file`, `write_file`, `replace_text`, `check_project` e `test_backend`. Il modello può invocarli con un oggetto JSON. Le operazioni sui file sono limitate ai nomi nel manifesto del progetto; gli errori dei tool tornano al modello per permettere un nuovo tentativo entro il budget. I file Python generati possono essere controllati sintatticamente; l’esecuzione automatica è limitata al backend gestito. Non è una shell generale e non installa pacchetti richiesti dal modello.

Il backend palestra offre registrazione, login, sessioni, permessi amministratore/iscritto, lezioni, prenotazioni, capienza e annullamento. Le password sono derivate con PBKDF2-SHA256 e sale, le sessioni usano cookie HttpOnly/SameSite e le scritture autenticate richiedono CSRF. Il database SQLite è in `.data/gym.sqlite3`. L’account amministratore iniziale è creato con password casuale; “Accesso amministratore” mostra le credenziali locali dopo l’avvio dell’anteprima. Il file è `.data/admin-credentials.json`, escluso dalla distribuzione dei file web e da Git.

“Anteprima” apre il progetto dentro il programma su un’origine locale separata. Per il gestionale avvia anche il backend. Il completamento richiede 11 verifiche HTTP funzionali, eseguite su un database di prova separato: registrazione, login, permessi, lezione, prenotazione, capienza, CSRF, proprietà delle prenotazioni, annullamento, elenco utenti e persistenza. I dati reali del progetto non vengono usati per queste prove.

Il gestionale è un’applicazione locale di base. Non include pagamenti, recupero password via email, abbonamenti, notifiche, distribuzione pubblica o una certificazione di produzione. Backend personalizzati diversi da questo template non vengono dichiarati funzionanti sulla sola base di un controllo di sintassi.

## Motore nativo opzionale

`python install_native.py` installa dalla release ufficiale b11573 di llama.cpp il runtime CPU Windows e il checkpoint ufficiale Qwen3-4B Q4_K_M. Le revisioni e i checksum sono conservati nel registro locale. Seleziona “Qwen3 · 4B Q4 · llama.cpp” nella Chat: il programma dimensiona il contesto del processo nativo secondo la selezione, include la sua memoria nel valore mostrato e lo termina con “Libera RAM”. La prima preparazione richiede tempo; la cache resta disponibile per richieste successive.

Il GGUF quantizzato viene letto da llama.cpp ed è una rappresentazione a precisione ridotta. Questo percorso non usa il decoder CMP e non prova un vantaggio esclusivo della nostra compressione lossless. La modalità CMP BF16 resta disponibile separatamente.
