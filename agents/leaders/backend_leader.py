from agents.leaders.base_leader import BaseLeader

class BackendLeader(BaseLeader):
    """
    Tier 2 - Gerente de Backend.
    Orquestra a implementação da lógica, APIs e Banco de Dados.
    Valida a integridade sistêmica contra a Spec Suprema.
    """
    def __init__(self):
        super().__init__(agent_id="backend-leader", department="backend")
        
        # Personalidade do Líder de Backend
        self.ai.name = "Gerente de Backend"
        self.ai.description = "Você é o Gerente de Backend. Seu foco é Arquitetura Sólida e Segurança."
        self.ai.instructions.extend([
            "Você coordena os trabalhadores de backend (Tier 3).",
            "Sua prioridade é a integridade da lógica de negócios e segurança dos dados.",
            "Use o Relatório de Auditoria para identificar falhas sistêmicas.",
            "Comande as correções usando 'delegate_task'."
        ])

    def start(self):
        import random
        import time
        
        base_delay = 2
        jitter = random.uniform(0, 6)
        total_delay = base_delay + jitter
        print(f"[{self.agent_id}] ⏳ Escalonando tráfego (Jitter: {total_delay:.1f}s)...")
        time.sleep(total_delay)
        
        # 1. Listener de resultados (não-bloqueante)
        print(f"[{self.agent_id}] 🎧 Monitorando resultados dos workers.")
        self.bus.subscribe("harness.results", self._handle_worker_results)
        
        # 2. Bloqueia no canal principal de ordens
        print(f"[{self.agent_id}] 📡 Escutando canal: {self.topic} (Depto: {self.department})")
        self.bus.subscribe_blocking(self.topic, self._process_task)

    def _handle_worker_results(self, result_payload: dict):
        agent = result_payload.get("agent_id")
        status = result_payload.get("status")
        exec_id = result_payload.get("execution_id")
        
        # Reage apenas ao worker correto e evita loop (não reagir ao próprio resultado)
        if agent == "backend-worker-01" and status == "success":
            print(f"[{self.agent_id}] ✅ backend-worker-01 concluiu. Fechando fase.")
            self.report_result(exec_id, "backend_phase_complete", "success", {"msg": "Backend implementado."})

    def _process_task(self, task_payload: dict):
        """
        Processa solicitações de lógica ou correções de auditoria.
        """
        # Desembrulha a mensagem se vier do Auditor Superior
        if "payload" in task_payload and isinstance(task_payload["payload"], dict):
            inner = task_payload["payload"]
            action = inner.get("action")
            params = inner.get("params", {})
        else:
            action = task_payload.get("action")
            params = task_payload.get("data", task_payload.get("params", {}))

        exec_id = task_payload.get("execution_id")
        
        # Idempotência: evita reprocessar se já está em andamento
        current_status = str(self.store.get_state(self.agent_id, exec_id or "global", "status") or "").upper()
        if "OCUPADO" in current_status:
            print(f"[{self.agent_id}] ⏩ Backend já em andamento. Ignorando duplicata.")
            return
        
        self.store.set_state(self.agent_id, exec_id or "global", "status", f"OCUPADO: {action}")
        print(f"[{self.agent_id}] Gerenciando tarefa de Backend para: {exec_id}")
        
        # Lê a spec para contexto real
        spec_summary = ""
        try:
            if hasattr(self, '_get_latest_spec'):
                spec_summary = self._get_latest_spec()[:1500]
        except Exception:
            pass
        
        contexto_prompt = f"""
        ### TAREFA DE BACKEND
        Ação: {action}
        Parâmetros: {params}
        
        PROTOCOLO DE LIDERANÇA (ESTRITO):
        1. Analise a tarefa e divida em subtarefas concretas de implementação.
        2. Use 'delegate_task' UMA VEZ com a tarefa completa:
           - target_agent='backend-worker-01'
           - topic='harness.backend.worker'
           - action='implement_backend' (string simples, não dict)
           - params com os detalhes concretos do que implementar
        
        WORKER CORRETO: backend-worker-01 (NÃO react-worker-01)
        CANAL CORRETO: harness.backend.worker
        
        O backend deve implementar:
        - API Flask na porta 5000
        - SQLite para persistência (database/tasks.db)
        - Rotas: GET/POST /tasks, PUT/DELETE /tasks/<id>
        - Schema: tasks(id, title, description, status, created_at)
        """
        
        response = self.safe_run(contexto_prompt)
        print(f"[{self.agent_id}] Estratégia de Backend delegada. Aguardando workers...")

if __name__ == "__main__":
    leader = BackendLeader()
    leader.start()
