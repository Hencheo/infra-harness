#!/bin/bash

# Cores para o terminal
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}🚀 Inicializando Exército Harness...${NC}"

# 1. Limpeza de Ambiente
echo "🧹 Limpando estados anteriores..."
python3 -c "import sqlite3; conn = sqlite3.connect('data/harness_state.db'); cursor = conn.cursor(); cursor.execute('DELETE FROM agent_state'); conn.commit(); conn.close()"

# Mata processos anteriores (se existirem)
pkill -f "agents/" || true

# 2. Sobe os Agentes em Background via UV (Tier 1 -> Tier 2 -> Tier 3)
echo "📡 Subindo Auditor Superior..."
PYTHONPATH=. uv run python -u agents/superior/superior_agent.py > logs/superior.log 2>&1 &

echo "📡 Subindo Líderes (Infra, Backend, Frontend, Data)..."
PYTHONPATH=. uv run python -u agents/leaders/infra_leader.py > logs/infra_leader.log 2>&1 &
PYTHONPATH=. uv run python -u agents/leaders/backend_leader.py > logs/backend_leader.log 2>&1 &
PYTHONPATH=. uv run python -u agents/leaders/frontend_leader.py > logs/frontend_leader.log 2>&1 &
PYTHONPATH=. uv run python -u agents/leaders/data_leader.py > logs/data_leader.log 2>&1 &

echo "📡 Subindo Workers (System, Backend, React, SQLite, Dependences)..."
PYTHONPATH=. uv run python -u agents/workers/system_worker.py > logs/system_worker.log 2>&1 &
PYTHONPATH=. uv run python -u agents/workers/backend_worker.py > logs/backend_worker.log 2>&1 &
PYTHONPATH=. uv run python -u agents/workers/react_worker.py > logs/react_worker.log 2>&1 &
PYTHONPATH=. uv run python -u agents/workers/sqlite_worker.py > logs/sqlite_worker.log 2>&1 &
PYTHONPATH=. uv run python -u agents/dependences/dependency_worker.py > logs/dependency_worker.log 2>&1 &

sleep 5
echo -e "${GREEN}✅ Todos os agentes estão em prontidão (via UV). Verifique o Cockpit!${NC}"

