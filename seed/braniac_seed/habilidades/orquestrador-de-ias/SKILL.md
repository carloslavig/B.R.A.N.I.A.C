---
name: orquestrador-de-ias
description: Divide uma tarefa grande ou com varias partes entre varias IAs ao mesmo tempo e junta o resultado. Use para pesquisas com varios angulos, planos, comparacoes, textos longos ou quando a pessoa pedir "usa varias IAs" / "orquestra".
---

# Orquestrador de IAs

1. Confirme que a tarefa tem mais de uma parte (ex.: "compare 3 notebooks e monte um plano de compra"). Se for simples, responda direto.
2. Chame a acao `orquestrar` com `{"tarefa": "<o pedido completo, com o que a pessoa quer no final>"}`.
3. O orquestrador divide em ate 3 partes, manda cada parte para uma IA diferente das chaves conectadas (Google, Groq, OpenRouter, Cerebras, Mistral) e junta tudo numa resposta so.
4. Entregue a resposta e diga quais IAs participaram. Nao acrescente nada que nao veio das partes.
5. Nunca mande para as IAs senhas, arquivos ou dados do PC: so o texto da tarefa.
