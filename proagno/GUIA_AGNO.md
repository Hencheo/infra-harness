# Guia de Referência: Agno (Anteriormente Phidata)

O **Agno** é um framework open-source projetado para construir sistemas multi-agente multimodais com memória, conhecimento e ferramentas integradas. Ele é ideal para criar agentes que não apenas geram texto, mas que agem e resolvem problemas complexos.
[text](https://docs.agno.com/)
---

## 1. Conceitos Fundamentais (ETCSLV no Agno)

O Agno se alinha perfeitamente com a arquitetura **ETCSLV** do Harness:

*   **Agents (E/T):** O núcleo do sistema. Utilizam LLMs para raciocinar e ferramentas para agir.
*   **Knowledge (C):** Suporte nativo a RAG (Retrieval-Augmented Generation) com bancos de vetores.
*   **Storage (S):** Persistência de sessões e memória em bancos SQL (SQLite, PostgreSQL).
*   **Teams (L/V):** Grupos de agentes que colaboram, permitindo delegação e supervisão.
*   **Workflows (L/V):** Orquestração determinística de passos, ideal para processos repetíveis.

---

## 2. Instalação

```bash
# Instalação básica
pip install -U agno

# Com suporte a AgentOS (Produção)
pip install -U 'agno[os]'
```

---

## 3. Criando seu Primeiro Agente

Um agente simples que utiliza ferramentas de busca (DuckDuckGo):

```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools.duckduckgo import DuckDuckGo

agent = Agent(
    model=OpenAIChat(id="gpt-4o"),
    description="Você é um assistente de pesquisa especializado em tecnologia.",
    tools=[DuckDuckGo()],
    show_tool_calls=True,
    markdown=True,
)

agent.print_response("Quais as principais novidades do framework Agno em 2026?", stream=True)
```

---

## 4. Multi-Agentes (Teams)

O Agno permite criar equipes onde um agente coordena outros especialistas:

```python
from agno.agent import Agent
from agno.agent.team import Team
from agno.models.openai import OpenAIChat
from agno.tools.duckduckgo import DuckDuckGo
from agno.tools.yfinance import YFinanceTools

# Agente Especialista em Finanças
finance_agent = Agent(
    name="Finance Agent",
    role="Analista de mercado financeiro",
    model=OpenAIChat(id="gpt-4o"),
    tools=[YFinanceTools(stock_price=True, analyst_recommendations=True)],
    instructions=["Sempre use tabelas para exibir dados financeiros."],
)

# Agente Especialista em Notícias
web_agent = Agent(
    name="Web Agent",
    role="Pesquisador de notícias",
    model=OpenAIChat(id="gpt-4o"),
    tools=[DuckDuckGo()],
    instructions=["Sempre cite as fontes das notícias."],
)

# Equipe Orquestrada
agent_team = Team(
    agents=[finance_agent, web_agent],
    model=OpenAIChat(id="gpt-4o"),
    instructions=["Combine as análises financeiras com as notícias recentes para um relatório completo."],
    show_tool_calls=True,
    markdown=True,
)

agent_team.print_response("Analise as ações da NVIDIA e as notícias recentes sobre IA.", stream=True)
```

---

## 5. AgentOS (Produção e API)

O **AgentOS** transforma seus agentes em uma API de produção pronta para o mundo real, com suporte a streaming, autenticação e isolamento de sessão.

```python
from agno.agent import Agent
from agno.os import AgentOS

assistant = Agent(name="Harness Assistant", markdown=True)

# Transforma o agente em uma aplicação FastAPI/Produção
agent_os = AgentOS(agents=[assistant], tracing=True)
app = agent_os.get_app()
```

---

## 6. Por que usar Agno no Projeto Harness?

1.  **Protocolo MCP Nativo:** Suporte direto ao *Model Context Protocol*, facilitando a integração de novas ferramentas.
2.  **Isolamento de Sessão:** Gerenciamento automático de memória por usuário.
3.  **Handoff Protocols:** Facilita a transferência de contexto entre agentes (Agente A -> Agente B).
4.  **Verificação Determinística:** Pode ser integrado com a fase de verificação do Harness para validar saídas de ferramentas antes da resposta final.

---
*Documentação gerada para o projeto HARNESS-INFRA em 2026-04-22.*
