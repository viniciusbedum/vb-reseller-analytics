-- Tabelas "brutas", no formato em que viriam do sistema transacional da distribuidora.
-- Os indicadores ficam nas views (03_views.sql); o Superset só lê as views.

DROP SCHEMA IF EXISTS rede CASCADE;
CREATE SCHEMA rede;
SET search_path TO rede;

-- Data de corte dos dados ("hoje" da simulação). As views usam isso em vez de CURRENT_DATE
-- para que os números não mudem sozinhos de um dia para o outro.
CREATE TABLE parametros (data_referencia date NOT NULL);

-- ---------------------------------------------------------------- hierarquia comercial
CREATE TABLE diretoria (
    id serial PRIMARY KEY,
    nome text NOT NULL
);

CREATE TABLE regional (
    id serial PRIMARY KEY,
    diretoria_id int NOT NULL REFERENCES diretoria(id),
    nome text NOT NULL,
    uf char(2) NOT NULL
);

CREATE TABLE carteira (
    id serial PRIMARY KEY,
    regional_id int NOT NULL REFERENCES regional(id),
    nome text NOT NULL,
    consultor text NOT NULL
);

CREATE TABLE grupo (
    id serial PRIMARY KEY,
    nome text NOT NULL
);

CREATE TABLE revenda (
    id serial PRIMARY KEY,
    carteira_id int NOT NULL REFERENCES carteira(id),
    grupo_id int REFERENCES grupo(id),
    nome text NOT NULL,
    cnpj text NOT NULL,
    marca text NOT NULL,          -- Marca Azul | Marca Laranja
    tipo text NOT NULL,           -- Loja de bairro | Posto | Supermercado
    cidade text NOT NULL
);

-- ---------------------------------------------------------------- vendas (revenda compra da distribuidora)
CREATE TABLE pedido (
    id serial PRIMARY KEY,
    revenda_id int NOT NULL REFERENCES revenda(id),
    data date NOT NULL,
    quantidade int NOT NULL,      -- unidades
    valor numeric(12,2) NOT NULL,
    vencimento date NOT NULL,
    data_pagamento date           -- NULL = ainda não pago
);
CREATE INDEX ON pedido (revenda_id, data);
CREATE INDEX ON pedido (vencimento);

CREATE TABLE meta_mensal (
    revenda_id int NOT NULL REFERENCES revenda(id),
    mes date NOT NULL,
    meta_volume int NOT NULL,             -- unidades no mês
    meta_recorrencia int NOT NULL,        -- nº mínimo de pedidos no mês
    meta_inadimplencia_max numeric(5,2) NOT NULL, -- % máximo de valor vencido em atraso
    PRIMARY KEY (revenda_id, mes)
);

-- ---------------------------------------------------------------- treinamentos mensais
CREATE TABLE funcionario (
    id serial PRIMARY KEY,
    revenda_id int NOT NULL REFERENCES revenda(id),
    nome text NOT NULL,
    cargo text NOT NULL
);

CREATE TABLE treinamento (
    id serial PRIMARY KEY,
    mes date NOT NULL,
    titulo text NOT NULL
);

CREATE TABLE treinamento_resposta (
    funcionario_id int NOT NULL REFERENCES funcionario(id),
    treinamento_id int NOT NULL REFERENCES treinamento(id),
    data_conclusao date NOT NULL,
    acertos int NOT NULL,
    total_questoes int NOT NULL,
    PRIMARY KEY (funcionario_id, treinamento_id)
);

-- ---------------------------------------------------------------- padronização visual da loja
CREATE TABLE padronizacao_etapa (
    ordem int PRIMARY KEY,
    nome text NOT NULL,
    sla_dias int                  -- NULL para a etapa final
);

CREATE TABLE padronizacao (
    id serial PRIMARY KEY,
    revenda_id int NOT NULL REFERENCES revenda(id),
    tipo text NOT NULL,           -- Fachada | Pintura | Frota | Comunicação visual
    data_abertura date NOT NULL
);

CREATE TABLE padronizacao_historico (
    padronizacao_id int NOT NULL REFERENCES padronizacao(id),
    etapa_ordem int NOT NULL REFERENCES padronizacao_etapa(ordem),
    data_inicio date NOT NULL,
    data_fim date,                -- NULL = etapa atual
    PRIMARY KEY (padronizacao_id, etapa_ordem)
);
