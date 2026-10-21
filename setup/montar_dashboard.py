"""Monta no Superset, via API REST, a conexão com o banco, os datasets, os 27 gráficos e o dashboard.

Chamado por setup/run.py. Pode rodar quantas vezes quiser: recria os gráficos e atualiza dashboard e datasets.
"""

import json
import os
import time
import uuid

import requests

BASE = os.environ.get("SUPERSET_URL", "http://superset:8088") + "/api/v1"
USUARIO = os.environ.get("ADMIN_USER", "admin")
SENHA = os.environ.get("ADMIN_PASSWORD", "admin")
DB_NOME = "Rede de Revendas (dados fictícios)"
DB_URI = "postgresql+psycopg2://analista:analista@db:5432/revendas"
DASH_TITULO = "Rede de Revendas | Programa Parceiros 2026"
DASH_SLUG = "rede-revendas"

s = requests.Session()


def api(metodo, caminho, **kw):
    r = s.request(metodo, BASE + caminho, **kw)
    for _ in range(5):  # o Superset limita requisições por segundo
        if r.status_code != 429:
            break
        time.sleep(1)
        r = s.request(metodo, BASE + caminho, **kw)
    if r.status_code >= 400:
        raise SystemExit(f"{metodo} {caminho} -> {r.status_code}: {r.text[:800]}")
    return r.json() if r.text else {}


def login():
    tok = api("POST", "/security/login",
              json={"username": USUARIO, "password": SENHA, "provider": "db", "refresh": True})["access_token"]
    s.headers["Authorization"] = f"Bearer {tok}"
    s.headers["X-CSRFToken"] = api("GET", "/security/csrf_token/")["result"]
    s.headers["Referer"] = BASE


def buscar(recurso, coluna, valor, op="eq"):
    q = f"(filters:!((col:{coluna},opr:{op},value:'{valor}')),page_size:100)"
    return api("GET", f"/{recurso}/?q={q}")["result"]


# --------------------------------------------------------------------------- criação idempotente
# Dashboard, banco e datasets são reaproveitados quando já existem; só os gráficos são recriados.
def dashboard():
    existentes = buscar("dashboard", "slug", DASH_SLUG)
    if existentes:
        dash_id = existentes[0]["id"]
        for c in api("GET", f"/dashboard/{dash_id}/charts")["result"]:
            api("DELETE", f"/chart/{c['id']}")
        return dash_id
    return api("POST", "/dashboard/", json={"dashboard_title": DASH_TITULO, "slug": DASH_SLUG, "published": True})["id"]


def banco():
    existentes = buscar("database", "database_name", DB_NOME)
    if existentes:
        return existentes[0]["id"]
    return api("POST", "/database/", json={
        "database_name": DB_NOME,
        "sqlalchemy_uri": DB_URI,
        "expose_in_sqllab": True,
        "allow_run_async": False,
    })["id"]


# --------------------------------------------------------------------------- datasets
def m(nome, expr, rotulo, fmt=None):
    return {"metric_name": nome, "expression": expr, "verbose_name": rotulo, "d3format": fmt}


ROTULOS = {
    "mes": "Mês", "diretoria": "Diretoria", "regional": "Regional", "uf": "UF", "carteira": "Carteira",
    "consultor": "Consultor", "revenda": "Revenda", "grupo": "Grupo", "marca": "Marca", "tipo": "Tipo de revenda",
    "cidade": "Cidade", "meta_volume": "Meta (unidades)", "volume": "Realizado (unidades)",
    "realizado": "Realizado (unidades)", "falta_unidades": "Faltam hoje (unidades)", "falta_projetada": "Vai faltar no fim do mês",
    "ritmo_atual_dia": "Ritmo atual (un./dia)", "ritmo_necessario_dia": "Ritmo necessário (un./dia)",
    "projecao_fim_mes": "Projeção fim do mês", "pct_projetado": "% projetado", "dias_restantes": "Dias restantes",
    "status_meta": "Status da meta", "trimestre_label": "Trimestre", "posicao": "Posição", "pontos": "Pontos",
    "pts_volume": "Volume (pts)", "pts_recorrencia": "Recorrência (pts)", "pts_inadimplencia": "Inadimplência (pts)",
    "pts_treinamento": "Treinamento (pts)", "premio_reais": "Prêmio (R$)", "pontos_para_top40": "Faltam p/ top 40",
    "treinamento": "Treinamento", "funcionario": "Funcionário", "cargo": "Cargo", "status": "Status",
    "data_conclusao": "Concluído em", "acertos": "Acertos (de 10)", "tipo_padronizacao": "Padronização",
    "etapa_atual": "Etapa atual", "etapa": "Etapa", "desde": "Na etapa desde", "dias_na_etapa": "Dias na etapa",
    "sla_dias": "SLA (dias)", "sla_estourado": "SLA estourado", "dias_total": "Dias desde a abertura",
    "data_abertura": "Aberta em", "pct_inadimplencia": "% inadimplência", "pct_meta_volume": "% da meta",
}

DATASETS = {
    "vw_kpi_mensal": [
        m("volume", "SUM(volume)", "Volume vendido (unidades)", ",d"),
        m("meta", "SUM(meta_volume)", "Meta de volume (unidades)", ",d"),
        m("pct_meta", "1.0 * SUM(volume) / NULLIF(SUM(meta_volume), 0)", "% da meta de volume", ".1%"),
        m("pct_meta_abaixo", "CASE WHEN SUM(volume) < 0.95 * SUM(meta_volume) "
          "THEN 1.0 * SUM(volume) / NULLIF(SUM(meta_volume), 0) END", "Abaixo de 95%", ".0%"),
        m("pct_meta_quase", "CASE WHEN SUM(volume) >= 0.95 * SUM(meta_volume) AND SUM(volume) < SUM(meta_volume) "
          "THEN 1.0 * SUM(volume) / NULLIF(SUM(meta_volume), 0) END", "Entre 95% e 100%", ".0%"),
        m("pct_meta_ok", "CASE WHEN SUM(volume) >= SUM(meta_volume) "
          "THEN 1.0 * SUM(volume) / NULLIF(SUM(meta_volume), 0) END", "Meta batida", ".0%"),
        m("pct_inadimplencia", "1.0 * SUM(valor_em_atraso) / NULLIF(SUM(valor_vencido), 0)", "% inadimplência", ".1%"),
        m("pct_treinamento", "1.0 * SUM(treinamento_aprovados) / NULLIF(SUM(funcionarios), 0)",
          "% funcionários aprovados no treinamento", ".0%"),
        m("pct_bateu_volume", "AVG(CASE WHEN bateu_volume THEN 1.0 ELSE 0 END)", "Bateram volume", ".0%"),
        m("pct_bateu_recorrencia", "AVG(CASE WHEN bateu_recorrencia THEN 1.0 ELSE 0 END)", "Bateram recorrência", ".0%"),
        m("pct_bateu_inadimplencia", "AVG(CASE WHEN bateu_inadimplencia THEN 1.0 ELSE 0 END)",
          "Dentro da meta de inadimplência", ".0%"),
        m("pct_bateu_treinamento", "AVG(CASE WHEN bateu_treinamento THEN 1.0 ELSE 0 END)", "Bateram treinamento", ".0%"),
        m("pts_volume", "AVG(pts_volume)", "Volume", ".0f"),
        m("pts_recorrencia", "AVG(pts_recorrencia)", "Recorrência", ".0f"),
        m("pts_inadimplencia", "AVG(pts_inadimplencia)", "Inadimplência", ".0f"),
        m("pts_treinamento", "AVG(pts_treinamento)", "Treinamento", ".0f"),
        m("faturamento", "SUM(faturamento)", "Faturamento (R$)", ",.0f"),
    ],
    "vw_projecao_mes_atual": [
        m("revendas", "COUNT(*)", "Revendas", ",d"),
        m("falta", "SUM(falta_projetada)", "Unidades que vão faltar", ",d"),
        m("pct_projetado", "1.0 * SUM(projecao_fim_mes) / NULLIF(SUM(meta_volume), 0)", "% projetado da meta", ".1%"),
    ],
    "vw_ranking_trimestre": [
        m("revendas", "COUNT(*)", "Revendas", ",d"),
        m("premio", "SUM(premio_reais)", "Prêmios (R$)", ",.0f"),
    ],
    "vw_treinamento_status": [
        m("funcionarios", "COUNT(*)", "Funcionários", ",d"),
        m("pct_aprovado", "AVG(CASE WHEN status = 'Aprovado' THEN 1.0 ELSE 0 END)", "% aprovados", ".0%"),
        m("pendentes", "SUM(CASE WHEN status = 'Pendente' THEN 1 ELSE 0 END)", "Pendentes", ",d"),
    ],
    "vw_padronizacao": [
        m("solicitacoes", "COUNT(*)", "Solicitações", ",d"),
        m("abertas", "SUM(CASE WHEN NOT concluida THEN 1 ELSE 0 END)", "Em andamento", ",d"),
        m("estouradas", "SUM(CASE WHEN sla_estourado THEN 1 ELSE 0 END)", "Com SLA estourado", ",d"),
    ],
    "vw_padronizacao_etapas": [
        m("dias_medios", "AVG(dias_na_etapa)", "Dias médios na etapa", ".1f"),
        m("sla", "MAX(sla_dias)", "SLA (dias)", ".0f"),
    ],
}

CAMPOS_COLUNA = ("id", "column_name", "verbose_name", "is_dttm", "type", "groupby", "filterable",
                 "expression", "description", "python_date_format")


def datasets(db_id):
    ids = {}
    for view, metricas in DATASETS.items():
        def achar(view=view):
            return next(d["id"] for d in buscar("dataset", "table_name", view) if d["database"]["id"] == db_id)

        try:
            ds_id = achar()
            api("PUT", f"/dataset/{ds_id}/refresh")  # pega colunas novas da view
        except StopIteration:
            ds_id = api("POST", "/dataset/", json={"database": db_id, "schema": "rede", "table_name": view})["id"]
        atual = api("GET", f"/dataset/{ds_id}")["result"]
        ids_metricas = {mt["metric_name"]: mt["id"] for mt in atual["metrics"]}
        metricas = [{**mt, "id": ids_metricas[mt["metric_name"]]} if mt["metric_name"] in ids_metricas else mt
                    for mt in metricas]
        colunas = []
        for c in atual["columns"]:
            c = {k: c.get(k) for k in CAMPOS_COLUNA}
            c["verbose_name"] = ROTULOS.get(c["column_name"])
            colunas.append(c)
        api("PUT", f"/dataset/{ds_id}?override_columns=false", json={
            "columns": colunas, "metrics": metricas, "main_dttm_col": "mes" if any(
                c["column_name"] == "mes" for c in colunas) else None})
        ids[view] = ds_id
    return ids


# --------------------------------------------------------------------------- gráficos
def filtro(coluna, op, valor):
    return {"clause": "WHERE", "expressionType": "SIMPLE", "subject": coluna, "operator": op,
            "comparator": valor, "filterOptionName": uuid.uuid4().hex}


def filtro_sql(sql):
    return {"clause": "WHERE", "expressionType": "SQL", "sqlExpression": sql, "filterOptionName": uuid.uuid4().hex}


FECHADOS = filtro_sql("mes_fechado")


def big(metrica, subtitulo, filtros=(), fmt=None):
    return {"viz_type": "big_number_total", "metric": metrica, "subheader": subtitulo,
            "adhoc_filters": list(filtros), "header_font_size": 0.4, "subheader_font_size": 0.15,
            "y_axis_format": fmt or "SMART_NUMBER", "time_range": "No filter"}


def barras(x, metricas, filtros=(), fmt="SMART_NUMBER", horizontal=True, empilhar=False, ordenar=None, asc=True):
    p = {"viz_type": "echarts_timeseries_bar", "x_axis": x, "metrics": metricas, "groupby": [],
         "adhoc_filters": list(filtros), "orientation": "horizontal" if horizontal else "vertical",
         "y_axis_format": fmt, "show_value": True, "show_legend": len(metricas) > 1, "row_limit": 1000,
         "time_range": "No filter", "x_axis_sort_asc": asc, "truncateYAxis": False, "rich_tooltip": True}
    if ordenar:
        p["x_axis_sort"] = ordenar
    if empilhar:
        p["stack"] = "Stack"
    return p


def tabela(colunas, ordem=None, filtros=(), limite=1000):
    p = {"viz_type": "table", "query_mode": "raw", "all_columns": colunas, "adhoc_filters": list(filtros),
         "row_limit": limite, "server_page_length": 20, "server_pagination": False, "page_length": 20,
         "include_search": True, "table_timestamp_format": "%d/%m/%Y", "time_range": "No filter",
         "show_cell_bars": False}
    if ordem:
        p["order_by_cols"] = [json.dumps(o) for o in ordem]
    return p


VERMELHO, AMARELO, VERDE = "#E04355", "#FCC700", "#5AC189"


def regra(coluna, op, valor, cor):
    return {"column": coluna, "operator": op, "targetValue": valor, "colorScheme": cor, "useGradient": False}


def faixa(coluna, de, ate, cor):
    return {"column": coluna, "operator": "≤ x <", "targetValueLeft": de, "targetValueRight": ate,
            "colorScheme": cor, "useGradient": False}


def tabela_agregada(grupos, metricas, filtros=(), ordem=None, cores=()):
    return {"viz_type": "table", "query_mode": "aggregate", "groupby": grupos, "metrics": metricas,
            "adhoc_filters": list(filtros), "row_limit": 1000, "order_desc": False, "include_search": False,
            "show_cell_bars": False, "time_range": "No filter", "timeseries_limit_metric": ordem,
            "conditional_formatting": list(cores)}


def graficos(ds):
    k, proj, rk, tr, pad, et = (ds["vw_kpi_mensal"], ds["vw_projecao_mes_atual"], ds["vw_ranking_trimestre"],
                                ds["vw_treinamento_status"], ds["vw_padronizacao"], ds["vw_padronizacao_etapas"])
    out_mes = filtro("mes", "==", "2026-10-01")
    return {
        # ---------------- Visão gerencial
        "big_volume": (k, "Volume vendido em 2026", big("volume", "unidades (jan → 20/out)", fmt=",d")),
        "big_pct_meta": (k, "% da meta de volume", big("pct_meta", "meses fechados (jan–set)", [FECHADOS], ".1%")),
        "big_inad": (k, "Inadimplência", big("pct_inadimplencia", "valor vencido em atraso (meta: até 5%)",
                                             [FECHADOS], ".1%")),
        "big_trein": (k, "Treinamento", big("pct_treinamento", "funcionários aprovados (meta: 80%)",
                                            [FECHADOS], ".0%")),
        "bar_regional": (k, "Onde a meta de volume não está sendo batida (% da meta, jan–set)",
                         barras("regional", ["pct_meta_abaixo", "pct_meta_quase", "pct_meta_ok"], [FECHADOS], ".0%",
                                empilhar=True, ordenar="sum", asc=False) | {"label_colors": {
                             "Abaixo de 95%": VERMELHO, "Entre 95% e 100%": AMARELO, "Meta batida": VERDE,
                             "pct_meta_abaixo": VERMELHO, "pct_meta_quase": AMARELO, "pct_meta_ok": VERDE}}),
        "heat_regional": (k, "% da meta de volume por regional e mês (jan–set)", {
            "viz_type": "heatmap_v2", "x_axis": "mes", "time_grain_sqla": "P1M", "groupby": "regional",
            "metric": "pct_meta", "linear_color_scheme": "schemeRdYlGn", "normalize_across": "heatmap",
            "show_values": True, "show_legend": False, "y_axis_format": ".0%", "x_axis_time_format": "%b/%y",
            "sort_x_axis": "alpha_asc", "sort_y_axis": "value_asc", "normalized": False,
            # escala centrada em 100%: <=90% vermelho, 100% amarelo, >=110% verde
            "value_bounds": [0.9, 1.1],
            "adhoc_filters": [FECHADOS], "time_range": "No filter", "row_limit": 10000}),
        "tab_regional": (k, "Resumo por diretoria e regional (jan–set)", tabela_agregada(
            ["diretoria", "regional"], ["pct_meta", "pct_bateu_volume", "pct_bateu_recorrencia", "pct_inadimplencia",
                                  "pct_treinamento"], [FECHADOS], ordem="pct_meta", cores=[
            regra("pct_meta", "<", 0.95, VERMELHO), faixa("pct_meta", 0.95, 1.0, AMARELO),
            regra("pct_meta", "≥", 1.0, VERDE),
            regra("pct_bateu_volume", "<", 0.35, VERMELHO), regra("pct_bateu_volume", "≥", 0.5, VERDE),
            regra("pct_bateu_recorrencia", "<", 0.85, VERMELHO), regra("pct_bateu_recorrencia", "≥", 0.9, VERDE),
            regra("pct_inadimplencia", ">", 0.05, VERMELHO), regra("pct_inadimplencia", "≤", 0.05, VERDE),
            regra("pct_treinamento", "<", 0.8, VERMELHO), regra("pct_treinamento", "≥", 0.8, VERDE)])),
        "linha_mensal": (k, "Volume realizado x meta por mês", {
            "viz_type": "echarts_timeseries_line", "x_axis": "mes", "time_grain_sqla": "P1M",
            "metrics": ["volume", "meta"], "groupby": [], "adhoc_filters": [FECHADOS], "y_axis_format": ",d",
            "x_axis_time_format": "%b/%y", "show_legend": True, "rich_tooltip": True, "markerEnabled": True,
            "time_range": "No filter", "row_limit": 10000}),
        # ---------------- Mês atual
        "big_risco": (proj, "Revendas em risco ou perto da meta",
                      big("revendas", "no ritmo atual não fecham outubro na meta",
                          [filtro("status_meta", "IN", ["3. Atenção: perto da meta", "4. Em risco"])], ",d")),
        "big_falta": (proj, "Unidades que vão faltar em outubro", big("falta", "se cada revenda mantiver o ritmo atual", fmt=",d")),
        "big_proj": (proj, "Projeção de outubro", big("pct_projetado", "da meta, mantido o ritmo atual", fmt=".1%")),
        "pie_status": (proj, "Situação das revendas em outubro", {
            "viz_type": "pie", "groupby": ["status_meta"], "metric": "revendas", "donut": True, "show_labels": True,
            "label_type": "value", "labels_outside": False, "show_legend": True, "legendOrientation": "bottom", "adhoc_filters": [],
            "row_limit": 100, "time_range": "No filter", "sort_by_metric": False,
            "label_colors": {"1. Meta batida": "#1A85A0", "2. No ritmo": "#5AC189",
                             "3. Atenção: perto da meta": "#FCC700", "4. Em risco": "#E04355"}}),
        "tab_perto": (proj, "Quem não fecha outubro na meta (menor diferença primeiro: vale uma ligação do consultor hoje)", tabela(
            ["revenda", "consultor", "regional", "meta_volume", "realizado", "projecao_fim_mes", "falta_projetada",
             "falta_unidades", "ritmo_atual_dia", "ritmo_necessario_dia", "status_meta"],
            ordem=[["falta_projetada", True]],
            filtros=[filtro("status_meta", "IN", ["3. Atenção: perto da meta", "4. Em risco"])])),
        # ---------------- Ranking
        "tab_rank_t3": (rk, "Ranking T3/2026 (fechado): top 40 ganham crédito em carteira", tabela(
            ["posicao", "revenda", "regional", "consultor", "pontos", "pts_volume", "pts_recorrencia",
             "pts_inadimplencia", "pts_treinamento", "premio_reais"],
            ordem=[["posicao", True]], filtros=[filtro("trimestre_label", "==", "T3/2026")], limite=100)),
        "tab_rank_t4": (rk, "T4/2026 parcial: quem está na briga pelo top 40", tabela(
            ["posicao", "revenda", "regional", "consultor", "pontos", "pontos_para_top40", "premio_reais"],
            ordem=[["posicao", True]], filtros=[filtro("trimestre_label", "==", "T4/2026")], limite=80)),
        "bar_pontos": (k, "Onde cada regional perde pontos (média de pontos/mês por indicador, máx. 260)",
                       barras("regional", ["pts_volume", "pts_recorrencia", "pts_inadimplencia", "pts_treinamento"],
                              [FECHADOS], ".0f", empilhar=True)),
        "big_premio": (rk, "Prêmios distribuídos no T3", big("premio", "em crédito na carteira das revendas",
                                                             [filtro("trimestre_label", "==", "T3/2026")], ",.0f")),
        # ---------------- Treinamentos
        "big_pend": (tr, "Funcionários com treinamento de outubro pendente", big(
            "pendentes", "prazo: 31/10", [out_mes], ",d")),
        "big_aprov": (tr, "Aprovação no treinamento de outubro (até agora)", big(
            "pct_aprovado", "dos funcionários das revendas", [out_mes], ".0%")),
        "bar_trein_mes": (tr, "% de funcionários aprovados por mês", barras(
            "mes", ["pct_aprovado"], fmt=".0%", horizontal=False) | {"time_grain_sqla": "P1M",
                                                                     "x_axis_time_format": "%b/%y"}),
        "bar_trein_reg": (tr, "Pendências de outubro por regional", barras(
            "regional", ["pendentes"], [out_mes], ",d", ordenar="pendentes", asc=True)),
        "tab_pend": (tr, "Quem ainda não fez o treinamento de outubro", tabela(
            ["revenda", "funcionario", "cargo", "consultor", "regional", "treinamento"],
            ordem=[["revenda", True]], filtros=[out_mes, filtro("status", "==", "Pendente")])),
        # ---------------- Padronização
        "big_pad_and": (pad, "Padronizações em andamento", big("abertas", "fachada, pintura, frota, comunicação", fmt=",d")),
        "big_pad_sla": (pad, "Com SLA estourado", big("estouradas", "paradas além do prazo da etapa", fmt=",d")),
        "bar_etapas": (et, "Tempo médio em cada etapa x SLA (dias)", barras(
            "etapa", ["dias_medios", "sla"], fmt=".1f", horizontal=False) | {"x_axis_sort_asc": True}),
        "bar_pad_reg": (et, "Tempo médio por etapa, por regional (dias)", barras(
            "regional", ["dias_medios"], fmt=".1f", ordenar="dias_medios", asc=True)),
        "tab_pad": (pad, "Solicitações em andamento (mais paradas primeiro)", tabela(
            ["revenda", "tipo_padronizacao", "etapa_atual", "desde", "dias_na_etapa", "sla_dias", "sla_estourado",
             "dias_total", "consultor", "regional"],
            ordem=[["sla_estourado", False], ["dias_na_etapa", False]],
            filtros=[filtro_sql("NOT concluida")])),
    }


# --------------------------------------------------------------------------- dashboard
ABAS = [
    ("Visão gerencial", [
        ("md:Para a **diretoria e o gerente regional**: onde a campanha não está performando. "
         "Use os filtros à esquerda (Diretoria → Regional → Consultor → Revenda) para descer na árvore.", 12, 8),
        ["big_volume", "big_pct_meta", "big_inad", "big_trein"],
        [("bar_regional", 5, 60), ("heat_regional", 7, 60)],
        [("tab_regional", 12, 55)],
        [("linha_mensal", 12, 45)],
    ]),
    ("Outubro: quem está perto da meta", [
        ("md:**Visão antecipada.** Projeção = ritmo de vendas até 20/out × dias do mês. "
         "\"Faltam 10 unidades\" aparece aqui *antes* de o mês fechar, a tempo do consultor agir.", 12, 8),
        [("big_risco", 3, 45), ("big_falta", 3, 45), ("big_proj", 3, 45), ("pie_status", 3, 45)],
        [("tab_perto", 12, 80)],
    ]),
    ("Ranking e prêmios", [
        ("md:Pontuação mensal: **Volume** 100 pts (≥100% da meta) ou 50 (≥90%) · **Recorrência** 60 · "
         "**Inadimplência** 60 (≤5%) · **Treinamento** 40 (≥80% aprovados) = **260 pts/mês**. "
         "Top 40 do trimestre: R$ 10 mil (1º–10º), R$ 5 mil (11º–25º), R$ 2,5 mil (26º–40º) em carteira.", 12, 10),
        [("bar_pontos", 8, 55), ("big_premio", 4, 55)],
        [("tab_rank_t3", 12, 75)],
        [("tab_rank_t4", 12, 75)],
    ]),
    ("Treinamentos", [
        ["big_pend", "big_aprov"],
        [("bar_trein_mes", 6, 50), ("bar_trein_reg", 6, 50)],
        [("tab_pend", 12, 70)],
    ]),
    ("Padronização (SLA)", [
        ["big_pad_and", "big_pad_sla"],
        [("bar_etapas", 6, 50), ("bar_pad_reg", 6, 50)],
        [("tab_pad", 12, 60)],
    ]),
]


def layout(chart_ids):
    pos = {"DASHBOARD_VERSION_KEY": "v2",
           "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["TABS-main"]},
           "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": DASH_TITULO}},
           "TABS-main": {"type": "TABS", "id": "TABS-main", "children": [], "parents": ["ROOT_ID"]}}
    abas_ids = []
    for a, (nome, linhas) in enumerate(ABAS):
        tab = f"TAB-{a}"
        abas_ids.append(tab)
        pos["TABS-main"]["children"].append(tab)
        pos[tab] = {"type": "TAB", "id": tab, "children": [], "parents": ["ROOT_ID", "TABS-main"],
                    "meta": {"text": nome, "defaultText": "Tab title"}}
        for li, linha in enumerate(linhas):
            row = f"ROW-{a}-{li}"
            pais = ["ROOT_ID", "TABS-main", tab, row]
            pos[tab]["children"].append(row)
            pos[row] = {"type": "ROW", "id": row, "children": [], "parents": pais[:-1],
                        "meta": {"background": "BACKGROUND_TRANSPARENT"}}
            if isinstance(linha, tuple):  # markdown ocupando a linha toda
                md = f"MARKDOWN-{a}-{li}"
                pos[row]["children"].append(md)
                pos[md] = {"type": "MARKDOWN", "id": md, "children": [], "parents": pais,
                           "meta": {"code": linha[0][3:], "width": linha[1], "height": linha[2]}}
                continue
            itens = [(c, 12 // len(linha), 30) if isinstance(c, str) else c for c in linha]
            for chave, largura, altura in itens:
                cid = f"CHART-{chave}"
                pos[row]["children"].append(cid)
                pos[cid] = {"type": "CHART", "id": cid, "children": [], "parents": pais,
                            "meta": {"chartId": chart_ids[chave], "width": largura, "height": altura,
                                     "uuid": str(uuid.uuid4())}}
    return pos, abas_ids


def filtros_nativos(ds_id, chart_ids, abas_ids):
    defs = [("diretoria", "Diretoria"), ("regional", "Regional"), ("consultor", "Consultor (carteira)"), ("revenda", "Revenda"),
            ("grupo", "Grupo"), ("marca", "Marca")]
    out, anterior = [], None
    for coluna, nome in defs:
        fid = f"NATIVE_FILTER-{coluna}"
        out.append({
            "id": fid, "name": nome, "filterType": "filter_select", "type": "NATIVE_FILTER",
            "targets": [{"datasetId": ds_id, "column": {"name": coluna}}],
            "controlValues": {"multiSelect": True, "enableEmptyFilter": False, "defaultToFirstItem": False,
                              "inverseSelection": False, "searchAllOptions": coluna == "revenda"},
            "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
            "cascadeParentIds": [anterior] if anterior and coluna in ("regional", "consultor", "revenda") else [],
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "chartsInScope": list(chart_ids.values()), "tabsInScope": abas_ids, "description": ""})
        anterior = fid
    return out


def main():
    login()
    db_id = banco()
    ds = datasets(db_id)
    dash_id = dashboard()
    chart_ids = {}
    for chave, (ds_id, titulo, params) in graficos(ds).items():
        params = {**params, "datasource": f"{ds_id}__table"}
        chart_ids[chave] = api("POST", "/chart/", json={
            "slice_name": titulo, "viz_type": params["viz_type"], "datasource_id": ds_id,
            "datasource_type": "table", "params": json.dumps(params), "dashboards": [dash_id]})["id"]
    pos, abas_ids = layout(chart_ids)
    meta = {"native_filter_configuration": filtros_nativos(ds["vw_kpi_mensal"], chart_ids, abas_ids),
            "color_scheme": "supersetColors", "refresh_frequency": 0, "cross_filters_enabled": True,
            "label_colors": {"Abaixo de 95%": "#E04355", "Entre 95% e 100%": "#FCC700", "Meta batida": "#5AC189",
                             "pct_meta_abaixo": "#E04355", "pct_meta_quase": "#FCC700", "pct_meta_ok": "#5AC189",
                             "1. Meta batida": "#1A85A0", "2. No ritmo": "#5AC189",
                             "3. Atenção: perto da meta": "#FCC700", "4. Em risco": "#E04355"},
            "timed_refresh_immune_slices": [], "expanded_slices": {}}
    api("PUT", f"/dashboard/{dash_id}", json={"dashboard_title": DASH_TITULO, "published": True,
                                              "position_json": json.dumps(pos), "json_metadata": json.dumps(meta)})
    print(f"ok: banco={db_id} datasets={len(ds)} graficos={len(chart_ids)} dashboard=/superset/dashboard/{DASH_SLUG}/")


if __name__ == "__main__":
    main()
