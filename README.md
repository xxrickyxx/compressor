# Compressor

Local lossless compression for model files, with a web interface and an
experimental Qwen3 inference engine that reads weights from the compressed
archive. Windows-first prototype; CPU inference.

## What works

- Independent zlib/raw blocks, indexed random access, CRC32 per block and
  full-file SHA-256 verification.
- Compress, restore and verify without overwriting the source or an existing
  destination.
- A local chat interface and authenticated API with OpenAI-style model listing,
  chat completions and SSE streaming.
- Qwen3 safetensors inference from CMP archives, using layer-at-a-time weight
  decoding, row-at-a-time embeddings and a chunked output head.

## Memory: what this actually saves

The **compressed archive is mapped read-only**, not expanded into a complete
file or a complete resident model in direct mode. The operating system pages
compressed data on demand. Each decoder layer is temporarily reconstructed
as numeric tensors for CPU computation and released afterwards. Only requested
embedding rows are decoded; the output head is processed in 2,048-row chunks.

It is **not possible for this implementation to compute with only compressed
bytes in RAM**. Temporary decoded weights, activations, KV cache, logits and
the Python/Torch runtime also consume memory. Mapping size is not resident
memory; actual RSS depends on paging and allocator behavior. There is no
guarantee of hardware savings until measured on the target model and machine.
`compression_mode="ram"` intentionally retains the expanded weights and uses
more memory; `direct` is the default mode for lower parameter residency.

## Results on full local files

| Model file | Original MB | CMP MB | Saved |
|---|---:|---:|---:|
| Qwen3-0.6B safetensors | 1503.3 | 1194.7 | 20.53% |
| BitNet safetensors | 1178.6 | 927.9 | 21.27% |
| BitNet GGUF | 1187.8 | 1012.4 | 14.76% |
| Whisper tiny | 75.5 | 69.1 | 8.55% |

Every archive passed full SHA-256 verification. Storage results do not imply
inference acceleration. The previous direct implementation generated three
tokens in about 64 seconds on an 8 GB Windows machine; subsequent optimizations
must be benchmarked separately.

After the row/chunk optimization, one real direct-mode test recorded **437.9 MB
process RSS** and **31.5 MB temporary numeric weights** while generating three
tokens in 67.6 seconds. The 1,503.3 MB checkpoint was not held as a full resident
model. These are measurements from one machine, not a hardware guarantee;
see [MEMORY.md](MEMORY.md) for sampling limitations and reproduction details.

## Run on this Windows installation

Double-click `Avvia.cmd`. It starts the local service and opens the browser.
The installed environment in `Desktop/matrix_ia/.venv` supplies Torch and
Transformers. The launcher uses the locally installed Codex Python to start it.
The DLL bootstrap explicitly loads the Visual C++ runtime before Torch,
including when launched with a clean Windows PATH.

## Set up on another machine

Use Python 3.11 or 3.12, create a virtual environment, then:

```sh
python -m pip install -r requirements.txt
python server.py --port 8765
```

On Windows, install Microsoft's supported Visual C++ Redistributable x64 if
the required runtime DLLs are absent ([official download guidance](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)). Keep the model's config and tokenizer
next to its original safetensors file. Compress with:

```sh
python compressione.py comprimi model.safetensors model.cmp
python compressione.py verifica model.cmp
```

Register the checkpoint using `register_model.py` (see API.md). No automatic
model downloads occur. Direct chat currently supports Qwen3 only; GGUF and
BitNet archives can be compressed but are not supported for direct inference.

## API

Default base URL: `http://127.0.0.1:8765/v1`.
The first run creates a persistent secret in `api-key.txt`. Supply it as
`Authorization: Bearer YOUR_KEY`; do not commit or share it publicly.
The API tab shows connection details locally.

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8765/v1", api_key="YOUR_KEY")
response = client.chat.completions.create(
    model="qwen3-0.6b-cmp",
    messages=[{"role": "user", "content": "Scrivi Ciao."}],
    temperature=0, max_tokens=24,
)
print(response.choices[0].message.content)
```

`openai` is an optional client dependency. [API.md](API.md) documents endpoints,
streaming, asynchronous compression jobs and deliberate compatibility limits.
`openapi.json` provides the API schema. To bind on another interface explicitly,
use `python server.py --host YOUR_LAN_IP --port 8765 --no-browser`.
The web UI and internal file picker remain loopback-only; external API calls
require the secret. Use a TLS reverse proxy for deployments across untrusted
networks; this server does not implement TLS.

## Tests

```sh
python test_compressione.py
python -m unittest test_api.py
python test_engine.py
```

`test_engine.py` uses locally available Qwen tokenizer assets and compares
prefill and cached-token logits against a small reference Qwen3. Model files,
benchmarks, secrets, logs and native binaries are excluded from Git.

## Licensing

Free noncommercial educational, research and personal learning use is covered
by [LICENSE-NONCOMMERCIAL.txt](LICENSE-NONCOMMERCIAL.txt). Business use requires
an accepted commercial order under [LICENSE-COMMERCIAL.md](LICENSE-COMMERCIAL.md).
This is **source-available dual licensing**, not OSI open source: restricting
business use is incompatible with the [Open Source Definition](https://opensource.org/osd).
See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
