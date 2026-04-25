import os
from agents.workers.base_worker import BaseWorker
from core.mcp_server import mcp_server

class BackendWorker(BaseWorker):
    """
    Tier 3 - Especialista em Backend Python/Flask.
    Responsável por criar arquivos de código do servidor: rotas, modelos, schemas,
    serviços, banco de dados e o app principal Flask.
    Escuta: harness.backend.worker
    """
    def __init__(self):
        super().__init__(agent_id="backend-worker-01", department="backend")
        
        # Personalidade especializada em backend Python
        self.ai.name = "Engenheiro Backend"
        self.ai.description = "Você é um engenheiro backend Python especializado em Flask, SQLite e APIs REST."
        self.ai.instructions.extend([
            "Você é um expert em Python, Flask, SQLite e arquitetura REST.",
            "Sua missão é criar os arquivos de código do servidor (backend) conforme solicitado.",
            "Use 'write_file' para escrever TODOS os arquivos .py necessários dentro de backend/.",
            "Sempre crie código funcional e completo — sem placeholders ou TODOs.",
            "Siga a estrutura padrão Flask: app/, models/, schemas/, services/, api/routes/.",
            "Para o banco de dados, use SQLite com o módulo sqlite3 padrão do Python.",
            "O main app deve rodar na porta 5000 com Flask.",
            "Após criar cada arquivo, confirme o path onde foi salvo.",
            "NUNCA crie componentes React ou frontend — apenas Python/Flask/SQL.",
        ])

    def _process_task(self, task_payload: dict):
        """
        Executa a tarefa de backend com inteligência real.
        Suporta payload embrulhado vindo do BaseWorker ou direto do Leader.
        """
        # Desembrulha payload se vier embrulhado
        if "payload" in task_payload and isinstance(task_payload["payload"], dict):
            inner = task_payload["payload"]
            action = inner.get("action")
            params = inner.get("params", {})
            sender_dept = task_payload.get("dept", inner.get("dept", ""))
        else:
            action = task_payload.get("action")
            params = task_payload.get("params", task_payload.get("data", {}))
            sender_dept = task_payload.get("dept", "")

        exec_id = task_payload.get("execution_id")

        # Trava de departamento: aceita 'backend' ou 'audit' (Superior)
        if sender_dept not in (self.department, "audit", ""):
            print(f"[{self.agent_id}] 🛡️ Bloqueio: Recusando ordem do depto '{sender_dept}'.")
            return

        print(f"[{self.agent_id}] 🐍 Iniciando implementação backend: {action}")
        self.store.set_state(self.agent_id, exec_id or "global", "status", f"OCUPADO: {action}")

        # Snapshot rápido do workspace para o prompt
        try:
            import os as _os
            ws_tree = []
            for root, dirs, files in _os.walk("workspace/backend"):
                level = root.replace("workspace/backend", "").count(_os.sep)
                indent = "  " * level
                ws_tree.append(f"{indent}{_os.path.basename(root)}/")
                for f in files:
                    ws_tree.append(f"{indent}  {f}")
            snapshot = "\n".join(ws_tree[:40]) if ws_tree else "(vazio)"
        except Exception:
            snapshot = "(não disponível)"

        prompt = f"""
### TAREFA DE BACKEND PYTHON/FLASK
**Ação:** {action}
**Parâmetros:** {params}
**ID Execução:** {exec_id}

### ESTRUTURA ATUAL DO BACKEND (workspace/backend/)
```
{snapshot}
```

### SUAS RESPONSABILIDADES
1. Leia a tarefa acima e crie/atualize os arquivos Python necessários.
2. Use `write_file` para salvar cada arquivo no caminho correto dentro de `backend/`.
3. Escreva código Python REAL e FUNCIONAL — sem pseudocódigo ou comentários genéricos.
4. Para cada arquivo criado, use o padrão: `backend/app/<módulo>/<arquivo>.py`

### ESTRUTURA ESPERADA DO BACKEND
```
backend/
  app/
    __init__.py       ← Factory do Flask app
    models/
      task.py         ← Modelo da tarefa (SQLite)
    schemas/
      task.py         ← Schema de validação/serialização
    services/
      task_service.py ← Lógica de negócio
    api/
      routes/
        tasks.py      ← Rotas REST: GET/POST/PUT/DELETE /tasks
    core/
      database.py     ← Conexão e init do SQLite
  main.py             ← Entrypoint: app.run(port=5000)
```

### REGRAS
- Porta: 5000
- Banco: SQLite (`database/tasks.db`)
- Tabela: tasks (id, title, description, status, created_at)
- Status values: 'pending', 'in_progress', 'completed'
- Use apenas bibliotecas padrão Python + Flask
"""

        response = self.safe_run(prompt)

        if response:
            status_final = "success"
            resultado = response.content
        else:
            status_final = "failed"
            resultado = "Falha após múltiplas tentativas (Rate Limit)."

        self.report_result(
            execution_id=exec_id,
            step_id=task_payload.get("step_id") or action,
            status=status_final,
            data={"output": resultado}
        )


if __name__ == "__main__":
    worker = BackendWorker()
    worker.start()
