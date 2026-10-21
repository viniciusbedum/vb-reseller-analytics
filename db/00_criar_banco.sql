-- Roda uma única vez, na primeira inicialização do Postgres (docker-entrypoint-initdb.d).
-- O banco "superset" guarda os metadados do Superset; o banco "revendas" guarda os dados analisados.
CREATE ROLE analista LOGIN PASSWORD 'analista';
CREATE DATABASE revendas OWNER analista;
