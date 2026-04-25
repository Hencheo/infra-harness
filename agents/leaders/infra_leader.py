import os
from agents.leaders.base_leader import BaseLeader

class InfraLeader(BaseLeader):
    """
    Tier 2 - Gerente de Infraestrutura.
    Orquestra a fundação física e preparação do ambiente.
    Comanda o system-worker (pastas) e o dependency-worker (instalações).
    
    CORREÇÃO CRÍTICA: 
    - Verificação determinística do workspace (sem LLM quando desnecessário)
    - Subscribe de results em thread separada (non-blocking)
    """
    def __init__(self):
        super().__init__(agent_id="infra-leader", department="infra")
        self._phase_reported = set()  # Evita reportar a mesma fase duas vezes
        
        # Personalidade do Líder de Infra
        self.ai.name = "Gerente de Infra"
        self.ai.description = "Você é o Gerente de Infraestrutura. Seu foco é Estabilidade e Fundação."
        self.ai.instructions.extend([
            "Você coordena os trabalhadores de infraestrutura (Tier 3).",
            "Sua prioridade é garantir que o ambiente físico esteja pronto para o Backend e Frontend.",
            "Use 'delegate_task' para comandar o 'system-worker' (para pastas) e o 'dependency-worker' (para pacotes).",
            "MAPA DE DELEGAÇÃO:",
            " - Para criar pastas e arquivos base: use target_agent='system-worker'.",
            " - Para instalar dependências e rodar scripts: use target_agent='dependency-worker'."
        ])

    def _check_workspace_structure(self) -> dict:
        """
        VERIFICAÇÃO DETERMINÍSTICA: Checa se a estrutura física já existe.
        Retorna um relatório sem gastar tokens de LLM.
        """
        workspace = "workspace"
        required_dirs = ["backend", "frontend", "config", "database", "docs", "scripts", "tests", "src"]
        required_files = ["README.md", "package.json", ".env"]
        
        missing_dirs = []
        missing_files = []
        existing_dirs = []
        existing_files = []
        
        for d in required_dirs:
            path = os.path.join(workspace, d)
            if os.path.isdir(path):
                existing_dirs.append(d)
            else:
                missing_dirs.append(d)
        
        for f in required_files:
            path = os.path.join(workspace, f)
            if os.path.isfile(path):
                existing_files.append(f)
            else:
                missing_files.append(f)
        
        return {
            "existing_dirs": existing_dirs,
            "missing_dirs": missing_dirs,
            "existing_files": existing_files,
            "missing_files": missing_files,
            "is_complete": len(missing_dirs) == 0 and len(missing_files) == 0,
        }
        
    def start(self):
        """
        Inicia a escuta de ordens e de resultados dos seus workers.
        CORREÇÃO: subscribe(results) é NÃO-BLOQUEANTE, subscribe_blocking(leader) bloqueia.
        """
        import random
        import time
        
        base_delay = 2
        jitter = random.uniform(0, 6)
        total_delay = base_delay + jitter
        print(f"[{self.agent_id}] ⏳ Escalonando tráfego (Jitter: {total_delay:.1f}s)...")
        time.sleep(total_delay)
        
        # 1. Registra o listener de resultados PRIMEIRO (não-bloqueante)
        print(f"[{self.agent_id}] 🎧 Monitorando resultados para fechar ciclo.")
        self.bus.subscribe("harness.results", self._handle_worker_results)
        
        # 2. Bloqueia no canal principal de ordens (mantém processo vivo)
        print(f"[{self.agent_id}] 📡 Escutando canal: {self.topic} (Depto: {self.department})")
        self.bus.subscribe_blocking(self.topic, self._process_task)

    def _handle_worker_results(self, result_payload: dict):
        """
        Recebe o retorno do worker e repassa o sucesso para o Auditor.
        """
        agent = result_payload.get("agent_id")
        status = result_payload.get("status")
        exec_id = result_payload.get("execution_id")
        
        # Se for um dos meus workers e deu sucesso, eu (Líder) reporto sucesso da fase
        if agent in ["system-worker", "dependency-worker"] and status == "success":
            # Evita reportar duplicatas
            report_key = f"{exec_id}:{agent}"
            if report_key in self._phase_reported:
                return
            self._phase_reported.add(report_key)
            
            print(f"[{self.agent_id}] 🎯 Worker '{agent}' concluiu. Reportando conclusão da fase ao Auditor.")
            self.report_result(exec_id, "infra_phase_complete", "success", {"msg": f"Infraestrutura preparada por {agent}"})

    def _process_task(self, task_payload: dict):
        """
        Processa solicitações de infraestrutura.
        CORREÇÃO: Verificação determinística ANTES de chamar LLM.
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
        
        # --- TRAVA CIRÚRGICA: Evita re-processamento se já estiver em andamento ou concluído ---
        current_status = self.store.get_state(self.agent_id, exec_id or "global", "status")
        status_str = str(current_status).upper()
        if "SUCCESS" in status_str:
            print(f"[{self.agent_id}] ⏩ Infra já confirmada. Pulando.")
            return
        # --------------------------------------------------------------------------------------
        
        print(f"[{self.agent_id}] Orquestrando Infraestrutura para: {exec_id}")
        self.store.set_state(self.agent_id, exec_id or "global", "status", "OCUPADO: Orquestrando Infra")
        
        # --- VERIFICAÇÃO DETERMINÍSTICA (SEM LLM) ---
        report = self._check_workspace_structure()
        
        if report["is_complete"]:
            # Tudo já existe! Reporta sucesso IMEDIATAMENTE sem gastar tokens
            print(f"[{self.agent_id}] ✅ Workspace completo! Dirs: {report['existing_dirs']}, Files: {report['existing_files']}")
            print(f"[{self.agent_id}] ⚡ Pulando LLM — estrutura verificada deterministicamente.")
            self.report_result(exec_id, "infra_foundation", "success", {
                "output": "Estrutura física validada e estável (Verificação Determinística).",
                "details": report
            })
            return
        
        # Se algo está faltando, delega para o system-worker com dados concretos
        if report["missing_dirs"] or report["missing_files"]:
            print(f"[{self.agent_id}] 🔧 Estrutura incompleta. Faltam dirs: {report['missing_dirs']}, files: {report['missing_files']}")
            
            # Delegação DETERMINÍSTICA (sem LLM) para o system-worker
            self.delegate_task(
                target_agent="system-worker",
                action="create_structure",
                params={
                    "missing_dirs": report["missing_dirs"],
                    "missing_files": report["missing_files"],
                    "workspace_root": "workspace"
                },
                topic="harness.infra.worker"
            )
            return

if __name__ == "__main__":
    leader = InfraLeader()
    leader.start()
