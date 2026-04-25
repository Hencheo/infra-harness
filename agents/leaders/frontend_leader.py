from agents.leaders.base_leader import BaseLeader

class FrontendLeader(BaseLeader):
    """
    Tier 2 - Gerente de Frontend.
    Orquestra a implementação de interfaces, UX e Estética.
    """
    def __init__(self):
        super().__init__(agent_id="frontend-leader", department="frontend")
        
        # Personalidade do Líder de Frontend
        self.ai.name = "Gerente de Frontend"
        self.ai.description = "Você é o Gerente de Frontend. Seu foco é UX/UI e Estética Premium."
        self.ai.instructions.extend([
            "Você coordena os trabalhadores de frontend (Tier 3).",
            "Sua prioridade é a estética, usabilidade e performance da interface baseada na Spec Suprema.",
            "Não aceite soluções simples. O objetivo é uma experiência WOW.",
            "Use o Relatório de Auditoria para comandar as correções necessárias."
        ])

    def _process_task(self, task_payload: dict):
        """
        Processa solicitações de UI ou correções de auditoria.
        """
        exec_id = task_payload.get("execution_id")
        instrucao = task_payload.get("data", {})
        
        # Verifica se existe um relatório de auditoria anterior via base
        audit_report = self._get_audit_report(exec_id)
        
        print(f"[{self.agent_id}] Gerenciando tarefa de Frontend para: {exec_id}")
        
        contexto_prompt = f"""
        ### TAREFA ATUAL
        {instrucao}
        """
        
        if audit_report:
            contexto_prompt += f"""
            ### ⚠️ ALERTA: CORREÇÃO NECESSÁRIA
            O Auditor Superior rejeitou a versão anterior. 
            Motivo da Rejeição: {audit_report}
            
            Sua missão é gerar uma instrução de correção focada apenas no erro acima (Delta de Contexto).
            """

        # O Líder decide o próximo passo para o trabalhador
        response = self.ai.run(contexto_prompt)
        
        print(f"[{self.agent_id}] Estratégia de Frontend definida.")
        
        # Aqui ele despacharia para o trabalhador via Event Bus (Fase 4.3)
        self.report_result(exec_id, "frontend_strategy", "success", {"instructions": response.content})

if __name__ == "__main__":
    leader = FrontendLeader()
    leader.start()
