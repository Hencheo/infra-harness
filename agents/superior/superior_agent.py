import os
import time
import yaml
from typing import Dict, Any
from agents.leaders.base_leader import BaseLeader
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from core.feature_tracker import feature_tracker
from core.protocols import build_context_reset
from core.observability import tracer, EventType
from dotenv import load_dotenv

load_dotenv()

# Carrega o workflow para state machine determinística
WORKFLOW_PATH = "workflows/HARNESS_MASTER_WORKFLOW.yaml"

def _load_phase_order():
    """Lê a sequência de fases do YAML."""
    if os.path.exists(WORKFLOW_PATH):
        with open(WORKFLOW_PATH, 'r') as f:
            wf = yaml.safe_load(f)
        return wf.get("phases", [])
    return []

PHASES = _load_phase_order()

class SuperiorAgent(BaseLeader):
    """
    Tier 1 - O Superior (Guardião da Spec Suprema).
    O único com autoridade para encerrar o ciclo e autorizar instalações físicas.
    
    CORREÇÃO CRÍTICA: Agora usa State Machine determinística para avançar fases,
    em vez de depender do LLM para decidir próximo passo.
    """
    def __init__(self):
        # Inicializa como Auditor (Ganha ferramentas de leitura)
        super().__init__(agent_id="superior-agent", department="audit", role="auditor")
        self.spec_path = "specs/SUPREME_SPEC.md"
        self._current_phase_index = 0
        self._phase_completed = set()  # IDs de fases já concluídas
        self._mission_active = False
        self._current_exec_id = None
        
        # Adiciona ferramenta de finalização (delegação)
        self.ai.tools.append(self.delegate_task)
        
        # Personalidade do Auditor Superior
        self.ai.name = "Superior Auditor SDD"
        self.ai.description = "Você é o Auditor Superior e o Autorizador Final do Harness."
        self.ai.instructions.extend([
            "Sua única 'Fonte da Verdade' é o documento em specs/SUPREME_SPEC.md.",
            "DIRETRIZ DE SEQUÊNCIA: Siga rigorosamente o arquivo workflows/HARNESS_MASTER_WORKFLOW.yaml.",
            "DIRETRIZ DE CAMINHOS: NUNCA use '/' ou caminhos absolutos. Use sempre '.' ou 'specs/'.",
            "MAPA DO RÁDIO (Canais Corretos):",
            " - Para Infraestrutura e Fundação (FASE 1): delegar para 'infra-leader' no tópico 'harness.infra.leader'.",
            " - Para Dados (FASE 2): delegar para 'data-leader' no tópico 'harness.data.leader'.",
            " - Para Backend (FASE 3): delegar para 'backend-leader' no tópico 'harness.backend.leader'.",
            " - Para Frontend (FASE 4): delegar para 'frontend-leader' no tópico 'harness.frontend.leader'.",
            "Sua função é gerenciar o projeto em FASES SEQUENCIAIS. Não inicie a Fase 2 antes da Fase 1 estar concluída.",
            "Sua função é comparar propostas com a Spec. Se aprovado, você é o responsável por FINALIZAR o ciclo.",
            "PROTOCOLO DE ENCERRAMENTO: Quando você emitir 'STATUS: APROVADO', acione o 'dependency-worker' em 'harness.infra.worker'."
        ])

    def _deterministic_pre_audit(self, proposta: dict) -> tuple[bool, str]:
        """
        Realiza checks rápidos sem custo de LLM (Hardened Verification Gate).
        """
        forbidden = ["rm -rf", "mkfs", "dd if=", "format ", "> /dev/sda"]
        proposta_str = str(proposta).lower()
        
        for term in forbidden:
            if term in proposta_str:
                return False, f"Violação de Segurança: Termo proibido '{term}' detectado."
        
        if not proposta:
            return False, "Proposta vazia ou malformada."
            
        return True, ""

    def _get_latest_spec(self) -> str:
        """
        Lê a versão mais atual da Spec Suprema do disco.
        """
        if os.path.exists(self.spec_path):
            with open(self.spec_path, 'r') as f:
                return f.read()
        return "ERRO: Spec Suprema não encontrada em " + self.spec_path

    def _get_current_phase(self) -> dict:
        """Retorna a fase atual baseada no índice."""
        if self._current_phase_index < len(PHASES):
            return PHASES[self._current_phase_index]
        return None

    def _advance_to_next_phase(self):
        """
        STATE MACHINE DETERMINÍSTICA: Avança para a próxima fase e delega automaticamente.
        Sem LLM, sem list_files, sem loops.
        Registra a fase concluída no FeatureTracker (JSON).
        """
        # Marca a fase atual como concluída no JSON antes de avançar
        current_phase = self._get_current_phase()
        if current_phase:
            try:
                feature_tracker.complete_phase(current_phase["id"])
            except Exception as e:
                print(f"[{self.agent_id}] ⚠️ FeatureTracker: {e}")
            
            # ── TRACE: Fase concluída com duração ──
            phase_duration = tracer.stop_phase_timer(current_phase["id"])
            tracer.emit(EventType.PHASE_COMPLETED, self.agent_id, {
                "phase_id": current_phase["id"],
                "phase_name": current_phase["name"],
                "duration_s": phase_duration,
            }, execution_id=self._current_exec_id)
            
            # ── CONTEXT ISOLATION: Sinaliza reset de contexto para a fase concluída ──
            # Agentes da fase completada devem limpar seu histórico para a próxima tarefa.
            reset_msg = build_context_reset(
                completed_phase=current_phase["id"],
                reason=f"Fase '{current_phase['name']}' concluída. Limpeza de contexto.",
                completed_leader=current_phase.get("leader"),
            )
            self.bus.publish("harness.context.reset", reset_msg)
            print(f"[{self.agent_id}] 🔄 CONTEXT RESET broadcast para fase: {current_phase['id']}")
            # ── FIM CONTEXT ISOLATION ──

        self._current_phase_index += 1
        phase = self._get_current_phase()
        
        if not phase:
            print(f"[{self.agent_id}] 🏁 TODAS AS FASES CONCLUÍDAS! Missão finalizada.")
            self.store.set_state(self.agent_id, self._current_exec_id or "global", "status", "✅ MISSÃO CONCLUÍDA")
            self._mission_active = False
            return
        
        self._dispatch_phase(phase)

    def _dispatch_phase(self, phase: dict):
        """
        Despacha uma fase específica para o líder correto via delegate_task.
        Usa dados CONCRETOS da Spec ao invés de parâmetros vazios.
        """
        # ── TRACE: Fase iniciada + cronômetro ──
        tracer.start_phase_timer(phase["id"])
        tracer.emit(EventType.PHASE_STARTED, self.agent_id, {
            "phase_id": phase["id"],
            "phase_name": phase["name"],
            "leader": phase["leader"],
        }, execution_id=self._current_exec_id)
        leader = phase["leader"]
        phase_id = phase["id"]
        objective = phase["objective"]
        
        # Mapa fixo de canais (determinístico, sem LLM)
        topic_map = {
            "infra-leader": "harness.infra.leader",
            "data-leader": "harness.data.leader",
            "backend-leader": "harness.backend.leader",
            "frontend-leader": "harness.frontend.leader",
        }
        
        topic = topic_map.get(leader)
        if not topic:
            print(f"[{self.agent_id}] ❌ Líder desconhecido: {leader}")
            return
        
        print(f"[{self.agent_id}] 📋 FASE {self._current_phase_index + 1}: {phase['name']} → {leader}")
        self.store.set_state(self.agent_id, self._current_exec_id or "global", "status", 
                            f"FASE {self._current_phase_index + 1}: {phase['name']}")
        
        # Lê a spec para enviar contexto real (não dicts vazios)
        spec_content = self._get_latest_spec()
        
        # Lê progresso atual do JSON para contexto compacto
        try:
            progress = feature_tracker.get_progress_summary()
            progress_ctx = f"Progresso geral: {progress['overall_progress']} ({progress['percentage']}%)"
        except Exception:
            progress_ctx = "(Progresso JSON não disponível)"
        
        # Despacho determinístico via delegate_task
        self.delegate_task(
            target_agent=leader,
            action=phase_id,
            params={
                "phase_id": phase_id,
                "objective": objective,
                "spec_summary": spec_content[:2000],  # Envia um resumo da spec
                "progress": progress_ctx,
                "execution_id": self._current_exec_id,
            },
            topic=topic
        )

    def _process_task(self, task_payload: dict):
        """
        Processa Auditoria ou Início de Missão.
        """
        exec_id = task_payload.get("execution_id")
        action = task_payload.get("action", "audit")
        data = task_payload.get("data", {})
        
        if action == "START_MISSION":
            if self._mission_active:
                print(f"[{self.agent_id}] ⏩ Missão já em andamento. Ignorando duplicata.")
                return
            
            self._mission_active = True
            self._current_exec_id = exec_id
            self._current_phase_index = 0
            self._phase_completed.clear()
            
            print(f"[{self.agent_id}] 🚀 MISSÃO RECEBIDA: {data}")
            self.store.set_state(self.agent_id, exec_id or "global", "status", "MISSÃO INICIADA")
            
            # Despacha a primeira fase DETERMINISTICAMENTE
            phase = self._get_current_phase()
            if phase:
                self._dispatch_phase(phase)
            else:
                print(f"[{self.agent_id}] ❌ Nenhuma fase definida no workflow!")
            return

        # FLUXO DE AUDITORIA (Original)
        print(f"[{self.agent_id}] Iniciando auditoria para {exec_id}...")
        self.store.set_state(self.agent_id, exec_id or "global", "status", f"OCUPADO: Auditando {exec_id}")
        is_valid, reason = self._deterministic_pre_audit(data)
        if not is_valid:
            self.report_result(exec_id, "superior_audit", "failed", {"audit_report": f"REJEITADO: {reason}"})
            return

        spec_atual = self._get_latest_spec()
        
        # Injeta progresso JSON compacto no prompt de auditoria
        try:
            progress = feature_tracker.get_progress_summary()
            progress_info = f"\n### PROGRESSO ATUAL (JSON):\n{progress['overall_progress']} concluídas ({progress['percentage']}%)\n"
        except Exception:
            progress_info = ""
        
        prompt_audit = f"### AUDITORIA: {data}{progress_info}\n### SPEC:\n{spec_atual}\nResponda com STATUS: [APROVADO/REJEITADO]."
        response = self.safe_run(prompt_audit)
        self.report_result(exec_id, "superior_audit", "success", {"audit_report": response.content})

    def start(self):
        """
        Inicia a escuta de auditoria E de resultados para orquestração.
        CORREÇÃO: subscribe(results) é NÃO-BLOQUEANTE, subscribe_blocking(audit) bloqueia.
        """
        import random
        import time
        
        base_delay = 2
        jitter = random.uniform(0, 4)
        total_delay = base_delay + jitter
        print(f"[{self.agent_id}] ⏳ Escalonando tráfego (Jitter: {total_delay:.1f}s)...")
        time.sleep(total_delay)
        
        # 1. Registra o listener de resultados PRIMEIRO (não-bloqueante)
        print(f"[{self.agent_id}] 🎧 Monitorando canal de resultados: harness.results")
        self.bus.subscribe("harness.results", self._handle_results)
        
        # 2. Bloqueia no canal principal de auditoria (mantém processo vivo)
        print(f"[{self.agent_id}] 📡 Escutando canal: {self.topic} (Depto: {self.department})")
        self.bus.subscribe_blocking(self.topic, self._process_task)

    def _handle_results(self, result_payload: dict):
        """
        STATE MACHINE: Reage aos resultados dos leaders para avançar as fases.
        SEM LLM — lógica puramente determinística.
        """
        status = result_payload.get("status")
        agent = result_payload.get("agent_id")
        step_id = result_payload.get("step_id", "")
        
        # Ignora nossos próprios resultados
        if agent == self.agent_id:
            return
        
        # Ignora se não há missão ativa
        if not self._mission_active:
            return
            
        # Só reage a SUCESSOs de LÍDERES ou do dependency-worker
        is_leader = "leader" in (agent or "")
        is_final_step = agent == "dependency-worker"
        
        if status == "success" and (is_leader or is_final_step):
            current_phase = self._get_current_phase()
            
            if not current_phase:
                return
            
            # Verifica se o resultado veio do líder da fase ATUAL
            expected_leader = current_phase.get("leader")
            if agent == expected_leader or is_final_step:
                phase_id = current_phase["id"]
                
                # Evita processar mesma fase duas vezes
                if phase_id in self._phase_completed:
                    print(f"[{self.agent_id}] ⏩ Fase {phase_id} já concluída. Ignorando resultado duplicado.")
                    return
                
                self._phase_completed.add(phase_id)
                print(f"[{self.agent_id}] ✅ FASE CONCLUÍDA: {current_phase['name']} (por {agent})")
                
                # Avança para a próxima fase automaticamente
                self._advance_to_next_phase()
            else:
                print(f"[{self.agent_id}] ℹ️ Resultado de {agent} recebido, mas fase atual espera {expected_leader}. Ignorando.")

if __name__ == "__main__":
    superior = SuperiorAgent()
    superior.start()
