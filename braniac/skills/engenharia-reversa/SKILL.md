---
name: engenharia-reversa
description: Descobre como um app, site, programa ou arquivo (.exe, .apk, Electron, .NET, JavaScript) funciona por dentro, sem o codigo-fonte, usando o REA (Reverse Engineer Anything) pelo Claude. Use quando o Dono pedir para entender/copiar uma funcao de um app ou site, comparar versoes, decompilar ou analisar um binario.
allowed-tools: delegar_ao_claude
---

# Engenharia reversa (REA, pelo Claude)

O REA (github.com/morluto/rea, MIT) roda como ferramenta MCP do **Claude Code** neste PC. O Jarvis nao roda o REA direto: ele **delega ao Claude**.

1. **So uso legal.** Pode: software do proprio Dono ou autorizado, pesquisa de seguranca, interoperabilidade, aprender como uma funcao funciona para fazer a propria versao. **Nao pode:** burlar DRM, licenca, anti-cheat, login/controle de acesso, ou copiar codigo de terceiros. Pedido assim: recuse com educacao e explique o motivo.
2. **Pegue o essencial** (no maximo 1 pergunta): qual app/site/arquivo (caminho no PC ou link) e o que ele quer saber (ex.: "como o app X faz o recurso Y").
3. **Chame `delegar_ao_claude`** com uma tarefa completa, por exemplo: "Use o REA (skill reverse-engineer-anything) para analisar <alvo> e explicar <pergunta>. Mostre as evidencias e os limites. Analise numa copia; nao execute binarios desconhecidos fora do REA."
4. **Avise o Dono** que o Claude esta analisando e que o resultado chega depois (ele prefere audio no WhatsApp).

Analise de binario nativo (exe/dll) pode precisar de Ghidra/Hopper/IDA, que ainda nao estao instalados; JavaScript, Electron e sites funcionam sem eles.
