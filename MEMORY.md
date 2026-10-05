# Misura della memoria — 5 ottobre 2026

Prova locale Windows con Qwen3-0.6B, modalità `direct`, tre token generati
(“Ciao.”). PATH ridotto a Windows/System32 per verificare il bootstrap DLL.

| Quantità | Valore |
|---|---:|
| File originale | 1.503,3 MB |
| Archivio CMP | 1.194,7 MB |
| RSS del processo prima della generazione | 381,8 MB |
| Picco RSS rilevato durante la generazione | 437,9 MB |
| Massimo dei pesi numerici temporanei contabilizzati | 31,5 MB |
| Tempo della risposta, incluso il passo EOS | 67,6 s |
| Token generati | 3 |

MB indica 1.000.000 byte. RSS è memoria fisica del processo; viene campionata
ogni 100 ms e non garantisce di catturare tutti i picchi istantanei. Il valore
dei pesi temporanei conta tensori di pesi, non tutti i buffer del decoder.
La cache file del sistema operativo e gli altri processi non sono inclusi.

L’archivio viene mappato read-only e le mappature vengono rilasciate dopo la
lettura di ciascun tensore o blocco di righe. Il modello non viene ricostruito
come file e i suoi pesi non rimangono tutti residenti. Embedding e uscita sono
letti per righe/blocchi; gli altri pesi vengono decodificati per strato.

La prova dimostra che questo processo può generare senza tenere in RAM tutti
i 1.503 MB di pesi originali. **Non significa che in RAM ci siano soltanto byte
compressi:** CPU, Torch, attivazioni, cache KV e lo strato corrente richiedono
memoria numerica. Non è un confronto completo con altri motori e non dimostra
un incremento dei token/s. La modalità RAM ha intenzionalmente un consumo diverso.

Riproduzione: `python measure_inference.py` nella cartella con le prove e i
checkpoint locali. Dati grezzi: `prove_modelli/memoria_inferenza.json`.
