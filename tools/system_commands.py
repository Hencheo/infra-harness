import os
import subprocess
from typing import Dict, Any

def get_logs(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Coleta logs reais do sistema ou do projeto.
    """
    lines = params.get("lines", 20)
    file_path = params.get("file", "sys_audit.log") # Default para log do Harness
    
    try:
        # Tenta ler o arquivo se existir, senão usa tail no syslog (se Linux)
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                data = f.readlines()[-lines:]
            return {"status": "success", "data": "".join(data)}
        else:
            # Fallback para dmesg ou similar se permitido
            output = subprocess.check_output(["tail", "-n", str(lines), "/var/log/syslog"], text=True)
            return {"status": "success", "data": output}
    except Exception as e:
        return {"status": "error", "message": f"Erro ao coletar logs: {str(e)}"}

def check_process(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verifica se um processo está rodando (ex: redis, python).
    """
    name = params.get("name")
    try:
        output = subprocess.check_output(["pgrep", "-f", name], text=True)
        return {"status": "success", "running": True, "pids": output.strip().split("\n")}
    except subprocess.CalledProcessError:
        return {"status": "success", "running": False, "message": "Processo não encontrado."}

def validate_fix(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validação genérica de uptime/saúde.
    """
    return {
        "status": "success",
        "timestamp": subprocess.check_output(["date"], text=True).strip(),
        "load": subprocess.check_output(["uptime"], text=True).strip()
    }

# Mapeamento de funções de sistema disponíveis
SYSTEM_TOOLS = {
    "get_logs": get_logs,
    "validate_fix": validate_fix,
    "check_process": check_process
}
