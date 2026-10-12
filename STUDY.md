# Studio tecnico e confronto — 12 ottobre 2026

## Risultato verificabile

Compressione è un prototipo di archiviazione lossless e inferenza Qwen3 da blocchi indipendenti. Non abbiamo dimostrato che sia più veloce o consumi meno memoria dei migliori motori locali. Il vantaggio misurato è la riduzione dei file mantenendo i byte originali, e la possibilità di calcolare senza mantenere tutti i pesi decodificati nel processo. Quest'ultima proprietà ha precedenti e comporta un costo di lettura e decodifica.

Qwen3-1.7B: 4.063.515.592 → 3.220.307.683 byte, −20,7507% con DEFLATE, verificati CRC32 e SHA-256. Il picco RSS in cache RAM era circa 3,84 GB: la percentuale di risparmio su disco non è la percentuale di risparmio della RAM. Qwen3-0.6B diretto: una precedente risposta di tre token ha raggiunto 437,9 MB RSS, ma impiegato 67,6 s; non è una misura confrontabile con benchmark di generazione lunghi. Vedere MEMORY.md e QWEN17_RESULTS.md.

## Progetti simili

| Progetto | Tecniche e obiettivo | Rapporto con noi |
|---|---|---|
| [DwarfStar / ds4, Salvatore Sanfilippo](https://github.com/antirez/ds4) | Motore nativo dedicato a modelli specifici, quantizzazione, streaming SSD, cache KV, API e agente | Condivide l'obiettivo di inferenza locale e caricamento da disco. Modelli, precisione e hardware diversi: nessuna percentuale di vantaggio confrontabile |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | Inferenza C/C++, GGUF, quantizzazioni, CPU/GPU, server | Baseline pratica da misurare sullo stesso PC. Noi aggiungiamo accesso lossless a blocchi safetensors, ma non abbiamo un confronto token/s omogeneo |
| [FlexGen / FlexLLMGen](https://github.com/FMInference/FlexLLMGen) e [paper](https://arxiv.org/abs/2303.06865) | Offloading fra GPU, CPU e disco, compressione, ottimizzazione del throughput | Precedente per gerarchia di memoria; workload e hardware non equivalenti alla nostra chat CPU |
| [EIE, 2016](https://arxiv.org/abs/1602.01528) | Acceleratore per reti sparse compresse e condivisione dei pesi | Precedente dell'inferenza su rappresentazioni compresse; hardware dedicato, non il nostro formato |
| [Zstandard](https://github.com/facebook/zstd), [XZ](https://tukaani.org/xz/) | Codec lossless generici | Confronto sperimentale possibile sugli stessi byte; non motori LLM |

Il README corrente di ds4 descrive Metal, CUDA e ROCm e una selezione intenzionalmente limitata di modelli. La nostra ricerca identifica ds4 come un progetto pertinente di Sanfilippo; il riferimento dell'utente potrebbe essere a un suo altro progetto. Non attribuiamo i nostri risultati al suo software.

## Confronto lossless eseguito

Vedere CODEC_RESULTS.md e compare_codecs.py. Campioni deterministici di 32 × 1 MiB, distribuiti lungo ciascun file, identici per tutti i codec. Payload indipendenti con fallback raw; esclusi indice e framing. Tre decodifiche con confronto esatto, mediana. Tempi pilota durante altre attività, senza isolamento del carico.

| Campione | DEFLATE 6 | Zstandard 3 | XZ preset 3 |
|---|---:|---:|---:|
| Qwen3-0.6B BF16: risparmio | 20,59% | 21,90% | 26,30% |
| Qwen3-0.6B: decodifica e verifica MB/s | 125,1 | 365,1 | 18,4 |
| BitNet GGUF i2_s quantizzato: risparmio | 17,45% | 17,78% | 17,09% |
| BitNet GGUF: decodifica e verifica MB/s | 156,0 | 409,8 | 16,7 |

Sul campione Qwen Zstandard produce un payload circa 1,64% più piccolo del nostro vecchio DEFLATE e decodifica circa 2,92 volte più rapidamente. XZ produce circa 5,63% meno byte di Zstandard, ma decodifica circa 19,9 volte più lentamente. **Non abbiamo inventato un codec superiore:** l'ottimizzazione introdotta in CMP v2 è usare Zstandard mantenendo accesso per blocchi e verifiche. Non deduciamo questi moltiplicatori per l'intera inferenza.

Sul file BitNet quantizzato completo il vecchio CMP ha risparmiato il 14,76%. La prova dimostra compressibilità di quel file, non di ogni GGUF Q4 o Q8. Il nostro motore Qwen attuale interpreta BF16/F16/F32 safetensors; archiviare GGUF non implica supporto per inferirlo direttamente.

## Algoritmi effettivamente utilizzati

| Componente | Funzionamento | Origine / esclusività |
|---|---|---|
| CMP v1 | Blocchi tipicamente 1 MiB, zlib livello 6 o raw, indice JSON finale, lettura di intervalli | Contenitore implementato nel progetto; [DEFLATE combina LZ77 e Huffman](https://www.rfc-editor.org/info/rfc1951/), tecniche pubbliche |
| CMP v2 | Stessa struttura di accesso, codec Zstandard livello 3, marker/versione distinti | Zstandard è una dipendenza esterna; nessuna esclusività sul codec |
| Integrità | CRC32 per blocco e SHA-256 completo | Algoritmi noti; CRC non è autenticazione, SHA non firma l'archivio |
| Pesi | Parsing safetensors, mmap del compresso, decodifica strato per strato, embedding per righe, uscita a blocchi | Implementazione locale sopra PyTorch/Transformers; offloading, tiling e mmap sono tecniche note |
| Cache | KV cache della generazione, modalità RAM, condivisione embedding/output legati | Comportamenti e tecniche già presenti nell'ecosistema Transformer |
| Memoria conversazioni | SQLite, messaggi completi persistiti, selezione degli scambi recenti entro budget di token, estratti da altre chat per sovrapposizione di parole | Codice di integrazione del progetto; non ricerca semantica neuronale né memoria illimitata |
| Loop | Coda di file, continuazioni, checkpoint, budget di passaggi/token, controllo file e link, tentativi di riparazione | Implementazione del progetto; architettura agente nota, nessuna garanzia di completare task arbitrari |

Il calcolo richiede operandi numerici decodificati. In RAM ci sono anche runtime, attivazioni, cache KV, buffer e pagine del sistema operativo. La modalità diretta non carica l'intero modello numerico; la modalità RAM lo conserva intenzionalmente. Aumentare il contesto aumenta il costo della cache KV e, con attenzione eager, può aumentare molto il picco delle attivazioni.

## Esclusività, provenienza e licenze

La ricerca pubblica trova precedenti rilevanti: **non possiamo dichiarare esclusivi gli algoritmi o l'idea di inferenza con pesi compressi**. Il repository contiene la nostra implementazione e integrazione, ma non abbiamo effettuato una verifica legale di brevetti, una ricerca esaustiva del prior art o una certificazione indipendente di originalità. Non si devono promettere diritti esclusivi su tecniche e librerie upstream.

Le licenze del repository riguardano il codice del progetto nei limiti dei diritti disponibili. Non sostituiscono le licenze di modelli, librerie o standard; vedere THIRD_PARTY_NOTICES.md. La licenza didattica non commerciale è source available e non equivale a una licenza open source OSI. La licenza commerciale non conferisce diritti sui componenti di terzi. Zstandard viene usato tramite python-zstandard, separatamente attribuito.

## Protocollo per confrontare i migliori motori

Un confronto attendibile richiede stesso checkpoint/tokenizer, precisione e quantizzazione, prompt, contesto, numero di thread, hardware e carico. Registrare cold start separatamente, prefill tokens/s, decode tokens/s, tempo al primo token, qualità delle risposte, processo RSS e memoria complessiva, cache del sistema operativo e spazio su disco. Eseguire almeno tre ripetizioni dopo riscaldamento, e includere deviazioni.

Confrontare il nostro BF16 diretto con BF16 nativo e llama.cpp BF16; confrontare separatamente la stessa quantizzazione se aggiungiamo un motore quantizzato. DwarfStar richiede una macchina e un modello supportati: benchmark di Mac grandi o GPU non sono confrontabili con questo PC Windows da 16 GB. La classifica dei migliori software e il nostro vantaggio percentuale in inferenza restano **non misurati**.

Per 500B, i soli pesi teorici sono circa 1.000 GB a 16 bit o 250 GB a 4 bit, prima di scale, metadati e altri buffer. Applicare il nostro 20–22% a questi numeri sarebbe un'ipotesi, non un risultato. La memoria diretta dipende dalla dimensione dello strato e dagli altri buffer, non soltanto dalla dimensione dell'archivio. Modelli densi e MoE hanno comportamenti diversi.


## Aggiornamento sperimentale v0.6

È stato integrato un percorso opzionale llama.cpp con Qwen3-4B Q4_K_M ufficiale. Il confronto locale con il nostro BF16 mostra minore RAM e maggior throughput sui sei compiti, ma cambia anche la precisione e non è un confronto omogeneo fra motori. Vedere QWEN4_RESULTS.md per tempi di caricamento separati, RSS aggregato, punteggi e limiti. Il guadagno appartiene al runtime nativo e alla quantizzazione, non a CMP. Il loop ora dispone di file tools, verifiche HTTP e backend palestra gestito con SQLite; questi componenti di integrazione non rendono esclusive le architetture agenti o gli algoritmi upstream.
