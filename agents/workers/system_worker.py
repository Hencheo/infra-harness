from agents.workers.base_worker import BaseWorker

class SystemWorker(BaseWorker):
    """
    Tier 3 - Arquiteto de Sistema.
    Responsável exclusivo pela criação de estrutura física (diretórios) e arquivos base (README, .env).
    """
    def __init__(self):
        super().__init__(agent_id="system-worker", department="infra", role="worker")
        
        # Personalidade do System Worker
        self.ai.name = "Arquiteto de Estrutura"
        self.ai.description = "Você é o responsável pela fundação física do projeto no Harness."
        self.ai.instructions.extend([
            "Sua única missão é criar a estrutura de diretórios e arquivos base solicitados pelo Auditor.",
            "Use 'create_directory' para garantir que as pastas existam.",
            "Use 'write_file' apenas para arquivos de configuração ou documentação inicial (.env, README, package.json).",
            "Você NÃO instala dependências e NÃO cria lógica de código."
        ])

if __name__ == "__main__":
    worker = SystemWorker()
    worker.start()
