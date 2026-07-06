#!/usr/bin/env bash
set -euo pipefail

QUEST_DIR="/Users/qixinchaye/Workspace/ymj8903668-droid-open-source/QUEST"
PYTHON="${QUEST_DIR}/.venv/bin/python"
UV="/Users/qixinchaye/.local/bin/uv"
MODE="${1:-status}"

cd "${QUEST_DIR}"

if [ ! -x "${PYTHON}" ]; then
  python3 -m venv .venv
fi

case "${MODE}" in
  status)
    "${PYTHON}" --version
    "${PYTHON}" - <<'PY'
mods = ["openai", "litellm", "requests", "transformers", "tiktoken", "tqdm", "json5", "qwen_agent", "sandbox_fusion", "pandas", "numpy", "torch", "vllm"]
for name in mods:
    try:
        mod = __import__(name)
        print(f"{name}: ok {getattr(mod, '__version__', '')}")
    except Exception as exc:
        print(f"{name}: missing {type(exc).__name__}: {str(exc)[:120]}")
PY
    ;;
  --install-lite|install-lite)
    if [ ! -x "${UV}" ]; then
      "${PYTHON}" -m pip install -r requirements-mac-lite.txt
    else
      "${UV}" pip install --python "${PYTHON}" -r requirements-mac-lite.txt
    fi
    ;;
  --install-full|install-full)
    echo "Installing full QUEST requirements, including torch/vllm. This can be large and slow." >&2
    if [ ! -x "${UV}" ]; then
      "${PYTHON}" -m pip install -r requirements.txt
    else
      "${UV}" pip install --python "${PYTHON}" -r requirements.txt
    fi
    ;;
  --smoke|smoke)
    "${PYTHON}" - <<'PY'
import sys
sys.path.insert(0, "inference")
import prompt
import tool_search
import tool_visit
import tool_memory
print("QUEST lightweight inference imports ok")
try:
    import torch
    print(f"torch ok {torch.__version__} mps_available={torch.backends.mps.is_available()}")
except Exception as exc:
    print(f"torch unavailable: {type(exc).__name__}: {str(exc)[:120]}")
PY
    ;;
  *)
    echo "Usage: $0 [status|--install-lite|--install-full|--smoke]" >&2
    exit 64
    ;;
esac
