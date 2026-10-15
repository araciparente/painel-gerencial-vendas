"""
Gera os dados usados pelo painel.

- data/vendas.csv  : base sintética (reprodutível, seed fixa) de vendas mensais
                     de uma distribuidora fictícia, por UF e categoria (2023-2025).
- data/br_uf.geojson : malha das UFs simplificada (a partir de
                     codeforamerica/click_that_hood, brazil-states.geojson).

Rodar uma vez:  python prepare_data.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import shape, mapping

DATA = Path(__file__).parent / "data"
rng = np.random.default_rng(2026)

# --------------------------------------------------------------------------
# 1) Malha simplificada
# --------------------------------------------------------------------------
RAW = DATA / "brazil-states.geojson"
if not RAW.exists():
    import urllib.request
    urllib.request.urlretrieve("https://raw.githubusercontent.com/codeforamerica/click_that_hood/"
                               "master/public/data/brazil-states.geojson", RAW)
src = json.loads((DATA / "brazil-states.geojson").read_text(encoding="utf-8"))
feats = []
for f in src["features"]:
    geom = shape(f["geometry"])
    if geom.geom_type == "MultiPolygon":  # descarta ilhas oceânicas minúsculas (ex.: Fernando de Noronha)
        from shapely.geometry import MultiPolygon
        geom = MultiPolygon([p for p in geom.geoms if p.area > 0.02]) if any(p.area > 0.02 for p in geom.geoms) else geom
    geom = geom.simplify(0.03, preserve_topology=True)
    g = mapping(geom)

    def rnd(c):
        return [rnd(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(c[0], 3), round(c[1], 3)]

    g = {"type": g["type"], "coordinates": rnd(g["coordinates"])}
    feats.append({"type": "Feature", "id": f["properties"]["sigla"],
                  "properties": {"sigla": f["properties"]["sigla"], "nome": f["properties"]["name"]},
                  "geometry": g})
(DATA / "br_uf.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                                               ensure_ascii=False), encoding="utf-8")

# --------------------------------------------------------------------------
# 2) Base de vendas sintética
# --------------------------------------------------------------------------
UF = {  # sigla: (nome, região, peso de mercado ~ população)
    "AC": ("Acre", "Norte", 0.9), "AP": ("Amapá", "Norte", 0.8), "AM": ("Amazonas", "Norte", 4.0),
    "PA": ("Pará", "Norte", 8.1), "RO": ("Rondônia", "Norte", 1.6), "RR": ("Roraima", "Norte", 0.6),
    "TO": ("Tocantins", "Norte", 1.5),
    "AL": ("Alagoas", "Nordeste", 3.1), "BA": ("Bahia", "Nordeste", 14.1), "CE": ("Ceará", "Nordeste", 8.8),
    "MA": ("Maranhão", "Nordeste", 6.8), "PB": ("Paraíba", "Nordeste", 4.0), "PE": ("Pernambuco", "Nordeste", 9.1),
    "PI": ("Piauí", "Nordeste", 3.3), "RN": ("Rio Grande do Norte", "Nordeste", 3.3), "SE": ("Sergipe", "Nordeste", 2.2),
    "DF": ("Distrito Federal", "Centro-Oeste", 2.8), "GO": ("Goiás", "Centro-Oeste", 7.1),
    "MT": ("Mato Grosso", "Centro-Oeste", 3.7), "MS": ("Mato Grosso do Sul", "Centro-Oeste", 2.8),
    "ES": ("Espírito Santo", "Sudeste", 3.8), "MG": ("Minas Gerais", "Sudeste", 20.5),
    "RJ": ("Rio de Janeiro", "Sudeste", 16.1), "SP": ("São Paulo", "Sudeste", 44.4),
    "PR": ("Paraná", "Sul", 11.4), "RS": ("Rio Grande do Sul", "Sul", 10.9), "SC": ("Santa Catarina", "Sul", 7.6),
}
CAT = {  # categoria: (participação base, margem base, ticket médio R$)
    "Eletrônicos": (0.27, 0.18, 1450.0),
    "Eletrodomésticos": (0.22, 0.21, 980.0),
    "Móveis": (0.16, 0.30, 760.0),
    "Informática": (0.15, 0.16, 2100.0),
    "Utilidades domésticas": (0.12, 0.38, 140.0),
    "Climatização": (0.08, 0.24, 1900.0),
}
# afinidade regional (multiplicador de demanda)
AFIN = {
    ("Nordeste", "Climatização"): 1.55, ("Norte", "Climatização"): 1.70, ("Centro-Oeste", "Climatização"): 1.30,
    ("Sul", "Climatização"): 0.65, ("Sul", "Móveis"): 1.25, ("Sudeste", "Informática"): 1.25,
}
# crescimento anual por região (os mercados emergentes crescem mais rápido)
GROWTH = {"Norte": 0.15, "Nordeste": 0.17, "Centro-Oeste": 0.12, "Sudeste": 0.05, "Sul": 0.07}

months = pd.date_range("2023-01-01", "2025-12-01", freq="MS")
SEAS = {1: 0.82, 2: 0.80, 3: 0.92, 4: 0.90, 5: 1.02, 6: 0.95, 7: 0.97, 8: 0.98,
        9: 0.96, 10: 1.02, 11: 1.38, 12: 1.45}  # Black Friday + Natal
TOTAL_BASE = 32_000_000  # receita mensal base da rede (R$)
peso_total = sum(v[2] for v in UF.values())

rows = []
for uf, (nome, reg, peso) in UF.items():
    uf_bias = rng.normal(1.0, 0.08)  # eficiência comercial da filial
    for cat, (share, mg, ticket) in CAT.items():
        afin = AFIN.get((reg, cat), 1.0)
        for i, m in enumerate(months):
            t = i / 12
            seas = SEAS[m.month]
            if cat == "Climatização":          # pico no verão
                seas *= {1: 1.6, 2: 1.5, 3: 1.2, 9: 1.2, 10: 1.4, 11: 1.4, 12: 1.6}.get(m.month, 0.6)
            base = TOTAL_BASE * (peso / peso_total) * share * afin * uf_bias
            receita = base * seas * (1 + GROWTH[reg]) ** t * rng.lognormal(0, 0.06)
            margem = mg + rng.normal(0, 0.012)

            # Evento plantado para a análise gerencial:
            # campanha agressiva de Eletrônicos no Nordeste (abr-jun/2025) ->
            # receita sobe, margem desaba.
            if reg == "Nordeste" and cat == "Eletrônicos" and m.year == 2025 and m.month in (4, 5, 6):
                receita *= 1.35
                margem -= 0.11
            # Ruptura logística no Sul (mai/2024 - enchentes no RS) -> queda de receita.
            if uf == "RS" and m.year == 2024 and m.month in (5, 6):
                receita *= 0.45 if m.month == 5 else 0.70

            pedidos = max(1, int(round(receita / (ticket * rng.normal(1, 0.04)))))
            rows.append({
                "mes": m.strftime("%Y-%m-%d"), "uf": uf, "estado": nome, "regiao": reg,
                "categoria": cat, "receita": round(receita, 2),
                "lucro_bruto": round(receita * margem, 2), "pedidos": pedidos,
            })

df = pd.DataFrame(rows)
df.to_csv(DATA / "vendas.csv", index=False)
print(f"{len(df):,} linhas | receita total R$ {df.receita.sum()/1e9:.2f} bi")
print(df.groupby(df.mes.str[:4]).receita.sum().map(lambda v: f"R$ {v/1e6:,.0f} mi"))
