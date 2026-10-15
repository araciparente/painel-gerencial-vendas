"""
Painel Gerencial de Vendas — Visões Coordenadas (Brushing & Linking)

Mantra de Shneiderman:
  1. Overview first ........ série histórica + mapa coroplético + KPIs
  2. Zoom and filter ........ brush na série (período), clique no mapa (UF),
                              clique nas barras (categoria), clique na matriz (região × categoria)
  3. Details-on-demand ...... tooltips enriquecidos + tabela filtrada

Todas as visões leem um único estado de seleção (dcc.Store "sel").
Cada visão é FILTRADA pelas seleções das outras e DESTACA a sua própria
(cross-filtering), para que o usuário nunca perca o contexto.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dash_table, dcc, html, no_update
from dash.dash_table.Format import Format, Group, Scheme, Sign, Symbol

BASE = Path(__file__).parent
DF = pd.read_csv(BASE / "data" / "vendas.csv", parse_dates=["mes"])
GEO = json.loads((BASE / "data" / "br_uf.geojson").read_text(encoding="utf-8"))

MESES = sorted(DF["mes"].unique())
UFS_POR_REGIAO = DF.groupby("regiao")["uf"].unique().apply(sorted).to_dict()
REGIOES = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"]
UF_INFO = DF.drop_duplicates("uf").set_index("uf")[["estado", "regiao"]]

# ---------------------------------------------------------------------------
# Paleta (segura para daltônicos)
#  - Okabe & Ito (2008): azul #0072B2 = dado/seleção; vermelhão #D55E00 = alerta
#  - Sequencial monocromática (claro -> azul escuro): legível em
#    deuteranopia, protanopia e tritanopia, e em escala de cinza.
#  - Significado nunca depende só da cor: há rótulos, sinais (+/−) e ▲▼.
# ---------------------------------------------------------------------------
AZUL = "#0072B2"
ALERTA = "#D55E00"
CINZA = "#C5CBD3"
TINTA = "#1F2933"
TINTA_2 = "#5B6573"
SEQ = [[0.0, "#EEF4FA"], [0.25, "#C3D9EC"], [0.5, "#7FB0D8"], [0.75, "#2F7FBF"], [1.0, "#0B3C6E"]]

METRICAS = {
    "receita": "Receita",
    "margem": "Margem bruta %",
    "pedidos": "Pedidos",
}
MES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


# ---------------------------------------------------------------------------
# Utilidades de formatação (pt-BR)
# ---------------------------------------------------------------------------
def br_num(v, dec=0):
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def brl(v):
    a = abs(v)
    if a >= 1e9:
        return f"R$ {br_num(v / 1e9, 2)} bi"
    if a >= 1e6:
        return f"R$ {br_num(v / 1e6, 1)} mi"
    if a >= 1e3:
        return f"R$ {br_num(v / 1e3, 1)} mil"
    return f"R$ {br_num(v, 0)}"


def fmt_metrica(v, metrica):
    if metrica == "receita":
        return brl(v)
    if metrica == "margem":
        return f"{br_num(v * 100, 1)}%"
    return br_num(v)


def mes_label(ts):
    ts = pd.Timestamp(ts)
    return f"{MES_PT[ts.month - 1]}/{ts.year}"


def agrega(d, por):
    """Agrega por uma ou mais chaves e calcula as métricas derivadas."""
    g = d.groupby(por, observed=True).agg(receita=("receita", "sum"),
                                          lucro=("lucro_bruto", "sum"),
                                          pedidos=("pedidos", "sum")).reset_index()
    g["margem"] = g["lucro"] / g["receita"]
    g["ticket"] = g["receita"] / g["pedidos"]
    return g


def filtra(sel, usar_periodo=True, usar_ufs=True, usar_cats=True):
    d = DF
    if usar_periodo and sel.get("periodo"):
        a, b = pd.Timestamp(sel["periodo"][0]), pd.Timestamp(sel["periodo"][1])
        d = d[(d["mes"] >= a) & (d["mes"] <= b)]
    if usar_ufs and sel.get("ufs"):
        d = d[d["uf"].isin(sel["ufs"])]
    if usar_cats and sel.get("cats"):
        d = d[d["categoria"].isin(sel["cats"])]
    return d


def variacao_aa(sel):
    """Variação vs. mesmo período do ano anterior, só sobre meses comparáveis."""
    d = filtra(sel, usar_periodo=False)
    if sel.get("periodo"):
        a, b = pd.Timestamp(sel["periodo"][0]), pd.Timestamp(sel["periodo"][1])
        meses = [m for m in MESES if a <= m <= b]
    else:
        meses = list(MESES)
    meses = [m for m in meses if (m - pd.DateOffset(years=1)) in set(MESES)]
    if not meses:
        return None, None
    ant = [m - pd.DateOffset(years=1) for m in meses]
    return d[d["mes"].isin(meses)], d[d["mes"].isin(ant)]


def layout_base(**kw):
    """Layout mínimo — Data-Ink Ratio de Tufte: sem fundo, sem bordas, sem grade
    vertical, grade horizontal quase invisível, sem legenda (rótulo direto)."""
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, 'Segoe UI', Roboto, Arial, sans-serif", size=12, color=TINTA_2),
        margin=dict(l=8, r=8, t=8, b=8), showlegend=False, separators=",.",
        hoverlabel=dict(bgcolor="white", bordercolor="#D7DCE2",
                        font=dict(family="Inter, 'Segoe UI', Roboto, Arial, sans-serif", size=12, color=TINTA)),
    )
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------
def fig_serie(sel, metrica):
    d = agrega(filtra(sel, usar_periodo=False), "mes").sort_values("mes")
    y = d[metrica]
    fig = go.Figure()
    if sel.get("periodo"):
        a, b = pd.Timestamp(sel["periodo"][0]), pd.Timestamp(sel["periodo"][1])
        fig.add_vrect(x0=a - pd.Timedelta(days=15), x1=b + pd.Timedelta(days=15),
                      fillcolor=AZUL, opacity=0.08, line_width=0, layer="below")
        dentro = d[(d["mes"] >= a) & (d["mes"] <= b)]
        fora_cor = CINZA
    else:
        dentro, fora_cor = d, AZUL

    custom = np.stack([d["mes"].map(mes_label), d["receita"].map(brl),
                       (d["margem"] * 100).map(lambda v: br_num(v, 1) + "%"),
                       d["pedidos"].map(br_num), d["ticket"].map(brl)], axis=-1)
    fig.add_trace(go.Scatter(
        x=d["mes"], y=y, mode="lines+markers", line=dict(color=fora_cor, width=2),
        marker=dict(size=5, color=fora_cor), customdata=custom,
        hovertemplate=("<b>%{customdata[0]}</b><br>Receita: %{customdata[1]}"
                       "<br>Margem bruta: %{customdata[2]}<br>Pedidos: %{customdata[3]}"
                       "<br>Ticket médio: %{customdata[4]}<extra></extra>"),
    ))
    if sel.get("periodo"):
        fig.add_trace(go.Scatter(x=dentro["mes"], y=dentro[metrica], mode="lines+markers",
                                 line=dict(color=AZUL, width=2.5), marker=dict(size=6, color=AZUL),
                                 hoverinfo="skip"))
    # rótulo direto do máximo, do mínimo e do último ponto (em vez de legenda/grade densa)
    for idx, desloc in ((y.idxmax(), 12), (y.idxmin(), -14), (d.index[-1], 12)):
        fig.add_annotation(x=d.loc[idx, "mes"], y=d.loc[idx, metrica],
                           text=fmt_metrica(d.loc[idx, metrica], metrica),
                           showarrow=False, yshift=desloc, font=dict(size=11, color=TINTA))
    tick = dict(receita=dict(tickprefix="R$ ", tickformat="~s"),
                margem=dict(tickformat=".0%"), pedidos=dict(tickformat="~s"))[metrica]
    fig.update_layout(**layout_base(
        dragmode="select", selectdirection="h", hovermode="closest",
        margin=dict(l=8, r=8, t=16, b=8), uirevision="serie",
        xaxis=dict(showgrid=False, showline=True, linecolor="#D7DCE2", ticks="",
                   tickformat="%b\n%Y", dtick="M3", fixedrange=True),
        yaxis=dict(showgrid=True, gridcolor="#EEF1F4", zeroline=False, showline=False,
                   fixedrange=True, nticks=4, **tick),
    ))
    if sel.get("periodo"):
        # Mantém o "brush" desenhado após o redesenho; sem isto o Plotly descarta a
        # seleção ao receber a nova figura e emite um "deselect" que apagaria o filtro.
        fig.update_layout(selections=[dict(
            type="rect", xref="x", yref="y",
            x0=pd.Timestamp(sel["periodo"][0]) - pd.Timedelta(days=15),
            x1=pd.Timestamp(sel["periodo"][1]) + pd.Timedelta(days=15),
            y0=0 if metrica != "margem" else y.min() * 0.9, y1=y.max() * 1.15,
            line=dict(color=AZUL, width=1, dash="dot"))])
    fig.update_xaxes(tickvals=[m for m in MESES if pd.Timestamp(m).month in (1, 7)],
                     ticktext=[mes_label(m) for m in MESES if pd.Timestamp(m).month in (1, 7)])
    return fig


def fig_mapa(sel, metrica):
    d = filtra(sel, usar_ufs=False)
    g = agrega(d, "uf")
    lider = (d.groupby(["uf", "categoria"])["receita"].sum().reset_index()
             .sort_values("receita", ascending=False).drop_duplicates("uf").set_index("uf")["categoria"])
    g["lider"] = g["uf"].map(lider)
    g["estado"] = g["uf"].map(UF_INFO["estado"])
    g["regiao"] = g["uf"].map(UF_INFO["regiao"])
    g["part"] = g["receita"] / g["receita"].sum()
    g["rank"] = g[metrica].rank(ascending=False, method="min").astype(int)

    sel_ufs = set(sel.get("ufs") or [])
    tem_sel = bool(sel_ufs)
    largura = [2.6 if u in sel_ufs else 0.6 for u in g["uf"]]
    cor_borda = [TINTA if u in sel_ufs else "white" for u in g["uf"]]

    custom = np.stack([g["estado"], g["regiao"], g["receita"].map(brl),
                       (g["margem"] * 100).map(lambda v: br_num(v, 1) + "%"),
                       g["pedidos"].map(br_num), (g["part"] * 100).map(lambda v: br_num(v, 1) + "%"),
                       g["rank"].astype(str) + "º de 27 em " + METRICAS[metrica].lower(), g["lider"]],
                      axis=-1)
    fig = go.Figure(go.Choropleth(
        geojson=GEO, featureidkey="id", locations=g["uf"], z=g[metrica],
        colorscale=SEQ, marker=dict(line=dict(width=largura, color=cor_borda)),
        selectedpoints=[i for i, u in enumerate(g["uf"]) if u in sel_ufs] if tem_sel else None,
        unselected=dict(marker=dict(opacity=0.35)),
        customdata=custom,
        hovertemplate=("<b>%{customdata[0]}</b> · %{customdata[1]}<br>"
                       "Receita: %{customdata[2]} (%{customdata[5]} do total)<br>"
                       "Margem bruta: %{customdata[3]}<br>Pedidos: %{customdata[4]}<br>"
                       "Ranking: %{customdata[6]}<br>Categoria líder: %{customdata[7]}"
                       "<extra>clique para selecionar</extra>"),
        colorbar=dict(thickness=8, len=0.55, x=0.02, xanchor="left", y=0.18, yanchor="bottom",
                      outlinewidth=0, nticks=4, title=dict(text=""),
                      tickformat={"receita": "~s", "margem": ".1%", "pedidos": "~s"}[metrica],
                      tickprefix="R$ " if metrica == "receita" else ""),
    ))
    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator",
                    bgcolor="rgba(0,0,0,0)")
    fig.update_layout(**layout_base(clickmode="event", uirevision="mapa", dragmode=False))
    return fig


def fig_barras(sel, metrica):
    g = agrega(filtra(sel, usar_cats=False), "categoria").sort_values(metrica)
    sel_c = set(sel.get("cats") or [])
    cores = [AZUL if (not sel_c or c in sel_c) else CINZA for c in g["categoria"]]
    custom = np.stack([g["receita"].map(brl), (g["margem"] * 100).map(lambda v: br_num(v, 1) + "%"),
                       g["pedidos"].map(br_num), g["ticket"].map(brl),
                       (g["receita"] / g["receita"].sum() * 100).map(lambda v: br_num(v, 1) + "%")], axis=-1)
    fig = go.Figure(go.Bar(
        y=g["categoria"], x=g[metrica], orientation="h", marker=dict(color=cores, line_width=0),
        text=[fmt_metrica(v, metrica) for v in g[metrica]], textposition="outside", cliponaxis=False,
        textfont=dict(color=TINTA, size=12), customdata=custom,
        hovertemplate=("<b>%{y}</b><br>Receita: %{customdata[0]} (%{customdata[4]} do total)"
                       "<br>Margem bruta: %{customdata[1]}<br>Pedidos: %{customdata[2]}"
                       "<br>Ticket médio: %{customdata[3]}<extra>clique para filtrar</extra>"),
    ))
    fig.update_layout(**layout_base(
        bargap=0.35, margin=dict(l=8, r=70, t=4, b=4), uirevision="barras", dragmode=False,
        xaxis=dict(visible=False, fixedrange=True),
        yaxis=dict(showgrid=False, showline=False, ticks="", fixedrange=True,
                   tickfont=dict(color=TINTA, size=12)),
    ))
    return fig


def fig_matriz(sel, metrica):
    d = filtra(sel, usar_ufs=False, usar_cats=False)
    g = agrega(d, ["regiao", "categoria"])
    cats = list(agrega(d, "categoria").sort_values("receita", ascending=False)["categoria"])
    piv = g.pivot(index="regiao", columns="categoria", values=metrica).reindex(index=REGIOES[::-1], columns=cats)
    texto = [[fmt_metrica(v, metrica) for v in row] for row in piv.values]

    # região "ativa" = todas as suas UFs estão na seleção
    sel_ufs = set(sel.get("ufs") or [])
    regs_sel = {r for r, ufs in UFS_POR_REGIAO.items() if sel_ufs and set(ufs) <= sel_ufs}
    sel_c = set(sel.get("cats") or [])

    fig = go.Figure(go.Heatmap(
        z=piv.values, x=[c.replace(" ", "<br>", 1) if len(c) > 12 else c for c in cats], y=piv.index,
        colorscale=SEQ, showscale=False, xgap=2, ygap=2, text=texto, texttemplate="%{text}",
        textfont=dict(size=10), customdata=np.array([[c for c in cats]] * len(piv.index)),
        hovertemplate="<b>%{y} · %{customdata}</b><br>" + METRICAS[metrica]
                      + ": %{text}<extra>clique para filtrar região + categoria</extra>",
    ))
    # contorno nas células da seleção ativa
    for i, r in enumerate(piv.index):
        for j, c in enumerate(cats):
            if (not regs_sel or r in regs_sel) and (not sel_c or c in sel_c) and (regs_sel or sel_c):
                fig.add_shape(type="rect", x0=j - 0.5, x1=j + 0.5, y0=i - 0.5, y1=i + 0.5,
                              line=dict(color=TINTA, width=2))
    fig.update_layout(**layout_base(
        margin=dict(l=8, r=8, t=4, b=4), uirevision="matriz", dragmode=False,
        xaxis=dict(side="top", showgrid=False, ticks="", fixedrange=True, tickfont=dict(size=10, color=TINTA)),
        yaxis=dict(showgrid=False, ticks="", fixedrange=True, tickfont=dict(size=11, color=TINTA)),
    ))
    return fig


def tabela_dados(sel):
    d = filtra(sel)
    g = agrega(d, ["uf", "categoria"])
    atual, anterior = variacao_aa(sel)
    if atual is not None:
        a = atual.groupby(["uf", "categoria"])["receita"].sum()
        b = anterior.groupby(["uf", "categoria"])["receita"].sum()
        var = (a / b - 1).rename("var").reset_index()
        g = g.merge(var, on=["uf", "categoria"], how="left")
    else:
        g["var"] = np.nan
    g["estado"] = g["uf"].map(UF_INFO["estado"])
    g["regiao"] = g["uf"].map(UF_INFO["regiao"])
    g = g.sort_values("receita", ascending=False)
    cols = ["estado", "regiao", "categoria", "receita", "margem", "pedidos", "ticket", "var"]
    return g[cols].round({"receita": 0, "margem": 4, "ticket": 2, "var": 4}).to_dict("records")


def kpis(sel):
    d = filtra(sel)
    r, l, p = d["receita"].sum(), d["lucro_bruto"].sum(), d["pedidos"].sum()
    atual, ant = variacao_aa(sel)

    def delta(fn):
        if atual is None or ant is None or len(ant) == 0:
            return None
        v0, v1 = fn(ant), fn(atual)
        return v1 - v0 if fn is _mg else v1 / v0 - 1

    itens = [
        ("Receita", brl(r), delta(lambda x: x["receita"].sum()), "pct"),
        ("Margem bruta", f"{br_num(l / r * 100, 1)}%" if r else "—", delta(_mg), "pp"),
        ("Pedidos", br_num(p), delta(lambda x: x["pedidos"].sum()), "pct"),
        ("Ticket médio", brl(r / p) if p else "—",
         delta(lambda x: x["receita"].sum() / x["pedidos"].sum()), "pct"),
    ]
    out = []
    for nome, valor, dv, tipo in itens:
        if dv is None:
            sub = html.Span("sem base comparável", className="kpi-delta neutro")
        else:
            sinal = "▲" if dv >= 0 else "▼"
            txt = (f"{sinal} {br_num(abs(dv) * 100, 1)} p.p." if tipo == "pp"
                   else f"{sinal} {br_num(abs(dv) * 100, 1)}%")
            sub = html.Span([txt, html.Span(" vs ano anterior", className="kpi-ref")],
                            className="kpi-delta " + ("pos" if dv >= 0 else "neg"))
        out.append(html.Div([html.Div(nome, className="kpi-nome"),
                             html.Div(valor, className="kpi-valor"), sub], className="kpi"))
    return out


def _mg(x):
    return x["lucro_bruto"].sum() / x["receita"].sum()


def chips(sel):
    itens = []
    if sel.get("periodo"):
        a, b = sel["periodo"]
        itens.append(("Período", f"{mes_label(a)} – {mes_label(b)}"))
    if sel.get("ufs"):
        ufs = sel["ufs"]
        reg = [r for r, u in UFS_POR_REGIAO.items() if sorted(u) == sorted(ufs)]
        itens.append(("Região" if reg else "UF", reg[0] if reg else ", ".join(sorted(ufs))))
    if sel.get("cats"):
        itens.append(("Categoria", ", ".join(sel["cats"])))
    if not itens:
        return [html.Span("Sem filtros — visão geral de toda a rede (jan/2023 – dez/2025)", className="chip-vazio")]
    return [html.Span([html.B(k + ": "), v], className="chip") for k, v in itens]


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
app = Dash(__name__, title="Painel Gerencial de Vendas")
server = app.server  # para gunicorn / Render

FMT_BRL = Format(group=Group.yes, precision=0, scheme=Scheme.fixed, symbol=Symbol.yes,
                 symbol_prefix="R$ ").group_delimiter(".").decimal_delimiter(",")
FMT_PCT = Format(precision=1, scheme=Scheme.percentage).decimal_delimiter(",")
FMT_VAR = Format(precision=1, scheme=Scheme.percentage, sign=Sign.positive).decimal_delimiter(",")
FMT_INT = Format(group=Group.yes, precision=0, scheme=Scheme.fixed).group_delimiter(".")

COLS = [
    dict(id="estado", name="Estado"), dict(id="regiao", name="Região"),
    dict(id="categoria", name="Categoria"),
    dict(id="receita", name="Receita", type="numeric", format=FMT_BRL),
    dict(id="margem", name="Margem bruta", type="numeric", format=FMT_PCT),
    dict(id="pedidos", name="Pedidos", type="numeric", format=FMT_INT),
    dict(id="ticket", name="Ticket médio", type="numeric", format=FMT_BRL),
    dict(id="var", name="Var. receita a/a", type="numeric", format=FMT_VAR),
]

GCFG = {"displaylogo": False, "modeBarButtonsToRemove":
        ["zoom2d", "pan2d", "lasso2d", "zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d",
         "toImage", "select2d"], "displayModeBar": False}


def painel(titulo, dica, corpo, cls=""):
    return html.Section([html.Header([html.H2(titulo), html.Span(dica, className="dica")]), corpo],
                        className="painel " + cls)


app.layout = html.Div([
    dcc.Store(id="sel", data={"periodo": None, "ufs": [], "cats": []}),
    html.Header([
        html.Div([
            html.H1("Painel Gerencial de Vendas"),
            html.P("Distribuidora fictícia · 27 UFs · 6 categorias · jan/2023 – dez/2025 · dados sintéticos"),
        ]),
        html.Div([
            html.Label("Métrica", htmlFor="metrica", className="rotulo"),
            dcc.RadioItems(id="metrica", value="receita", inline=True, className="seg",
                           options=[{"label": v, "value": k} for k, v in METRICAS.items()]),
        ], className="controles"),
    ], className="topo"),

    html.Div([html.Div(id="chips", className="chips"),
              html.Button("Limpar seleção", id="limpar", className="btn", n_clicks=0)],
             className="barra-filtros", **{"aria-live": "polite"}),

    html.Div(id="kpis", className="kpis"),

    painel("1 · Visão geral temporal",
           "Arraste horizontalmente para selecionar um período · duplo clique limpa",
           dcc.Graph(id="serie", config=GCFG, style={"height": "240px"})),

    html.Div([
        painel("2 · Distribuição espacial por UF", "Clique em um estado para filtrar (clique de novo para remover)",
               # topojson servido localmente: o painel não depende do CDN do Plotly
               dcc.Graph(id="mapa", config={**GCFG, "topojsonURL": "/assets/topojson/"},
                         style={"height": "460px"}), "mapa"),
        html.Div([
            painel("3 · Ranking de categorias", "Clique em uma barra para filtrar",
                   dcc.Graph(id="barras", config=GCFG, style={"height": "210px"})),
            painel("4 · Matriz região × categoria", "Clique em uma célula para filtrar região e categoria",
                   dcc.Graph(id="matriz", config=GCFG, style={"height": "210px"})),
        ], className="coluna"),
    ], className="grade"),

    painel("5 · Detalhes sob demanda", "Tabela filtrada pela seleção atual · clique nos cabeçalhos para ordenar",
           dash_table.DataTable(
               id="tabela", columns=COLS, page_size=10, sort_action="native",
               style_as_list_view=True,
               style_table={"overflowX": "auto"},
               style_header={"fontWeight": "600", "color": TINTA, "backgroundColor": "white",
                             "borderBottom": f"1px solid {TINTA}", "fontSize": "12px"},
               style_cell={"fontFamily": "Inter, 'Segoe UI', Roboto, Arial, sans-serif", "fontSize": "13px",
                           "padding": "6px 10px", "color": TINTA, "border": "none",
                           "borderBottom": "1px solid #EEF1F4", "backgroundColor": "white"},
               style_cell_conditional=[{"if": {"column_id": c}, "textAlign": "left"}
                                       for c in ("estado", "regiao", "categoria")],
               style_data_conditional=[
                   {"if": {"filter_query": "{var} < 0", "column_id": "var"}, "color": ALERTA, "fontWeight": "600"},
                   {"if": {"filter_query": "{margem} < 0.12", "column_id": "margem"},
                    "color": ALERTA, "fontWeight": "600"},
               ],
               tooltip_header={"var": "Receita do período vs. os mesmos meses do ano anterior "
                                      "(apenas meses com base comparável).",
                               "margem": "Lucro bruto ÷ receita. Em destaque: margens abaixo de 12%.",
                               "ticket": "Receita ÷ pedidos."},
               tooltip_delay=200, tooltip_duration=None,
           )),

    html.Footer("Overview first, zoom and filter, details-on-demand (Shneiderman, 1996) · "
                "Visões coordenadas com brushing & linking · Paleta Okabe-Ito + sequencial monocromática",
                className="rodape"),
], className="pagina")


# ---------------------------------------------------------------------------
# Callbacks — (1) interações atualizam o estado único de seleção
# ---------------------------------------------------------------------------
@app.callback(
    Output("sel", "data"),
    Output("mapa", "clickData"), Output("barras", "clickData"), Output("matriz", "clickData"),
    Input("serie", "selectedData"), Input("mapa", "clickData"), Input("barras", "clickData"),
    Input("matriz", "clickData"), Input("limpar", "n_clicks"),
    State("sel", "data"), prevent_initial_call=True,
)
def atualiza_selecao(brush, clk_mapa, clk_bar, clk_mat, _n, sel):
    sel = dict(sel)
    origem = ctx.triggered_id
    reset_clicks = (None, None, None)

    if origem == "limpar":
        return {"periodo": None, "ufs": [], "cats": []}, *reset_clicks

    if origem == "serie":
        if not brush or "range" not in brush:
            sel["periodo"] = None
        else:
            a, b = (pd.Timestamp(x) for x in brush["range"]["x"])
            # inclusão estrita: o brush redesenhado (mês ± 15 dias) reproduz o mesmo
            # conjunto de meses, então o ciclo seleção -> redesenho é estável
            meses = [m for m in MESES if a <= m <= b]
            if not meses:  # brush estreito entre dois pontos: usa o mês mais próximo
                meio = a + (b - a) / 2
                meses = [min(MESES, key=lambda m: abs(m - meio))]
            novo = [pd.Timestamp(meses[0]).strftime("%Y-%m-%d"), pd.Timestamp(meses[-1]).strftime("%Y-%m-%d")]
            if novo == sel.get("periodo"):
                return no_update, no_update, no_update, no_update
            sel["periodo"] = novo
        return sel, *reset_clicks

    if origem == "mapa":
        if not clk_mapa:
            return no_update, no_update, no_update, no_update
        uf = clk_mapa["points"][0]["location"]
        ufs = list(sel.get("ufs") or [])
        sel["ufs"] = [u for u in ufs if u != uf] if uf in ufs else ufs + [uf]
        return sel, *reset_clicks

    if origem == "barras":
        if not clk_bar:
            return no_update, no_update, no_update, no_update
        cat = clk_bar["points"][0]["y"]
        cats = list(sel.get("cats") or [])
        sel["cats"] = [c for c in cats if c != cat] if cat in cats else cats + [cat]
        return sel, *reset_clicks

    if origem == "matriz":
        if not clk_mat:
            return no_update, no_update, no_update, no_update
        pt = clk_mat["points"][0]
        reg, cat = pt["y"], pt["customdata"]
        ufs_reg = list(UFS_POR_REGIAO[reg])
        ja = sorted(sel.get("ufs") or []) == sorted(ufs_reg) and (sel.get("cats") or []) == [cat]
        sel["ufs"], sel["cats"] = ([], []) if ja else (ufs_reg, [cat])
        return sel, *reset_clicks

    return no_update, no_update, no_update, no_update


# ---------------------------------------------------------------------------
# Callbacks — (2) o estado de seleção redesenha TODAS as visões (linking)
# ---------------------------------------------------------------------------
@app.callback(
    Output("serie", "figure"), Output("mapa", "figure"), Output("barras", "figure"),
    Output("matriz", "figure"), Output("tabela", "data"), Output("kpis", "children"),
    Output("chips", "children"), Output("tabela", "page_current"),
    Input("sel", "data"), Input("metrica", "value"),
)
def redesenha(sel, metrica):
    return (fig_serie(sel, metrica), fig_mapa(sel, metrica), fig_barras(sel, metrica),
            fig_matriz(sel, metrica), tabela_dados(sel), kpis(sel), chips(sel), 0)


if __name__ == "__main__":
    import os
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 8050)))
