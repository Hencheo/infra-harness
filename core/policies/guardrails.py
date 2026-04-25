from typing import Dict, Any, Tuple
from rich.console import Console

console = Console()

class GuardrailEngine:
    """
    Motor de Políticas e Guardrails (Fronteira de Segurança).
    Interfere em intenções de agentes antes que elas virem ações.
    """
    
    # Lista de ferramentas que exigem aprovação ou são proibidas
    FORBIDDEN_TOOLS = ["delete_file", "rm", "format_disk"]
    DANGEROUS_PARAMS = ["-rf", "/root", "/etc", "/home", "/var"]
    
    # Hierarquia de Permissões
    WRITE_TOOLS = ["write_file", "create_file", "edit_file", "save_code"]
    DELEGATION_TOOLS = ["delegate_task"]
    INFRA_TOOLS = ["install_dependency", "format_disk"] # Ações que alteram o ambiente/SO

    # Tabela de Roteamento Estrita do Auditor (Tier 1 -> Tier 2)
    AUDITOR_ROUTING = {
        "data-leader": "harness.data.leader",
        "backend-leader": "harness.backend.leader",
        "frontend-leader": "harness.frontend.leader",
        "infra-leader": "harness.infra.leader"
    }

    PHASE_ORDER = ["infra-leader", "data-leader", "backend-leader", "frontend-leader"]

    def validate_request(self, agent_id: str, tool_name: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Avalia se uma chamada de ferramenta é permitida com base no Agente e na Ação.
        """
        is_leader = "leader" in agent_id or "superior" in agent_id
        is_worker = "worker" in agent_id
        is_infra = "dependency-worker" in agent_id

        # 1. Checa Parâmetros de Caminho (Sanitização)
        param_str = str(params).lower()
        
        # Bloqueia Caminhos Absolutos (que começam com /)
        # Nota: params pode ter 'path': '/etc'. O str(params) terá "'path': '/etc'"
        if "': '/" in param_str or "': \"/" in param_str:
             return False, "Caminhos absolutos são proibidos. Use caminhos relativos ao projeto."
        
        # Bloqueia Path Traversal (tentativa de subir níveis com ..)
        if ".." in param_str:
            return False, "Path Traversal detectado (..). Você não pode sair da área de trabalho."

        # 2. Checa termos proibidos globais
        for forbidden in self.DANGEROUS_PARAMS:
            if forbidden in param_str:
                return False, f"Parâmetro perigoso detectado: '{forbidden}'"

        # 3. Trava de Hierarquia: Líderes e Superiores NUNCA escrevem arquivos.
        if is_leader:
            if tool_name in self.WRITE_TOOLS:
                return False, f"Violação: O agente '{agent_id}' (Líder) não pode executar ações de escrita. Ele deve DELEGAR."
        
        # 4. Trava de Infraestrutura: Apenas o dependency-worker instala dependências.
        if tool_name in self.INFRA_TOOLS:
            if not is_infra:
                return False, f"Violação de Privilégio: O agente '{agent_id}' não tem permissão para alterar o ambiente do sistema (Infra)."
        
        # 5. Trava de Delegados: Trabalhadores NUNCA delegam tarefas.
        if is_worker:
            if tool_name in self.DELEGATION_TOOLS:
                return False, f"Violação: O agente '{agent_id}' (Trabalhador) não tem autoridade para delegar tarefas."

        # 6. Trava de Diretórios: Somente o system-worker cria pastas.
        if tool_name == "create_directory":
            if "system-worker" not in agent_id:
                return False, f"Violação: O agente '{agent_id}' não tem permissão para criar diretórios. Apenas o 'system-worker' tem esta competência."

        # 7. Trava de Arquivos Base para o System-Worker: Restringe escrita apenas a boilerplates.
        if "system-worker" in agent_id and tool_name == "write_file":
            import os
            path = params.get("path", "")
            filename = os.path.basename(path).lower()
            allowed_files = [".env", "readme.md", "package.json"]
            if filename not in allowed_files:
                return False, f"Violação de Escopo: O 'system-worker' só tem permissão física para escrever arquivos base ({', '.join(allowed_files)}). Tentativa em '{filename}' bloqueada."

        # 9. Trava de Hierarquia e Roteamento do Auditor Superior
        if agent_id == "superior-agent" and tool_name == "delegate_task":
            target = params.get("target_agent", "")
            topic = params.get("topic", "")
            
            # Bloqueia fala direta com Workers (Deve falar apenas com Leaders)
            if "leader" not in target:
                return False, f"Violação de Hierarquia: O Auditor Superior só pode delegar tarefas para LÍDERES (Tier 2). Tentativa de falar diretamente com o worker '{target}' negada."
            
            # Valida canal de rádio contra a tabela de roteamento
            if target in self.AUDITOR_ROUTING:
                expected_topic = self.AUDITOR_ROUTING[target]
                if topic != expected_topic:
                    return False, f"Erro de Endereçamento: O canal '{topic}' está incorreto para o líder '{target}'. O canal correto é '{expected_topic}'."

            # --- TRAVA FÍSICA DE SEQUÊNCIA (PHASE LOCK) ---
            # NOTA: O Superior agora gerencia fases via State Machine determinística.
            # Este guardrail é uma rede de segurança adicional.
            if target in self.PHASE_ORDER:
                target_idx = self.PHASE_ORDER.index(target)
                if target_idx > 0:
                    prev_agent = self.PHASE_ORDER[target_idx - 1]
                    
                    # Consulta o Banco de Dados para ver o status do antecessor
                    from core.store import StateStore
                    store = StateStore()
                    
                    # Pegamos o status atual
                    status = str(store.get_state(prev_agent, "global", "status") or "").lower()
                    
                    # Permite se: sucesso detectado, fase concluída, ou se é rate limit transitório
                    phase_ok = any(kw in status for kw in ["success", "concluí", "estável", "completa", "verificad", "fase"])
                    is_transient = any(kw in status for kw in ["rate limit", "aguardando", "online"])
                    
                    if not phase_ok:
                        if is_transient:
                            console.print(f"[yellow]⚠️  Aviso: {prev_agent} em estado transitório ({status[:50]}), Superior prossegue...[/yellow]")
                        elif "ocupado" in status:
                            return False, f"BLOQUEIO DE FASE: O Auditor não pode acionar o '{target}' enquanto o '{prev_agent}' não reportar SUCCESS. Status atual de {prev_agent}: {status}"
            # -----------------------------------------------

        return True, "Ação permitida."

    def log_denial(self, tool_name: str, reason: str):
        """
        Gera um log de negação em destaque (Vermelho).
        """
        console.print(f"\n[bold white on red] 🛡️  POLÍTICA VIOLADA [/bold white on red]")
        console.print(f"[red]Ação Negada:[/red] {tool_name}")
        console.print(f"[red]Motivo:[/red] {reason}\n")

# Singleton
guardrails = GuardrailEngine()
