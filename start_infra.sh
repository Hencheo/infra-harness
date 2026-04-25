#!/bin/bash

# Harness Infrastructure Setup & Start
# Este script prepara o ambiente e sobe o Redis

echo "🛠️ Preparando infraestrutura do Harness..."

echo "🔌 Preparando ambiente..."
if [ ! -d ".venv" ]; then
    uv venv .venv
fi

# 2. Instala dependências do Python via uv (Apontando direto para o binário do venv)
echo "📦 Instalando bibliotecas essenciais..."
uv pip install --python .venv/bin/python3 redis rich agno openai python-dotenv fireworks-ai

# 3. Garante pastas necessárias
mkdir -p data
echo "📡 Iniciando Servidor Redis..."

# Tenta via Docker (Recomendado)
if command -v docker &> /dev/null; then
    echo "🐳 Detectado Docker. Subindo container Redis..."
    docker run --name harness-redis -p 6379:6379 -d redis &> /dev/null || docker start harness-redis
    echo "✅ Redis rodando via Docker na porta 6379."
else
    # Tenta via serviço local se o Docker não existir
    echo "🖥️ Docker não encontrado. Tentando serviço local..."
    if command -v redis-server &> /dev/null; then
        redis-server --daemonize yes
        echo "✅ Redis rodando via redis-server local."
    else
        echo "❌ ERRO: Redis não encontrado. Por favor, instale o Redis ou o Docker."
        exit 1
    fi
fi

echo "🚀 Infraestrutura pronta! Agora você pode rodar o cockpit e os agentes."
