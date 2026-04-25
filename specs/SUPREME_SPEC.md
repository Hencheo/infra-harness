# 📜 SUPREME SPEC: HARNESS TASK MANAGER V1

## 1. VISÃO GERAL
O objetivo deste projeto é criar um Gerenciador de Tarefas robusto e esteticamente premium, utilizando uma arquitetura separada entre Frontend, Backend e Banco de Dados.

## 2. STACK TÉCNICA
- **Database:** SQLite (Arquivo: `tasks.db` dentro da workspace).
- **Backend:** Python (Flask ou FastAPI).
- **Frontend:** React + Tailwind CSS (ou CSS Moderno).
- **Infra:** Gerenciamento de dependências via `pip` e `npm`.

## 3. REQUISITOS DE DADOS (Tier 2: Data)
- **Tabela `tasks`**:
    - `id`: INTEGER PRIMARY KEY
    - `title`: TEXT NOT NULL
    - `description`: TEXT
    - `status`: TEXT (Valores: 'pending', 'completed')
    - `created_at`: TIMESTAMP

## 4. REQUISITOS DE BACKEND (Tier 2: Backend)
- **API REST**:
    - `GET /tasks`: Lista todas as tarefas.
    - `POST /tasks`: Cria uma nova tarefa.
    - `PUT /tasks/<id>`: Alterna o status da tarefa.
    - `DELETE /tasks/<id>`: Remove uma tarefa.
- O servidor deve rodar na porta `5000`.

## 5. REQUISITOS DE FRONTEND (Tier 2: Frontend)
- **Interface**:
    - Lista de tarefas com cards elegantes.
    - Formulário simples para adicionar novas tarefas.
    - Efeito visual de "check" ao completar uma tarefa.
    - **Aesthetics**: Dark mode por padrão, tipografia moderna (Inter), bordas arredondadas e sombras suaves.

## 6. CRITÉRIOS DE AUDITORIA (Tier 1: Superior)
- **Localização**: Todos os arquivos DEVEM estar dentro da pasta `/workspace`.
- **Integridade**: O código Python deve passar na validação de sintaxe AST.
- **Segurança**: Caminhos não podem vazar para fora da sandbox.
- **Aprovação**: O projeto só é considerado completo após a instalação das dependências pelo `DependencyWorker`.

---
*Assinado: Antigravity Orchestrator*
