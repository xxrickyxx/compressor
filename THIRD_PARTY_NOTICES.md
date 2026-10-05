# Third-party components

Compressor's dual licensing covers only its original code. This repository
does not include downloaded model weights, tokenizer assets, Torch binaries,
DLL runtimes, the matrix_ia project or its virtual environment.

- Python and its standard library retain their PSF license terms.
- PyTorch, Transformers, safetensors and psutil retain their own upstream
  licenses. Install and distribute them according to those terms.
- Qwen and any other model or tokenizer remain subject to the license supplied
  with the particular checkpoint. A Compressor commercial order does not
  authorize otherwise restricted model usage.
- Microsoft Visual C++ runtime libraries retain Microsoft's terms. The runtime
  bootstrap searches local installed libraries; it does not redistribute them.

Check the notices included with each installed version before redistributing
an application containing those components.
