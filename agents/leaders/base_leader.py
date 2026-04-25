from typing import Dict, Any
from agents.workers.base_worker import BaseWorker
from core.mcp_server import mcp_server

class BaseLeader(BaseWorker):
    """
    Classe base para os Líderes (Tier 2).
    Adiciona capacidades de delegação e supervisão sobre os Workers.
    """
    def __init__(self, agent_id: str, department: str, role: str = "leader"):
        # Inicializa como Líder (Ganha Read e List automaticamente)
        super().__init__(agent_id=agent_id, department=department, role=role)
        
        # Adiciona a ferramenta de delegação
        self.ai.tools.append(self.delegate_task)
        
        # Ajusta instruções para focar em gestão
        self.ai.instructions.append(
            f"Você é o Líder do departamento {department}. "
            "Sua principal ferramenta é 'delegate_task'. Use-a para enviar ordens aos seus trabalhadores."
        )

    def delegate_task(self, target_agent: str, action: str, params: Dict[str, Any], topic: str = None):
        """
        Envia uma tarefa técnica para o canal especificado ou do departamento.
        """
        # Se não for passado um tópico, usa o padrão do departamento
        final_topic = topic if topic else f"harness.{self.department}.worker"
        
        print(f"[{self.agent_id}] DELEGANDO ({self.department}): {action} para {target_agent} no canal {final_topic}")
        
        payload = {
            "target_agent": target_agent, 
            "dept": self.department, # Assinatura do depto (usado na validação de recebimento)
            "payload": {"action": action, "params": params}
        }

        return mcp_server.call_tool(
            agent_id=self.agent_id, 
            tool_name="delegate_task", 
            params={"target_agent": target_agent, "topic": final_topic, "payload": payload}
        )

    def _get_audit_report(self, execution_id: str) -> Dict[str, Any]:
        """
        Recupera o relatório de auditoria mais recente para esta execução.
        """
        return self.store.get_state("engine", execution_id, "superior_audit")
