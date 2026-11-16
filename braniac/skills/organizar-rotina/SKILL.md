---
name: organizar-rotina
description: Monta ou reorganiza o dia/semana do Dono com a ferramenta agenda (compromissos, tarefas sem data, rotina fixa). Use quando ele pedir para organizar o dia, montar a rotina, encaixar tarefas ou disser que esta perdido/atrasado.
allowed-tools: agenda
---

# Organizar a rotina do Dono

1. **Veja o que existe:** chame `agenda` com acao `organizar` (dia pedido; padrao hoje). Isso traz o que ja esta marcado, os horarios livres e as tarefas sem data.
2. **Pergunte so o que falta e muda o plano** (no maximo 1 pergunta): prazo de alguma tarefa, ou que horas ele quer parar. Nao pergunte o que a agenda ja diz.
3. **Monte a proposta** em blocos curtos, nesta ordem de prioridade:
   - compromissos com hora (nao mexa neles);
   - o que tem prazo ou gera dinheiro (vagas, clientes, Airbnb, Layla/Loja);
   - o resto das tarefas sem data, as maiores no periodo em que ele rende mais (manha, se ele nao disser outra coisa);
   - pausas: almoco e 10-15 min a cada ~2 h; nada marcado depois das 22h.
   Cada bloco com duracao realista (tarefa desconhecida = 60 min).
4. **Mostre a proposta em lista curta** (hora - tarefa) e pergunte "Posso marcar assim?". So marque sem perguntar se ele ja disse "pode marcar"/"organiza e marca".
5. **Ao marcar:** uma chamada `agenda` acao `adicionar` por bloco (titulo, quando, duracao). Tarefa sem data que foi encaixada: depois de marcar o bloco, `concluir` a tarefa sem data pelo id dela (para nao ficar duplicada).
6. **Rotina fixa** (academia, remedio, estudo): `adicionar` com `repetir` (diario, dias_uteis, semanal, mensal).
7. Termine com 1 frase: quantos blocos marcou e o primeiro horario. Ele recebe lembrete no WhatsApp 15 min antes de cada um.

Nunca invente compromisso nem prazo. Se a agenda estiver vazia, diga e pergunte o que ele tem para fazer.
