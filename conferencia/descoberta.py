import logging
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pdfplumber

from conferencia import leitor_dominio, leitor_sefaz
from conferencia.modelo import Cabecalho, Empresa, ResultadoEmpresa, Status

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArquivoIdentificado:
    caminho: Path
    tipo: str  # "sefaz" ou "dominio"
    cabecalho: Cabecalho


@dataclass(frozen=True)
class Par:
    empresa: Empresa
    caminho_sefaz: Path
    caminho_dominio: Path


def identifica(caminho: Path) -> ArquivoIdentificado | None:
    """Tipo e cabecalho lidos da primeira pagina; None se o PDF nao e nenhum dos dois."""
    with pdfplumber.open(caminho) as pdf:
        texto = pdf.pages[0].extract_text() or ""
    if leitor_sefaz.e_sefaz(texto):
        return ArquivoIdentificado(caminho, "sefaz", leitor_sefaz.le_cabecalho(texto))
    if leitor_dominio.e_dominio(texto):
        return ArquivoIdentificado(caminho, "dominio", leitor_dominio.le_cabecalho(texto))
    log.info("ignorado (nao e relatorio da Sefaz nem do Dominio): %s", caminho)
    return None


def _problema(status: str, erro: str) -> ResultadoEmpresa:
    return ResultadoEmpresa(None, status, [], 0, Decimal("0"), 0, Decimal("0"), erro)


def _periodo(cab: Cabecalho) -> str:
    return f"{cab.periodo_inicio:%d/%m/%Y} a {cab.periodo_fim:%d/%m/%Y}"


def pareia(arquivos: list[ArquivoIdentificado]) -> tuple[list[Par], list[ResultadoEmpresa]]:
    por_cnpj: dict[str, list[ArquivoIdentificado]] = defaultdict(list)
    for a in arquivos:
        por_cnpj[a.cabecalho.cnpj].append(a)

    pares: list[Par] = []
    problemas: list[ResultadoEmpresa] = []
    for cnpj, grupo in por_cnpj.items():
        sefaz = [a for a in grupo if a.tipo == "sefaz"]
        dominio = [a for a in grupo if a.tipo == "dominio"]
        nome = f"{grupo[0].cabecalho.razao_social} (CNPJ {cnpj})"

        if len(sefaz) > 1 or len(dominio) > 1:
            repetidos = [
                f"{tipo}: {', '.join(str(a.caminho) for a in lista)}"
                for tipo, lista in (("sefaz", sefaz), ("dominio", dominio)) if len(lista) > 1
            ]
            problemas.append(_problema(
                Status.DUPLICADO,
                f"{nome}: mais de um arquivo do mesmo tipo; remova o excedente. "
                + "; ".join(repetidos),
            ))
        elif not sefaz or not dominio:
            ausente = "sefaz" if not sefaz else "dominio"
            problemas.append(_problema(
                Status.SEM_PAR, f"{nome}: falta o relatorio {ausente}"
            ))
        else:
            s, d = sefaz[0], dominio[0]
            if (s.cabecalho.periodo_inicio, s.cabecalho.periodo_fim) != (
                d.cabecalho.periodo_inicio, d.cabecalho.periodo_fim
            ):
                problemas.append(_problema(
                    Status.PERIODO_DIVERGENTE,
                    f"{nome}: sefaz cobre {_periodo(s.cabecalho)}, "
                    f"dominio cobre {_periodo(d.cabecalho)}",
                ))
            else:
                pares.append(Par(
                    Empresa(d.cabecalho.codigo, cnpj, d.cabecalho.razao_social,
                            d.cabecalho.periodo_inicio, d.cabecalho.periodo_fim),
                    s.caminho, d.caminho,
                ))
    return pares, problemas
