"""
Protocolos A2A (Agent-to-Agent) — Contratos Estritos de Comunicação.

Define schemas tipados para TODAS as mensagens que trafegam entre agentes,
substituindo a comunicação ad-hoc por contratos formais e validáveis.

Cada mensagem no Harness deve ser construída via uma factory deste módulo
e validada antes de ser publicada ou processada.

Referência: Análise de Lacunas, Seção 1 — "Externalização de Interação: Protocolos"
"""

from enum import Enum
from typing import Dict, Any, Optional, List, Tuple
import time


# ── Lifecycle States (Máquina de Estados) ────────────────────────
# Estados válidos para tarefas, fora do raciocínio do LLM.
# Ref: Seção 1.2 — "Semântica de Ciclo de Vida"

class TaskState(str, Enum):
    """Estados possíveis de uma tarefa no ciclo de vida do Harness."""
    INTENT = "intent"           # Intenção declarada, ainda não despachada
    DELEGATED = "delegated"     # Enviada ao agente alvo via EventBus
    ACCEPTED = "accepted"       # Agente alvo confirmou recebimento
    IN_PROGRESS = "in_progress" # Agente está executando
    SUCCESS = "success"         # Concluída com sucesso
    FAILED = "failed"           # Falhou
    HALTED = "halted"           # Interrompida por circuit breaker ou humano
    RETRY = "retry"             # Marcada para retry

# Transições válidas na máquina de estados (de → para)
VALID_TRANSITIONS = {
    TaskState.INTENT: [TaskState.DELEGATED],
    TaskState.DELEGATED: [TaskState.ACCEPTED, TaskState.FAILED],
    TaskState.ACCEPTED: [TaskState.IN_PROGRESS, TaskState.FAILED],
    TaskState.IN_PROGRESS: [TaskState.SUCCESS, TaskState.FAILED, TaskState.HALTED],
    TaskState.FAILED: [TaskState.RETRY, TaskState.HALTED],
    TaskState.RETRY: [TaskState.DELEGATED],
    TaskState.SUCCESS: [],  # Estado terminal
    TaskState.HALTED: [],   # Estado terminal
}


# ── Schemas de Mensagens ─────────────────────────────────────────

# Campos obrigatórios para cada tipo de mensagem A2A.
# A validação checa presença e tipo desses campos.

DELEGATION_SCHEMA = {
    "required": ["target_agent", "action", "dept"],
    "optional": ["execution_id", "params", "topic", "payload", "phase_id"],
    "types": {
        "target_agent": str,
        "action": str,
        "dept": str,
        "execution_id": (str, type(None)),
        "params": (dict, type(None)),
        "topic": (str, type(None)),
    }
}

RESULT_SCHEMA = {
    "required": ["agent_id", "step_id", "status"],
    "optional": ["execution_id", "data", "timestamp"],
    "types": {
        "agent_id": str,
        "step_id": str,
        "status": str,
        "execution_id": (str, type(None)),
        "data": (dict, type(None)),
    }
}

CONTEXT_RESET_SCHEMA = {
    "required": ["completed_phase", "reason"],
    "optional": ["completed_leader", "timestamp"],
    "types": {
        "completed_phase": str,
        "reason": str,
        "completed_leader": (str, type(None)),
    }
}

ALERT_SCHEMA = {
    "required": ["type", "step_id", "message"],
    "optional": ["execution_id", "retries", "max_retries", "timestamp"],
    "types": {
        "type": str,
        "step_id": str,
        "message": str,
    }
}

# Valores válidos para campos enumeráveis
VALID_STATUSES = {"success", "failed", "retry", "halted", "denied"}
VALID_ALERT_TYPES = {"CIRCUIT_BREAKER", "GUARDRAIL_VIOLATION", "RATE_LIMIT", "HUMAN_OVERRIDE"}


# ── Validação ────────────────────────────────────────────────────

def validate_message(payload: dict, schema: dict, msg_type: str = "message") -> Tuple[bool, str]:
    """
    Valida um payload contra um schema A2A.
    
    Retorna (True, "") se válido, ou (False, "motivo") se inválido.
    
    Ref: Seção 1.3 — "Captura e Normalização de Intenção"
    """
    if not isinstance(payload, dict):
        return False, f"[A2A] {msg_type}: Payload não é um dicionário (recebido: {type(payload).__name__})"
    
    # Checa campos obrigatórios
    for field in schema["required"]:
        if field not in payload:
            return False, f"[A2A] {msg_type}: Campo obrigatório ausente: '{field}'"
        if payload[field] is None:
            return False, f"[A2A] {msg_type}: Campo obrigatório '{field}' é None"
    
    # Checa tipos dos campos presentes
    type_rules = schema.get("types", {})
    for field, expected_type in type_rules.items():
        if field in payload and payload[field] is not None:
            if not isinstance(payload[field], expected_type):
                return False, (
                    f"[A2A] {msg_type}: Campo '{field}' tem tipo inválido "
                    f"(esperado: {expected_type}, recebido: {type(payload[field]).__name__})"
                )
    
    return True, ""


def validate_delegation(payload: dict) -> Tuple[bool, str]:
    """Valida um payload de delegação de tarefa."""
    return validate_message(payload, DELEGATION_SCHEMA, "DELEGATION")


def validate_result(payload: dict) -> Tuple[bool, str]:
    """Valida um payload de resultado de tarefa."""
    is_valid, reason = validate_message(payload, RESULT_SCHEMA, "RESULT")
    if not is_valid:
        return is_valid, reason
    
    # Validação semântica: status deve ser um valor reconhecido
    status = payload.get("status", "")
    if status not in VALID_STATUSES:
        return False, f"[A2A] RESULT: Status '{status}' não é válido. Válidos: {VALID_STATUSES}"
    
    return True, ""


def validate_alert(payload: dict) -> Tuple[bool, str]:
    """Valida um payload de alerta do sistema."""
    is_valid, reason = validate_message(payload, ALERT_SCHEMA, "ALERT")
    if not is_valid:
        return is_valid, reason
    
    alert_type = payload.get("type", "")
    if alert_type not in VALID_ALERT_TYPES:
        return False, f"[A2A] ALERT: Tipo '{alert_type}' não é válido. Válidos: {VALID_ALERT_TYPES}"
    
    return True, ""


# ── Factories (Construtores de Mensagem) ──────────────────────────
# Garantem que mensagens sempre nasçam no formato correto.

def build_delegation(
    target_agent: str,
    action: str,
    dept: str,
    params: Optional[Dict] = None,
    execution_id: Optional[str] = None,
    topic: Optional[str] = None,
    phase_id: Optional[str] = None,
) -> dict:
    """Constrói um payload de delegação A2A com timestamp automático."""
    return {
        "target_agent": target_agent,
        "action": action,
        "dept": dept,
        "params": params or {},
        "execution_id": execution_id,
        "topic": topic,
        "phase_id": phase_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def build_result(
    agent_id: str,
    step_id: str,
    status: str,
    data: Optional[Dict] = None,
    execution_id: Optional[str] = None,
) -> dict:
    """Constrói um payload de resultado A2A com timestamp automático."""
    return {
        "execution_id": execution_id,
        "step_id": step_id,
        "agent_id": agent_id,
        "status": status,
        "data": data or {},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def build_context_reset(
    completed_phase: str,
    reason: str,
    completed_leader: Optional[str] = None,
) -> dict:
    """Constrói um payload de reset de contexto A2A."""
    return {
        "completed_phase": completed_phase,
        "completed_leader": completed_leader,
        "reason": reason,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ── Teste rápido ──────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Testes do Protocolo A2A ===\n")
    
    # 1. Delegação válida
    msg = build_delegation("system-worker", "create_structure", "infra")
    ok, err = validate_delegation(msg)
    print(f"✅ Delegação válida: {ok}")
    
    # 2. Delegação inválida (sem target_agent)
    ok, err = validate_delegation({"action": "test", "dept": "infra"})
    print(f"❌ Delegação sem target: {ok} — {err}")
    
    # 3. Resultado válido
    msg = build_result("backend-worker", "create_api", "success", {"output": "ok"})
    ok, err = validate_result(msg)
    print(f"✅ Resultado válido: {ok}")
    
    # 4. Resultado com status inválido
    msg = build_result("worker", "step1", "maybe")
    ok, err = validate_result(msg)
    print(f"❌ Status inválido: {ok} — {err}")
    
    # 5. Payload não-dict
    ok, err = validate_delegation("isto é uma string")
    print(f"❌ Payload string: {ok} — {err}")
    
    print("\n=== Lifecycle States ===")
    for state in TaskState:
        transitions = VALID_TRANSITIONS.get(state, [])
        print(f"  {state.value} → {[t.value for t in transitions]}")
