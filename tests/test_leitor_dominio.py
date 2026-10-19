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
    assert l.valor_contabil == Decimal("52.10")

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
             "30.306.294/0001-45 1-933 106 AL 140,00 0,00 0,00 0,00 0,00 0,00")
    l = parse_linha(texto)
    assert l.numero == 7421
    assert l.serie == ""
    assert l.especie == 39
    assert l.nome_emitente == "SUPER TESTE LTDA"
    assert l.valor_contabil == Decimal("140.00")

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
        ["Total Série", "Sistema licenciado para TESTE"],
        [BASE, "Total Série", "Total Geral", "114,20 ICMS 0,00"],
    ])
    cab, lancs = le_dominio(pdf)
    assert cab.codigo == "101"
    assert cab.cnpj == "12345678000195"
    assert [l.numero for l in lancs] == [1004582, 1004583, 1004582]
    assert [l.valor_contabil for l in lancs] == [Decimal("52.10"), Decimal("10.00"), Decimal("52.10")]


def test_le_dominio_levanta_em_linha_de_dados_invalida(tmp_path):
    pdf = tmp_path / "dominio.pdf"
    _gera_pdf(pdf, [CABECALHO + [BASE.replace("11.222.333/0001-44", "", 1)]])
    with pytest.raises(ValueError):
        le_dominio(pdf)


# --- reconciliacao contra o Total Geral ---

OUTRA = BASE.replace("1004582", "1004583", 1).replace("AL 52,10", "AL 10,00", 1)


def test_parse_linha_aceita_ancora_cpf_de_produtor_rural():
    texto = BASE.replace("11.222.333/0001-44", "123.456.789-00", 1)
    assert parse_linha(texto).cnpj_emitente == "00012345678900"


def test_parse_linha_levanta_com_duas_linhas_de_dados_na_mesma_linha_de_texto():
    # mecanismo 3: a 2a linha completa seria tratada como "cauda" de colunas e sumiria
    with pytest.raises(ValueError, match="mais de um CNPJ/CPF"):
        parse_linha(BASE + " " + OUTRA)


def test_le_dominio_bem_formado_reconcilia_com_o_total_geral(tmp_path):
    pdf = tmp_path / "dominio.pdf"
    _gera_pdf(pdf, [CABECALHO + [BASE, OUTRA, "Total Geral", "62,10 ICMS 0,00"]])
    _, lancs = le_dominio(pdf)
    assert len(lancs) == 2


def test_le_dominio_levanta_quando_uma_linha_de_dados_nao_e_reconhecida(tmp_path):
    # codigo grudado na data: a linha nao casa com o inicio de dado e sumiria sem erro
    pdf = tmp_path / "dominio.pdf"
    ilegivel = OUTRA.replace("775 01/09/2026", "77501/09/2026", 1)
    _gera_pdf(pdf, [CABECALHO + [BASE, ilegivel, "Total Geral", "62,10 ICMS 0,00"]])
    with pytest.raises(ValueError, match="Total Geral"):
        le_dominio(pdf)


def test_le_dominio_sem_lancamentos_com_total_geral_zerado_e_lido_com_sucesso(tmp_path):
    pdf = tmp_path / "dominio.pdf"
    _gera_pdf(pdf, [CABECALHO + ["Total Geral", "0,00 ICMS 0,00"]])
    assert le_dominio(pdf)[1] == []


def test_le_dominio_levanta_quando_total_geral_declara_valor_e_nada_foi_lido(tmp_path):
    pdf = tmp_path / "dominio.pdf"
    _gera_pdf(pdf, [CABECALHO + ["Total Geral", "128.450,60 ICMS 0,00"]])
    with pytest.raises(ValueError, match="Total Geral"):
        le_dominio(pdf)


def test_le_dominio_levanta_sem_total_geral(tmp_path):
    pdf = tmp_path / "dominio.pdf"
    _gera_pdf(pdf, [CABECALHO + [BASE]])
    with pytest.raises(ValueError, match="Total Geral"):
        le_dominio(pdf)


def test_le_cabecalho_tira_o_campo_de_pagina_da_razao_social():
    # linha real: o 'Página: 0001' do canto direito vem na mesma linha da razão social
    texto = ("101 - FARMACIA MODELO LTDA Página: 0001\n"
             "CNPJ: 12.345.678/0001-95 Emissão: 18/10/2026\n"
             "Período: 01/08/2026 até 31/08/2026\n")
    assert le_cabecalho(texto).razao_social == "FARMACIA MODELO LTDA"


@pytest.mark.parametrize("texto", [
    "CNPJ: 12.345.678/0001-95 Emissão: 18/10/2026",   # cabeçalho com âncora de CNPJ
    "1 CRF 0,00 20,08 0,00 0,00 0,00 0,00",           # tipo de linha de rodapé nunca visto
])
def test_parse_linha_linhas_reais_que_nao_sao_dado_retornam_none(texto):
    assert parse_linha(texto) is None


def test_total_geral_com_o_valor_na_linha_seguinte_colado_ao_icms(tmp_path):
    # layout real: rótulo com o '1' da zebra, valor contábil na linha de baixo
    pdf = tmp_path / "d.pdf"
    _gera_pdf(pdf, [CABECALHO + [BASE, "1Total Geral", "52,10ICMS 0,00 0,00 0,00 0,00 0,00 52,10",
                                 "1 CRF 0,00 20,08 0,00 0,00 0,00 0,00"]])
    assert len(le_dominio(pdf)[1]) == 1


def test_le_dominio_separa_nome_longo_que_invade_a_coluna_do_cnpj(tmp_path):
    # no PDF real o nome do fornecedor se sobrepõe ao CNPJ; o texto extraído sai embaralhado
    # ('29GAMA COM SERV4 3D.I2S1T4R...'). Cada célula é desenhada à parte, sem sobreposição
    # de caracteres dentro dela: a leitura deve seguir as células, não o texto.
    pdf = tmp_path / "d.pdf"
    c = canvas.Canvas(str(pdf), pagesize=landscape(A4))
    for y, texto in zip((550, 535, 520, 505), CABECALHO):
        c.drawString(20, y, texto)
    y = 480
    for x, texto in [(20, "318"), (60, "29/08/2026"), (140, "29/08/2026"), (220, "1007733"),
                     (280, "36"), (300, "29"), (320, "GAMA COM SERV DISTR SA"),
                     (350, "61.198.164/0039-32"), (440, "240000023"), (520, "1-102"),
                     (560, "101"), (575, "AL"), (600, "715,30"), (650, "ICMS")]:
        c.drawString(x, y, texto)
    c.drawString(20, 450, "Total Geral")
    c.drawString(20, 435, "715,30")
    c.showPage()
    c.save()
    [l] = le_dominio(pdf)[1]
    assert (l.cnpj_emitente, l.numero, l.especie, l.valor_contabil) == (
        "61198164003932", 1007733, 36, Decimal("715.30"))


def test_le_cabecalho_levanta_com_cnpj_vazio_em_vez_de_zeros():
    texto = ("101 - FARMACIA MODELO LTDA\nCNPJ:\n"
             "Período: 01/09/2026 até 30/09/2026\n")
    with pytest.raises(ValueError):
        le_cabecalho(texto)


def test_le_dominio_em_formato_us_le_corretamente_e_avisa_uma_vez(tmp_path, caplog):
    import logging
    pdf = tmp_path / "dominio_us.pdf"
    us = BASE.replace("52,10", "1,052.10")
    _gera_pdf(pdf, [CABECALHO + [us, us], ["1Total Geral", "2,104.20ICMS 0.00 0.00"]])
    with caplog.at_level(logging.WARNING):
        _, lancs = le_dominio(pdf)
    assert [l.valor_contabil for l in lancs] == [Decimal("1052.10")] * 2
    avisos = [r for r in caplog.records if r.levelno == logging.WARNING and "formato numérico" in r.getMessage()]
    assert len(avisos) == 1
    msg = avisos[0].getMessage()
    assert "esperado 1.234,56 e encontrado 1,234.56" in msg and "Domínio" in msg and "dominio_us.pdf" in msg


def test_le_dominio_em_formato_br_nao_avisa_formato(tmp_path, caplog):
    import logging
    pdf = tmp_path / "dominio.pdf"
    _gera_pdf(pdf, [CABECALHO + [BASE, "Total Geral", "52,10 ICMS 0,00"]])
    with caplog.at_level(logging.WARNING):
        le_dominio(pdf)
    assert not [r for r in caplog.records if "formato numérico" in r.getMessage()]
