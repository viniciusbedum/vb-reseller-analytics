"""Carrega o banco de dados fictício e monta o dashboard no Superset.

Roda no container "setup" do docker-compose, depois que o Postgres e o Superset estão de pé.
Na primeira vez cria tabelas, dados e views; nas seguintes só atualiza as views e o dashboard
(RECRIAR_DADOS=1 força a recriação dos dados).
"""

import importlib
import os
import sys
from pathlib import Path

import psycopg2

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "db"), str(RAIZ / "setup")]

gerar_dados = importlib.import_module("02_gerar_dados")
montar_dashboard = importlib.import_module("montar_dashboard")


def executar_sql(conn, arquivo):
    with conn.cursor() as cur:
        cur.execute((RAIZ / "db" / arquivo).read_text())
    conn.commit()


def dados_carregados(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('rede.parametros') IS NOT NULL")
        return cur.fetchone()[0]


def main():
    conn = psycopg2.connect(gerar_dados.DSN)
    if os.environ.get("RECRIAR_DADOS") == "1" or not dados_carregados(conn):
        print("criando tabelas e gerando dados fictícios...", flush=True)
        executar_sql(conn, "01_schema.sql")
        gerar_dados.gerar(conn)
    print("criando views de indicadores...", flush=True)
    executar_sql(conn, "03_views.sql")
    print("montando dashboard no Superset...", flush=True)
    montar_dashboard.main()


if __name__ == "__main__":
    main()
