from datetime import date
from pathlib import Path
import pytest
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from conferencia.descoberta import ArquivoIdentificado, identifica, pareia
from conferencia.modelo import Cabecalho, Status

def cab(cnpj="12345678000195", codigo=None, fim=date(2026, 9, 30)):
    return Cabecalho(codigo, cnpj, "FARMACIA MODELO LTDA", date(2026, 9, 1), fim)

def arq(tipo, nome, **kw):
    return ArquivoIdentificado(Path(nome), tipo, cab(**kw))

def test_pareia_um_de_cada_tipo():
    pares, problemas = pareia([
        arq("sefaz", "s.pdf"),
        arq("dominio", "d.pdf", codigo="101"),
    ])
    assert problemas == []
    assert len(pares) == 1
    assert pares[0].empresa.codigo == "101"
    assert pares[0].empresa.razao_social == "FARMACIA MODELO LTDA"
    assert pares[0].empresa.periodo_fim == date(2026, 9, 30)
    assert pares[0].caminho_sefaz == Path("s.pdf")
    assert pares[0].caminho_dominio == Path("d.pdf")

def test_so_um_dos_tipos_vira_sem_par():
    pares, problemas = pareia([arq("sefaz", "s.pdf")])
    assert pares == []
    assert problemas[0].status == Status.SEM_PAR
    assert problemas[0].empresa is None and problemas[0].ocorrencias == []
    assert "dominio" in problemas[0].erro.lower()

def test_so_dominio_diz_que_falta_sefaz():
    _, problemas = pareia([arq("dominio", "d.pdf", codigo="101")])
    assert problemas[0].status == Status.SEM_PAR
    assert "sefaz" in problemas[0].erro.lower()

def test_periodos_diferentes_viram_periodo_divergente():
    pares, problemas = pareia([
        arq("sefaz", "s.pdf"),
        arq("dominio", "d.pdf", codigo="101", fim=date(2026, 10, 31)),
    ])
    assert pares == []
    assert problemas[0].status == Status.PERIODO_DIVERGENTE
    assert "30/09/2026" in problemas[0].erro and "31/10/2026" in problemas[0].erro

def test_dois_arquivos_do_mesmo_tipo_viram_duplicado():
    # caso real: "Entradas 101.pdf" e "Entradas 101 novo.pdf" na mesma pasta
    pares, problemas = pareia([
        arq("sefaz", "s.pdf"),
        arq("dominio", "d1.pdf", codigo="101"),
        arq("dominio", "d2.pdf", codigo="101"),
    ])
    assert pares == []
    assert problemas[0].status == Status.DUPLICADO
    assert "d1.pdf" in problemas[0].erro and "d2.pdf" in problemas[0].erro

def test_varias_empresas_sao_pareadas_independentemente():
    pares, problemas = pareia([
        arq("sefaz", "s1.pdf"),
        arq("dominio", "d1.pdf", codigo="101"),
        arq("sefaz", "s2.pdf", cnpj="11222333000144"),
    ])
    assert len(pares) == 1 and len(problemas) == 1
    assert problemas[0].status == Status.SEM_PAR


# --- identifica: PDFs fabricados com reportlab ---

def _gera_pdf(caminho, linhas):
    c = canvas.Canvas(str(caminho), pagesize=landscape(A4))
    y = 550
    for texto in linhas:
        c.drawString(20, y, texto)
        y -= 15
    c.showPage()
    c.save()

SEFAZ = [
    "SECRETARIA DE ESTADO DA FAZENDA DE ALAGOAS",
    "CNPJ: 12.345.678/0001-95",
    "Razão Social: FARMACIA MODELO LTDA",
    "Período: 01/09/2026 - 30/09/2026",
]
DOMINIO = [
    "ACOMPANHAMENTO DE ENTRADAS",
    "101 - FARMACIA MODELO LTDA",
    "CNPJ: 12.345.678/0001-95",
    "Período: 01/09/2026 até 30/09/2026",
]

def test_identifica_sefaz(tmp_path):
    pdf = tmp_path / "qualquer nome.pdf"
    _gera_pdf(pdf, SEFAZ)
    r = identifica(pdf)
    assert r.tipo == "sefaz" and r.caminho == pdf
    assert r.cabecalho.cnpj == "12345678000195" and r.cabecalho.codigo is None

def test_identifica_dominio(tmp_path):
    pdf = tmp_path / "x.pdf"
    _gera_pdf(pdf, DOMINIO)
    r = identifica(pdf)
    assert r.tipo == "dominio" and r.cabecalho.codigo == "101"

def test_identifica_pdf_alheio_devolve_none(tmp_path):
    pdf = tmp_path / "boleto.pdf"
    _gera_pdf(pdf, ["BOLETO DE COBRANCA"])
    assert identifica(pdf) is None

def test_identifica_cabecalho_incompleto_levanta(tmp_path):
    pdf = tmp_path / "x.pdf"
    _gera_pdf(pdf, DOMINIO[:2])
    with pytest.raises(ValueError):
        identifica(pdf)
