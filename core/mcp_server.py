from typing import Dict, Any, Callable
import os
from core.policies.guardrails import guardrails

class ToolRegistry:
    """
    Registro Central de Ferramentas (Padrão MCP Proxy).
    Atua como o único ponto de entrada para execução de ações no mundo real.
    """
    WORKSPACE_ROOT = "workspace"

    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._cache: Dict[str, Any] = {} # Cache cirúrgico para evitar logs repetitivos
        self._register_default_tools()
        # Garante que a workspace física exista
        if not os.path.exists(self.WORKSPACE_ROOT):
            os.makedirs(self.WORKSPACE_ROOT)

    def _get_safe_path(self, relative_path: str) -> str:
        """
        Converte um caminho relativo do agente em um caminho físico dentro da workspace.
        """
        if not relative_path: return self.WORKSPACE_ROOT
        # Remove barras iniciais e evita sair da pasta via ..
        clean_path = os.path.normpath(relative_path).lstrip(os.sep).replace("..", "")
        return os.path.join(self.WORKSPACE_ROOT, clean_path)

    def _register_default_tools(self):
        """
        Registra as ferramentas reais do sistema.
        """
        self.register_tool("read_file", self._real_read_file)
        self.register_tool("write_file", self._real_write_file)
        self.register_tool("list_files", self._real_list_files)
        self.register_tool("ping", self._real_ping)
        self.register_tool("delete_file", self._real_delete_file)
        self.register_tool("install_dependency", self._real_install_dependency)
        self.register_tool("filter_logs", self._deterministic_filter_logs)
        self.register_tool("delegate_task", self._deterministic_delegate)
        self.register_tool("create_directory", self._real_create_directory)

    def _real_install_dependency(self, params: Dict[str, Any]):
        """
        Instala dependências reais dentro da WORKSPACE_ROOT.
        """
        import subprocess
        package = params.get("package") 
        manager = params.get("manager", "auto")
        
        # Define o caminho de execução (Sempre dentro da workspace)
        cwd = self.WORKSPACE_ROOT
        
        print(f"[ToolRegistry] Instalando dependências na WORKSPACE (Manager: {manager})...")
        
        try:
            if manager == "auto":
                if os.path.exists(os.path.join(cwd, "package.json")): manager = "npm"
                elif os.path.exists(os.path.join(cwd, "requirements.txt")): manager = "pip"
                else: return {"status": "error", "message": "Nenhum manifesto encontrado na workspace."}

            command = []
            if manager == "npm":
                command = ["npm", "install", package] if package else ["npm", "install"]
            elif manager == "pip":
                command = ["pip", "install", package] if package else ["pip", "install", "-r", "requirements.txt"]
            
            output = subprocess.check_output(command, cwd=cwd, stderr=subprocess.STDOUT, text=True)
            return {"status": "success", "output": output}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _real_read_file(self, params: Dict[str, Any]):
        path = self._get_safe_path(params.get("path"))
        if not os.path.exists(path):
            return {"status": "error", "message": f"Arquivo não encontrado na workspace: {path}"}
        
        try:
            with open(path, 'r') as f:
                content = f.read()
            return {"status": "success", "content": content}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _real_write_file(self, params: Dict[str, Any]):
        path = self._get_safe_path(params.get("path"))
        content = params.get("content", "")
        
        try:
            # Garante que o diretório existe dentro da workspace
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write(content)
            return {"status": "success", "message": f"Arquivo escrito na workspace: {path}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _real_list_files(self, params: Dict[str, Any]):
        directory = self._get_safe_path(params.get("directory", "."))
        try:
            files = os.listdir(directory)
            return {"status": "success", "files": files}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _real_create_directory(self, params: Dict[str, Any]):
        path = self._get_safe_path(params.get("directory"))
        try:
            os.makedirs(path, exist_ok=True)
            return {"status": "success", "message": f"Diretório criado/verificado: {path}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _real_ping(self, params: Dict[str, Any]):
        import subprocess
        host = params.get("host", "8.8.8.8")
        try:
            # Executa ping real (1 pacote)
            output = subprocess.check_output(["ping", "-c", "1", host], stderr=subprocess.STDOUT, text=True)
            return {"status": "success", "output": output}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _real_delete_file(self, params: Dict[str, Any]):
        # Nota: Esta ferramenta será barrada pelos Guardrails para a maioria dos agentes
        path = self._get_safe_path(params.get("path"))
        try:
            if os.path.exists(path):
                os.remove(path)
                return {"status": "success", "message": f"Arquivo deletado da workspace: {path}"}
            return {"status": "error", "message": "Arquivo não existe na workspace."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _deterministic_delegate(self, params: Dict[str, Any]):
        """
        Ferramenta física de delegação. Envia uma mensagem para o rádio.
        """
        from core.event_bus import EventBus
        bus = EventBus()
        target = params.get("target_agent")
        payload = params.get("payload")
        
        # Prioriza o tópico passado pelo Líder (Isolamento por Depto)
        topic = params.get("topic", f"harness.agents.{target}")
        
        bus.publish(topic, payload)
        
        return {
            "status": "success",
            "message": f"Tarefa delegada via canal: {topic}"
        }

    def register_tool(self, name: str, func: Callable):
        self._tools[name] = func
        print(f"[ToolRegistry] Ferramenta registrada: {name}")

    def call_tool(self, agent_id: str, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ponto de entrada único para chamada de ferramentas com Guardrails.
        """
        # --- INTERCEPTAÇÃO DE SEGURANÇA (FASE 3.2 - AGORA COM ACL) ---
        allowed, reason = guardrails.validate_request(agent_id, tool_name, params)
        if not allowed:
            guardrails.log_denial(tool_name, reason)
            return {"status": "denied", "message": reason}
        # ---------------------------------------------

        # --- CACHE CIRÚRGICO (Evita flood de list_files nos logs) ---
        import time
        cache_key = f"{tool_name}:{str(params)}"
        if tool_name == "list_files":
            cache_entry = self._cache.get(cache_key)
            if cache_entry and (time.time() - cache_entry['ts'] < 2.0):
                return cache_entry['result']
        # -----------------------------------------------------------

        if tool_name not in self._tools:
            return {"status": "error", "message": f"Ferramenta {tool_name} não encontrada."}
        
        print(f"[ToolRegistry] Invocando: {tool_name} com params: {params}")
        
        try:
            # Executa a ferramenta
            result = self._tools[tool_name](params)
            
            # Salva no cache se for list_files
            if tool_name == "list_files":
                self._cache[cache_key] = {'ts': time.time(), 'result': result}
                
            return result
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # --- Implementações Determinísticas Inteligentes ---

    def _deterministic_filter_logs(self, params: Dict[str, Any]):
        """
        Filtra logs localmente para enviar apenas o essencial ao LLM.
        """
        raw_logs = params.get("raw_data", "")
        keyword = params.get("keyword", "ERROR")
        
        lines = raw_logs.split("\n")
        filtered = [line for line in lines if keyword in line]
        
        return {
            "status": "success",
            "count": len(filtered),
            "filtered_data": "\n".join(filtered)
        }

# Singleton para acesso global facilitado
mcp_server = ToolRegistry()

if __name__ == "__main__":
    # Teste 1: Líder tentando escrever arquivo (Deve ser NEGADO)
    print("\n[Teste] Líder tentando criar arquivo...")
    res_leader = mcp_server.call_tool("frontend-leader", "write_file", {"path": "ui.html", "content": "test"})
    print(f"Resultado Líder: {res_leader['status']}")
    
    # Teste 2: Auditor tentando deletar arquivo (Deve ser NEGADO)
    print("\n[Teste] Auditor tentando deletar arquivo...")
    res_auditor = mcp_server.call_tool("superior-agent", "delete_file", {"path": "core.py"})
    print(f"Resultado Auditor: {res_auditor['status']}")

    # Teste 3: Worker tentando fazer um ping real (Deve ser PERMITIDO)
    print("\n[Teste] Worker fazendo ping real...")
    res_worker = mcp_server.call_tool("frontend-worker", "ping", {"host": "8.8.8.8"})
    print(f"Resultado Worker: {res_worker['status']}")
    if res_worker['status'] == "success":
        print(f"Saída do Ping: {res_worker.get('output', '')[:50]}...")

    # Teste 4: Líder delegando tarefa (Deve ser PERMITIDO)
    print("\n[Teste] Líder delegando tarefa...")
    res_del = mcp_server.call_tool("frontend-leader", "delegate_task", {
        "target_agent": "worker-1",
        "payload": {"action": "build_button"}
    })
    print(f"Resultado Delegação Líder: {res_del['status']}")

    # Teste 5: Worker tentando delegar tarefa (Deve ser NEGADO)
    print("\n[Teste] Worker tentando delegar...")
    res_del_fail = mcp_server.call_tool("frontend-worker", "delegate_task", {
        "target_agent": "worker-2",
        "payload": {"action": "hack"}
    })
    print(f"Resultado Delegação Worker: {res_del_fail['status']}")
