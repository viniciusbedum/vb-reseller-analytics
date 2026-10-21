"""Gera dados fictícios (mas coerentes) de uma rede de 300 revendas ao longo de 2026.

Chamado por setup/run.py. Os dados são determinísticos (seed fixa): rodar de novo gera exatamente o mesmo banco.
"""

import calendar
import os
import random
from datetime import date, timedelta

import psycopg2
from psycopg2.extras import execute_values

DSN = os.environ.get("DADOS_DSN", "host=db dbname=revendas user=analista password=analista")
DATA_REF = date(2026, 10, 20)  # último dia com dados ("ontem" da simulação)
INICIO = date(2026, 1, 1)

# Sazonalidade: o produto vende mais no inverno
SAZONALIDADE = {1: 0.95, 2: 0.93, 3: 0.97, 4: 0.98, 5: 1.03, 6: 1.10,
                7: 1.15, 8: 1.12, 9: 1.02, 10: 1.00, 11: 0.98, 12: 1.00}

# (diretoria, regional, uf, cidades, efeito_volume, risco_inadimplencia, lentidao_padronizacao)
# Os efeitos criam uma "história" para os gráficos contarem:
#   Pará e Ceará vendem bem abaixo da meta, Bahia/RS/DF ligeiramente abaixo; Rio Grande do Sul tem problema de inadimplência;
#   o Nordeste demora mais na padronização.
REGIONAIS = [
    ("Diretoria Sul/Sudeste", "SP Capital", "SP", ["São Paulo", "Guarulhos", "Osasco"], 1.05, 0.025, 1.0),
    ("Diretoria Sul/Sudeste", "SP Interior", "SP", ["Campinas", "Ribeirão Preto", "Sorocaba"], 1.00, 0.025, 1.0),
    ("Diretoria Sul/Sudeste", "Paraná", "PR", ["Curitiba", "Londrina", "Maringá"], 0.98, 0.03, 0.9),
    ("Diretoria Sul/Sudeste", "Rio Grande do Sul", "RS", ["Porto Alegre", "Caxias do Sul", "Pelotas"], 0.96, 0.15, 1.0),
    ("Diretoria Centro-Oeste/Norte", "Goiás", "GO", ["Goiânia", "Anápolis", "Rio Verde"], 1.03, 0.03, 1.1),
    ("Diretoria Centro-Oeste/Norte", "Distrito Federal", "DF", ["Brasília", "Taguatinga", "Ceilândia"], 0.97, 0.03, 1.0),
    ("Diretoria Centro-Oeste/Norte", "Pará", "PA", ["Belém", "Ananindeua", "Santarém"], 0.88, 0.035, 1.3),
    ("Diretoria Nordeste", "Bahia", "BA", ["Salvador", "Feira de Santana", "Vitória da Conquista"], 0.95, 0.03, 1.5),
    ("Diretoria Nordeste", "Pernambuco", "PE", ["Recife", "Olinda", "Caruaru"], 1.01, 0.03, 1.4),
    ("Diretoria Nordeste", "Ceará", "CE", ["Fortaleza", "Caucaia", "Juazeiro do Norte"], 0.90, 0.035, 1.6),
]

NOMES = ["Ana", "Bruno", "Carla", "Diego", "Eduarda", "Felipe", "Gabriela", "Henrique", "Isabela", "João",
         "Juliana", "Lucas", "Mariana", "Nicolas", "Patrícia", "Rafael", "Sabrina", "Thiago", "Vanessa", "Wesley",
         "Aline", "Caio", "Débora", "Fábio", "Larissa", "Marcos", "Natália", "Otávio", "Priscila", "Renato"]
SOBRENOMES = ["Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira", "Costa", "Rodrigues", "Almeida", "Nascimento",
              "Ferreira", "Araújo", "Ribeiro", "Carvalho", "Gomes", "Martins", "Rocha", "Barbosa", "Melo", "Cardoso"]
BAIRROS = ["Centro", "Jardim América", "Vila Nova", "São José", "Boa Vista", "Santa Cruz", "Primavera",
           "Industrial", "Bela Vista", "Esperança", "Liberdade", "Alvorada", "Planalto", "Progresso"]
GRUPOS = ["Grupo Horizonte", "Grupo Aliança", "Rede Pioneira", "Grupo Vale Norte", "Rede União",
          "Grupo Atlântico", "Rede Serra Verde", "Grupo Ômega"]
TREINAMENTOS = ["Segurança no ambiente de trabalho", "Direção defensiva nas entregas",
                "Atendimento ao consumidor", "Regras do Programa Parceiros 2026", "Exposição de produtos no ponto de venda",
                "Venda consultiva no balcão", "Técnicas de oferta no balcão",
                "Primeiros socorros", "Gestão de estoque", "Como orientar o cliente no uso do produto"]
ETAPAS = [(1, "Solicitada", 3), (2, "Vistoria", 7), (3, "Orçamento aprovado", 5),
          (4, "Em execução", 20), (5, "Concluída", None)]


def pessoa():
    return f"{random.choice(NOMES)} {random.choice(SOBRENOMES)}"


def meses():
    m = INICIO
    while m <= DATA_REF:
        yield m
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)


def gerar(conn):
    random.seed(42)
    cur = conn.cursor()
    cur.execute("SET search_path TO rede")
    cur.execute("INSERT INTO parametros VALUES (%s)", (DATA_REF,))

    # ------------------------------------------------------------ hierarquia
    dir_ids = {}
    revendas = []  # dicts com perfil de comportamento
    for dir_nome, reg_nome, uf, cidades, ef_vol, risco, lentidao in REGIONAIS:
        if dir_nome not in dir_ids:
            cur.execute("INSERT INTO diretoria (nome) VALUES (%s) RETURNING id", (dir_nome,))
            dir_ids[dir_nome] = cur.fetchone()[0]
        cur.execute("INSERT INTO regional (diretoria_id, nome, uf) VALUES (%s, %s, %s) RETURNING id",
                    (dir_ids[dir_nome], reg_nome, uf))
        reg_id = cur.fetchone()[0]
        for n in range(1, 4):
            cur.execute("INSERT INTO carteira (regional_id, nome, consultor) VALUES (%s, %s, %s) RETURNING id",
                        (reg_id, f"Carteira {uf}-{n:02d}", pessoa()))
            cart_id = cur.fetchone()[0]
            for _ in range(10):
                revendas.append(dict(carteira_id=cart_id, uf=uf, regional=reg_nome, cidade=random.choice(cidades),
                                     ef_vol=ef_vol, risco=risco, lentidao=lentidao))

    for nome in GRUPOS:
        cur.execute("INSERT INTO grupo (nome) VALUES (%s)", (nome,))

    for i, r in enumerate(revendas, start=1):
        tipo = random.choices(["Loja de bairro", "Posto", "Supermercado"], [0.65, 0.2, 0.15])[0]
        base = {"Loja de bairro": (300, 1400), "Posto": (120, 500), "Supermercado": (200, 800)}[tipo]
        freq = {"Loja de bairro": (5, 10), "Posto": (2, 5), "Supermercado": (3, 6)}[tipo]
        sobrenome = random.choice(SOBRENOMES)
        nome = {"Loja de bairro": random.choice([f"Comercial {sobrenome}", f"Depósito {random.choice(BAIRROS)}",
                                              f"Empório {random.choice(NOMES)}"]),
                "Posto": f"Posto {random.choice(BAIRROS)}",
                "Supermercado": f"Supermercado {sobrenome}"}[tipo]
        r.update(
            id=i, tipo=tipo, nome=f"{nome} ({r['cidade']})",
            marca=random.choices(["Marca Azul", "Marca Laranja"], [0.55, 0.45])[0],
            grupo_id=random.randint(1, len(GRUPOS)) if random.random() < 0.3 else None,
            base=random.randint(*base),
            freq=random.uniform(*freq),
            desempenho=random.gauss(1.0, 0.07) * r["ef_vol"],
            tendencia=random.gauss(0, 0.008),
            inad=r["risco"] * random.uniform(0.2, 1.8),
            engajamento=random.betavariate(9, 2),
        )
        cnpj = f"{random.randint(10, 99)}.{random.randint(100, 999)}.{random.randint(100, 999)}/0001-{random.randint(10, 99)}"
        cur.execute(
            "INSERT INTO revenda (id, carteira_id, grupo_id, nome, cnpj, marca, tipo, cidade) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (i, r["carteira_id"], r["grupo_id"], r["nome"], cnpj, r["marca"], r["tipo"], r["cidade"]))
    cur.execute("SELECT setval('revenda_id_seq', (SELECT MAX(id) FROM revenda))")

    # ------------------------------------------------------------ metas e pedidos
    # oscilação de cada regional mês a mês (mês bom, mês ruim), além do efeito fixo da regional
    oscilacao = {(reg[1], mes.month): random.gauss(1, 0.05) for reg in REGIONAIS for mes in meses()}
    metas, pedidos = [], []
    for r in revendas:
        for idx, mes in enumerate(meses()):
            saz = SAZONALIDADE[mes.month]
            meta_vol = int(round(r["base"] * saz / 10) * 10)
            meta_rec = max(2, round(r["freq"] * 0.85))
            metas.append((r["id"], mes, meta_vol, meta_rec, 5.0))

            dias_mes = calendar.monthrange(mes.year, mes.month)[1]
            alvo = (r["base"] * saz * r["desempenho"] * oscilacao[(r["regional"], mes.month)]
                    * (1 + r["tendencia"] * idx) * random.gauss(1, 0.06))
            n_pedidos = max(1, round(random.gauss(r["freq"], 1.2)))
            dias = sorted(random.sample(range(1, dias_mes + 1), min(n_pedidos, dias_mes)))
            for d in dias:
                dia = date(mes.year, mes.month, d)
                if dia > DATA_REF:
                    continue
                qtd = max(5, int(alvo / len(dias) * random.uniform(0.7, 1.3)))
                valor = round(qtd * random.uniform(82, 92), 2)
                venc = dia + timedelta(days=28)
                if random.random() < r["inad"]:
                    pago = venc + timedelta(days=random.randint(8, 75))
                else:
                    pago = venc + timedelta(days=random.randint(-6, 3))
                if pago > DATA_REF:
                    pago = None
                pedidos.append((r["id"], dia, qtd, valor, venc, pago))

    execute_values(cur, "INSERT INTO meta_mensal VALUES %s", metas)
    execute_values(cur, "INSERT INTO pedido (revenda_id, data, quantidade, valor, vencimento, data_pagamento) VALUES %s",
                   pedidos, page_size=5000)

    # ------------------------------------------------------------ treinamentos
    trein_ids = []
    for idx, mes in enumerate(meses()):
        cur.execute("INSERT INTO treinamento (mes, titulo) VALUES (%s, %s) RETURNING id", (mes, TREINAMENTOS[idx]))
        trein_ids.append((cur.fetchone()[0], mes))

    respostas = []
    for r in revendas:
        n_func = {"Loja de bairro": (2, 6), "Posto": (3, 9), "Supermercado": (4, 10)}[r["tipo"]]
        cargos = ["Gerente", "Atendente", "Entregador", "Entregador", "Atendente", "Caixa"]
        for k in range(random.randint(*n_func)):
            cur.execute("INSERT INTO funcionario (revenda_id, nome, cargo) VALUES (%s, %s, %s) RETURNING id",
                        (r["id"], pessoa(), cargos[k % len(cargos)]))
            func_id = cur.fetchone()[0]
            prob = min(0.99, r["engajamento"] * random.uniform(0.85, 1.15))
            for t_id, mes in trein_ids:
                dias_mes = calendar.monthrange(mes.year, mes.month)[1]
                if random.random() > prob:
                    continue
                dia = date(mes.year, mes.month, random.randint(1, dias_mes))
                if dia > DATA_REF:
                    continue
                acertos = min(10, max(3, round(random.gauss(8, 1.4))))
                respostas.append((func_id, t_id, dia, acertos, 10))
    execute_values(cur, "INSERT INTO treinamento_resposta VALUES %s", respostas, page_size=5000)

    # ------------------------------------------------------------ padronização
    execute_values(cur, "INSERT INTO padronizacao_etapa VALUES %s", ETAPAS)
    historico = []
    for r in random.sample(revendas, 140):
        # mais solicitações recentes que antigas
        abertura = DATA_REF - timedelta(days=3 + int(random.betavariate(1, 1.6) * ((DATA_REF - INICIO).days - 3)))
        tipo = random.choice(["Fachada", "Pintura", "Frota", "Comunicação visual"])
        cur.execute("INSERT INTO padronizacao (revenda_id, tipo, data_abertura) VALUES (%s, %s, %s) RETURNING id",
                    (r["id"], tipo, abertura))
        pad_id = cur.fetchone()[0]
        inicio = abertura
        for ordem, _, sla in ETAPAS:
            if sla is None:
                historico.append((pad_id, ordem, inicio, None))
                break
            dur = max(1, round(random.expovariate(1 / (sla * 1.1 * r["lentidao"]))))
            fim = inicio + timedelta(days=dur)
            if fim > DATA_REF:
                historico.append((pad_id, ordem, inicio, None))
                break
            historico.append((pad_id, ordem, inicio, fim))
            inicio = fim
    execute_values(cur, "INSERT INTO padronizacao_historico VALUES %s", historico)

    conn.commit()
    print(f"revendas={len(revendas)} metas={len(metas)} pedidos={len(pedidos)} "
          f"respostas_treinamento={len(respostas)} etapas_padronizacao={len(historico)}")


if __name__ == "__main__":
    gerar(psycopg2.connect(DSN))
