---
name: mapas-satelite
description: Cena de mapa animado sobre satélite aberto (Brasil, estado e município com zoom que acompanha a fala, pinos com nomes, créditos automáticos) no Estudio3D. Use quando um pedido de vídeo (do Dono ou do Aliado) precisar mostrar onde fica uma cidade, estado ou lugar.
allowed-tools: estudio_3d delegar_ao_claude
---

# Mapas sobre satélite (feito no nosso Estudio3D, do zero)

Não é cópia de nenhum kit pago: usa só fontes abertas (NASA Blue Marble, Sentinel-2 cloudless **2016** da EOX com CC BY 4.0, malhas do IBGE). O mosaico de 2017 em diante da EOX é só uso não comercial: **nunca troque a camada** `s2cloudless_3857`.

## Como pedir (cena do roteiro / pedido da fila)
```json
{"titulo": "Cidade C", "peca": "mapa", "inicio": 0, "fim": 17.6,
 "dados": {"uf": "BA", "municipio": "Cidade C", "zoom_final": "cidade",
           "pinos": [{"nome": "Porto Seguro", "lat": -16.4435, "lon": -39.0643}]}}
```
- `uf` (2 letras) e `municipio` são obrigatórios; `zoom_final` = `cidade` (padrão) ou `estado`; até 8 `pinos` (nome, lat, lon).
- O zoom vai ao estado na **última** vez que a legenda cita o estado e ao município na última citação do município/cidade depois disso: por isso a narração deve falar "primeiro o Brasil, depois a Bahia, por fim a cidade".
- Use `inicio`/`fim` para a cena cobrir esse trecho da fala.

## O que acontece sozinho (sem gastar IA)
`link/render_estudio.py` baixa as divisas (`tools/geo.py`) e o satélite (`tools/sat.py`, ~1 minuto na primeira vez de cada cidade, depois fica em cache em `Estudio3D/public/geo`), e renderiza. Os créditos saem no rodapé do vídeo. Sem satélite (rede/fonte fora), o mapa sai só com as divisas.

## Limites e honestidade
- Só Brasil, estado e município (IBGE). Mapa de ruas, bandeiras dentro do estado, fotos em cartão e mergulhos de câmera com borrão **ainda não** foram recriados: se pedirem, diga que não existe e chame o Claude (`delegar_ao_claude`).
- Mosaico novo = ~1 min de download de fontes públicas (poucas dezenas de tiles); não rode dezenas de cidades de uma vez.
- Descrição do vídeo: cole o crédito do rodapé ("Imagens: NASA · Sentinel-2 cloudless 2016 by EOX IT Services GmbH (contém dados Copernicus Sentinel modificados 2016) · Divisas: IBGE").
