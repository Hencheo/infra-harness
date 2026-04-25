import os
import sys
import json
import sqlite3
import time
from datetime import datetime

# Garante que o Python encontre o diretório 'core' e outros na raiz do projeto
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from rich.live import Live
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.console import Console
from rich.text import Text
from core.event_bus import EventBus

console = Console()

class Cockpit:
    def __init__(self):
        self.bus = EventBus()
        self.db_path = os.path.join(project_root, "data/harness_state.db")
        self.messages = []
        self.active_tasks = []
        self.max_messages = 8
        
        import threading
        self.thread = threading.Thread(target=self._listen_radio, daemon=True)
        self.thread.start()

    def _listen_radio(self):
        pubsub = self.bus.redis_client.pubsub()
        pubsub.psubscribe("harness.*")
        for message in pubsub.listen():
            if message['type'] == 'pmessage':
                try:
                    data = json.loads(message['data'])
                    topic = message['channel']
                    
                    # Formata log de chamada: Quem -> Onde (Ação)
                    source = data.get("agent_id", "System")
                    action = data.get("action", data.get("status", "call"))
                    log_entry = f"[bold cyan]{source}[/bold cyan] ➡️ [yellow]{topic}[/yellow] ([white]{action}[/white])"
                    
                    self.messages.append(log_entry)
                    if len(self.messages) > self.max_messages:
                        self.messages.pop(0)
                        
                    # Se for uma tarefa, joga pro topo
                    if "action" in data:
                        self.active_tasks = [f"🚀 [bold green]EXECUÇÃO ATIVA:[/bold green] {data['action']} (ID: {data.get('execution_id', 'N/A')})"]
                except:
                    pass

    def get_agent_table(self):
        table = Table(expand=True, border_style="dim")
        table.add_column("AGENTE", style="bold white")
        table.add_column("DEPTO", style="magenta")
        table.add_column("STATUS", style="bold")
        table.add_column("ÚLTIMO SINAL", justify="right", style="dim")

        rows = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Pega o último sinal de cada agente
                cursor.execute("SELECT agent_id, MAX(updated_at), value FROM agent_state GROUP BY agent_id")
                for row in cursor.fetchall():
                    agent, ts, val = row
                    val_lower = val.lower()
                    
                    # Lógica de Status: Se tiver 'ocupado' ou 'processing' no valor do estado
                    is_busy = "ocupado" in val_lower or "processing" in val_lower or "executando" in val_lower
                    status_text = "OCUPADO" if is_busy else "ONLINE"
                    status_style = "bold green" if is_busy else "bold yellow"
                    
                    depto = "Backend" if "backend" in agent else ("Frontend" if "frontend" in agent else ("Audit" if "superior" in agent else "Infra"))
                    last_signal = ts.split("T")[-1][:8] if ts else "-"
                    
                    rows.append({
                        "agent": agent,
                        "depto": depto,
                        "status": status_text,
                        "style": status_style,
                        "ts": last_signal,
                        "busy_rank": 0 if is_busy else 1 # Para ordenação (0 vem primeiro)
                    })
        except:
            table.add_row("Aguardando agentes...", "-", "-", "-")
            return table

        # Ordena: Ocupados primeiro, depois por nome de agente
        rows.sort(key=lambda x: (x["busy_rank"], x["agent"]))

        for r in rows:
            table.add_row(r["agent"], r["depto"], Text(r["status"], style=r["style"]), r["ts"])
            
        return table

def run():
    cockpit = Cockpit()
    console = Console()
    
    with Live(screen=True, refresh_per_second=4) as live:
        while True:
            # Layout de 3 andares
            layout = Layout()
            layout.split_column(
                Layout(name="top", size=5),
                Layout(name="mid", ratio=1),
                Layout(name="bot", size=10)
            )
            
            # TOPO: Tarefa em Execução
            task_info = "\n".join(cockpit.active_tasks) if cockpit.active_tasks else "⏸️ AGUARDANDO NOVA MISSÃO NA SPEC..."
            layout["top"].update(Panel(task_info, title="[bold white]TOP: TAREFA EM EXECUÇÃO[/bold white]", border_style="green"))
            
            # MEIO: Quem está trabalhando
            layout["mid"].update(Panel(cockpit.get_agent_table(), title="[bold white]MID: QUEM ESTÁ TRABALHANDO[/bold white]", border_style="cyan"))
            
            # BASE: Feed de Chamadas
            call_feed = "\n".join(cockpit.messages)
            layout["bot"].update(Panel(call_feed, title="[bold white]BOT: QUEM ESTÁ SENDO CHAMADO (RADIO FEED)[/bold white]", border_style="blue"))
            
            live.update(layout)
            time.sleep(0.2)

if __name__ == "__main__":
    run()
