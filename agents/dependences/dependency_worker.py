import os
from agents.workers.base_worker import BaseWorker
from core.mcp_server import mcp_server

class DependencyWorker(BaseWorker):
    """
    Tier 3 - Especialista em Dependências e Infraestrutura.
    Responsável apenas por analisar a stack e instalar os pacotes necessários.
    TERMINANTEMENTE PROIBIDO de escrever código-fonte de aplicação.
    """
    def __init__(self, department: str = "infra"):
        super().__init__(agent_id="dependency-worker", department=department)
        
        # Restrição severa de escopo
        self.ai.instructions.append(
            "Sua única missão é garantir que todas as dependências do projeto estejam instaladas."
        )
        self.ai.instructions.append(
            "Você deve: 1. Listar arquivos para identificar a stack (Python, Node, etc). "
            "2. Ler arquivos de manifesto (requirements.txt, package.json). "
            "3. Usar a ferramenta 'install_dependency' para garantir a instalação."
        )
        self.ai.instructions.append(
            "VOCÊ É PROIBIDO DE ESCREVER CÓDIGO DE LÓGICA OU INTERFACE. "
            "Sua única ferramenta de escrita permitida é para atualizar arquivos de manifesto se necessário."
        )
        
        # Adiciona a ferramenta dedicada
        self.ai.tools.append(self.install_dependency)

    def install_dependency(self, manager: str = "auto", package: str = None):
        """
        Chama a ferramenta física de instalação de dependências.
        """
        return mcp_server.call_tool(
            agent_id=self.agent_id, 
            tool_name="install_dependency", 
            params={"manager": manager, "package": package}
        )

    def _process_task(self, task_payload: dict):
        exec_id = task_payload.get("execution_id")
        action = task_payload.get("action")
        
        # Verificação de Departamento
        if task_payload.get("dept") != self.department:
            print(f"[{self.agent_id}] 🛡️ Bloqueio: Ordem de depto externo negada.")
            return

        print(f"[{self.agent_id}] 📦 Analisando stack e instalando dependências: {action}")
        
        prompt = f"""
        ### TAREFA DE INFRAESTRUTURA
        Ação: {action}
        
        Analise o diretório atual, identifique os arquivos de dependência e execute a instalação.
        Não escreva código de aplicação. Apenas garanta que o ambiente está pronto para rodar.
        """
        
        response = self.ai.run(prompt)
        
        self.report_result(exec_id, task_payload.get("step_id"), "success", {"log": response.content})

if __name__ == "__main__":
    # Pode ser iniciado para qualquer departamento que precise dele
    import sys
    dept = sys.argv[1] if len(sys.argv) > 1 else "infra"
    worker = DependencyWorker(department=dept)
    worker.start()
