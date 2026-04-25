from agents.leaders.base_leader import BaseLeader

class DataLeader(BaseLeader):
    """
    Tier 2 - Líder de Dados.
    Responsável pela modelagem, integridade e arquitetura de armazenamento.
    """
    def __init__(self):
        super().__init__(agent_id="data-leader", department="data")
        
        # Personalidade do Líder de Dados
        self.ai.name = "Arquiteto de Dados"
        self.ai.description = "Você é o Líder de Dados. Seu foco é Modelagem, SQL e Performance."
        self.ai.instructions.extend([
            "Você coordena os trabalhadores de dados (Tier 3).",
            "Sua prioridade é a integridade e normalização das tabelas.",
            "Use o Relatório de Auditoria para ajustar schemas que foram rejeitados.",
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
        
        if agent == "sqlite-worker" and status == "success":
            self.report_result(exec_id, "data_phase_complete", "success", {"msg": "Banco de dados configurado."})

    def _process_task(self, task_payload: dict):
        """
        Processa solicitações de modelagem ou correções de auditoria.
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
        
        # Gestão de Erro: Verifica se há rejeição do Auditor via método da base
        audit_report = self._get_audit_report(exec_id)
        
        print(f"[{self.agent_id}] Gerenciando tarefa de Dados para: {exec_id}")
        
        contexto_prompt = f"""
        ### TAREFA DE DADOS
        Ação: {action}
        Parâmetros: {params}
        
        PROTOCOLO DE LIDERANÇA (ESTRITO):
        1. Use 'delegate_task' EXCLUSIVAMENTE para:
           - topic='harness.data.worker', target_agent='sqlite-worker'
        
        NUNCA invente nomes de tópicos. Use apenas o listado acima.
        """
        
        if audit_report:
            contexto_prompt += f"""
            ### ⚠️ ALERTA: CORREÇÃO DE SCHEMA NECESSÁRIA
            O Auditor Superior rejeitou a versão anterior. 
            Relatório de Erros: {audit_report}
            
            Sua missão é gerar uma instrução de correção (Delta de Contexto) focada apenas no ajuste dos dados acima.
            """

        response = self.safe_run(contexto_prompt)
        print(f"[{self.agent_id}] Estratégia de Dados delegada. Aguardando workers...")

if __name__ == "__main__":
    leader = DataLeader()
    leader.start()
