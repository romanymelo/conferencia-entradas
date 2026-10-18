import logging
from datetime import date
from decimal import Decimal
import pytest
from conferencia.leitor_sefaz import (
    decompoe_chave, e_sefaz, le_cabecalho, le_sefaz, parse_linha,
)


def palavras(*textos):
    """Simula page.extract_words(): uma palavra por item, x crescente."""
    return [{"text": t, "x0": i * 10.0, "x1": i * 10.0 + 5.0} for i, t in enumerate(textos)]


LINHA = palavras(
    "01/09/2026", "08:52:43", "11.222.333/0001-44", "FORNECEDOR", "TESTE", "LTDA",
    "1", "/", "1004582", "2" * 44, "Saída", "Ativa", "192,40",
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
    assert n.valor == Decimal("189.63")


def test_parse_linha_le_situacao_cancelada():
    linha = palavras(
        "01/09/2026", "08:52:43", "11.222.333/0001-44", "FORNECEDOR",
        "1", "/", "99", "3" * 44, "Saída", "Cancelada", "500,00",
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
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(caminho), pagesize=landscape(A4))
    for linhas in paginas:
        y = 550
        for texto in linhas:
            c.drawString(20, y, texto)
            y -= 15
        c.showPage()
    c.save()


def _linha(chave, valor="192,40"):
    return f"01/09/2026 08:52:43 11.222.333/0001-44 FORNECEDOR TESTE 1 / 99 {chave} Saída Ativa {valor}"


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
        CABECALHO + [_linha(CHAVE_OK), _linha(CHAVE_OK, "1.532,66")],
        ["pagina sem nenhuma linha de dados"],
        [_linha(CHAVE_OK), "Quantidade de Notas: 3"],
    ])
    cab, notas = le_sefaz(pdf)
    assert cab.cnpj == "12345678000195"
    assert [n.valor for n in notas] == [Decimal("189.63"), Decimal("1532.66"), Decimal("189.63")]
    assert all(n.chave == CHAVE_OK for n in notas)


def test_le_sefaz_avisa_divergencia_da_chave_sem_interromper(tmp_path, caplog):
    pdf = tmp_path / "sefaz.pdf"
    chave_ruim = "9" * 44
    _gera_pdf(pdf, [CABECALHO + [_linha(chave_ruim), _linha(CHAVE_OK)]])
    with caplog.at_level(logging.WARNING):
        _, notas = le_sefaz(pdf)
    assert len(notas) == 2
    avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(avisos) == 1 and chave_ruim in avisos[0].getMessage()
