# Qwen3-4B — prova reale del 12 ottobre 2026

Checkpoint ufficiale [Qwen/Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B), revisione `1cfa9a7208912126459214e8b04321603b3df60c`. Tutti i download corrispondono agli SHA-256 LFS pubblicati. Tre archivi CMP v2 Zstandard, verifiche CRC32 e SHA-256 complete. Originali conservati sul disco per riproducibilità; inferenza letta dagli archivi, non dagli originali.

| Dato | Valore |
|---|---:|
| File originali | 8.044.982.000 byte |
| Archivi + indice | 6.298.455.884 byte |
| Risparmio disco | 21,7095% |
| Risposta diretta a 17 × 23 | 391 |
| Token generati in prova diretta | 3 |
| Tempo diretto, incluso EOS | 195,2 s |
| Picco RSS diretto, campionato ogni 100 ms | 633,6 MB |
| Massimo pesi numerici contabilizzati diretto | 201,9 MB |
| Byte numerici letti durante la risposta | 32,180 GB |

La decodifica dei pesi viene ripetuta a ogni passo: questo spiega il costo in tempo e I/O. Il picco RSS non comprende gli altri processi e la cache dei file del sistema operativo, e può non catturare un picco istantaneo. Contesto 1.024, prompt 33 token, CPU, quattro thread, generazione deterministica, thinking disattivato.

## Confronto breve con cache RAM

Stesse sei richieste, massimo 24 token, contesto 1.024, CPU e generazione deterministica. È un controllo locale, non un benchmark generale di qualità. Risultati 0.6B e 1.7B conservati dalla prova precedente sulla stessa macchina; le esecuzioni non sono state isolate da ogni altra attività.

| Modello | Risposte esatte | Picco RSS GB | Token/s dopo prima richiesta, incluso prefill |
|---|---:|---:|---:|
| Qwen3-0.6B | 2/6 | 1,57 | 1,25 |
| Qwen3-1.7B | 4/6 | 3,84 | 1,11 |
| Qwen3-4B | 5/6 | 8,47 | 0,25 |

Il 4B risponde correttamente a moltiplicazione, sequenza, logica, istruzione esatta e traduzione. Nella deduplicazione cambia gli elementi plurali in singolari (`mela,pera,banana`), quindi fallisce il confronto esatto. Il miglioramento di qualità su queste richieste ha un costo consistente in memoria e tempo; non dimostra un'ottimizzazione del motore né un vantaggio su llama.cpp.

La modalità RAM conserva circa 8,04 GB di pesi numerici. I 6,30 GB compressi su disco non diventano automaticamente un modello residente da 6,30 GB. Per liberare il modello usare “Libera RAM del modello”; per un uso a minore memoria scegliere “A strati”, accettando la lentezza misurata.

Riproduzione: `python measure_qwen4.py` per il test diretto e `python compare_qwen_models.py --models qwen3-4b-cmp` per i sei compiti in RAM. Dati grezzi locali in prove_modelli/qwen4_direct.json e prove_modelli/confronto_qwen.json. Richiede i pesi già scaricati; scaricamento `python download_qwen17.py --size 4 --codec zstd`.

SHA-256 delle tre parti originali: `328a91d3122359d5547f9d79521205bc0a46e1f79a792dfe650e99fc2d651223`, `6cd087b316306a68c562436b5492edbcf6e16c6dba3a1308279caa5a58e21ca5`, `e4bf436957184f4eeb86a80e9db394503f1f56446b2e6b7edeac5b81470f4ca1`.


## Percorso opzionale llama.cpp Q4_K_M

Runtime ufficiale b11573, [modello GGUF ufficiale](https://huggingface.co/Qwen/Qwen3-4B-GGUF), revisione `bc640142c66e1fdd12af0bd68f40445458f3869b`. File Q4_K_M: 2.497.280.256 byte. Riduzione della precisione rispetto al BF16: non è compressione lossless né inferenza CMP.

Stesse sei richieste, contesto effettivamente allocato 1.024, quattro thread CPU, massimo 24 token, temperatura zero, thinking disattivato. 5/6 risposte esatte, picco RSS aggregato processo Python + llama.cpp **4,874 GB**, throughput caldo **2,776 token/s incluso prefill**, contro 8,469 GB e 0,252 token/s del percorso BF16 RAM. In questo piccolo test: circa −42,45% RSS e 11,04 volte il throughput caldo. Cambiano sia motore sia precisione: non si può attribuire il guadagno al nostro algoritmo CMP o generalizzarlo a altri task.

L’avvio del processo nativo e caricamento sono durati 10,15 s, prima della prima richiesta da 1,60 s. Il BF16 caricava i pesi durante la prima richiesta: confrontare 1,60 s con 59,23 s senza includere il caricamento sarebbe scorretto. I tempi delle richieste native sono esclusivamente generazione + prefill dopo la preparazione.

Entrambi falliscono la stessa deduplicazione, con risposte leggermente diverse. Il punteggio non è una misura generale di conservazione della qualità dopo la quantizzazione. llama.cpp e il checkpoint mantengono le proprie licenze; nessuna esclusività su questa accelerazione.
