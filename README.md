# Painel Gerencial de Vendas — Visões Coordenadas

Dashboard em **Python + Plotly Dash** que aplica o mantra de Shneiderman
(*overview first, zoom and filter, details-on-demand*) com **Multiple Coordinated Views**
e **brushing & linking**.

| # | Visão | Papel no mantra | Interação |
|---|-------|-----------------|-----------|
| 1 | Série histórica mensal | Overview temporal | Arrastar (brush) seleciona período; duplo clique limpa |
| 2 | Mapa coroplético por UF | Overview espacial | Clique alterna UF na seleção |
| 3 | Barras ordenadas por categoria | Distribuição categórica | Clique alterna categoria |
| 4 | Matriz de calor região × categoria | Distribuição categórica cruzada | Clique seleciona região + categoria |
| 5 | KPIs + tabela filtrada + tooltips | Details-on-demand | Ordenação, paginação, tooltips nos cabeçalhos |

## Rodar localmente

```bash
pip install -r requirements.txt
python app.py            # http://127.0.0.1:8050
```

Os dados já estão em `data/`. Para regenerá-los: `pip install shapely` e `python prepare_data.py`
(o script baixa a malha original se `data/brazil-states.geojson` não existir — ver comentário no topo).

## Publicar (link para o Moodle) — Render, plano gratuito

1. Crie um repositório no GitHub e envie esta pasta (`git init && git add . && git commit -m "painel" && git push`).
2. Em <https://render.com> → **New → Blueprint** → selecione o repositório (o `render.yaml` já configura tudo).
   Alternativa: **New → Web Service**, Build `pip install -r requirements.txt`,
   Start `gunicorn app:server --workers 2 --bind 0.0.0.0:$PORT`.
3. Aguarde o build (~3 min). O link fica no formato `https://painel-gerencial-vendas.onrender.com`.

> No plano gratuito o serviço "dorme" após 15 min sem acesso; a primeira visita leva ~50 s para acordar.
> Abra o link um pouco antes da correção/apresentação.

## Estrutura

```
app.py                 # layout, figuras e callbacks (estado único de seleção)
prepare_data.py        # gera data/vendas.csv (sintético, seed fixa) e simplifica a malha
data/vendas.csv        # 5.832 linhas: mês × UF × categoria (2023–2025)
data/br_uf.geojson     # malha das UFs simplificada (~100 KB)
assets/style.css       # estilo (carregado automaticamente pelo Dash)
assets/topojson/       # topojson base servido localmente (sem dependência de CDN)
requirements.txt · Procfile · render.yaml
```

Fonte da malha: `codeforamerica/click_that_hood` (brazil-states.geojson).
Os dados de vendas são **sintéticos** e incluem dois eventos plantados para análise:
campanha de Eletrônicos no Nordeste (abr–jun/2025: receita ↑, margem ↓ ~11 p.p.) e
ruptura logística no RS (mai–jun/2024).
