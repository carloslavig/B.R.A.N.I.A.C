# Seed vira o Braniac real (decisão do Carlos, 16/11/2026)

**Problema:** o instalador público (este repositório) é um programa à parte, escrito do zero (39 módulos em `seed/braniac_seed`).
O Braniac que roda no PC do dono é outro código, com 151 módulos e guardado no repositório privado `braniac-fonte`. Por isso, push no privado
nunca chega a quem instalou: o `auto_update.py` e o `atualizador.py` só baixam as releases deste repositório.

**Objetivo:** o instalador passa a rodar o MESMO núcleo do Braniac do dono. A personalização (nome, voz, chaves, pessoas, módulos)
fica num perfil local que o onboarding cria, e o código não leva nada da vida do dono.

## Tamanho do trabalho (medido em 16/11)
- 151 módulos no `braniac/`: só 20 estão limpos. 49 têm poucas menções ao dono. Em 82 a vida do dono está misturada na lógica
  (`jarvis.py` 184 menções, `airbnb_vigia.py` 93, `rotina.py` 60, `alma_mente.py` 50, `contexto.py`, `atender.py`...).
- Varredura (`scripts/varrer_pessoal.py`) no código do `braniac/` (sem `data/`): 933 achados em 203 arquivos.
  São 833 nomes de pessoas/lugares, 31 caminhos de usuário, 21 pastas fixas de outro disco (`E:\...`), 24 telefones e 24 e-mails.
  Nenhuma chave de API.
- Fora do repositório privado e necessários: `braniac2-app/` (janela B.R.A.N.I.A.C 1) e `local-ia/` (leitura do WhatsApp).

## Fases
0. **Feito:** a trava `scripts/varrer_pessoal.py` roda no `build.ps1`. Ela barra caminhos, telefones, e-mails, chaves e os nomes de
   `scripts/termos-pessoais.txt` (lista local, fora do git). Ela já achou nomes reais de um amigo no seed, que foram trocados por nomes fictícios.
   Esses nomes continuam no HISTÓRICO público (commit 70f1aa3). Tirar de lá exige reescrever o histórico e fazer force push, e quem decide isso é o dono.
1. **Feito em 16/11:** o `braniac-fonte` está em dia (main = branch de trabalho).
   **Também feito em 16/11 (adianta a fase 5):** `scripts/exportar.py` gera `braniac/` neste repositório a partir do `braniac-fonte`.
   Os nomes viram papéis pela lista local `scripts/trocas-pessoais.json`. As exclusões ficam em `scripts/fora-do-publico.txt` (vida pessoal,
   negócio do parceiro, habilidades de terceiros), e a configuração inicial das empresas vai em `braniac/padrao/`. As habilidades de terceiros
   são baixadas do GitHub de cada autor só se a pessoa marcar (`habilidades_terceiros.py`). Para atualizar: rodar o exportador, a varredura
   com `--export` e os testes da cópia, depois commit.
2. **Perfil do dono:** criar `perfil.json` em `data/`, com o nome, a forma de tratamento, as pessoas de prioridade (família), a cidade e os módulos ligados.
   Os nomes fixos do núcleo (`jarvis.FAMILIA_LIVRE`, `router.REGRA_TRATAMENTO`, `contexto.contato("carlos")`, `tratamento.py`, `dono.py`)
   passam a ler desse arquivo. No PC do dono, o perfil reproduz o comportamento de hoje, e os testes atuais têm que continuar passando.
3. **Módulos pessoais viram opcionais**, no formato `modulos_embutidos/<id>/manifest.json` que o seed já usa: Airbnb, Link (vídeos de prefeitura),
   vaquinha, Zelo, loja, cortes, Exército, financeiro InfinitePay. O `server` sobe sem eles.
4. **Caminhos:** tudo sai de `paths` (`%LOCALAPPDATA%\BRANIAC-dados` ou da variável de ambiente). Nada de pastas fixas do PC do dono, `E:\` nem `C:\Users\<nome>`.
5. **Empacotar o real:** um `scripts/exportar.py` copia do `braniac-fonte` só o núcleo, os módulos genéricos, a `ui/` e as skills genéricas.
   Depois roda a varredura, e o `build.ps1` empacota isso no lugar de `seed/braniac_seed`. A janela passa a ser a do `braniac2-app`
   (B2, prédio, aba Vozes). O onboarding atual (chaves → consentimento → nome/voz → módulos) passa a gravar o `perfil.json`.
6. **Atualização:** cada release deste repositório sai do script da fase 5. O `auto_update.py` que já existe entrega a release a quem instalou.
7. **Teste num PC limpo:** usar a VM isolada (controle da VM no `braniac-fonte`), nunca o PC do dono.

Nada é publicado (push/release) sem o OK do dono.
