---
name: consultar-lei
description: Le leis e decretos federais do Brasil no site oficial do Planalto (mostra se foram revogados) e procura normas no acervo legalize-br. Use quando o Dono perguntar o que diz uma lei/decreto, regra de edital, direitos ou pedir para conferir se uma norma ainda vale.
allowed-tools: consultar_lei
---

# Consultar leis brasileiras

**Fonte principal = Planalto (oficial).** Se voce sabe o tipo, o numero e o ano (ex.: "Decreto 703 de 1992", "Lei 8.078/1990"):
1. Chame `consultar_lei` com `tipo` ("lei" ou "decreto"), `numero` (so digitos) e `ano`. Volta o texto oficial; **leia o inicio: se aparecer "Revogado pelo..." a norma NAO vale mais**. Textos longos vem em blocos de 6 mil caracteres: continue com `a_partir`.

**Nao sabe o numero?** Chame `consultar_lei` so com `termo` (2 a 4 palavras, ex.: "locacao imoveis urbanos"). Vem `[id] tipo data (local) titulo :: ementa`; para ler, chame com `id`. ATENCAO: esse acervo (legalize-br) e quase todo de estados e municipios; so 778 normas federais e quase nenhuma lei importante (Codigo de Defesa do Consumidor, Estatuto dos Militares etc. NAO estao). Se nao achar, diga e peça o numero ao Dono ou pesquise na web.

Responda simples e em ate 6 linhas: numero e data da norma, o que ela manda de verdade e, se for regra de prova/edital, os numeros exatos (limites, prazos). Diga sempre se foi revogada ou alterada. Portarias de ministerios/Exercito e normas anteriores a 1988 podem nao estar no Planalto por essa busca: nesse caso diga isso. Isto nao e consultoria juridica.

**Numeros que voce NAO deve inventar** (use estes; se a lei nao esta aqui e voce nao tem certeza do numero, diga que nao sabe): CDC = lei 8078/1990; Inquilinato = lei 8245/1991; ECA = lei 8069/1990; Codigo Civil = lei 10406/2002; CPC = lei 13105/2015; Maria da Penha = lei 11340/2006; Lei de Drogas = lei 11343/2006; Marco Civil da Internet = lei 12965/2014; LGPD = lei 13709/2018; Licitacoes = lei 14133/2021; Estatuto do Idoso = lei 10741/2003; Estatuto da Pessoa com Deficiencia = lei 13146/2015. Codigo Penal (decreto-lei 2848/1940), CLT (decreto-lei 5452/1943) e Constituicao NAO cabem na ferramenta: diga isso.
