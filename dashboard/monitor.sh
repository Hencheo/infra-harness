#!/bin/bash

# Harness Infrastructure Monitor
# Atalho para iniciar o Cockpit de monitoramento

echo "🚀 Iniciando Monitor de Orquestração Harness..."

# Ativa o ambiente virtual se existir na raiz
VENV_PATH="$SCRIPT_DIR/../.venv/bin/activate"
if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
fi

# Verifica se o Redis está rodando
if ! command -v redis-cli &> /dev/null || ! redis-cli ping &> /dev/null; then
    echo "⚠️ AVISO: Redis não detectado ou desligado. O rádio não funcionará."
fi

# Detecta o diretório onde o script está localizado
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Tenta localizar o executável do Python dentro do venv
PYTHON_VENV="$SCRIPT_DIR/../.venv/bin/python3"

if [ -f "$PYTHON_VENV" ]; then
    echo "🐍 Usando Python do ambiente virtual (.venv)..."
    "$PYTHON_VENV" "$SCRIPT_DIR/cockpit.py"
else
    echo "⚠️ .venv não encontrado na raiz. Tentando Python do sistema..."
    python3 "$SCRIPT_DIR/cockpit.py"
fi
