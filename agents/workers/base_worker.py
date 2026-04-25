import os
import time
import logging

# Silencia logs verbosos de bibliotecas externas
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("agno").setLevel(logging.WARNING)
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from core.mcp_server import mcp_server
from core.event_bus import EventBus
from core.store import StateStore
from dotenv import load_dotenv

load_dotenv()

class BaseWorker:
    """
    Classe base para todos os trabalhadores (Agentes) do Harness.
    Tier 3: O braço executor com permissões de escrita.
    """
    def __init__(self, agent_id: str, department: str, role: str = "worker"):
        self.agent_id = agent_id
        self.department = department
        self.role = role
        
        # Separação de canais: Líderes ouvem .leader, Workers ouvem .worker
        suffix = "leader" if role == "leader" else "worker"
        self.topic = f"harness.{department}.{suffix}"
        
        self.bus = EventBus()
        self.store = StateStore()

        # Define o conjunto de ferramentas com base no Papel (Role)
        if role == "leader":
            # Líderes: Leitura + Delegação (Sem Escrita)
            tools = [self.read_file, self.list_files]
        elif role == "auditor":
            # Auditor: Leitura + Delegação (Autoridade Máxima)
            tools = [self.read_file, self.list_files]
        elif "system-worker" in agent_id:
            # System Worker: Apenas o necessário para infra (DEDICADO)
            tools = [self.read_file, self.write_file, self.list_files, self.create_directory]
        else:
            # Trabalhadores: Leitura + Escrita + Sistema
            tools = [self.read_file, self.write_file, self.list_files, self.ping, self.check_process]

        # Inteligência (Configuração Base)
        self.ai = Agent(
            name=f"{role.capitalize()} {agent_id}",
            model=OpenAIChat(
                id=os.getenv("DEFAULT_MODEL"),
                api_key=os.getenv("FIREWORKS_API_KEY"),
                base_url=os.getenv("FIREWORKS_API_BASE")
            ),
            description=f"Você é um {role} do departamento {department}.",
            instructions=[
                f"Sua função principal é atuar como {role} no Harness.",
                "PROTOCOLO DE ESTADO: Verifique o [AUTO-SNAPSHOT] no início da mensagem para entender o ambiente atual.",
                "Evite usar 'list_files' se a informação necessária já estiver no Snapshot. Use-o apenas para explorar subpastas que não aparecem na listagem inicial.",
                "Mantenha a segurança e integridade do projeto."
            ],
            tools=tools,
            markdown=True
        )
        
        # Check-in Inicial: Aparecer no Cockpit imediatamente
        self.store.set_state(self.agent_id, "global", "status", "ONLINE (Aguardando missão)")

    # --- MCP Tools Proxies ---
    
    def create_directory(self, directory: str):
        return mcp_server.call_tool(self.agent_id, "create_directory", {"directory": directory})
    
    def read_file(self, path: str):
        return mcp_server.call_tool(self.agent_id, "read_file", {"path": path})

    def write_file(self, path: str, content: str):
        return mcp_server.call_tool(self.agent_id, "write_file", {"path": path, "content": content})

    def safe_run(self, prompt: str, max_retries: int = 5, delay: int = 60):
        """
        Executa a IA com tolerância a Rate Limit (exceção ou texto) e feedback no Cockpit.
        Inclui um cooldown fixo para evitar estouro de RPM (Requests Per Minute).
        """
        # Governador de Velocidade: Garante que cada agente "respire" antes de chamar a API
        # Aumentado para 4s para maior proteção de RPM
        time.sleep(4) 

        # Snapshot automático para reduzir chamadas redundantes de list_files (Economia de tokens/tempo)
        try:
            files = os.listdir("workspace")
            prompt = f"[AUTO-SNAPSHOT] Workspace (.): {files}\n\n" + prompt
        except: pass

        for attempt in range(max_retries):
            try:
                response = self.ai.run(prompt)
                
                # Detecção de Rate Limit "escondido" no conteúdo (Agno catch-all)
                if response and response.content:
                    content_lower = response.content.lower()
                    if "429" in content_lower or "rate limit" in content_lower:
                        raise Exception(f"Rate Limit detectado no conteúdo: {response.content}")
                
                return response
            except Exception as e:
                err_msg = str(e).lower()
                if "429" in err_msg or "rate limit" in err_msg:
                    print(f"[{self.agent_id}] ⚠️ Rate Limit detectado (Tentativa {attempt+1}). Dormindo {delay}s...")
                    self.store.set_state(self.agent_id, "global", "status", f"🚨 RATE LIMIT: Aguardando {delay}s...")
                    time.sleep(delay)
                    continue
                raise e
        return None

    def list_files(self, directory: str = "."):
        return mcp_server.call_tool(self.agent_id, "list_files", {"directory": directory})

    def ping(self, host: str = "8.8.8.8"):
        return mcp_server.call_tool(self.agent_id, "ping", {"host": host})

    def check_process(self, name: str):
        return mcp_server.call_tool(self.agent_id, "check_process", {"name": name})

    def start(self):
        """
        Inicia a escuta com Jitter para evitar avalanche de API no startup.
        Usa subscribe_blocking() como última chamada para manter o processo vivo.
        Subclasses que precisam de múltiplos canais devem chamar subscribe() (não-bloqueante)
        ANTES de chamar subscribe_blocking() no último canal.
        """
        import random
        # Tier 1 e 2 começam antes, Tier 3 (Workers) esperam mais
        base_delay = 2 if self.role in ["leader", "auditor"] else 7
        jitter = random.uniform(0, 8)
        total_delay = base_delay + jitter
        
        print(f"[{self.agent_id}] ⏳ Escalonando tráfego (Jitter: {total_delay:.1f}s)...")
        time.sleep(total_delay)
        
        print(f"[{self.agent_id}] 📡 Escutando canal: {self.topic} (Depto: {self.department})")
        # NOTA: Subclasses que fazem override de start() devem chamar 
        # subscribe() para canais extras e subscribe_blocking() para o último.
        self.bus.subscribe_blocking(self.topic, self._process_task)

    def _process_task(self, task_payload: dict):
        """
        Lógica de processamento com inteligência de rádio (suporta payloads embrulhados).
        """
        # Desembrulha a mensagem se vier no formato do Auditor Superior
        if "payload" in task_payload and isinstance(task_payload["payload"], dict):
            inner = task_payload["payload"]
            action = inner.get("action")
            params = inner.get("params", {})
        else:
            action = task_payload.get("action")
            params = task_payload.get("data", task_payload.get("params", {}))

        sender_dept = task_payload.get("dept")
        exec_id = task_payload.get("execution_id")

        # --- TRAVA DE SEGURANÇA ESTRUTURAL (Multi-Tier) ---
        # Aceita se vier do próprio depto OU se vier da Auditoria Superior (audit)
        if sender_dept != self.department and sender_dept != "audit":
            print(f"[{self.agent_id}] ⚠️ TENTATIVA DE INVASÃO: Ordem do depto '{sender_dept}' negada.")
            return 
        # --------------------------------------------------

        print(f"[{self.agent_id}] ✅ Ordem aceita: {action} (Exec: {exec_id})")
        
        # Reporta que começou a trabalhar (para visibilidade no Cockpit)
        self.store.set_state(self.agent_id, exec_id or "global", "status", f"OCUPADO: {action}")

        # --- EXECUÇÃO REAL VIA LLM (SAFE) ---
        # Constrói o contexto da tarefa para a IA
        contexto = f"Tarefa recebida: {action}\nParâmetros: {params}\nID Execução: {exec_id}"
        
        try:
            response = self.safe_run(contexto)
            if response:
                resultado_final = response.content
                status_final = "success"
            else:
                resultado_final = "Falha após múltiplas tentativas de Rate Limit."
                status_final = "failed"
        except Exception as e:
            resultado_final = f"Erro na execução: {str(e)}"
            status_final = "failed"
        # -----------------------------
        
        # Reporta resultado real
        self.report_result(exec_id, task_payload.get("step_id") or action, status_final, {"output": resultado_final})

    def report_result(self, execution_id: str, step_id: str, status: str, data: dict):
        """
        Envia o resultado para o tópico central de resultados e persiste no banco.
        """
        payload = {
            "execution_id": execution_id,
            "step_id": step_id,
            "agent_id": self.agent_id,
            "status": status,
            "data": data,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        # CRÍTICO: Salva no DB ANTES de publicar no bus.
        # O callback do Superior dispara imediatamente no publish e o guardrail
        # consulta o DB — se salvarmos depois, ele lê o status antigo (OCUPADO).
        status_msg = f"{status}: {str(data)[:50]}"
        self.store.set_state(self.agent_id, execution_id or "global", "status", status_msg)
        
        self.bus.publish("harness.results", payload)

if __name__ == "__main__":
    # Exemplo de inicialização de um worker genérico
    worker = BaseWorker("generic-worker", "backend")
    worker.start()
