#!/bin/bash
# Atalho para o Log Daemon do Harness

# Cores
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}📡 Conectando ao rádio central de logs...${NC}"

# Executa o daemon usando o ambiente python atual
python3 dashboard/log_daemon.py
