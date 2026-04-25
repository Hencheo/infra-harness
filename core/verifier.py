from typing import Dict, Any

class DeterministicVerifier:
    """
    Componente de Verificação Determinística (Camada V).
    Executa testes locais para confirmar se os objetivos foram atingidos
    sem necessidade de raciocínio de LLM.
    """
    
    def verify(self, step_id: str, result_data: Any) -> bool:
        """
        Seleciona e executa o teste de sucesso apropriado para o passo.
        """
        method_name = f"_verify_{step_id}"
        verifier_method = getattr(self, method_name, self._default_verify)
        
        print(f"[Verifier] Verificando passo: {step_id}")
        return verifier_method(result_data)

    def _default_verify(self, result_data: Any) -> bool:
        # Por padrão, se houver um status de sucesso no resultado, consideramos válido
        if isinstance(result_data, dict):
            return result_data.get("status") == "success"
        return True

    def _verify_extracao_logs(self, result_data: Any) -> bool:
        """
        Verifica se os logs foram realmente coletados e contêm dados.
        """
        if not result_data or "data" not in result_data:
            return False
        return len(result_data["data"]) > 0

    def _verify_analise_erro(self, result_data: Any) -> bool:
        """
        Verifica se a análise gerou um conteúdo útil (não está vazia).
        """
        if not result_data or "content" not in result_data:
            return False
        return len(result_data["content"]) > 10

    def _verify_deploy_script(self, result_data: Any) -> bool:
        """
        Verificação física e técnica: Checa existência, tamanho e sintaxe.
        """
        file_path = result_data.get("file_path")
        if not file_path:
            return False
        
        # 1. Check de Existência e Tamanho
        if not self._verify_file_integrity(file_path):
            return False

        # 2. Check de Sintaxe (se for Python)
        if file_path.endswith(".py"):
            if not self._verify_python_syntax(file_path):
                return False
        
        print(f"[Verifier] SUCESSO: Arquivo {file_path} validado fisicamente.")
        return True

    # --- Utilitários Determinísticos (HVG) ---

    def _verify_python_syntax(self, file_path: str) -> bool:
        """
        Analisa a árvore sintática (AST) do arquivo para garantir que o código é válido.
        """
        import ast
        import os
        if not os.path.exists(file_path): return False
        try:
            with open(file_path, 'r') as f:
                ast.parse(f.read())
            return True
        except Exception as e:
            print(f"[Verifier] ❌ ERRO DE SINTAXE detectado em {file_path}: {e}")
            return False

    def _verify_file_integrity(self, file_path: str, min_bytes: int = 5) -> bool:
        """
        Verifica se o arquivo existe e não é um 'placeholder' vazio.
        """
        import os
        if not os.path.exists(file_path):
            print(f"[Verifier] ❌ ARQUIVO FANTASMA: {file_path} não existe no disco.")
            return False
        
        size = os.path.getsize(file_path)
        if size < min_bytes:
            print(f"[Verifier] ❌ ARQUIVO CORROMPIDO: {file_path} possui apenas {size} bytes.")
            return False
        return True

# Singleton
verifier = DeterministicVerifier()
