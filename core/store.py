import sqlite3
import json
import os
from typing import Any, Optional, Dict
from datetime import datetime

class StateStore:
    """
    Componente de Persistência (State Store) do Harness.
    Garante que os agentes tenham "memória" persistente entre execuções.
    """
    def __init__(self, db_path: str = "data/harness_state.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """
        Inicializa o banco de dados e as tabelas necessárias.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Tabela principal de estado dos agentes conforme ARQUITETURA_HARNESS.txt
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(agent_id, session_id, key)
                )
            """)
            conn.commit()

    def set_state(self, agent_id: str, session_id: str, key: str, value: Any):
        """
        Salva ou atualiza um fragmento de estado.
        """
        json_value = json.dumps(value)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agent_state (agent_id, session_id, key, value, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(agent_id, session_id, key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
            """, (agent_id, session_id, key, json_value, datetime.now().isoformat()))
            conn.commit()
            print(f"[StateStore] Salvo: {agent_id}/{key} em {session_id}")

    def get_state(self, agent_id: str, session_id: str, key: str) -> Optional[Any]:
        """
        Recupera um fragmento de estado.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT value FROM agent_state 
                WHERE agent_id = ? AND session_id = ? AND key = ?
            """, (agent_id, session_id, key))
            result = cursor.fetchone()
            if result:
                return json.loads(result[0])
        return None

    def get_all_agent_state(self, agent_id: str, session_id: str) -> Dict[str, Any]:
        """
        Recupera todo o estado de um agente em uma sessão específica.
        """
        states = {}
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT key, value FROM agent_state 
                WHERE agent_id = ? AND session_id = ?
            """, (agent_id, session_id))
            for key, value in cursor.fetchall():
                states[key] = json.loads(value)
        return states

# Teste rápido
if __name__ == "__main__":
    store = StateStore()
    
    # Simula salvando estado de um agente
    store.set_state("hermes-01", "sessao-abc", "objetivo", "Monitorar servidores")
    store.set_state("hermes-01", "sessao-abc", "tasks_completas", ["setup", "auth"])
    
    # Recupera
    objetivo = store.get_state("hermes-01", "sessao-abc", "objetivo")
    print(f"[Teste] Objetivo recuperado: {objetivo}")
    
    tudo = store.get_all_agent_state("hermes-01", "sessao-abc")
    print(f"[Teste] Estado completo: {tudo}")
