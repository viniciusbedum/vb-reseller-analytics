# Configuração do Superset para rodar localmente (demonstração).
# Em produção: SECRET_KEY forte vinda de variável de ambiente, HTTPS e usuário de banco somente leitura.
import os

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "troque-esta-chave-em-producao")

# Metadados do Superset (usuários, gráficos, dashboards) ficam no mesmo Postgres, num banco separado
SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://superset:superset@db:5432/superset"

# Números no padrão brasileiro: 1.234,5 e R$
D3_FORMAT = {
    "decimal": ",",
    "thousands": ".",
    "grouping": [3],
    "currency": ["R$ ", ""],
}

FEATURE_FLAGS = {
    "DASHBOARD_CROSS_FILTERS": True,
}

# Sem cabeçalhos de segurança estritos: o acesso é só local
TALISMAN_ENABLED = False
