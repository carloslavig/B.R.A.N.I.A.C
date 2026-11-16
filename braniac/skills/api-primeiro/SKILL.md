---
name: api-primeiro
description: Antes de automatizar um site pelo navegador (clicar/digitar), tenta virar API - captura o trafego do site e gera um cliente Python/JS (reverse-api-engineer). Use quando o Dono pedir para automatizar, ler ou preencher algo num site de forma repetida, ou para reduzir uso do navegador.
allowed-tools: delegar_ao_claude
---

# API primeiro, navegador por ultimo (13/11/2026)

Ferramenta: `reverse-api-engineer` (github.com/kalil0321/reverse-api-engineer, MIT), instalada com `uv tool` em `C:\Users\usuario\.local\bin` (fora do PATH: use o caminho completo ou `$env:PATH`).
Ela grava o trafego (HAR) de um site e um modelo gera um cliente de API. Saida: `~/.reverse-api/runs/scripts/<run_id>/`.

## Quando vale
- Tarefa REPETIDA num site publico ou do Dono (listar vagas, consultar preco/status, ler uma lista).
- Ja ha API oficial (Gmail, Vercel, GitHub)? Use a oficial, nem precisa disso.
- Nao vale: WhatsApp (usar `wpp_direto`/Baileys quando parear), captcha, login que o Dono faz, conta bancaria (Cofre so le, nao automatizar por API nao oficial), qualquer coisa que burle controle de acesso ou termos.

## Como rodar (sempre pelo Claude, via `delegar_ao_claude`)
```
$env:PATH = "C:\Users\usuario\.local\bin;$env:PATH"
reverse-api-engineer agent --headless --json -p "<o que buscar>" -u <url inicial>
reverse-api-engineer agent --dry-run -p "x" -u <url>        # valida sem gastar
reverse-api-engineer list --json ; reverse-api-engineer run <run_id>
```
- `--headless` obrigatorio (o modo com Chrome exige a depuracao remota do Chrome 146+).
- Modo agente usa o SDK do Claude (gasta tokens do Dono): so 1 captura por site, depois reaproveite o script gerado.
- **Revise o script gerado antes de rodar** e rode so contra o site-alvo. Nunca com senha/token no prompt; sessao logada so se o Dono pedir.
- Guarde o script bom em `braniac/data/apis/<site>/` (data/ nao vai ao Git) e registre no banco o que ele faz.
- Se o site bloquear (anti-bot) ou exigir captcha: pare e volte ao navegador, avisando o Dono.
