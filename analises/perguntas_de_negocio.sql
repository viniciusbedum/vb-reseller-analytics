-- Perguntas de negócio respondidas direto em SQL, sem passar pelo Superset.
-- Rodar num cliente SQL conectado em localhost:5433, banco revendas (analista / analista).
SET search_path TO rede;


-- 1. Curva ABC: quais revendas concentram 80% do volume do ano?
--    Técnica: SUM() OVER com ORDER BY para acumulado; classificação por faixa do acumulado.
WITH vol AS (
    SELECT revenda_id, revenda, regional, SUM(volume) AS volume
    FROM vw_kpi_mensal
    GROUP BY 1, 2, 3
),
acum AS (
    SELECT *,
           100.0 * SUM(volume) OVER (ORDER BY volume DESC, revenda_id) / SUM(volume) OVER () AS pct_acumulado
    FROM vol
)
SELECT CASE WHEN pct_acumulado <= 80 THEN 'A' WHEN pct_acumulado <= 95 THEN 'B' ELSE 'C' END AS curva,
       COUNT(*) AS revendas,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_revendas,
       SUM(volume) AS volume
FROM acum
GROUP BY 1
ORDER BY 1;


-- 2. Quem está caindo? Revendas cujo % da meta caiu 3 meses seguidos (jul → set).
--    Usa % da meta e não volume bruto: a meta já embute a sazonalidade (o inverno vende mais),
--    então a queda natural de agosto/setembro não vira falso alarme.
--    Técnica: LAG() para comparar cada mês com o anterior; BOOL_AND para "todos os meses".
WITH mensal AS (
    SELECT revenda_id, revenda, consultor, regional, mes, pct_meta_volume,
           pct_meta_volume - LAG(pct_meta_volume) OVER (PARTITION BY revenda_id ORDER BY mes) AS variacao
    FROM vw_kpi_mensal
    WHERE mes_fechado
)
SELECT revenda, consultor, regional,
       MAX(pct_meta_volume) FILTER (WHERE mes = DATE '2026-06-01') AS pct_meta_jun,
       MAX(pct_meta_volume) FILTER (WHERE mes = DATE '2026-09-01') AS pct_meta_set,
       MAX(pct_meta_volume) FILTER (WHERE mes = DATE '2026-09-01') - MAX(pct_meta_volume) FILTER (WHERE mes = DATE '2026-06-01') AS variacao_pp
FROM mensal
WHERE mes BETWEEN DATE '2026-06-01' AND DATE '2026-09-01'
GROUP BY revenda_id, revenda, consultor, regional
HAVING BOOL_AND(variacao < 0) FILTER (WHERE mes >= DATE '2026-07-01')
ORDER BY variacao_pp
LIMIT 10;


-- 3. Revendas que não bateram a meta de volume em nenhum mês fechado.
--    Técnica: agregação booleana com HAVING; COUNT FILTER.
SELECT revenda, regional, consultor,
       COUNT(*) AS meses,
       ROUND(AVG(pct_meta_volume), 1) AS pct_medio_da_meta,
       COUNT(*) FILTER (WHERE pts_volume = 50) AS meses_entre_90_e_100
FROM vw_kpi_mensal
WHERE mes_fechado
GROUP BY revenda_id, revenda, regional, consultor
HAVING NOT BOOL_OR(bateu_volume)
ORDER BY pct_medio_da_meta
LIMIT 15;


-- 4. Aging da inadimplência: quanto do valor vencido está em atraso, por faixa de dias e regional.
--    Técnica: CASE para faixas + pivot com SUM FILTER.
WITH ref AS (SELECT data_referencia FROM parametros),
vencidos AS (
    SELECT r.regional, p.valor,
           COALESCE(p.data_pagamento, ref.data_referencia) - p.vencimento AS dias_atraso
    FROM pedido p
    CROSS JOIN ref
    JOIN vw_revenda r ON r.revenda_id = p.revenda_id
    WHERE p.vencimento <= ref.data_referencia
)
SELECT regional,
       ROUND(SUM(valor) FILTER (WHERE dias_atraso BETWEEN 6 AND 30)) AS "6 a 30 dias",
       ROUND(SUM(valor) FILTER (WHERE dias_atraso BETWEEN 31 AND 60)) AS "31 a 60 dias",
       ROUND(SUM(valor) FILTER (WHERE dias_atraso > 60)) AS "mais de 60 dias",
       ROUND(100.0 * SUM(valor) FILTER (WHERE dias_atraso > 5) / SUM(valor), 1) AS pct_em_atraso
FROM vencidos
GROUP BY regional
ORDER BY pct_em_atraso DESC;


-- 5. Treinamento ajuda a vender? Correlação entre % de aprovados e % da meta atingida.
--    Técnica: CORR() e comparação de médias entre grupos.
WITH rev AS (
    SELECT revenda_id,
           1.0 * SUM(treinamento_aprovados) / NULLIF(SUM(funcionarios), 0) AS pct_treinamento,
           1.0 * SUM(volume) / NULLIF(SUM(meta_volume), 0) AS pct_meta
    FROM vw_kpi_mensal
    WHERE mes_fechado
    GROUP BY 1
)
SELECT ROUND(CORR(pct_treinamento, pct_meta)::numeric, 3) AS correlacao,
       ROUND(100 * AVG(pct_meta) FILTER (WHERE pct_treinamento >= 0.8), 1) AS pct_meta_bem_treinadas,
       ROUND(100 * AVG(pct_meta) FILTER (WHERE pct_treinamento < 0.6), 1) AS pct_meta_mal_treinadas
FROM rev;


-- 6. Ranking de consultores: quem tem mais revendas em risco em outubro, em número e em proporção da carteira.
--    Técnica: RANK() sobre uma agregação; NULLIF para evitar divisão por zero.
SELECT consultor, regional,
       COUNT(*) AS revendas,
       COUNT(*) FILTER (WHERE status_meta = '4. Em risco') AS em_risco,
       ROUND(100.0 * COUNT(*) FILTER (WHERE status_meta = '4. Em risco') / COUNT(*), 0) AS pct_em_risco,
       SUM(falta_projetada) AS unidades_que_vao_faltar,
       RANK() OVER (ORDER BY SUM(falta_projetada) DESC) AS prioridade
FROM vw_projecao_mes_atual
GROUP BY consultor, regional
ORDER BY prioridade
LIMIT 10;


-- 7. Média móvel de 3 meses do % da meta por regional (tira o ruído mês a mês).
--    Técnica: AVG() OVER com janela ROWS BETWEEN.
WITH reg AS (
    SELECT regional, mes, 1.0 * SUM(volume) / SUM(meta_volume) AS pct_meta
    FROM vw_kpi_mensal
    WHERE mes_fechado
    GROUP BY 1, 2
)
SELECT regional, to_char(mes, 'MM/YYYY') AS mes,
       ROUND(100 * pct_meta, 1) AS pct_meta,
       ROUND(100 * AVG(pct_meta) OVER (PARTITION BY regional ORDER BY mes
                                       ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1) AS media_movel_3m
FROM reg
WHERE regional IN ('Pará', 'SP Capital')
ORDER BY regional, mes;
