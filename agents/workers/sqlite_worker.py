import os
from agents.workers.base_worker import BaseWorker

class SQLiteWorker(BaseWorker):
    """
    Tier 3 - Especialista em SQLite.
    Responsável por criar arquivos .db, tabelas e executar scripts SQL.
    """
    def __init__(self):
        super().__init__(agent_id="sqlite-worker", department="data")
        
        self.ai.instructions.extend([
            "Você é um especialista em SQLite e Python (sqlite3).",
            "Sua tarefa é criar e gerenciar bancos de dados relacionais dentro da pasta 'workspace/'.",
            "Sempre utilize scripts SQL limpos ou código Python para manipular os dados.",
            "Certifique-se de que todos os arquivos .db sejam salvos na workspace.",
            "Ao finalizar a criação de um banco, use a ferramenta 'list_files' para confirmar a existência do arquivo."
        ])

    def _process_task(self, task_payload: dict):
        exec_id = task_payload.get("execution_id")
        action = task_payload.get("action")
        params = task_payload.get("params", {})
        
        # Trava de Depto
        if task_payload.get("dept") != self.department:
            return

        print(f"[{self.agent_id}] 🗄️ Gerenciando dados SQLite: {action}")
        
        prompt = f"""
        ### TAREFA DE DADOS (SQLITE)
        Ação: {action}
        Contexto: {params}
        
        ### REGRAS
        1. Crie os arquivos .db necessários.
        2. Defina o schema conforme solicitado.
        3. Use suas ferramentas de escrita para salvar scripts ou bancos.
        """
        
        response = self.ai.run(prompt)
        
        self.report_result(exec_id, task_payload.get("step_id"), "success", {"output": response.content})

if __name__ == "__main__":
    worker = SQLiteWorker()
    worker.start()
