from dataclasses import replace
from datetime import date

import pdfplumber
import pytest

from conferencia.modelo import Empresa, Status
from conferencia.relatorio_pdf import _documento, escreve_relatorio, nome_arquivo


def texto_do_pdf(caminho):
    with pdfplumber.open(caminho) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def test_nome_arquivo_sanitiza_caractere_invalido_no_windows(resultado_divergente):
    resultado_divergente.empresa = Empresa(
        "18", "11444777002539", "BETA & CIA. S.A",
        date(2026, 9, 1), date(2026, 9, 30),
    )
    nome = nome_arquivo(resultado_divergente)
    assert not set(nome) & set(r'<>:"/\|?*&')
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
    # a nota 9999 foi conferida sem divergencia: nao esta nas ocorrencias
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    texto = texto_do_pdf(destino)
    assert "1/9999" not in texto and "9999" not in texto
    for o in resultado_divergente.ocorrencias:
        assert str(o.numero) in texto


def test_cabecalho_traz_empresa_periodo_quantidades_e_totais(tmp_path, resultado_divergente):
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    texto = texto_do_pdf(destino)
    assert "701" in texto and "EMPRESA COM ERRO LTDA" in texto
    assert "44.555.666/0001-72" in texto
    assert "01/09/2026 a 30/09/2026" in texto
    assert "Sefaz: 5 notas, R$ 2.000,00" in texto
    assert "Domínio: 5 notas, R$ 1.829,25" in texto


def test_cnpj_emitente_formatado_e_cpf_nao_vira_cnpj(tmp_path, resultado_divergente):
    resultado_divergente.ocorrencias[1] = replace(
        resultado_divergente.ocorrencias[1], cnpj_emitente="00052998224725"  # CPF fabricado para teste, DV valido
    )
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    texto = texto_do_pdf(destino)
    assert "45.723.174/0011-92" in texto
    assert "529.982.247-25" in texto
    assert "00.052.998/2247-25" not in texto


def test_serie_vazia_mostra_so_o_numero(tmp_path, resultado_divergente):
    resultado_divergente.ocorrencias[1] = replace(
        resultado_divergente.ocorrencias[1], serie="", numero=6100244
    )
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    texto = texto_do_pdf(destino)
    assert "6100244" in texto and "/6100244" not in texto


def test_serie_e_numero_longos_nao_invadem_a_coluna_seguinte(tmp_path, resultado_divergente):
    resultado_divergente.ocorrencias[0] = replace(
        resultado_divergente.ocorrencias[0], serie="999", numero=999999999
    )
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    assert "999/999999999" in texto_do_pdf(destino)


def test_resultado_sem_empresa_levanta_erro_claro(tmp_path, resultado_sem_par):
    with pytest.raises(ValueError, match="sem empresa"):
        nome_arquivo(resultado_sem_par)
    with pytest.raises(ValueError, match="sem empresa"):
        escreve_relatorio(resultado_sem_par, tmp_path / "x.pdf")


def test_categoria_sem_bloco_nao_some_em_silencio(tmp_path, resultado_divergente):
    resultado_divergente.ocorrencias[0] = replace(
        resultado_divergente.ocorrencias[0], categoria="INEXISTENTE"
    )
    with pytest.raises(ValueError, match="INEXISTENTE"):
        escreve_relatorio(resultado_divergente, tmp_path / "x.pdf")


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


def test_documento_cnpj_comecando_em_zeros_nao_vira_cpf():
    assert _documento("00000000000191") == "00.000.000/0001-91"  # Banco do Brasil
    assert _documento("00012345000199") == "00.012.345/0001-99"


def test_documento_cpf_zero_preenchido_com_dv_valido():
    assert _documento("00052998224725") == "529.982.247-25"  # CPF fabricado para teste


def test_documento_cnpj_comum_e_tamanho_estranho():
    assert _documento("45723174001192") == "45.723.174/0011-92"
    assert _documento("123") == "123"
