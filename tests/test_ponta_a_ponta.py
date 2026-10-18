import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from conferencia.modelo import Categoria, Status
from main import executa

AMOSTRA = Path(__file__).parent / "amostra"


# --- PDFs fabricados (dados fictícios) ---

def _pdf(caminho, linhas):
    c = canvas.Canvas(str(caminho), pagesize=landscape(A4))
    y = 550
    for texto in linhas:
        c.drawString(20, y, texto)
        y -= 15
    c.showPage()
    c.save()


def _chave(numero: int) -> str:
    return "276" + "666" + "45723174001192" + "55" + "001" + f"{numero:09d}" + "0" * 10


def _soma(valores) -> str:
    total = sum((Decimal(v.replace(".", "").replace(",", ".")) for v in valores), Decimal("0"))
    return f"{total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _sefaz(caminho, notas, cnpj="12.345.678/0001-95"):
    linhas = [
        "SECRETARIA DE ESTADO DA FAZENDA DE ALAGOAS",
        f"CNPJ: {cnpj}",
        "Razão Social: FARMACIA MODELO LTDA",
        "Período: 01/09/2026 - 30/09/2026",
    ]
    for numero, valor in notas:
        linhas.append(
            f"05/09/2026 08:52:43 45.723.174/0011-92 FORNECEDOR TESTE LTDA 1 / {numero} "
            f"{_chave(numero)} Saída Ativa {valor}"
        )
    linhas += [f"Quantidade de Notas: {len(notas)}", f"Valor Total: {_soma(v for _, v in notas)}"]
    _pdf(caminho, linhas)


def _dominio(caminho, notas, cnpj="12.345.678/0001-95", extra=()):
    linhas = [
        "ACOMPANHAMENTO DE ENTRADAS",
        "101 - FARMACIA MODELO LTDA",
        f"CNPJ: {cnpj}",
        "Período: 01/09/2026 até 30/09/2026",
    ]
    for numero, valor in notas:
        linhas.append(
            f"1 05/09/2026 05/09/2026 {numero} 1 36 6 FORNECEDOR TESTE LTDA "
            f"45.723.174/0011-92 240000015 1-102 101 AL {valor} ICMS 0,00"
        )
    _pdf(caminho, [*linhas, *extra, f"Total Geral {_soma(v for _, v in notas)} 0,00"])


@pytest.fixture
def entrada(tmp_path):
    pasta = tmp_path / "entrada"
    pasta.mkdir()
    return pasta


def _resumo(saida):
    aba = load_workbook(next(saida.rglob("*.xlsx")))["Resumo"]
    cab = [c.value for c in aba[1]]
    return [{cab[i]: c.value for i, c in enumerate(linha)} for linha in aba.iter_rows(min_row=2)]


def _log(saida):
    return next(saida.rglob("log_execucao.txt")).read_text(encoding="utf-8")


# --- testes com dados fabricados ---

def test_pasta_vazia_nao_quebra(tmp_path):
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    saida = tmp_path / "saida"
    assert executa(entrada, saida) == 0


def test_pasta_de_entrada_inexistente_levanta(tmp_path):
    with pytest.raises(NotADirectoryError):
        executa(tmp_path / "nao_existe", tmp_path / "saida")


def test_empresa_divergente_gera_pdf_planilha_e_log(entrada, tmp_path):
    saida = tmp_path / "saida"
    _sefaz(entrada / "s.pdf", [(100, "50,00"), (101, "70,00")])
    _dominio(entrada / "d.pdf", [(100, "50,00")])

    assert executa(entrada, saida) == 1

    # subdiretório vem do período declarado, não da data de hoje
    pasta = saida / "2026-09"
    assert (pasta / "resumo_conferencia_2026-09.xlsx").is_file()
    assert [p.name for p in pasta.glob("101_*.pdf")] == ["101_FARMACIA_MODELO_LTDA.pdf"]
    [linha] = _resumo(saida)
    assert linha["Código"] == "101" and linha["Status"] == Status.DIVERGENTE
    assert linha[Categoria.FALTANDO] == 1
    assert linha["Período"] == "01/09/2026 a 30/09/2026"
    assert linha["Qtd Sefaz"] == 2 and linha["Qtd Domínio"] == 1
    assert Decimal(str(linha["Total Sefaz"])) == Decimal("120.00")
    log = _log(saida)
    assert "101" in log and "s.pdf" in log and "d.pdf" in log


def test_empresa_sem_ocorrencia_tambem_gera_pdf(entrada, tmp_path):
    saida = tmp_path / "saida"
    _sefaz(entrada / "s.pdf", [(100, "50,00")])
    _dominio(entrada / "d.pdf", [(100, "50,00")])
    assert executa(entrada, saida) == 0
    assert list((saida / "2026-09").glob("101_*.pdf"))
    assert _resumo(saida)[0]["Status"] == Status.OK


def test_agrega_linhas_de_cfop_da_mesma_nota_e_fecha_com_a_sefaz(entrada, tmp_path):
    # uma nota, duas linhas de CFOP no Domínio: 52,10 + 140,30 = 192,40 (valor da Sefaz)
    saida = tmp_path / "saida"
    _sefaz(entrada / "s.pdf", [(100, "192,40")])
    _dominio(entrada / "d.pdf", [(100, "52,10"), (100, "140,30")])

    assert executa(entrada, saida) == 0

    [linha] = _resumo(saida)
    assert linha["Status"] == Status.OK
    assert linha["Qtd Domínio"] == 1
    assert Decimal(str(linha["Total Domínio"])) == Decimal("189.63")
    assert Decimal(str(linha["Total Sefaz"])) == Decimal("189.63")
    assert linha[Categoria.VALOR_DIVERGENTE] == 0


def test_empresa_sem_notas_no_mes_com_relatorios_vazios_e_coerentes_sai_ok(entrada, tmp_path):
    saida = tmp_path / "saida"
    _sefaz(entrada / "s.pdf", [])
    _dominio(entrada / "d.pdf", [])
    assert executa(entrada, saida) == 0
    [linha] = _resumo(saida)
    assert linha["Status"] == Status.OK
    assert linha["Qtd Sefaz"] == 0 and linha["Qtd Domínio"] == 0


def test_sem_par_aparece_no_resumo_sem_pdf(entrada, tmp_path):
    saida = tmp_path / "saida"
    _sefaz(entrada / "s.pdf", [(100, "50,00")])
    assert executa(entrada, saida) == 0
    [linha] = _resumo(saida)
    assert linha["Status"] == Status.SEM_PAR and "dominio" in linha["Observação"].lower()
    assert not list(saida.rglob("*.pdf"))


def test_arquivo_ilegivel_nao_derruba_a_rodada(entrada, tmp_path):
    # spec §5.2: falha em uma empresa não interrompe as demais
    saida = tmp_path / "saida"
    _sefaz(entrada / "s.pdf", [(100, "50,00")])
    _dominio(entrada / "d.pdf", [(100, "50,00")])
    (entrada / "quebrado.pdf").write_bytes(b"isto nao e um PDF")

    assert executa(entrada, saida) == 0

    linhas = _resumo(saida)
    assert Status.OK in [l["Status"] for l in linhas]
    erro = next(l for l in linhas if l["Status"] == Status.ERRO_LEITURA)
    assert "quebrado.pdf" in erro["Observação"]
    assert "quebrado.pdf" in _log(saida)
    assert list(saida.rglob("101_*.pdf"))


def test_linha_fora_do_layout_derruba_so_a_empresa(entrada, tmp_path):
    # linha de dados sem CNPJ: pular em silêncio esconderia um FALTANDO
    saida = tmp_path / "saida"
    _sefaz(entrada / "s1.pdf", [(100, "50,00")])
    _dominio(entrada / "d1.pdf", [(100, "50,00")], extra=["1 05/09/2026 05/09/2026 101 1 36 lixo"])
    _sefaz(entrada / "s2.pdf", [(200, "10,00")], cnpj="11.222.333/0001-81")
    _dominio(entrada / "d2.pdf", [(200, "10,00")], cnpj="11.222.333/0001-81")

    assert executa(entrada, saida) == 0

    linhas = _resumo(saida)
    assert sorted(l["Status"] for l in linhas) == sorted([Status.OK, Status.ERRO_LEITURA])
    erro = next(l for l in linhas if l["Status"] == Status.ERRO_LEITURA)
    assert "d1.pdf" in erro["Observação"]
    assert "d1.pdf" in _log(saida)
    assert len(list(saida.rglob("*.pdf"))) == 1


def test_sefaz_com_nota_perdida_na_leitura_vira_erro_de_leitura_nao_ok(entrada, tmp_path):
    # chave partida em dois tokens: sem o rodape a empresa sairia OK com 0 notas lidas
    saida = tmp_path / "saida"
    _pdf(entrada / "s.pdf", [
        "SECRETARIA DE ESTADO DA FAZENDA DE ALAGOAS",
        "CNPJ: 12.345.678/0001-95",
        "Razão Social: FARMACIA MODELO LTDA",
        "Período: 01/09/2026 - 30/09/2026",
        f"05/09/2026 08:52:43 45.723.174/0011-92 FORNECEDOR TESTE LTDA 1 / 100 "
        f"{_chave(100)} Saída Ativa 50,00",
        f"05/09/2026 08:52:43 45.723.174/0011-92 FORNECEDOR TESTE LTDA 1 / 101 "
        f"{_chave(101)[:20]} {_chave(101)[20:]} Saída Ativa 70,00",
        "Quantidade de Notas: 2", "Valor Total: 120,00",
    ])
    _dominio(entrada / "d.pdf", [(100, "50,00"), (101, "70,00")])
    assert executa(entrada, saida) == 0
    [linha] = _resumo(saida)
    assert linha["Status"] == Status.ERRO_LEITURA
    assert "Quantidade de Notas" in linha["Observação"]


# --- teste de ouro: depende dos PDFs reais, locais e não versionados ---

@pytest.fixture
def pasta_amostra(tmp_path):
    pdfs = sorted(AMOSTRA.glob("*.pdf")) if AMOSTRA.exists() else []
    if len(pdfs) < 2:
        pytest.skip(
            f"crie a pasta {AMOSTRA} e coloque nela os dois PDFs reais da empresa 101: "
            "'Entradas 101 novo.pdf' (Domínio) e 'Notas fiscais entrada 101.pdf' (Sefaz)"
        )
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    for p in pdfs:
        shutil.copy(p, entrada)
    return entrada, tmp_path / "saida"


def test_teste_de_ouro_empresa_101(pasta_amostra):
    entrada, saida = pasta_amostra
    assert executa(entrada, saida) == 0

    aba = load_workbook(next(saida.rglob("*.xlsx")))["Resumo"]
    cabecalho = [c.value for c in aba[1]]
    linha = {cabecalho[i]: c.value for i, c in enumerate(aba[2])}

    assert linha["Código"] == "101"
    assert linha["Status"] == Status.OK
    assert linha["Qtd Sefaz"] == 204
    assert Decimal(str(linha["Total Sefaz"])) == Decimal("133721.36")
    assert Decimal(str(linha["Total Domínio"])) == Decimal("137112.13")
    assert linha[Categoria.FALTANDO] == 0
    assert linha[Categoria.SOBRANDO] == 0
    assert linha[Categoria.VALOR_DIVERGENTE] == 0
    assert linha[Categoria.CANCELADA_NAO_ZERADA] == 0
    assert linha[Categoria.AMBIGUO] == 0
    assert linha[Categoria.FORA_DO_PERIODO] == 3
    assert linha[Categoria.NAO_NFE] == 3


def test_gera_pdf_para_a_empresa_conferida(pasta_amostra):
    entrada, saida = pasta_amostra
    executa(entrada, saida)
    assert [p.name for p in saida.rglob("101_*.pdf")]


def test_falha_ao_gravar_pdf_preserva_a_conferencia(entrada, tmp_path, monkeypatch):
    saida = tmp_path / "saida"
    _sefaz(entrada / "s.pdf", [(100, "50,00"), (101, "70,00")])
    _dominio(entrada / "d.pdf", [(100, "50,00")])

    def nega(*a, **k):
        raise PermissionError("pdf aberto")
    monkeypatch.setattr("main.escreve_relatorio", nega)

    assert executa(entrada, saida) == 1
    [linha] = _resumo(saida)
    assert linha["Status"] == Status.DIVERGENTE and linha[Categoria.FALTANDO] == 1
    assert "PDF" in linha["Observação"]
    assert "pdf aberto" in _log(saida)


def test_log_sobrevive_a_falha_da_planilha(entrada, tmp_path, monkeypatch):
    saida = tmp_path / "saida"
    _sefaz(entrada / "s.pdf", [(100, "50,00")])
    _dominio(entrada / "d.pdf", [(100, "50,00")])

    def nega(*a, **k):
        raise PermissionError("planilha aberta no Excel")
    monkeypatch.setattr("main.escreve_planilha", nega)

    with pytest.raises(PermissionError):
        executa(entrada, saida)
    assert "101" in _log(saida)
