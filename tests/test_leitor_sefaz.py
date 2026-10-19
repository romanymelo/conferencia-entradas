import logging
from datetime import date
from decimal import Decimal
import pytest
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from conferencia.leitor_sefaz import (
    decompoe_chave, e_sefaz, le_cabecalho, le_sefaz, parse_linha,
)


def palavras(*textos):
    """Simula page.extract_words(): uma palavra por item, x crescente."""
    return [{"text": t, "x0": i * 10.0, "x1": i * 10.0 + 5.0} for i, t in enumerate(textos)]


LINHA = palavras(
    "01/09/2026", "08:52:43", "11.222.333/0001-44", "FORNECEDOR", "TESTE", "LTDA",
    "1", "/", "1004582", "2" * 44, "Saída", "Ativa", "192.40",
)


def test_e_sefaz_reconhece_o_cabecalho():
    assert e_sefaz("SECRETARIA DE ESTADO DA FAZENDA DE ALAGOAS\nNotas Fiscais de Entrada")


def test_e_sefaz_rejeita_dominio():
    assert not e_sefaz("ACOMPANHAMENTO DE ENTRADAS")


def test_le_cabecalho():
    texto = (
        "Período: 01/09/2026 - 30/09/2026\n"
        "CNPJ: 12.345.678/0001-95\n"
        "Razão Social: FARMACIA MODELO LTDA\n"
    )
    c = le_cabecalho(texto)
    assert c.codigo is None
    assert c.cnpj == "12345678000195"
    assert c.razao_social == "FARMACIA MODELO LTDA"
    assert (c.periodo_inicio, c.periodo_fim) == (date(2026, 9, 1), date(2026, 9, 30))


def test_parse_linha_extrai_todos_os_campos():
    n = parse_linha(LINHA)
    assert n.cnpj_emitente == "11222333000144"
    assert n.nome_emitente == "FORNECEDOR TESTE LTDA"
    assert n.serie == "1"
    assert n.numero == 1004582
    assert n.data_emissao == date(2026, 9, 1)
    assert n.chave == "2" * 44
    assert n.situacao == "Ativa"
    assert n.valor == Decimal("192.40")


def test_parse_linha_le_situacao_cancelada():
    linha = palavras(
        "01/09/2026", "08:52:43", "11.222.333/0001-44", "FORNECEDOR",
        "1", "/", "99", "3" * 44, "Saída", "Cancelada", "500.00",
    )
    assert parse_linha(linha).situacao == "Cancelada"


@pytest.mark.parametrize("texto", [
    "Quantidade de Notas: 204",
    "Emissão CNPJ/CPF Razão Social Emissor Série/Num. Chave de Acesso",
    "",
])
def test_parse_linha_ignora_linha_que_nao_e_dado(texto):
    assert parse_linha(palavras(*texto.split())) is None


def test_decompoe_chave_extrai_cnpj_serie_e_numero():
    # chave real da nota 1004582, serie 1, emitente 45.723.174/0011-92
    chave = "27260945723174001192550010010045821234567890"
    assert decompoe_chave(chave) == ("45723174001192", "1", 1004582)


def test_decompoe_chave_rejeita_tamanho_errado():
    with pytest.raises(ValueError):
        decompoe_chave("123")


# --- le_sefaz: PDF fabricado com reportlab, uma linha por nota ---

CHAVE_OK = "27260911222333000144550010000000991066378260"  # cnpj 11222333000144, serie 1, numero 99


def _gera_pdf(caminho, paginas):
    c = canvas.Canvas(str(caminho), pagesize=landscape(A4))
    for linhas in paginas:
        y = 550
        for texto in linhas:
            c.drawString(20, y, texto)
            y -= 15
        c.showPage()
    c.save()


def _linha(chave, valor="192.40"):
    return f"01/09/2026 08:52:43 11.222.333/0001-44 FORNECEDOR TESTE 1 / 99 {chave} Saída Ativa {valor}"


def _rodape(qtd, total):
    return [f"Quantidade de Notas: {qtd}", f"Valor Total: {total}"]


CABECALHO = [
    "SECRETARIA DE ESTADO DA FAZENDA DE ALAGOAS",
    "Notas Fiscais de Entrada",
    "Período: 01/09/2026 - 30/09/2026",
    "CNPJ: 12.345.678/0001-95",
    "Razão Social: FARMACIA MODELO LTDA",
]


def test_le_sefaz_le_paginas_inclusive_sem_dados_e_com_uma_nota(tmp_path):
    pdf = tmp_path / "sefaz.pdf"
    _gera_pdf(pdf, [
        CABECALHO + [_linha(CHAVE_OK), _linha(CHAVE_OK, "1,532.66")],
        ["pagina sem nenhuma linha de dados"],
        [_linha(CHAVE_OK), *_rodape(3, "1,917.46")],
    ])
    cab, notas = le_sefaz(pdf)
    assert cab.cnpj == "12345678000195"
    assert [n.valor for n in notas] == [Decimal("192.40"), Decimal("1532.66"), Decimal("192.40")]
    assert all(n.chave == CHAVE_OK for n in notas)


def test_le_sefaz_avisa_divergencia_da_chave_sem_interromper(tmp_path, caplog):
    pdf = tmp_path / "sefaz.pdf"
    chave_ruim = "9" * 44
    _gera_pdf(pdf, [CABECALHO + [_linha(chave_ruim), _linha(CHAVE_OK), *_rodape(2, "384.80")]])
    with caplog.at_level(logging.WARNING):
        _, notas = le_sefaz(pdf)
    assert len(notas) == 2
    avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(avisos) == 1 and chave_ruim in avisos[0].getMessage()


def test_parse_linha_aceita_emissor_cpf_com_14_digitos():
    linha = palavras(
        "01/09/2026", "08:52:43", "123.456.789-00", "PRODUTOR", "RURAL",
        "1", "/", "5", "4" * 44, "Saída", "Ativa", "10.00",
    )
    assert parse_linha(linha).cnpj_emitente == "00012345678900"


def test_parse_linha_rejeita_situacao_desconhecida():
    linha = palavras(
        "01/09/2026", "08:52:43", "11.222.333/0001-44", "FORNECEDOR",
        "1", "/", "5", "4" * 44, "Saída", "Ativa", "10.00",
    )
    linha[-2]["text"] = "Xyz"
    with pytest.raises(ValueError):
        parse_linha(linha)


def test_le_sefaz_agrupa_linha_com_tops_proximos_em_fronteira_de_arredondamento(tmp_path):
    from unittest.mock import MagicMock, patch
    textos = _linha(CHAVE_OK).split()
    palavras_pdf = [
        {"text": t, "x0": i * 10.0, "x1": i * 10.0 + 5.0, "top": 100.4 if i % 2 else 100.6}
        for i, t in enumerate(textos)
    ]
    pagina = MagicMock()
    pagina.extract_words.return_value = palavras_pdf
    pagina.extract_text.return_value = chr(10).join(CABECALHO + _rodape(1, "192.40"))
    pdf = MagicMock(pages=[pagina])
    pdf.__enter__.return_value = pdf
    with patch("conferencia.leitor_sefaz.pdfplumber.open", return_value=pdf):
        _, notas = le_sefaz(tmp_path / "x.pdf")
    assert len(notas) == 1


# --- reconciliacao contra o rodape (Quantidade de Notas / valor total) ---

def test_le_sefaz_bem_formado_reconcilia_com_o_rodape(tmp_path):
    pdf = tmp_path / "sefaz.pdf"
    _gera_pdf(pdf, [CABECALHO + [_linha(CHAVE_OK), _linha(CHAVE_OK, "10.00"), *_rodape(2, "202.40")]])
    _, notas = le_sefaz(pdf)
    assert len(notas) == 2


def test_le_sefaz_levanta_quando_a_chave_vem_partida_em_dois_tokens(tmp_path):
    # mecanismo 1: a linha nao tem palavra de 44 digitos e sumiria sem erro
    pdf = tmp_path / "sefaz.pdf"
    partida = _linha(CHAVE_OK[:20] + " " + CHAVE_OK[20:])
    _gera_pdf(pdf, [CABECALHO + [_linha(CHAVE_OK), partida, *_rodape(2, "384.80")]])
    with pytest.raises(ValueError, match="Quantidade de Notas"):
        le_sefaz(pdf)


def test_le_sefaz_sem_notas_com_rodape_zerado_e_lido_com_sucesso(tmp_path):
    pdf = tmp_path / "sefaz.pdf"
    _gera_pdf(pdf, [CABECALHO + _rodape(0, "0.00")])
    assert le_sefaz(pdf)[1] == []


def test_le_sefaz_levanta_quando_rodape_declara_notas_e_nenhuma_foi_lida(tmp_path):
    pdf = tmp_path / "sefaz.pdf"
    _gera_pdf(pdf, [CABECALHO + _rodape(204, "133,721.36")])
    with pytest.raises(ValueError, match="Quantidade de Notas"):
        le_sefaz(pdf)


def test_le_sefaz_levanta_quando_o_valor_total_nao_fecha(tmp_path):
    pdf = tmp_path / "sefaz.pdf"
    _gera_pdf(pdf, [CABECALHO + [_linha(CHAVE_OK), *_rodape(1, "189.64")]])
    with pytest.raises(ValueError, match="valor total"):
        le_sefaz(pdf)


def test_le_sefaz_levanta_sem_rodape(tmp_path):
    pdf = tmp_path / "sefaz.pdf"
    _gera_pdf(pdf, [CABECALHO + [_linha(CHAVE_OK)]])
    with pytest.raises(ValueError, match="rodape"):
        le_sefaz(pdf)


def _pdf_mock(palavras_pdf, texto):
    from unittest.mock import MagicMock
    pagina = MagicMock()
    pagina.extract_words.return_value = palavras_pdf
    pagina.extract_text.return_value = texto
    pdf = MagicMock(pages=[pagina])
    pdf.__enter__.return_value = pdf
    return pdf


def _palavras_em(top, textos, x_inicial=0):
    return [
        {"text": t, "x0": (x_inicial + i) * 10.0, "x1": (x_inicial + i) * 10.0 + 5.0, "top": top}
        for i, t in enumerate(textos)
    ]


def test_parse_linha_levanta_com_duas_chaves_na_mesma_linha():
    # mecanismo 2: duas notas fundidas num so cluster perderiam a segunda
    linha = palavras(*(_linha(CHAVE_OK).split() + _linha(CHAVE_OK, "70.00").split()))
    with pytest.raises(ValueError, match="mais de uma chave"):
        parse_linha(linha)


def test_le_sefaz_levanta_com_duas_linhas_fundidas_por_proximidade(tmp_path):
    from unittest.mock import patch
    a = _palavras_em(100.0, _linha(CHAVE_OK).split())
    b = _palavras_em(101.0, _linha(CHAVE_OK, "70.00").split(), x_inicial=len(a))
    pdf = _pdf_mock(a + b, chr(10).join(CABECALHO + _rodape(2, "259.63")))
    with patch("conferencia.leitor_sefaz.pdfplumber.open", return_value=pdf):
        with pytest.raises(ValueError):
            le_sefaz(tmp_path / "x.pdf")


def test_linhas_da_pagina_nao_encadeia_a_tolerancia():
    from unittest.mock import MagicMock
    from conferencia.leitor_sefaz import _linhas_da_pagina
    pagina = MagicMock()
    pagina.extract_words.return_value = [
        {"text": str(i), "x0": i * 10.0, "x1": i * 10.0 + 5.0, "top": 100.0 + 1.5 * i}
        for i in range(6)
    ]
    linhas = _linhas_da_pagina(pagina)
    assert len(linhas) > 1  # tops de 100,0 a 107,5: nao e uma linha so
    assert all(l[-1]["top"] - l[0]["top"] <= 2.0 for l in linhas)


def test_le_cabecalho_levanta_com_cnpj_vazio_em_vez_de_zeros():
    texto = (
        "Período: 01/09/2026 - 30/09/2026\n"
        "CNPJ:\n"
        "Razão Social: FARMACIA MODELO LTDA\n"
    )
    with pytest.raises(ValueError):
        le_cabecalho(texto)


def _avisos_de_formato(caplog):
    return [r for r in caplog.records if r.levelno == logging.WARNING and "formato numérico" in r.getMessage()]


def test_le_sefaz_em_formato_br_le_corretamente_e_avisa_uma_vez(tmp_path, caplog):
    pdf = tmp_path / "sefaz_br.pdf"
    _gera_pdf(pdf, [
        CABECALHO + [_linha(CHAVE_OK, "192,40"), _linha(CHAVE_OK, "1.532,66")],
        [_linha(CHAVE_OK, "192,40"), *_rodape(3, "1.917,46")],
    ])
    with caplog.at_level(logging.WARNING):
        _, notas = le_sefaz(pdf)
    assert [n.valor for n in notas] == [Decimal("192.40"), Decimal("1532.66"), Decimal("192.40")]
    avisos = _avisos_de_formato(caplog)
    assert len(avisos) == 1
    msg = avisos[0].getMessage()
    assert "esperado 1,234.56 e encontrado 1.234,56" in msg and "Sefaz" in msg and "sefaz_br.pdf" in msg


def test_le_sefaz_em_formato_us_nao_avisa_formato(tmp_path, caplog):
    pdf = tmp_path / "sefaz.pdf"
    _gera_pdf(pdf, [CABECALHO + [_linha(CHAVE_OK), *_rodape(1, "192.40")]])
    with caplog.at_level(logging.WARNING):
        le_sefaz(pdf)
    assert _avisos_de_formato(caplog) == []


def test_rodape_em_formato_br_captura_o_valor_inteiro_e_nao_um_fragmento():
    from conferencia.leitor_sefaz import _RODAPE
    from conferencia.parsing import parse_valor
    achados = _RODAPE.findall("Quantidade de Notas: 3 1.917,46")
    assert achados == [("3", "1.917,46")]
    assert parse_valor(achados[0][1]) == Decimal("1917.46")
