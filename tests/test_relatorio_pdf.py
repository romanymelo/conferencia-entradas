from datetime import date

import pdfplumber

from conferencia.modelo import Empresa, Status
from conferencia.relatorio_pdf import escreve_relatorio, nome_arquivo


def texto_do_pdf(caminho):
    with pdfplumber.open(caminho) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def test_nome_arquivo_sanitiza_caractere_invalido_no_windows(resultado_divergente):
    resultado_divergente.empresa = Empresa(
        "18", "11444777002539", "BETA & CIA. S.A",
        date(2026, 9, 1), date(2026, 9, 30),
    )
    nome = nome_arquivo(resultado_divergente)
    assert not set(nome) & set('<>:"/\|?*&')
    assert nome.startswith("18_") and nome.endswith(".pdf")


def test_nome_arquivo_colapsa_espacos_e_corta_em_80(resultado_divergente):
    resultado_divergente.empresa = Empresa(
        "18", "11444777002539", "A   B" + " X" * 100,
        date(2026, 9, 1), date(2026, 9, 30),
    )
    nome = nome_arquivo(resultado_divergente)
    assert " " not in nome and "__" not in nome
    assert nome.startswith("18_A_B_X")
    assert len(nome) <= 80 + len(".pdf")


def test_relatorio_traz_a_chave_de_acesso(tmp_path, resultado_divergente):
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    chaves = [o.chave for o in resultado_divergente.ocorrencias if o.chave]
    assert chaves and chaves[0] in texto_do_pdf(destino).replace(" ", "")


def test_chave_cabe_inteira_numa_unica_linha(tmp_path, resultado_divergente):
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    chave = resultado_divergente.ocorrencias[0].chave
    linhas = texto_do_pdf(destino).splitlines()
    assert any(chave in linha for linha in linhas)


def test_relatorio_e_paisagem_a4(tmp_path, resultado_divergente):
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    with pdfplumber.open(destino) as pdf:
        assert pdf.pages[0].width > pdf.pages[0].height


def test_relatorio_nao_lista_notas_conferidas(tmp_path, resultado_divergente):
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    texto = texto_do_pdf(destino)
    assert str(len(resultado_divergente.ocorrencias)) in texto


def test_blocos_na_ordem_com_contagem_no_titulo(tmp_path, resultado_divergente):
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    texto = texto_do_pdf(destino)
    erros = texto.index("Erros (1)")
    informativos = texto.index("Informativos (1)")
    assert erros < informativos
    assert "Alertas" not in texto  # bloco vazio nao aparece


def test_empresa_sem_ocorrencia_gera_pdf_de_conferencia_limpa(tmp_path, resultado_ok):
    destino = tmp_path / "ok.pdf"
    escreve_relatorio(resultado_ok, destino)
    assert "sem divergências" in texto_do_pdf(destino).lower()


def test_rodape_alerta_sobre_a_virada_de_mes(tmp_path, resultado_divergente):
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    assert "data de entrada" in texto_do_pdf(destino).lower()


def test_rodape_aparece_em_todas_as_paginas(tmp_path, resultado_divergente):
    base = resultado_divergente.ocorrencias[0]
    resultado_divergente.ocorrencias = [base] * 80
    destino = tmp_path / "longo.pdf"
    escreve_relatorio(resultado_divergente, destino)
    with pdfplumber.open(destino) as pdf:
        assert len(pdf.pages) > 1
        for pagina in pdf.pages:
            assert "data de entrada" in (pagina.extract_text() or "").lower()


def test_relatorio_exibe_o_status(tmp_path, resultado_divergente):
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    assert Status.DIVERGENTE in texto_do_pdf(destino)
