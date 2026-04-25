#!/bin/bash

# Cores para o terminal
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

MISSION_NAME=${1:-"Task Manager V1"}
MISSION_DATA=${2:-"Inicie o projeto Task Manager conforme a SUPREME_SPEC.md"}
EXEC_ID=${3:-"M-$(date +%s)"}

echo -e "${YELLOW}🔥 Disparando Missão: ${MISSION_NAME}...${NC}"

PYTHONPATH=. uv run python -c "
import json, redis
r = redis.Redis(host='localhost', port=6379, decode_responses=True)
mission = {
    'agent_id': 'USER',
    'action': 'START_MISSION',
    'data': '$MISSION_DATA',
    'execution_id': '$EXEC_ID'
}
r.publish('harness.audit.leader', json.dumps(mission))
"

echo -e "${GREEN}🎯 Sinal enviado (ID: $EXEC_ID)! Acompanhe o fluxo no Cockpit.${NC}"
