import logging
import re
from decimal import Decimal
from pathlib import Path

import pdfplumber

from conferencia.modelo import Cabecalho, NotaSefaz
from conferencia.parsing import (
    normaliza_cnpj, normaliza_numero, normaliza_serie, parse_data_br, parse_valor_br,
)

log = logging.getLogger(__name__)

_CHAVE = re.compile(r"\d{44}")
_DATA = re.compile(r"\d{2}/\d{2}/\d{4}")
_CNPJ_CPF = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2}")
_SITUACOES = {"Ativa", "Cancelada"}
_TOLERANCIA_TOP = 2.0  # pt: palavras de uma mesma linha visual
_PERIODO = re.compile(r"Período:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})")
_CNPJ_ROTULO = re.compile(r"^CNPJ:\s*(\S+)", re.MULTILINE)
# Rodape (spec 2.1): quantidade e valor total declarados pela propria Sefaz.
_RODAPE = re.compile(r"Quantidade de Notas:?\s*(\d+)[^\d]*(\d[\d.]*,\d{2})")
_RAZAO_ROTULO = re.compile(r"^Razão Social:\s*(.+?)\s*$", re.MULTILINE)


def e_sefaz(texto_primeira_pagina: str) -> bool:
    return "SECRETARIA DE ESTADO DA FAZENDA DE ALAGOAS" in texto_primeira_pagina


def le_cabecalho(texto: str) -> Cabecalho:
    periodo = _PERIODO.search(texto)
    cnpj = _CNPJ_ROTULO.search(texto)
    razao = _RAZAO_ROTULO.search(texto)
    if not (periodo and cnpj and razao):
        raise ValueError("cabecalho da Sefaz incompleto")
    return Cabecalho(
        codigo=None,
        cnpj=normaliza_cnpj(cnpj.group(1)),
        razao_social=razao.group(1),
        periodo_inicio=parse_data_br(periodo.group(1)),
        periodo_fim=parse_data_br(periodo.group(2)),
    )


def decompoe_chave(chave: str) -> tuple[str, str, int]:
    """(cnpj_emitente, serie, numero) das posicoes 7-20, 23-25 e 26-34 da chave."""
    if not _CHAVE.fullmatch(chave):
        raise ValueError(f"chave de acesso invalida: {chave!r}")
    return normaliza_cnpj(chave[6:20]), normaliza_serie(chave[22:25]), normaliza_numero(chave[25:34])


def parse_linha(palavras: list[dict]) -> NotaSefaz | None:
    """Linha de dados = a que tem uma palavra de 44 digitos (a chave)."""
    textos = [p["text"] for p in sorted(palavras, key=lambda p: p["x0"])]
    achados = [i for i, t in enumerate(textos) if _CHAVE.fullmatch(t)]
    if not achados:
        return None
    if len(achados) > 1:
        raise ValueError(f"mais de uma chave de acesso na mesma linha: {' '.join(textos)!r}")
    k = achados[0]
    # layout: data hora cnpj nome... serie / numero chave tipo situacao valor
    if k < 6 or len(textos) < k + 4 or not _DATA.fullmatch(textos[0]) or not _CNPJ_CPF.fullmatch(textos[2]):
        raise ValueError(f"linha de dados fora do layout esperado: {' '.join(textos)!r}")
    if textos[k + 2] not in _SITUACOES:
        raise ValueError(f"situacao inesperada {textos[k + 2]!r}: {' '.join(textos)!r}")
    return NotaSefaz(
        cnpj_emitente=normaliza_cnpj(textos[2]),
        nome_emitente=" ".join(textos[3:k - 3]),
        serie=normaliza_serie(textos[k - 3]),
        numero=normaliza_numero(textos[k - 1]),
        data_emissao=parse_data_br(textos[0]),
        chave=textos[k],
        situacao=textos[k + 2],
        valor=parse_valor_br(textos[k + 3]),
    )


def _linhas_da_pagina(pagina) -> list[list[dict]]:
    """Agrupa palavras por proximidade vertical (tolerancia, nao arredondamento)."""
    linhas: list[list[dict]] = []
    top_inicial = None  # ancora = 1a palavra do cluster; ancorar na anterior encadeia sem limite
    for p in sorted(pagina.extract_words(), key=lambda p: p["top"]):
        if top_inicial is None or p["top"] - top_inicial > _TOLERANCIA_TOP:
            linhas.append([])
            top_inicial = p["top"]
        linhas[-1].append(p)
    return linhas


def _confere_rodape(texto: str, notas: list[NotaSefaz]) -> None:
    """Reconcilia o que foi lido com o que a Sefaz declara no rodape (spec 2.1).
    Comparacao exata em Decimal: o total declarado e uma soma exata dos valores.
    Relatorio sem notas e legitimo (rodape declara 0): so falha se o rodape declarar mais.
    SUPOSICAO (amostra so tem notas Ativa): o total declarado inclui as canceladas."""
    rodapes = _RODAPE.findall(texto)
    if len(rodapes) != 1:
        raise ValueError(
            f"rodape da Sefaz (Quantidade de Notas / valor total) encontrado {len(rodapes)} vez(es); esperado 1"
        )
    qtd, total = int(rodapes[0][0]), parse_valor_br(rodapes[0][1])
    if qtd != len(notas):
        raise ValueError(
            f"Quantidade de Notas declarada no rodape ({qtd}) difere das linhas lidas ({len(notas)})"
        )
    soma = sum((n.valor for n in notas), Decimal("0"))
    if soma != total:
        raise ValueError(f"valor total declarado no rodape ({total}) difere da soma lida ({soma})")


def le_sefaz(caminho: Path) -> tuple[Cabecalho, list[NotaSefaz]]:
    notas: list[NotaSefaz] = []
    textos: list[str] = []
    with pdfplumber.open(caminho) as pdf:
        cabecalho = le_cabecalho(pdf.pages[0].extract_text() or "")
        for pagina in pdf.pages:
            textos.append(pagina.extract_text() or "")
            for linha in _linhas_da_pagina(pagina):
                nota = parse_linha(linha)
                if nota is None:
                    continue
                lido = (nota.cnpj_emitente, nota.serie, nota.numero)
                da_chave = decompoe_chave(nota.chave)
                if da_chave != lido:
                    log.warning(
                        "chave %s diverge da linha: linha (cnpj, serie, numero) = %s; chave = %s",
                        nota.chave, lido, da_chave,
                    )
                notas.append(nota)
    _confere_rodape("\n".join(textos), notas)
    return cabecalho, notas
