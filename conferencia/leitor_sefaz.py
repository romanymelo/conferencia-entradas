import logging
import re
from collections import defaultdict
from pathlib import Path

import pdfplumber

from conferencia.modelo import Cabecalho, NotaSefaz
from conferencia.parsing import (
    normaliza_cnpj, normaliza_numero, normaliza_serie, parse_data_br, parse_valor_br,
)

log = logging.getLogger(__name__)

_CHAVE = re.compile(r"\d{44}")
_DATA = re.compile(r"\d{2}/\d{2}/\d{4}")
_CNPJ = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
_PERIODO = re.compile(r"Período:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})")
_CNPJ_ROTULO = re.compile(r"^CNPJ:\s*(\S+)", re.MULTILINE)
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
    k = achados[0]
    # layout: data hora cnpj nome... serie / numero chave tipo situacao valor
    if k < 6 or len(textos) < k + 4 or not _DATA.fullmatch(textos[0]) or not _CNPJ.fullmatch(textos[2]):
        raise ValueError(f"linha de dados fora do layout esperado: {' '.join(textos)!r}")
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
    por_top = defaultdict(list)
    for p in pagina.extract_words():
        por_top[round(p["top"])].append(p)
    return [por_top[top] for top in sorted(por_top)]


def le_sefaz(caminho: Path) -> tuple[Cabecalho, list[NotaSefaz]]:
    notas: list[NotaSefaz] = []
    with pdfplumber.open(caminho) as pdf:
        cabecalho = le_cabecalho(pdf.pages[0].extract_text() or "")
        for pagina in pdf.pages:
            for linha in _linhas_da_pagina(pagina):
                nota = parse_linha(linha)
                if nota is None:
                    continue
                esperado = (nota.cnpj_emitente, nota.serie, nota.numero)
                if decompoe_chave(nota.chave) != esperado:
                    log.warning(
                        "chave %s diverge da linha lida (cnpj, serie, numero) = %s",
                        nota.chave, esperado,
                    )
                notas.append(nota)
    return cabecalho, notas
