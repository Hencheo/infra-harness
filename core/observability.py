"""
Observabilidade Estruturada — Traces de Execução e Métricas do Harness.

Captura todos os eventos significativos do ciclo de vida dos agentes em 
formato estruturado (JSONL), permitindo rastreamento causal completo
do fluxo de execução sem depender de re-polling do workspace.

Cada evento possui:
- trace_id: identificador único do evento
- parent_id: link causal ao evento que o originou (cadeia de causalidade)
- agent_id: quem emitiu o evento
- event_type: classificação (DELEGATION, RESULT, PHASE_TRANSITION, etc.)
- metadata: dados específicos do evento

Referência: Análise de Lacunas, Seção 2.3 — "Observabilidade e Traces de Execução Estruturados"
"""

import json
import os
import uuid
import time
import threading
from typing import Dict, Any, Optional, List
from enum import Enum
from collections import defaultdict


# ── Tipos de Evento ──────────────────────────────────────────────

class EventType(str, Enum):
    """Classificação de todos os eventos rastreáveis no Harness."""
    # Ciclo de vida de tarefas
    TASK_DELEGATED = "task.delegated"
    TASK_ACCEPTED = "task.accepted"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    
    # Controle de fluxo
    PHASE_STARTED = "phase.started"
    PHASE_COMPLETED = "phase.completed"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    
    # Intervenções do Harness
    CIRCUIT_BREAKER = "harness.circuit_breaker"
    RETRY = "harness.retry"
    CONTEXT_RESET = "harness.context_reset"
    GUARDRAIL_BLOCKED = "harness.guardrail_blocked"
    
    # Observações
    RATE_LIMIT = "agent.rate_limit"
    LLM_CALL = "agent.llm_call"
    VERIFICATION = "harness.verification"


# ── Trace Event ──────────────────────────────────────────────────

def _create_event(
    event_type: EventType,
    agent_id: str,
    metadata: Optional[Dict] = None,
    parent_id: Optional[str] = None,
    execution_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Cria um evento de trace estruturado.
    
    Cada evento é auto-contido e imutável após criação.
    """
    return {
        "trace_id": str(uuid.uuid4())[:12],
        "parent_id": parent_id,
        "execution_id": execution_id,
        "event_type": event_type.value if isinstance(event_type, EventType) else event_type,
        "agent_id": agent_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "epoch_ms": int(time.time() * 1000),
        "metadata": metadata or {},
    }


# ── Trace Collector (Singleton) ──────────────────────────────────

class TraceCollector:
    """
    Coletor central de traces de execução.
    
    Thread-safe, escreve em JSONL para persistência e mantém um buffer
    em memória para consultas rápidas de métricas.
    
    Uso:
        from core.observability import tracer
        
        trace_id = tracer.emit(EventType.TASK_STARTED, "backend-worker", 
                               {"action": "create_api"}, execution_id="abc123")
        
        # Depois, ao completar:
        tracer.emit(EventType.TASK_COMPLETED, "backend-worker", 
                    {"result": "success"}, parent_id=trace_id, execution_id="abc123")
    """
    
    def __init__(self, log_path: str = "logs/traces.jsonl", buffer_size: int = 500):
        self._log_path = log_path
        self._lock = threading.Lock()
        self._buffer: List[Dict] = []
        self._buffer_size = buffer_size
        self._counters: Dict[str, int] = defaultdict(int)
        self._phase_timers: Dict[str, float] = {}  # phase_id → start_epoch
        
        # Garante que o diretório de logs existe
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
    
    def emit(
        self,
        event_type: EventType,
        agent_id: str,
        metadata: Optional[Dict] = None,
        parent_id: Optional[str] = None,
        execution_id: Optional[str] = None,
    ) -> str:
        """
        Emite um evento de trace.
        
        Persiste em JSONL e mantém no buffer em memória.
        Retorna o trace_id gerado para encadeamento causal.
        """
        event = _create_event(event_type, agent_id, metadata, parent_id, execution_id)
        trace_id = event["trace_id"]
        
        with self._lock:
            # Atualiza contadores
            self._counters[event["event_type"]] += 1
            self._counters["_total"] += 1
            
            # Buffer em memória (circular)
            self._buffer.append(event)
            if len(self._buffer) > self._buffer_size:
                self._buffer = self._buffer[-self._buffer_size:]
            
            # Persistência em JSONL (append-only)
            try:
                with open(self._log_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
            except Exception as e:
                print(f"[Tracer] ⚠️ Falha ao persistir trace: {e}")
        
        # Log compacto no console
        meta_preview = str(metadata)[:80] if metadata else ""
        print(f"[Trace] {event['event_type']} | {agent_id} | {meta_preview}")
        
        return trace_id
    
    # ── Phase Timing ─────────────────────────────────────────────
    
    def start_phase_timer(self, phase_id: str):
        """Inicia o cronômetro de uma fase."""
        self._phase_timers[phase_id] = time.time()
    
    def stop_phase_timer(self, phase_id: str) -> Optional[float]:
        """Para o cronômetro e retorna a duração em segundos."""
        start = self._phase_timers.pop(phase_id, None)
        if start:
            duration = time.time() - start
            return round(duration, 2)
        return None
    
    # ── Métricas Agregadas ───────────────────────────────────────
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Retorna métricas agregadas do Harness.
        
        Ideal para o Cockpit/Dashboard ou para injetar no contexto
        do Superior Agent como base de decisão.
        """
        with self._lock:
            total = self._counters.get("_total", 0)
            
            # Conta sucessos e falhas
            successes = self._counters.get(EventType.TASK_COMPLETED.value, 0)
            failures = self._counters.get(EventType.TASK_FAILED.value, 0)
            retries = self._counters.get(EventType.RETRY.value, 0)
            circuit_breaks = self._counters.get(EventType.CIRCUIT_BREAKER.value, 0)
            guardrail_blocks = self._counters.get(EventType.GUARDRAIL_BLOCKED.value, 0)
            
            # Taxa de sucesso
            task_total = successes + failures
            success_rate = round((successes / task_total * 100) if task_total > 0 else 0, 1)
            
            return {
                "total_events": total,
                "task_successes": successes,
                "task_failures": failures,
                "success_rate_pct": success_rate,
                "retries": retries,
                "circuit_breaker_activations": circuit_breaks,
                "guardrail_blocks": guardrail_blocks,
                "events_by_type": dict(self._counters),
                "active_phase_timers": list(self._phase_timers.keys()),
            }
    
    def get_recent_events(self, n: int = 20, event_type: Optional[str] = None) -> List[Dict]:
        """
        Retorna os N eventos mais recentes, opcionalmente filtrados por tipo.
        """
        with self._lock:
            if event_type:
                filtered = [e for e in self._buffer if e["event_type"] == event_type]
                return filtered[-n:]
            return self._buffer[-n:]
    
    def get_agent_trace(self, agent_id: str, n: int = 20) -> List[Dict]:
        """
        Retorna os últimos N eventos de um agente específico.
        Útil para diagnosticar problemas de um agente individual.
        """
        with self._lock:
            filtered = [e for e in self._buffer if e["agent_id"] == agent_id]
            return filtered[-n:]
    
    def get_execution_trace(self, execution_id: str) -> List[Dict]:
        """
        Retorna todos os eventos de uma execução específica.
        Reconstrói a cadeia causal completa de um workflow.
        """
        with self._lock:
            return [e for e in self._buffer if e.get("execution_id") == execution_id]


# Singleton
tracer = TraceCollector()


# ── Teste rápido ──────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Testes de Observabilidade ===\n")
    
    # Simula um fluxo completo
    t = TraceCollector(log_path="logs/test_traces.jsonl")
    
    # 1. Workflow inicia
    wf_id = t.emit(EventType.WORKFLOW_STARTED, "engine", 
                    {"workflow": "Harness Master SDD"}, execution_id="exec-001")
    
    # 2. Fase 1 inicia
    t.start_phase_timer("PHASE_1_INFRA")
    p1_id = t.emit(EventType.PHASE_STARTED, "superior-agent",
                    {"phase": "PHASE_1_INFRA", "leader": "infra-leader"},
                    parent_id=wf_id, execution_id="exec-001")
    
    # 3. Delegação
    d_id = t.emit(EventType.TASK_DELEGATED, "infra-leader",
                   {"target": "system-worker", "action": "create_structure"},
                   parent_id=p1_id, execution_id="exec-001")
    
    # 4. Task inicia e completa
    t.emit(EventType.TASK_STARTED, "system-worker",
           {"action": "create_structure"}, parent_id=d_id, execution_id="exec-001")
    
    time.sleep(0.1)  # Simula trabalho
    
    t.emit(EventType.TASK_COMPLETED, "system-worker",
           {"result": "8 dirs criados"}, parent_id=d_id, execution_id="exec-001")
    
    # 5. Fase completa
    duration = t.stop_phase_timer("PHASE_1_INFRA")
    t.emit(EventType.PHASE_COMPLETED, "superior-agent",
           {"phase": "PHASE_1_INFRA", "duration_s": duration},
           parent_id=p1_id, execution_id="exec-001")
    
    # 6. Simula uma falha e retry
    fail_id = t.emit(EventType.TASK_FAILED, "backend-worker",
                      {"error": "timeout"}, execution_id="exec-001")
    t.emit(EventType.RETRY, "engine",
           {"step": "create_api", "attempt": 2}, parent_id=fail_id, execution_id="exec-001")
    
    # Métricas
    print("\n--- Métricas Agregadas ---")
    metrics = t.get_metrics()
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    
    # Trace de execução
    print(f"\n--- Trace da Execução exec-001 ({len(t.get_execution_trace('exec-001'))} eventos) ---")
    for ev in t.get_execution_trace("exec-001"):
        print(f"  [{ev['trace_id']}] {ev['event_type']} | {ev['agent_id']}")
    
    # Limpa arquivo de teste
    try:
        os.remove("logs/test_traces.jsonl")
    except:
        pass
    
    print("\n✅ Todos os testes de observabilidade passaram!")
