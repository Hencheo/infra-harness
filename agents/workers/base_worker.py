import os
import time
import uuid
import json
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
from core.protocols import validate_result, build_result
from core.observability import tracer, EventType
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
            markdown=True,
            # ── CONTEXT ISOLATION: Cada run é isolada, sem histórico contaminante ──
            add_history_to_context=False,
            num_history_runs=0,
        )
        
        # Contador de tarefas processadas nesta sessão (para diagnóstico)
        self._tasks_processed = 0
        self._current_session_tag = str(uuid.uuid4())[:8]
        
        # Check-in Inicial: Aparecer no Cockpit imediatamente
        self.store.set_state(self.agent_id, "global", "status", "ONLINE (Aguardando missão)")

    # ── CONTEXT ISOLATION (Spawning Limpo) ───────────────────────────
    
    def _reset_context(self, completed_action: str = "", summary: str = ""):
        """
        Reseta o contexto do agente para a próxima tarefa.
        
        Gera um novo session_id no Agno Agent, garantindo que a próxima
        chamada a self.ai.run() comece com uma janela de contexto 100% limpa.
        
        Baseado na estratégia Anthropic V2: ao finalizar uma feature,
        o agente atual é "morto" e um novo nasce com contexto limpo.
        
        Ref: Análise de Lacunas, Seção 5.3 — "Limpeza de Contexto por Feature"
        """
        old_session = self._current_session_tag
        
        # Arquiva o contexto da sessão que está terminando
        self._archive_context(old_session, completed_action, summary)
        
        # Gera uma nova sessão limpa
        self._current_session_tag = str(uuid.uuid4())[:8]
        self.ai.session_id = f"{self.agent_id}-{self._current_session_tag}"
        self._tasks_processed += 1
        
        print(f"[{self.agent_id}] 🔄 CONTEXT RESET: Sessão {old_session} → {self._current_session_tag} "
              f"(Tasks processadas: {self._tasks_processed})")
    
    def _archive_context(self, session_tag: str, action: str, summary: str):
        """
        Arquiva um resumo da sessão completada em cold storage (arquivo de log).
        Isso preserva a "memória episódica" sem poluir o contexto ativo.
        
        Ref: Análise de Lacunas, Seção 4.1 — "Separação de Contexto Ativo e Experiência"
        """
        archive_dir = "logs/context_archive"
        os.makedirs(archive_dir, exist_ok=True)
        
        archive_entry = {
            "agent_id": self.agent_id,
            "session_tag": session_tag,
            "action": action,
            "summary": summary[:500] if summary else "(sem resumo)",
            "tasks_processed": self._tasks_processed,
            "archived_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        
        archive_path = os.path.join(archive_dir, f"{self.agent_id}_history.jsonl")
        try:
            with open(archive_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(archive_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[{self.agent_id}] ⚠️ Falha ao arquivar contexto: {e}")
    
    # ── FIM CONTEXT ISOLATION ─────────────────────────────────────────

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
                    # ── TRACE: Rate Limit ──
                    tracer.emit(EventType.RATE_LIMIT, self.agent_id, {
                        "attempt": attempt + 1,
                        "delay_s": delay,
                    })
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
        
        # ── TRACE: Task iniciada ──
        task_trace_id = tracer.emit(EventType.TASK_STARTED, self.agent_id, {
            "action": action,
            "params_keys": list(params.keys()) if isinstance(params, dict) else [],
        }, execution_id=exec_id)

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
        
        # ── TRACE: Task concluída ou falhada ──
        trace_type = EventType.TASK_COMPLETED if status_final == "success" else EventType.TASK_FAILED
        tracer.emit(trace_type, self.agent_id, {
            "action": action,
            "status": status_final,
            "output_preview": str(resultado_final)[:100] if resultado_final else "",
        }, parent_id=task_trace_id, execution_id=exec_id)
        
         # Reporta resultado real
        self.report_result(exec_id, task_payload.get("step_id") or action, status_final, {"output": resultado_final})
        
        # ── CONTEXT ISOLATION: Reset após conclusão da task ──
        # Ao terminar uma task (sucesso ou falha), limpa o contexto para a próxima.
        # Isso impede que o histórico de uma task pollua o raciocínio da seguinte.
        self._reset_context(
            completed_action=action or "unknown",
            summary=str(resultado_final)[:300] if resultado_final else ""
        )
        # ── FIM CONTEXT ISOLATION ──

    def report_result(self, execution_id: str, step_id: str, status: str, data: dict):
        """
        Envia o resultado para o tópico central de resultados e persiste no banco.
        
        PROTOCOLO A2A: Valida o payload contra o schema de resultado
        antes de publicar no EventBus.
        """
        payload = build_result(
            agent_id=self.agent_id,
            step_id=step_id,
            status=status,
            data=data,
            execution_id=execution_id,
        )
        
        # ── A2A VALIDATION: Garante que o resultado é válido antes de publicar ──
        is_valid, reason = validate_result(payload)
        if not is_valid:
            print(f"[{self.agent_id}] ⛔ A2A REJEITADO (report_result): {reason}")
            # Corrige para um status válido para não travar o fluxo
            payload["status"] = "failed"
            payload["data"] = {"error": f"Payload original inválido: {reason}"}
        # ── FIM A2A VALIDATION ──
        
        # CRÍTICO: Salva no DB ANTES de publicar no bus.
        # O callback do Superior dispara imediatamente no publish e o guardrail
        # consulta o DB — se salvarmos depois, ele lê o status antigo (OCUPADO).
        status_msg = f"{payload['status']}: {str(payload['data'])[:50]}"
        self.store.set_state(self.agent_id, execution_id or "global", "status", status_msg)
        
        self.bus.publish("harness.results", payload)

if __name__ == "__main__":
    # Exemplo de inicialização de um worker genérico
    worker = BaseWorker("generic-worker", "backend")
    worker.start()
