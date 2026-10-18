import re
from pathlib import Path

import pdfplumber

from conferencia.modelo import Cabecalho, LancamentoDominio
from conferencia.parsing import (
    normaliza_cnpj, normaliza_numero, normaliza_serie, parse_data_br, parse_valor_br,
)

_DATA = re.compile(r"\d{2}/\d{2}/\d{4}")
_CNPJ_CPF = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2}")
_UF = re.compile(r"[A-Z]{2}")
_INICIO_DADO = re.compile(r"\d+ \d{2}/\d{2}/\d{4}")
_ZEBRA = re.compile(r"^1\s+(?=\d+\s+\d{2}/\d{2}/\d{4})")  # '1' solto antes do codigo
_PERIODO = re.compile(r"Período:\s*(\d{2}/\d{2}/\d{4})\s+até\s+(\d{2}/\d{2}/\d{4})")
_CNPJ_ROTULO = re.compile(r"^CNPJ:\s*(\S+)", re.MULTILINE)
_EMPRESA = re.compile(r"^(\d+)\s+-\s+(.+?)\s*$", re.MULTILINE)


def e_dominio(texto_primeira_pagina: str) -> bool:
    return "ACOMPANHAMENTO DE ENTRADAS" in texto_primeira_pagina


def le_cabecalho(texto: str) -> Cabecalho:
    periodo = _PERIODO.search(texto)
    cnpj = _CNPJ_ROTULO.search(texto)
    empresa = _EMPRESA.search(texto)
    if not (periodo and cnpj and empresa):
        raise ValueError("cabecalho do Dominio incompleto")
    return Cabecalho(
        codigo=empresa.group(1),
        cnpj=normaliza_cnpj(cnpj.group(1)),
        razao_social=empresa.group(2),
        periodo_inicio=parse_data_br(periodo.group(1)),
        periodo_fim=parse_data_br(periodo.group(2)),
    )


def parse_linha(texto: str) -> LancamentoDominio | None:
    """Linha de dados = a que comeca por codigo e data; o CNPJ/CPF formatado e a ancora."""
    texto = _ZEBRA.sub("", texto.strip(), count=1)
    if not _INICIO_DADO.match(texto):
        return None
    ancora = _CNPJ_CPF.search(texto)
    if not ancora:
        raise ValueError(f"linha de dados sem CNPJ/CPF: {texto!r}")
    antes = texto[:ancora.start()].split()
    depois = texto[ancora.end():].split()
    # antes: codigo emissao entrada | nota [serie] especie cod.fornecedor | nome...
    # Suposicao (evidencia da amostra, ainda nao confirmada em PDF real): linha de
    # servico (esp. 39) vem sem serie, entao os numericos antes do nome sao 3, nao 4.
    n = 0
    while 3 + n < len(antes) and antes[3 + n].isdigit():
        n += 1
    ufs = [i for i, t in enumerate(depois) if _UF.fullmatch(t)]
    if (n not in (3, 4) or len(antes) <= 3 + n or not _DATA.fullmatch(antes[1])
            or not _DATA.fullmatch(antes[2]) or not ufs or len(depois) <= ufs[0] + 1):
        raise ValueError(f"linha de dados fora do layout esperado: {texto!r}")
    serie = normaliza_serie(antes[4]) if n == 4 else ""
    return LancamentoDominio(
        cnpj_emitente=normaliza_cnpj(ancora.group()),
        nome_emitente=" ".join(antes[3 + n:]),
        serie=serie,
        numero=normaliza_numero(antes[3]),
        especie=int(antes[1 + n]),
        data_emissao=parse_data_br(antes[1]),
        data_entrada=parse_data_br(antes[2]),
        valor_contabil=parse_valor_br(depois[ufs[0] + 1]),
    )


def le_dominio(caminho: Path) -> tuple[Cabecalho, list[LancamentoDominio]]:
    lancamentos: list[LancamentoDominio] = []
    with pdfplumber.open(caminho) as pdf:
        cabecalho = le_cabecalho(pdf.pages[0].extract_text() or "")
        for pagina in pdf.pages:
            for linha in (pagina.extract_text() or "").splitlines():
                lancamento = parse_linha(linha)
                if lancamento is not None:
                    lancamentos.append(lancamento)
    return cabecalho, lancamentos
