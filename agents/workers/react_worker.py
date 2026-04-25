import os
from typing import Dict, Any
from agents.workers.base_worker import BaseWorker

class ReactWorker(BaseWorker):
    """
    Tier 3 - Especialista React (Frontend).
    Responsável por transformar designs e requisitos de UI em componentes reais.
    """
    def __init__(self):
        super().__init__(agent_id="react-worker-01", department="frontend")
        
        # Especialização das instruções para React
        self.ai.instructions.extend([
            "Você é um expert em React.js e arquitetura de componentes.",
            "Sempre utilize as melhores práticas: componentes funcionais, hooks e separação de interesses.",
            "Para estilização, priorize CSS moderno ou frameworks solicitados na Spec.",
            "Seu objetivo é criar interfaces 'Pixel Perfect' e com animações suaves.",
            "Ao criar um componente, sempre verifique se o arquivo foi escrito corretamente no diretório src/."
        ])

    def _process_task(self, task_payload: dict):
        """
        Executa a tarefa de criação de interface usando inteligência artificial.
        """
        exec_id = task_payload.get("execution_id")
        action = task_payload.get("action")
        params = task_payload.get("params", {})
        
        # --- TRAVA DE DEPARTAMENTO (Herdada do BaseWorker) ---
        sender_dept = task_payload.get("dept")
        if sender_dept != self.department:
            print(f"[{self.agent_id}] 🛡️ Bloqueio: Recusando ordem do depto '{sender_dept}'.")
            return
        # ----------------------------------------------------

        print(f"[{self.agent_id}] 🎨 Iniciando trabalho de UI: {action}")
        
        prompt = f"""
        ### TAREFA DE FRONTEND (REACT)
        Ação: {action}
        Parâmetros: {params}
        
        ### ORIENTAÇÃO
        Execute a tarefa acima criando os arquivos necessários.
        Use suas ferramentas de 'write_file' para salvar o código.
        Seja detalhista e garanta uma estética premium.
        """
        
        response = self.ai.run(prompt)
        
        # Reporta o sucesso para a Engine
        self.report_result(
            execution_id=exec_id, 
            step_id=task_payload.get("step_id"), 
            status="success", 
            data={"output": response.content}
        )

if __name__ == "__main__":
    worker = ReactWorker()
    worker.start()
