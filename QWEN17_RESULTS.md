# Prova locale: Qwen3-1.7B su 16 GB RAM

12 ottobre 2026. Windows, CPU, cache RAM, contesto 1.024, massimo 24 token
per risposta, generazione deterministica. Un modello caricato per volta.

Scelto il checkpoint ufficiale [Qwen/Qwen3-1.7B](https://huggingface.co/Qwen/Qwen3-1.7B):
architettura densa, 1,7 miliardi di parametri dichiarati, compatibile con il motore
Qwen3 esistente. Non è una classifica globale dei modelli vicini a 1B.
Revision: `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`.

| Misura | Qwen3-0.6B | Qwen3-1.7B |
|---|---:|---:|
| File ufficiali originali | 1.503,3 MB | 4.063,5 MB |
| Archivi CMP e indice | 1.194,7 MB | 3.220,3 MB |
| Risparmio su disco | 20,53% | 20,75% |
| Picco RSS del processo rilevato | 1.571,7 MB | 3.837,7 MB |
| Token/s dopo la prima richiesta | 1,25 | 1,11 |
| Prima richiesta, incluso caricamento dei pesi | 20,2 s | 42,6 s |
| Risposte nel formato esatto richiesto | 2/6 | 4/6 |

MB indica 1.000.000 byte. RSS è campionata ogni 100 ms; non comprende la cache
file del sistema operativo né altri processi. La velocità include il calcolo
del prompt e la risposta, non è una misura della sola decodifica dei token.
Sono test brevi su un singolo computer, non garanzie di prestazioni.

Le sei prove riguardano moltiplicazione, sequenza, confronto logico, istruzione
esatta, elementi distinti in ordine e traduzione. Qwen1.7 calcola 391 nella
moltiplicazione ma scrive anche l’espressione; il criterio esatto lo segna come
fallimento di formato. Una risposta verbosa sulla sequenza viene tagliata dal
limite di 24 token: questo punteggio non misura ogni capacità del modello.

La maggiore accuratezza osservata ha un costo di memoria e velocità. Il nostro
motore usa BF16 e non applica ulteriore quantizzazione in questa prova. La
compressione è senza perdita e tutti gli archivi passano CRC32/SHA-256.

Il checkpoint ha due file safetensors. Sono compressi separatamente e collegati
da un indice `cmp-sharded-v1`; il motore può caricare il tensore dalla parte
corretta. In RAM, embedding e uscita condividono i pesi quando previsto dalla
configurazione, evitando una copia numerica duplicata.

Nella diagnosi iniziale, il processo del servizio con Qwen0.6 occupava circa
2 GB, contro quasi 12 GB usati dall’intero sistema. Il modello non spiegava
tutta la RAM occupata. Il pulsante **Libera RAM del modello** permette di
scaricare i pesi senza chiudere il servizio e rifiuta l’operazione durante
un’inferenza attiva.

Dati completi locali: `prove_modelli/confronto_qwen.json`,
`prove_modelli/CONFRONTO_QWEN.md`, `prove_modelli/qwen17_compression.json`.
Riproduzione: `download_qwen17.py`, poi `compare_qwen_models.py` con l’ambiente
dedicato. File dei modelli e chiavi API sono esclusi da Git.
