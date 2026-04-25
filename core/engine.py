import yaml
import uuid
import os
import time
from typing import Dict, List, Any, Optional
from core.event_bus import EventBus
from core.store import StateStore
from core.verifier import verifier
from core.feature_tracker import feature_tracker
import threading

class WorkflowEngine:
    """
    O Cérebro do Harness. 
    Lê definições de DAG (YAML) e gerencia a execução dos workflows.
    """
    # ── Circuit Breaker Defaults ──────────────────────────────────────
    DEFAULT_MAX_RETRIES = 3        # Máximo de tentativas por step antes de parar
    DEFAULT_RETRY_COOLDOWN = 10    # Segundos de espera entre retries
    # ─────────────────────────────────────────────────────────────────

    def __init__(self, event_bus: EventBus, state_store: StateStore):
        self.bus = event_bus
        self.store = state_store
        self.active_workflows: Dict[str, Dict] = {}
        # Circuit Breaker: contadores de retry por (execution_id, step_id)
        self._retry_counts: Dict[str, int] = {}

    def load_workflow(self, file_path: str) -> Dict:
        """
        Lê e valida o arquivo YAML do workflow.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Workflow não encontrado: {file_path}")
        
        with open(file_path, 'r') as f:
            workflow_def = yaml.safe_load(f)
        
        print(f"[Engine] Workflow carregado: {workflow_def.get('name')}")
        return workflow_def

    def execute(self, workflow_path: str):
        """
        Inicia a execução de um workflow.
        """
        workflow_def = self.load_workflow(workflow_path)
        execution_id = str(uuid.uuid4())
        
        # Lê limites de circuit breaker do YAML (ou usa defaults)
        cb_config = workflow_def.get('circuit_breaker', {})
        max_retries = cb_config.get('max_retries', self.DEFAULT_MAX_RETRIES)
        retry_cooldown = cb_config.get('retry_cooldown_seconds', self.DEFAULT_RETRY_COOLDOWN)

        # Estado inicial do workflow
        execution_state = {
            "execution_id": execution_id,
            "name": workflow_def['name'],
            "status": "RUNNING",
            "current_step_index": 0,
            "steps": workflow_def['steps'],
            "results": {},
            "max_retries": max_retries,
            "retry_cooldown": retry_cooldown,
        }
        
        # Salva o estado inicial na Store
        self.store.set_state("engine", execution_id, "workflow_context", execution_state)
        
        # Dispara o primeiro passo
        self._dispatch_step(execution_id, execution_state)
        
        return execution_id

    def start_coordinator(self):
        """
        Inicia o loop de coordenação para ouvir resultados dos agentes.
        """
        print("[Engine] Coordenador iniciado. Ouvindo resultados...")
        self.bus.subscribe("harness.results", self._handle_agent_result)

    def _handle_agent_result(self, result_payload: Dict):
        """
        Processa o resultado vindo de um agente ou sistema.
        """
        exec_id = result_payload.get("execution_id")
        step_id = result_payload.get("step_id")
        status = result_payload.get("status") # ex: "success", "failed", "retry"
        
        print(f"[Engine] Resultado recebido de {step_id}: {status}")
        
        # Recupera o estado atual
        state = self.store.get_state("engine", exec_id, "workflow_context")
        if not state:
            print(f"[Erro] Contexto não encontrado para {exec_id}")
            return

        # Salva o resultado do passo
        state['results'][step_id] = result_payload.get("data")
        
        # --- VERIFICAÇÃO DETERMINÍSTICA (FASE 3 - CAMADA V) ---
        is_valid = verifier.verify(step_id, result_payload.get("data"))
        if not is_valid:
            print(f"[Verifier] ❌ FALHA DETECTADA no passo {step_id}. Acionando Ralph Loop...")
            # Armazena o erro para feedback no próximo loop
            state['last_error'] = {
                "step_id": step_id,
                "msg": "Falha na verificação determinística (Sintaxe, Integridade ou Existência)."
            }
            status = "failed"
        # ------------------------------------------------------

        # ── CIRCUIT BREAKER: Ralph Loop com limite rígido de retries ──
        if status == "failed" or result_payload.get("needs_retry", False):
            retry_key = f"{exec_id}::{step_id}"
            self._retry_counts[retry_key] = self._retry_counts.get(retry_key, 0) + 1
            current_retries = self._retry_counts[retry_key]
            max_retries = state.get('max_retries', self.DEFAULT_MAX_RETRIES)
            cooldown = state.get('retry_cooldown', self.DEFAULT_RETRY_COOLDOWN)

            if current_retries > max_retries:
                # ⛔ CIRCUIT BREAKER ATIVADO — para tudo
                state['status'] = "HALTED_CIRCUIT_BREAKER"
                state['halted_step'] = step_id
                state['halt_reason'] = (
                    f"Step '{step_id}' falhou {current_retries} vezes consecutivas "
                    f"(limite: {max_retries}). Loop interrompido pelo Circuit Breaker."
                )
                self.store.set_state("engine", exec_id, "workflow_context", state)
                print(f"\n[CIRCUIT BREAKER] ⛔ WORKFLOW PARADO")
                print(f"  Step:     {step_id}")
                print(f"  Retries:  {current_retries}/{max_retries}")
                print(f"  Razão:    {state['halt_reason']}")
                print(f"  Ação:     Intervenção humana necessária ou mudança de estratégia.\n")

                # Publica alerta no bus para observabilidade
                self.bus.publish("harness.alerts", {
                    "type": "CIRCUIT_BREAKER",
                    "execution_id": exec_id,
                    "step_id": step_id,
                    "retries": current_retries,
                    "max_retries": max_retries,
                    "message": state['halt_reason'],
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                })
                return

            # Dentro do limite: retry com cooldown
            print(f"[Ralph Loop] Meta não atingida em {step_id}. "
                  f"Retry {current_retries}/{max_retries} após {cooldown}s de cooldown...")
            time.sleep(cooldown)
            self._dispatch_step(exec_id, state)
            return
        # ── FIM DO CIRCUIT BREAKER ──────────────────────────────────────

        # Avança para o próximo passo se o atual foi sucesso
        if status == "success":
            # Limpa o contador de retries deste step (sucesso = reset)
            retry_key = f"{exec_id}::{step_id}"
            self._retry_counts.pop(retry_key, None)

            # ── FEATURE TRACKER: Registra progresso no JSON ──
            try:
                # Tenta mapear o step_id para uma fase no features.json
                # Convenção: steps cujo ID contém o phase_id são mapeados automaticamente
                current_step = state['steps'][state['current_step_index']]
                phase_id = current_step.get('phase_id') or step_id
                feature_tracker.complete_phase(phase_id)
            except Exception as e:
                # Não-fatal: o tracker é um complemento, não bloqueia o fluxo
                print(f"[Engine] ⚠️ FeatureTracker não conseguiu registrar '{step_id}': {e}")
            # ── FIM FEATURE TRACKER ──────────────────────────────

            state['current_step_index'] += 1
            
            if state['current_step_index'] < len(state['steps']):
                self.store.set_state("engine", exec_id, "workflow_context", state)
                self._dispatch_step(exec_id, state)
            else:
                state['status'] = "COMPLETED"
                self.store.set_state("engine", exec_id, "workflow_context", state)
                print(f"[Engine] Workflow {state['name']} CONCLUÍDO com sucesso!")

    def _dispatch_step(self, execution_id: str, state: Dict):
        """
        Envia o passo atual para o Event Bus ou executa localmente se for sistema.
        """
        current_step = state['steps'][state['current_step_index']]
        
        # Lógica Híbrida: Sistema (Script) vs Agente (LLM)
        if current_step.get('agent') == "system":
            self._execute_system_step(execution_id, current_step)
        else:
            self._dispatch_agent_step(execution_id, current_step)

    def _execute_system_step(self, execution_id: str, step: Dict):
        """
        Executa uma tarefa determinística localmente.
        """
        from tools.system_commands import SYSTEM_TOOLS
        
        action = step['action']
        params = step.get('params', {})
        
        print(f"[Engine] Executando Tarefa de Sistema: {action}")
        
        if action in SYSTEM_TOOLS:
            result = SYSTEM_TOOLS[action](params)
            # No futuro, aqui chamaremos a lógica de transição de estado (Step 2)
            print(f"[Engine] Resultado do Sistema: {result['status']}")
            
            # Simulando salvamento de resultado e avanço (simplificado para este passo)
            self.store.set_state("engine", execution_id, f"result_{step['id']}", result)
        else:
            print(f"[Erro] Ação de sistema não encontrada: {action}")

    def _dispatch_agent_step(self, execution_id: str, step: Dict):
        """
        Envia o passo para o Event Bus para ser processado por um agente LLM.
        """
        agent_topic = f"harness.agents.{step['agent']}"
        payload = {
            "execution_id": execution_id,
            "step_id": step['id'],
            "action": step['action'],
            "params": step['params'],
            "timestamp": os.popen('date -u +"%Y-%m-%dT%H:%M:%SZ"').read().strip()
        }
        
        print(f"[Engine] Disparando Passo Agente: {step['id']} para {step['agent']}")
        self.bus.publish(agent_topic, payload)

# Teste da Fase 2, Passo 2 (Ralph Loop e Coordenador)
if __name__ == "__main__":
    from core.event_bus import EventBus
    from core.store import StateStore
    import time
    import threading

    # Inicializa a fundação
    bus = EventBus()
    store = StateStore()
    engine = WorkflowEngine(bus, store)

    # Inicia o coordenador em uma thread separada
    coord_thread = threading.Thread(target=engine.start_coordinator, daemon=True)
    coord_thread.start()

    # Executa o mock workflow
    exec_id = engine.execute("workflows/mock-workflow.yaml")
    
    time.sleep(1) # Aguarda o processamento do primeiro passo (System)
    
    # 1. Simula um resultado de SUCESSO do primeiro passo (extracao_logs) manualmente 
    # para forçar o avanço para o segundo passo (analise_erro)
    bus.publish("harness.results", {
        "execution_id": exec_id,
        "step_id": "extracao_logs",
        "status": "success",
        "data": "Logs filtrados com sucesso"
    })

    time.sleep(1)

    # 4. TESTE DE ARQUIVO FANTASMA: Agente diz que criou o arquivo, mas Verifier checa o disco
    print("\n--- TESTANDO DETECÇÃO DE ARQUIVO FANTASMA ---")
    bus.publish("harness.results", {
        "execution_id": exec_id,
        "step_id": "deploy_script",
        "status": "success",
        "data": {"file_path": "fix_error.py"} # O arquivo não existe no disco real
    })

    time.sleep(2)
