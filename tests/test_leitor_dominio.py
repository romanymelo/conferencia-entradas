from datetime import date
from decimal import Decimal
import pytest
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from conferencia.leitor_dominio import e_dominio, le_cabecalho, le_dominio, parse_linha

BASE = ("775 01/09/2026 01/09/2026 1004582 1 36 6 FORNECEDOR TESTE LTDA "
        "11.222.333/0001-44 240000015 1-102 101 AL 52,10 ICMS "
        "0,00 0,00 0,00 0,00 0,00 0,00 52,10")

def test_e_dominio_reconhece_o_cabecalho():
    assert e_dominio("ACOMPANHAMENTO DE ENTRADAS")

def test_e_dominio_rejeita_sefaz():
    assert not e_dominio("SECRETARIA DE ESTADO DA FAZENDA DE ALAGOAS")

def test_le_cabecalho():
    texto = ("101 - FARMACIA MODELO LTDA\n"
             "CNPJ: 12.345.678/0001-95\n"
             "Período: 01/09/2026 até 30/09/2026\n")
    c = le_cabecalho(texto)
    assert c.codigo == "101"
    assert c.cnpj == "12345678000195"
    assert c.razao_social == "FARMACIA MODELO LTDA"
    assert (c.periodo_inicio, c.periodo_fim) == (date(2026, 9, 1), date(2026, 9, 30))

def test_parse_linha_extrai_todos_os_campos():
    l = parse_linha(BASE)
    assert l.cnpj_emitente == "11222333000144"
    assert l.nome_emitente == "FORNECEDOR TESTE LTDA"
    assert l.numero == 1004582
    assert l.serie == "1"
    assert l.especie == 36
    assert l.data_emissao == date(2026, 9, 1)
    assert l.data_entrada == date(2026, 9, 1)
    assert l.valor_contabil == Decimal("49.16")

def test_parse_linha_descarta_o_um_solto_da_listra_zebrada():
    assert parse_linha("1 " + BASE) == parse_linha(BASE)

def test_parse_linha_le_datas_de_emissao_e_entrada_distintas():
    texto = BASE.replace("775 01/09/2026 01/09/2026", "197 31/08/2026 01/09/2026", 1)
    l = parse_linha(texto)
    assert l.data_emissao == date(2026, 8, 31)
    assert l.data_entrada == date(2026, 9, 1)

def test_parse_linha_aceita_serie_zero():
    texto = BASE.replace("1004582 1 36", "300215 0 36", 1)
    assert parse_linha(texto).serie == "0"

def test_parse_linha_aceita_valor_contabil_zerado():
    texto = BASE.replace("AL 52,10 ICMS", "AL 0,00 ICMS", 1)
    assert parse_linha(texto).valor_contabil == Decimal("0.00")

def test_parse_linha_le_especie_fora_de_nfe_sem_coluna_tipo():
    # servico: sem serie, sem "ICMS" na coluna Tipo (leitura A: 7421 | 39 | cod. fornecedor 42)
    texto = ("926 01/09/2026 01/09/2026 7421 39 42 SUPER TESTE LTDA "
             "30.306.294/0001-45 1-933 106 AL 152,00 0,00 0,00 0,00 0,00 0,00")
    l = parse_linha(texto)
    assert l.numero == 7421
    assert l.serie == ""
    assert l.especie == 39
    assert l.nome_emitente == "SUPER TESTE LTDA"
    assert l.valor_contabil == Decimal("152.00")

@pytest.mark.parametrize("texto", [
    "Total Série",
    "1Total Série",
    "Total Geral",
    "Código Data Emissão Data Entrada Nota Série Espécie Código Fornecedor",
    "Sistema licenciado para EMPRESA EXEMPLO LTDA - ME",
    "",
])
def test_parse_linha_ignora_linha_que_nao_e_dado(texto):
    assert parse_linha(texto) is None

@pytest.mark.parametrize("texto", [
    "775 01/09/2026 01/09/2026 1004582 1 36 6 SEM CNPJ LTDA 240000015 1-102 101 AL 52,10",
    BASE.split(" AL ")[0],
    # nome comecando por digitos: 5 numericos seguidos, nao adivinha
    BASE.replace("FORNECEDOR TESTE", "2000 DISTRIBUIDORA", 1),
    # 2 numericos antes do nome
    BASE.replace("1004582 1 36 6", "1004582 36", 1),
])
def test_parse_linha_de_dados_fora_do_layout_levanta(texto):
    with pytest.raises(ValueError):
        parse_linha(texto)


# --- le_dominio: PDF fabricado com reportlab ---

def _gera_pdf(caminho, paginas):
    c = canvas.Canvas(str(caminho), pagesize=landscape(A4))
    for linhas in paginas:
        y = 550
        for texto in linhas:
            c.drawString(20, y, texto)
            y -= 15
        c.showPage()
    c.save()


CABECALHO = [
    "ACOMPANHAMENTO DE ENTRADAS",
    "101 - FARMACIA MODELO LTDA",
    "CNPJ: 12.345.678/0001-95",
    "Período: 01/09/2026 até 30/09/2026",
]


def test_le_dominio_le_paginas_inclusive_sem_dados_e_multipagina(tmp_path):
    pdf = tmp_path / "dominio.pdf"
    outra = BASE.replace("1004582", "1004583", 1).replace("AL 52,10", "AL 10,00", 1)
    _gera_pdf(pdf, [
        CABECALHO + [BASE, outra],
        ["Total Série", "Total Geral", "Sistema licenciado para TESTE"],
        [BASE, "Total Série"],
    ])
    cab, lancs = le_dominio(pdf)
    assert cab.codigo == "101"
    assert cab.cnpj == "12345678000195"
    assert [l.numero for l in lancs] == [1004582, 1004583, 1004582]
    assert [l.valor_contabil for l in lancs] == [Decimal("49.16"), Decimal("10.00"), Decimal("49.16")]


def test_le_dominio_levanta_em_linha_de_dados_invalida(tmp_path):
    pdf = tmp_path / "dominio.pdf"
    _gera_pdf(pdf, [CABECALHO + [BASE.replace("11.222.333/0001-44", "", 1)]])
    with pytest.raises(ValueError):
        le_dominio(pdf)
