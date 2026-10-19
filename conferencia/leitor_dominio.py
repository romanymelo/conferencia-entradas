import re
from decimal import Decimal
from pathlib import Path

import pdfplumber

from conferencia.modelo import Cabecalho, LancamentoDominio
from conferencia.parsing import (
    normaliza_cnpj, normaliza_numero, normaliza_serie, parse_data_br, parse_valor,
    avisa_se_formato_mudou,
)

# FORMATO NUMERICO: hoje o Dominio escreve em formato BR (126.970,40). parse_valor aceita
# BR e US; se o documento vier em outro formato, um aviso (por documento) e logado.
FORMATO_ESPERADO = "BR"
_DATA = re.compile(r"\d{2}/\d{2}/\d{4}")
_CNPJ_CPF = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2}")
_UF = re.compile(r"[A-Z]{2}")
_INICIO_DADO = re.compile(r"\d+ \d{2}/\d{2}/\d{4}")
_ZEBRA = re.compile(r"^1\s+(?=\d+\s+\d{2}/\d{2}/\d{4})")  # '1' solto antes do codigo
_PERIODO = re.compile(r"Período:\s*(\d{2}/\d{2}/\d{4})\s+até\s+(\d{2}/\d{2}/\d{4})")
_CNPJ_ROTULO = re.compile(r"^CNPJ:\s*(\S+)", re.MULTILINE)
# Rodape (spec 2.2): a linha "Total Geral" abre com o Valor Contabil total.
# No PDF real o valor fica na linha SEGUINTE ao rotulo, colado ao 'ICMS' ('126.970,40ICMS').
_ROTULO_TOTAL_GERAL = re.compile(r"Total Geral")
_PRIMEIRO_VALOR = re.compile(r"(?<![\d.,])(\d[\d.,]*[.,]\d{2})(?!\d)")
_EMPRESA = re.compile(r"^(\d+)\s+-\s+(.+?)\s*$", re.MULTILINE)
# Campo de cabecalho que divide a linha com a razao social ('... LTDA Página: 0001').
_CAMPO_DE_CABECALHO = re.compile(r"\s+[^\W\d_][\w.]*:.*$")
_TOLERANCIA_TOP = 2.0  # pt: celulas de uma mesma linha visual
_FOLGA_CELULA = 0.5  # pt: caracteres contiguos (mesma celula) distam menos que isto


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
        razao_social=_CAMPO_DE_CABECALHO.sub("", empresa.group(2)),
        periodo_inicio=parse_data_br(periodo.group(1)),
        periodo_fim=parse_data_br(periodo.group(2)),
    )


def parse_linha(texto: str) -> LancamentoDominio | None:
    """Linha de dados = a que comeca por codigo e data; o CNPJ/CPF formatado e a ancora."""
    texto = _ZEBRA.sub("", texto.strip(), count=1)
    if not _INICIO_DADO.match(texto):
        return None
    ancoras = list(_CNPJ_CPF.finditer(texto))
    if not ancoras:
        raise ValueError(f"linha de dados sem CNPJ/CPF: {texto!r}")
    if len(ancoras) > 1:
        raise ValueError(f"mais de um CNPJ/CPF na mesma linha (linhas fundidas?): {texto!r}")
    ancora = ancoras[0]
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
        valor_contabil=parse_valor(depois[ufs[0] + 1]),
    )


def _total_geral(linhas: list[str], caminho: Path) -> Decimal:
    """Valor Contabil do 'Total Geral': 1o valor monetario da linha seguinte ao rotulo."""
    rotulos = [i for i, l in enumerate(linhas) if _ROTULO_TOTAL_GERAL.search(l)]
    if len(rotulos) != 1:
        raise ValueError(f"Total Geral do Dominio encontrado {len(rotulos)} vez(es); esperado 1")
    seguintes = [l for l in linhas[rotulos[0] + 1:] if l.strip()]
    valor = _PRIMEIRO_VALOR.search(seguintes[0]) if seguintes else None
    if not valor:
        raise ValueError("Total Geral do Dominio sem valor na linha seguinte ao rotulo")
    avisa_se_formato_mudou(valor.group(1), FORMATO_ESPERADO, caminho)
    return parse_valor(valor.group(1))


def _confere_total_geral(linhas: list[str], lancamentos: list[LancamentoDominio], caminho: Path) -> None:
    """Reconcilia a soma de todos os lancamentos (NF-e ou nao) com o Total Geral (spec 2.2).
    Comparacao exata em Decimal: o Total Geral e uma soma exata dos Valores Contabeis.
    Relatorio sem lancamentos e legitimo (Total Geral 0,00): so falha se o total declarado for maior."""
    total = _total_geral(linhas, caminho)
    soma = sum((l.valor_contabil for l in lancamentos), Decimal("0"))
    if soma != total:
        raise ValueError(f"Total Geral declarado ({total}) difere da soma dos lancamentos lidos ({soma})")


def _celulas(pagina) -> list[tuple[float, float, str]]:
    """(top, x0, texto) de cada celula, na ordem de desenho do PDF. O Dominio desenha cada
    celula separada e o nome do fornecedor invade a coluna do CNPJ: ordenar os caracteres
    por posicao os embaralha ('29GAMA COM SERV4 3D.I2S1T4R...'), a ordem do fluxo nao."""
    celulas: list[tuple[float, float, str]] = []
    anterior = None
    for c in pagina.chars:
        if (anterior is None or abs(c["x0"] - anterior["x1"]) > _FOLGA_CELULA
                or abs(c["top"] - anterior["top"]) > _TOLERANCIA_TOP):
            celulas.append((c["top"], c["x0"], ""))
        top, x0, texto = celulas[-1]
        celulas[-1] = (top, x0, texto + c["text"])
        anterior = c
    return celulas


def _linhas_da_pagina(pagina) -> list[str]:
    """Reconstroi as linhas visuais juntando as celulas por proximidade vertical e x."""
    linhas: list[list[tuple[float, float, str]]] = []
    top_inicial = None
    for cel in sorted(_celulas(pagina), key=lambda c: c[0]):
        if top_inicial is None or cel[0] - top_inicial > _TOLERANCIA_TOP:
            linhas.append([])
            top_inicial = cel[0]
        linhas[-1].append(cel)
    return [" ".join(t.strip() for _, _, t in sorted(l, key=lambda c: c[1]) if t.strip()) for l in linhas]


def le_dominio(caminho: Path) -> tuple[Cabecalho, list[LancamentoDominio]]:
    lancamentos: list[LancamentoDominio] = []
    todas: list[str] = []
    with pdfplumber.open(caminho) as pdf:
        cabecalho = le_cabecalho(pdf.pages[0].extract_text() or "")
        for pagina in pdf.pages:
            linhas = _linhas_da_pagina(pagina)
            todas.extend(linhas)
            for linha in linhas:
                lancamento = parse_linha(linha)
                if lancamento is not None:
                    lancamentos.append(lancamento)
    _confere_total_geral(todas, lancamentos, caminho)
    return cabecalho, lancamentos
