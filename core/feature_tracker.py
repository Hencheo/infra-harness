"""
Feature Tracker — Rastreador de Progresso via JSON.

Substitui o rastreamento de estado por Markdown (SUPREME_SPEC.md) 
por um arquivo JSON estruturado (specs/features.json) que os agentes
podem ler e atualizar de forma atômica e segura.

Referência: Análise de Lacunas, Seção 5.1 — "Substituição de Markdown por JSON"
"""

import json
import os
import threading
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone


class FeatureTracker:
    """
    Gerenciador atômico de progresso de features.
    
    Garante que:
    - Leituras e escritas são thread-safe (lock)
    - O arquivo JSON nunca é corrompido (write-to-temp + rename)
    - Cada mutação é registrada com timestamp
    """
    
    def __init__(self, json_path: str = "specs/features.json"):
        self.json_path = json_path
        self._lock = threading.Lock()
    
    # ── Leitura ──────────────────────────────────────────────────────

    def load(self) -> Dict[str, Any]:
        """Carrega o estado completo do JSON de features."""
        with self._lock:
            if not os.path.exists(self.json_path):
                raise FileNotFoundError(f"Feature tracker não encontrado: {self.json_path}")
            with open(self.json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    
    def get_phase(self, phase_id: str) -> Optional[Dict]:
        """Retorna os dados de uma fase específica pelo ID."""
        data = self.load()
        for phase in data.get("phases", []):
            if phase["id"] == phase_id:
                return phase
        return None
    
    def get_next_pending_phase(self) -> Optional[Dict]:
        """Retorna a primeira fase com status=false (próxima a ser executada)."""
        data = self.load()
        for phase in data.get("phases", []):
            if not phase.get("status", False):
                return phase
        return None  # Todas concluídas
    
    def get_next_pending_task(self, phase_id: str) -> Optional[Dict]:
        """Retorna a próxima task pendente (status=false) dentro de uma fase."""
        phase = self.get_phase(phase_id)
        if not phase:
            return None
        for task in phase.get("tasks", []):
            if not task.get("status", False):
                return task
        return None  # Todas as tasks da fase concluídas
    
    def get_progress_summary(self) -> Dict[str, Any]:
        """
        Gera um resumo compacto do progresso geral.
        Ideal para injetar no contexto do agente sem sobrecarregar.
        """
        data = self.load()
        phases = data.get("phases", [])
        
        total_tasks = 0
        completed_tasks = 0
        phase_summaries = []
        
        for phase in phases:
            tasks = phase.get("tasks", [])
            done = sum(1 for t in tasks if t.get("status", False))
            total_tasks += len(tasks)
            completed_tasks += done
            
            phase_summaries.append({
                "id": phase["id"],
                "name": phase["name"],
                "phase_status": phase.get("status", False),
                "tasks_done": done,
                "tasks_total": len(tasks),
            })
        
        return {
            "project": data.get("project", "Unknown"),
            "overall_progress": f"{completed_tasks}/{total_tasks}",
            "percentage": round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1),
            "phases": phase_summaries,
        }

    # ── Escrita Atômica ──────────────────────────────────────────────

    def _save(self, data: Dict[str, Any]):
        """
        Salva o estado de forma atômica (write-to-temp + rename).
        Previne corrupção em caso de crash durante a escrita.
        """
        tmp_path = self.json_path + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self.json_path)  # Atômico no Linux
    
    def complete_task(self, phase_id: str, task_id: str) -> bool:
        """
        Marca uma task específica como concluída (status: true).
        Se todas as tasks da fase estiverem concluídas, marca a fase também.
        
        Retorna True se a operação foi bem-sucedida.
        """
        with self._lock:
            data = self._load_unsafe()
            
            for phase in data.get("phases", []):
                if phase["id"] != phase_id:
                    continue
                
                for task in phase.get("tasks", []):
                    if task["id"] == task_id:
                        task["status"] = True
                        task["completed_at"] = datetime.now(timezone.utc).isoformat()
                        print(f"[FeatureTracker] ✅ Task '{task_id}' concluída na fase '{phase_id}'")
                        
                        # Auto-complete da fase se todas as tasks estiverem done
                        all_done = all(t.get("status", False) for t in phase.get("tasks", []))
                        if all_done:
                            phase["status"] = True
                            phase["completed_at"] = datetime.now(timezone.utc).isoformat()
                            print(f"[FeatureTracker] 🎯 Fase '{phase_id}' AUTO-COMPLETADA (todas as tasks concluídas)")
                        
                        self._save(data)
                        return True
            
            print(f"[FeatureTracker] ⚠️ Task '{task_id}' não encontrada na fase '{phase_id}'")
            return False
    
    def complete_phase(self, phase_id: str) -> bool:
        """
        Marca uma fase inteira como concluída (status: true), 
        incluindo todas as suas tasks.
        """
        with self._lock:
            data = self._load_unsafe()
            
            for phase in data.get("phases", []):
                if phase["id"] == phase_id:
                    phase["status"] = True
                    phase["completed_at"] = datetime.now(timezone.utc).isoformat()
                    # Marca todas as tasks como concluídas
                    for task in phase.get("tasks", []):
                        if not task.get("status", False):
                            task["status"] = True
                            task["completed_at"] = datetime.now(timezone.utc).isoformat()
                    
                    self._save(data)
                    print(f"[FeatureTracker] 🎯 Fase '{phase_id}' marcada como CONCLUÍDA")
                    return True
            
            print(f"[FeatureTracker] ⚠️ Fase '{phase_id}' não encontrada")
            return False
    
    def reset_phase(self, phase_id: str) -> bool:
        """Reseta uma fase e todas as suas tasks para status=false."""
        with self._lock:
            data = self._load_unsafe()
            
            for phase in data.get("phases", []):
                if phase["id"] == phase_id:
                    phase["status"] = False
                    phase.pop("completed_at", None)
                    for task in phase.get("tasks", []):
                        task["status"] = False
                        task.pop("completed_at", None)
                    
                    self._save(data)
                    print(f"[FeatureTracker] 🔄 Fase '{phase_id}' resetada")
                    return True
            return False
    
    def _load_unsafe(self) -> Dict[str, Any]:
        """Carrega sem lock (para uso interno quando já estamos dentro do lock)."""
        with open(self.json_path, 'r', encoding='utf-8') as f:
            return json.load(f)


# Singleton
feature_tracker = FeatureTracker()


# ── Teste rápido ──────────────────────────────────────────────────
if __name__ == "__main__":
    tracker = FeatureTracker()
    
    print("--- Progresso Atual ---")
    summary = tracker.get_progress_summary()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    
    print("\n--- Próxima Fase Pendente ---")
    next_phase = tracker.get_next_pending_phase()
    if next_phase:
        print(f"  ID: {next_phase['id']}, Nome: {next_phase['name']}")
        
        next_task = tracker.get_next_pending_task(next_phase['id'])
        if next_task:
            print(f"  Próxima task: {next_task['id']} — {next_task['description']}")
    
    print("\n--- Teste de Completar Task ---")
    tracker.complete_task("PHASE_1_INFRA", "infra_dirs")
    
    summary = tracker.get_progress_summary()
    print(f"  Progresso: {summary['overall_progress']} ({summary['percentage']}%)")
    
    # Reset para não sujar o estado
    tracker.reset_phase("PHASE_1_INFRA")
    print("  (Reset aplicado)")
