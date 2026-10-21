-- Views = "tradução" dos dados brutos em indicadores. É isso que o Superset lê.
SET search_path TO rede;

-- Revenda com toda a árvore comercial achatada (Diretoria > Regional > Carteira > Revenda)
CREATE OR REPLACE VIEW vw_revenda AS
SELECT r.id AS revenda_id,
       r.nome AS revenda,
       r.cnpj,
       r.marca,
       r.tipo,
       r.cidade,
       COALESCE(gr.nome, 'Sem grupo') AS grupo,
       c.nome AS carteira,
       c.consultor,
       rg.nome AS regional,
       rg.uf,
       d.nome AS diretoria
FROM revenda r
JOIN carteira c ON c.id = r.carteira_id
JOIN regional rg ON rg.id = c.regional_id
JOIN diretoria d ON d.id = rg.diretoria_id
LEFT JOIN grupo gr ON gr.id = r.grupo_id;

-- Indicadores da campanha por revenda e mês, com a pontuação
-- Regra: Volume 100 pts (>=100% da meta) ou 50 pts (>=90%); Recorrência 60; Inadimplência 60; Treinamento 40
CREATE OR REPLACE VIEW vw_kpi_mensal AS
WITH ref AS (SELECT data_referencia FROM parametros),
vol AS (
    SELECT revenda_id, date_trunc('month', data)::date AS mes,
           SUM(quantidade) AS volume, COUNT(*) AS pedidos, SUM(valor) AS faturamento
    FROM pedido, ref
    WHERE data <= ref.data_referencia
    GROUP BY 1, 2
),
inad AS (
    SELECT revenda_id, date_trunc('month', vencimento)::date AS mes,
           SUM(valor) AS valor_vencido,
           SUM(valor) FILTER (WHERE data_pagamento IS NULL OR data_pagamento > vencimento + 5) AS valor_em_atraso
    FROM pedido, ref
    WHERE vencimento <= ref.data_referencia
    GROUP BY 1, 2
),
trein AS (
    SELECT f.revenda_id, t.mes,
           COUNT(*) AS funcionarios,
           COUNT(*) FILTER (WHERE tr.acertos >= 7) AS aprovados
    FROM funcionario f
    CROSS JOIN treinamento t
    LEFT JOIN treinamento_resposta tr ON tr.funcionario_id = f.id AND tr.treinamento_id = t.id
    GROUP BY 1, 2
),
base AS (
    SELECT m.mes,
           (m.mes < date_trunc('month', ref.data_referencia)) AS mes_fechado,
           m.revenda_id,
           m.meta_volume,
           COALESCE(v.volume, 0) AS volume,
           COALESCE(v.faturamento, 0) AS faturamento,
           m.meta_recorrencia,
           COALESCE(v.pedidos, 0) AS pedidos,
           m.meta_inadimplencia_max,
           COALESCE(i.valor_vencido, 0) AS valor_vencido,
           COALESCE(i.valor_em_atraso, 0) AS valor_em_atraso,
           COALESCE(t.funcionarios, 0) AS funcionarios,
           COALESCE(t.aprovados, 0) AS treinamento_aprovados
    FROM meta_mensal m
    CROSS JOIN ref
    LEFT JOIN vol v ON v.revenda_id = m.revenda_id AND v.mes = m.mes
    LEFT JOIN inad i ON i.revenda_id = m.revenda_id AND i.mes = m.mes
    LEFT JOIN trein t ON t.revenda_id = m.revenda_id AND t.mes = m.mes
    WHERE m.mes <= ref.data_referencia
),
calc AS (
    SELECT b.*,
           ROUND(100.0 * b.volume / NULLIF(b.meta_volume, 0), 1) AS pct_meta_volume,
           GREATEST(b.meta_volume - b.volume, 0) AS falta_unidades,
           ROUND(100.0 * b.valor_em_atraso / NULLIF(b.valor_vencido, 0), 2) AS pct_inadimplencia,
           ROUND(100.0 * b.treinamento_aprovados / NULLIF(b.funcionarios, 0), 1) AS pct_treinamento
    FROM base b
)
SELECT c.mes,
       c.mes_fechado,
       r.*,
       c.meta_volume, c.volume, c.faturamento, c.pct_meta_volume, c.falta_unidades,
       c.meta_recorrencia, c.pedidos,
       c.meta_inadimplencia_max, c.valor_vencido, c.valor_em_atraso, COALESCE(c.pct_inadimplencia, 0) AS pct_inadimplencia,
       c.funcionarios, c.treinamento_aprovados, c.pct_treinamento,
       (c.volume >= c.meta_volume) AS bateu_volume,
       (c.pedidos >= c.meta_recorrencia) AS bateu_recorrencia,
       (COALESCE(c.pct_inadimplencia, 0) <= c.meta_inadimplencia_max) AS bateu_inadimplencia,
       (COALESCE(c.pct_treinamento, 0) >= 80) AS bateu_treinamento,
       CASE WHEN c.volume >= c.meta_volume THEN 100
            WHEN c.volume >= 0.9 * c.meta_volume THEN 50 ELSE 0 END AS pts_volume,
       CASE WHEN c.pedidos >= c.meta_recorrencia THEN 60 ELSE 0 END AS pts_recorrencia,
       CASE WHEN COALESCE(c.pct_inadimplencia, 0) <= c.meta_inadimplencia_max THEN 60 ELSE 0 END AS pts_inadimplencia,
       CASE WHEN COALESCE(c.pct_treinamento, 0) >= 80 THEN 40 ELSE 0 END AS pts_treinamento
FROM calc c
JOIN vw_revenda r ON r.revenda_id = c.revenda_id;

-- Mês corrente: quanto falta para a meta e se o ritmo atual chega lá ("faltam 10 unidades")
CREATE OR REPLACE VIEW vw_projecao_mes_atual AS
WITH ref AS (
    SELECT data_referencia,
           EXTRACT(day FROM data_referencia)::int AS dias_decorridos,
           EXTRACT(day FROM (date_trunc('month', data_referencia) + interval '1 month - 1 day'))::int AS dias_no_mes
    FROM parametros
),
k AS (
    SELECT k.*, ref.dias_decorridos, ref.dias_no_mes
    FROM vw_kpi_mensal k, ref
    WHERE k.mes = date_trunc('month', ref.data_referencia)
)
SELECT k.mes, k.revenda_id, k.revenda, k.marca, k.tipo, k.cidade, k.grupo,
       k.carteira, k.consultor, k.regional, k.uf, k.diretoria,
       k.meta_volume, k.volume AS realizado, k.falta_unidades,
       ROUND(k.volume::numeric / k.dias_decorridos, 1) AS ritmo_atual_dia,
       ROUND(k.falta_unidades::numeric / NULLIF(k.dias_no_mes - k.dias_decorridos, 0), 1) AS ritmo_necessario_dia,
       ROUND(k.volume::numeric / k.dias_decorridos * k.dias_no_mes) AS projecao_fim_mes,
       ROUND(100.0 * k.volume / k.dias_decorridos * k.dias_no_mes / NULLIF(k.meta_volume, 0), 1) AS pct_projetado,
       GREATEST(k.meta_volume - ROUND(k.volume::numeric / k.dias_decorridos * k.dias_no_mes), 0) AS falta_projetada,
       k.dias_no_mes - k.dias_decorridos AS dias_restantes,
       CASE WHEN k.volume >= k.meta_volume THEN '1. Meta batida'
            WHEN k.volume::numeric / k.dias_decorridos * k.dias_no_mes >= k.meta_volume THEN '2. No ritmo'
            WHEN k.volume::numeric / k.dias_decorridos * k.dias_no_mes >= 0.9 * k.meta_volume THEN '3. Atenção: perto da meta'
            ELSE '4. Em risco' END AS status_meta
FROM k;

-- Ranking trimestral da campanha + prêmio em carteira (top 40)
CREATE OR REPLACE VIEW vw_ranking_trimestre AS
WITH ref AS (SELECT data_referencia FROM parametros),
pts AS (
    SELECT date_trunc('quarter', mes)::date AS trimestre,
           revenda_id, revenda, carteira, consultor, regional, diretoria, grupo, marca,
           SUM(pts_volume) AS pts_volume,
           SUM(pts_recorrencia) AS pts_recorrencia,
           SUM(pts_inadimplencia) AS pts_inadimplencia,
           SUM(pts_treinamento) AS pts_treinamento,
           SUM(pts_volume + pts_recorrencia + pts_inadimplencia + pts_treinamento) AS pontos,
           SUM(volume) AS volume,
           COUNT(*) AS meses_apurados
    FROM vw_kpi_mensal
    GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9
),
rk AS (
    SELECT p.*,
           RANK() OVER (PARTITION BY trimestre ORDER BY pontos DESC, volume DESC) AS posicao
    FROM pts p
),
corte AS (
    SELECT trimestre, MIN(pontos) AS pontos_top40
    FROM rk WHERE posicao <= 40 GROUP BY 1
)
SELECT 'T' || EXTRACT(quarter FROM rk.trimestre) || '/' || EXTRACT(year FROM rk.trimestre) AS trimestre_label,
       rk.*,
       (rk.trimestre + interval '3 months' <= (SELECT data_referencia FROM ref) + 1) AS trimestre_fechado,
       CASE WHEN rk.posicao <= 10 THEN 10000
            WHEN rk.posicao <= 25 THEN 5000
            WHEN rk.posicao <= 40 THEN 2500 ELSE 0 END AS premio_reais,
       GREATEST(c.pontos_top40 - rk.pontos, 0) AS pontos_para_top40
FROM rk
JOIN corte c ON c.trimestre = rk.trimestre;

-- Treinamento: quem fez, quem não fez (por funcionário)
CREATE OR REPLACE VIEW vw_treinamento_status AS
WITH ref AS (SELECT data_referencia FROM parametros)
SELECT t.mes,
       t.titulo AS treinamento,
       f.id AS funcionario_id,
       f.nome AS funcionario,
       f.cargo,
       r.*,
       tr.data_conclusao,
       tr.acertos,
       CASE WHEN tr.funcionario_id IS NULL AND t.mes = date_trunc('month', ref.data_referencia) THEN 'Pendente'
            WHEN tr.funcionario_id IS NULL THEN 'Não realizado'
            WHEN tr.acertos >= 7 THEN 'Aprovado'
            ELSE 'Reprovado' END AS status
FROM treinamento t
CROSS JOIN ref
CROSS JOIN funcionario f
JOIN vw_revenda r ON r.revenda_id = f.revenda_id
LEFT JOIN treinamento_resposta tr ON tr.funcionario_id = f.id AND tr.treinamento_id = t.id
WHERE t.mes <= ref.data_referencia;

-- Padronização: situação atual de cada solicitação e SLA da etapa em que está
CREATE OR REPLACE VIEW vw_padronizacao AS
WITH ref AS (SELECT data_referencia FROM parametros),
atual AS (
    SELECT DISTINCT ON (h.padronizacao_id) h.*
    FROM padronizacao_historico h
    ORDER BY h.padronizacao_id, h.etapa_ordem DESC
)
SELECT p.id AS padronizacao_id,
       p.tipo AS tipo_padronizacao,
       p.data_abertura,
       e.ordem || '. ' || e.nome AS etapa_atual,
       (e.sla_dias IS NULL) AS concluida,
       a.data_inicio AS desde,
       CASE WHEN e.sla_dias IS NULL THEN NULL ELSE ref.data_referencia - a.data_inicio END AS dias_na_etapa,
       e.sla_dias,
       (e.sla_dias IS NOT NULL AND ref.data_referencia - a.data_inicio > e.sla_dias) AS sla_estourado,
       CASE WHEN e.sla_dias IS NULL THEN a.data_inicio - p.data_abertura
            ELSE ref.data_referencia - p.data_abertura END AS dias_total,
       r.*
FROM padronizacao p
CROSS JOIN ref
JOIN atual a ON a.padronizacao_id = p.id
JOIN padronizacao_etapa e ON e.ordem = a.etapa_ordem
JOIN vw_revenda r ON r.revenda_id = p.revenda_id;

-- Padronização: tempo gasto em cada etapa (para comparar com o SLA)
CREATE OR REPLACE VIEW vw_padronizacao_etapas AS
WITH ref AS (SELECT data_referencia FROM parametros)
SELECT h.padronizacao_id,
       p.tipo AS tipo_padronizacao,
       e.ordem || '. ' || e.nome AS etapa,
       e.sla_dias,
       COALESCE(h.data_fim, ref.data_referencia) - h.data_inicio AS dias_na_etapa,
       (h.data_fim IS NULL) AS em_andamento,
       r.*
FROM padronizacao_historico h
CROSS JOIN ref
JOIN padronizacao p ON p.id = h.padronizacao_id
JOIN padronizacao_etapa e ON e.ordem = h.etapa_ordem
JOIN vw_revenda r ON r.revenda_id = p.revenda_id
WHERE e.sla_dias IS NOT NULL;
