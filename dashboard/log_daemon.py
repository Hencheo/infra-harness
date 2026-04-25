import os
import time
import sys
from rich.console import Console
from rich.text import Text

# Garante que o console use cores mesmo em background se necessário
console = Console(force_terminal=True)

# Mapa de cores por departamento/agente
COLORS = {
    "superior": "bold magenta",
    "infra": "bold cyan",
    "data": "bold yellow",
    "backend": "bold green",
    "frontend": "bold blue",
    "system": "white",
    "sqlite": "yellow",
    "react": "blue",
    "dependency": "red",
    "guardrails": "bold red"
}

def get_color(filename):
    for key, color in COLORS.items():
        if key in filename.lower():
            return color
    return "white"

def tail_logs():
    log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
    
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    files_state = {} # path: last_size
    
    console.print("\n[bold green]🚀 HARNESS LOG DAEMON V1[/bold green]")
    console.print("[dim]Monitorando fluxo de rádio e pensamento dos agentes...[/dim]\n")

    while True:
        try:
            current_logs = [f for f in os.listdir(log_dir) if f.endswith(".log")]
            
            for f in current_logs:
                path = os.path.join(log_dir, f)
                size = os.path.getsize(path)
                
                if path not in files_state:
                    # Se o arquivo é novo, começa lendo as últimas 5 linhas ou do zero
                    files_state[path] = max(0, size - 1000) 
                
                if size > files_state[path]:
                    with open(path, "r", errors="ignore") as file:
                        file.seek(files_state[path])
                        lines = file.readlines()
                        files_state[path] = size
                        
                        for line in lines:
                            clean_line = line.strip()
                            if clean_line:
                                agent_id = f.replace(".log", "").upper()
                                color = get_color(f)
                                
                                # Formatação Premium
                                timestamp = time.strftime("%H:%M:%S")
                                msg = Text()
                                msg.append(f"{timestamp} ", style="dim")
                                msg.append(f"[{agent_id}] ", style=color)
                                
                                # Destaca alertas de Rate Limit ou Guardrails
                                if "RATE LIMIT" in clean_line or "VIOLADA" in clean_line:
                                    msg.append(clean_line, style="bold yellow on red")
                                elif "DELEGANDO" in clean_line:
                                    msg.append(clean_line, style="bold green")
                                else:
                                    msg.append(clean_line)
                                    
                                console.print(msg)
            
            time.sleep(0.5)
        except KeyboardInterrupt:
            console.print("\n[bold red]👋 Log Daemon encerrado.[/bold red]")
            break
        except Exception as e:
            time.sleep(2)
            continue

if __name__ == "__main__":
    tail_logs()
