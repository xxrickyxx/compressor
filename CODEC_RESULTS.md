# Confronto codec: prova pilota

32 blocchi da 1 MiB distribuiti uniformemente per ciascun file, stesso campione per tutti i codec. Blocchi indipendenti, fallback raw se non conviene. Dimensioni solo payload: esclusi indici e framing CMP. Tempi non sono token/s. Misura pilota durante altre attività, non classifica controllata. SHA-256 e offset nel JSON; verifica byte per byte, tre decodifiche, mediana.

| Modello | Codec | Risparmio campione | Compressione MB/s | Decodifica + confronto MB/s |
|---|---|---:|---:|---:|
| qwen3-0.6b-cmp | DEFLATE/zlib6 (CMP payload) | 20.59% | 8.4 | 125.1 |
| qwen3-0.6b-cmp | Zstandard3 | 21.90% | 264.1 | 365.1 |
| qwen3-0.6b-cmp | XZ/LZMA2 preset3 | 26.30% | 3.4 | 18.4 |
| BitNet GGUF i2_s | DEFLATE/zlib6 (CMP payload) | 17.45% | 17.4 | 156.0 |
| BitNet GGUF i2_s | Zstandard3 | 17.78% | 204.9 | 409.8 |
| BitNet GGUF i2_s | XZ/LZMA2 preset3 | 17.09% | 3.4 | 16.7 |

Questi campioni non autorizzano a estrapolare il rapporto a tutto il modello, a tutte le quantizzazioni o a 500B. XZ e Zstd qui sono codec per blocchi, non benchmark di llama.cpp.