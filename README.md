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
- Multi-file Qwen checkpoints through a `cmp-sharded-v1` JSON manifest. Each
  original safetensors part is compressed and verified separately.

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
The dedicated `.venv` inside Compressor supplies Torch, Transformers, psutil
and safetensors. For first setup or repair, double-click `Configura.cmd`.
The launcher checks dependencies and refuses incomplete interpreters instead
of silently switching to a Python without inference packages. The program
no longer depends on another Desktop project.
The DLL bootstrap explicitly loads the Visual C++ runtime before Torch,
including when launched with a clean Windows PATH.
The llama.cpp child process also receives the available local runtime DLL
directories in its own PATH. Keep the complete official `runtime/llama`
package together; copying only `llama-server.exe` is insufficient. This does
not change the system PATH. See [VALIDAZIONE.md](VALIDAZIONE.md) for the
Windows-only PATH regression and full Qwen3-4B startup check.

## Set up on another machine

Use Python 3.11 or 3.12, create a virtual environment, then:

```sh
python setup_env.py
# Windows:
.venv/Scripts/python.exe server.py --port 8765
```

On Windows, install Microsoft's supported Visual C++ Redistributable x64 if
the required runtime DLLs are absent ([official download guidance](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)). Keep the model's config and tokenizer
next to its original safetensors file. Compress with:

```sh
python compressione.py comprimi model.safetensors model.cmp
python compressione.py verifica model.cmp
```

Register the checkpoint using `register_model.py` (see API.md). No model weight
downloads occur. Configura.cmd can recover official config/tokenizer assets
for the known Qwen3-0.6B archive if the former Desktop project was removed.
Direct chat currently supports Qwen3 only; GGUF and
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

## Context window

The chat panel shows the current process memory and includes **Libera RAM del
modello** to discard cached numeric weights while keeping the service and
conversation open. It refuses to unload during an active operation. In RAM
mode, expanded weights intentionally remain resident until unloaded or replaced.

The context window is adjustable in the chat UI from **128 to 8,192 tokens**
(default 1,024). It includes the full chat template/history and the generated
answer. Increasing this limit does not preallocate the whole window, but long
prompts need more memory and CPU time. API clients can pass
`extra_body={"context_window": 2048}`. If little room remains, the response is
shortened; prompts that fill the window are rejected without silent truncation.

## Tests

To download and prepare the official dense Qwen3-1.7B checkpoint:

```sh
.venv/Scripts/python.exe download_qwen17.py
.venv/Scripts/python.exe compare_qwen_models.py
```

The download helper pins the upstream revision, verifies the official weight
SHA-256 values, compresses both safetensors parts and registers the manifest
for chat/API usage. It uses bounded HTTP ranges for large downloads. Model
assets and archives remain outside Git. The comparison uses six short tasks;
its exact-match score is not a general model ranking.

When a checkpoint ties its input and output embeddings, RAM mode now shares
the same tensor instead of keeping two copies, matching the standard model.

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


## v0.5 — persistent chat, task loop and comparisons

The interface supports Italian, English and Simplified Chinese. Conversations are saved locally, with optional lexical retrieval from earlier chats. Static multipage website tasks support checkpoints, continuations, step/token budgets, navigation repair and file/link checks. See [CHAT_AND_TASKS.md](CHAT_AND_TASKS.md).

CMP v2 adds Zstandard; old v1 archives remain readable. Official Qwen3-4B: 8,045.0 MB → 6,298.5 MB (−21.71%), full integrity verified. Download and register: `python download_qwen17.py --size 4 --codec zstd`.

[STUDY.md](STUDY.md) documents prior work, algorithms and limits of exclusivity. [CODEC_RESULTS.md](CODEC_RESULTS.md) compares identical BF16 and quantized samples. No inference throughput advantage over DwarfStar or llama.cpp has been demonstrated. Our codecs and upstream algorithms are not exclusive.

Real 4B inference and quality measurements: [QWEN4_RESULTS.md](QWEN4_RESULTS.md).


## v0.6

Scoped file tools, targeted edits, backend API tests and a trusted local gym-management template with SQLite, accounts, lessons and bookings. Optional official llama.cpp + Qwen3-4B Q4 runtime for faster coding loops. See [CHAT_AND_TASKS.md](CHAT_AND_TASKS.md) and [QWEN4_RESULTS.md](QWEN4_RESULTS.md). Quantized inference is separate from lossless CMP inference.
