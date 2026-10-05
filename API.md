# API v0.3

Il servizio ascolta per impostazione predefinita su `127.0.0.1:8765`.
La chiave persistente è in `api-key.txt`; la scheda API dell’interfaccia mostra
URL, modello e chiave. Non inserire la chiave in Git o in codice pubblico.

Tutte le chiamate `/v1/*` e `/openapi.json` richiedono:

```http
Authorization: Bearer LA_TUA_CHIAVE
```

## Modelli e chat

`GET /v1/models` restituisce una lista compatibile con il formato OpenAI.
Il modello locale già registrato è `qwen3-0.6b-cmp`.

`POST /v1/chat/completions`:

```json
{
  "model": "qwen3-0.6b-cmp",
  "messages": [{"role": "user", "content": "Scrivi Ciao."}],
  "max_tokens": 24,
  "temperature": 0,
  "stream": false,
  "compression_mode": "direct"
}
```

La risposta contiene `choices[0].message.content`, `finish_reason` e `usage`.
Con `stream: true` il servizio restituisce eventi SSE `data: {...}` con
`choices[0].delta.content`, un evento conclusivo e `data: [DONE]`.
Durante le attese lunghe invia commenti SSE keep-alive. Se il client interrompe
uno stream e il server rileva la disconnessione, annulla la relativa generazione.

`compression_mode` è un’estensione: `direct` usa pesi temporanei a strati;
`ram` conserva i pesi decodificati. I client OpenAI possono inviarla tramite
`extra_body={"compression_mode": "direct"}`. Il default è `direct`.

Supportati: messaggi testuali `system`, `user`, `assistant`; una risposta;
generazione deterministica `temperature=0`; massimo 128 token di risposta e
512 token di contesto. Non supportati: tools, immagini, audio, JSON strutturato,
embeddings e generazione multipla. Le opzioni non implementate non costituiscono
garanzie di compatibilità completa con qualsiasi prodotto.

Una sola operazione può eseguire per volta. Conflitti restituiscono HTTP 409;
chiavi non valide HTTP 401; richieste non valide HTTP 400. Dopo l’avvio di uno
stream, eventuali errori sono eventi SSE con un campo `error`.

Esempio SDK opzionale:

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8765/v1", api_key="LA_TUA_CHIAVE")
for event in client.chat.completions.create(
    model="qwen3-0.6b-cmp", messages=[{"role":"user","content":"Ciao!"}],
    max_tokens=24, temperature=0, stream=True,
):
    if event.choices[0].delta.content:
        print(event.choices[0].delta.content, end="", flush=True)
```

Imposta timeout lunghi nel client: la modalità diretta è sperimentale e lenta.

## Compressione asincrona

`POST /v1/jobs` accetta:

```json
{
  "action": "compress",
  "source": "C:\\modelli\\model.safetensors",
  "target": "C:\\modelli\\model.cmp"
}
```

Risposta HTTP 202: `{"id":"ID_OPERAZIONE","object":"job"}`.
`action` può essere `compress`, `extract`, `verify`. `verify` non richiede
`target`. I percorsi si riferiscono al **computer del server**, non al client.
La chiave API autorizza accesso ai file con i permessi del processo: consegnala
solo a integrazioni fidate.

`GET /v1/jobs/ID` restituisce `busy`, `phase`, `progress`, `result`, `error`.
`POST /v1/jobs/ID/cancel` con corpo `{}` richiede l’annullamento del lavoro
attivo. Sono conservate in memoria le ultime 20 operazioni; il riavvio le azzera.

## Registrare un altro checkpoint Qwen3

```sh
python register_model.py --archive model.cmp --config-dir percorso_checkpoint --id mio-qwen --label "Il mio Qwen"
```

Il comando verifica l’archivio e registra il modello in `models.json`, escluso
da Git perché contiene percorsi locali. Servono config e tokenizer del checkpoint
originale. Se presente, `models.json` sostituisce l’elenco delle prove locali.

## Connessioni da altri computer

L’avvio normale resta locale. Per la LAN scegli esplicitamente l’interfaccia:

```sh
python server.py --host 192.168.1.10 --port 8765 --no-browser
```

Usa quindi `http://192.168.1.10:8765/v1` nel client e la chiave API. L’interfaccia
web e `/api/*` restano disponibili soltanto da loopback. Non vengono aperte
porte firewall automaticamente e non viene attivato CORS indiscriminato.
Il servizio non implementa HTTPS: un’esposizione Internet richiede un reverse
proxy TLS e gestione dell’accesso adeguata al deployment.

`GET /health` è un controllo di disponibilità, senza segreti o dati dei modelli.
Non verifica che Torch o il modello siano caricati. `/openapi.json` descrive
le API autenticate.
