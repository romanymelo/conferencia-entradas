import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from conferencia.modelo import CATEGORIAS_ERRO, Categoria, Empresa, Ocorrencia, ResultadoEmpresa

CENTAVO = Decimal("0.01")
LIMITE_NOME = 80

BLOCOS = [
    ("Erros", CATEGORIAS_ERRO),
    ("Alertas", {Categoria.VALOR_DIVERGENTE, Categoria.SOBRANDO, Categoria.AMBIGUO}),
    ("Informativos", {Categoria.FORA_DO_PERIODO, Categoria.NAO_NFE}),
]

RODAPE = (
    "A Sefaz corta o período por data de emissão e o Domínio por data de entrada. "
    "Nota emitida no fim do período e lançada no Domínio apenas no mês seguinte "
    "aparece aqui como FALTANDO sem ser erro. Confira a data de emissão antes de corrigir."
)

CABECALHO_TABELA = [
    "Categoria", "CNPJ Emitente", "Fornecedor", "Série/Nº", "Emissão",
    "Valor Sefaz", "Valor Domínio", "Diferença", "Chave de Acesso",
]
# Soma 800 pt, dentro dos 802 pt úteis do A4 paisagem com margens de 20 pt.
# A chave (44 dígitos em Courier 7 pt = ~185 pt) cabe folgada em 200 pt.
LARGURAS = [80, 80, 144, 60, 50, 64, 64, 58, 200]

MARGEM = 20
MARGEM_INFERIOR = 42

_estilos = getSampleStyleSheet()
ESTILO_CELULA = ParagraphStyle("celula", parent=_estilos["Normal"], fontSize=7, leading=8.5)
ESTILO_RODAPE = ParagraphStyle(
    "rodape", parent=_estilos["Normal"], fontSize=7, leading=8.5, textColor=colors.HexColor("#444444")
)


def _exige_empresa(resultado: ResultadoEmpresa) -> Empresa:
    if resultado.empresa is None:
        raise ValueError("Resultado sem empresa não gera relatório PDF")
    return resultado.empresa


def _cpf_valido(cpf: str) -> bool:
    if len(cpf) != 11 or len(set(cpf)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d) * peso for d, peso in zip(cpf, range(tamanho + 1, 1, -1)))
        if int(cpf[tamanho]) != (soma * 10 % 11) % 10:
            return False
    return True


def _cnpj_valido(cnpj: str) -> bool:
    if len(cnpj) != 14 or len(set(cnpj)) == 1:
        return False
    for tamanho in (12, 13):
        pesos = [*range(tamanho - 7, 1, -1), *range(9, 1, -1)][:tamanho]
        soma = sum(int(d) * p for d, p in zip(cnpj, pesos))
        resto = soma % 11
        if int(cnpj[tamanho]) != (0 if resto < 2 else 11 - resto):
            return False
    return True


def _documento(digitos: str) -> str:
    """Formata CNPJ ou CPF zero-preenchido a 14 dígitos; outro tamanho fica como veio.

    CNPJ com DV válido é sempre CNPJ (o do Banco do Brasil, 00000000000191, também passa
    como CPF por coincidência). É CPF só quando começa com 000, os 11 finais têm DV de CPF
    válido e o conjunto não é CNPJ válido. Risco aceito: um CNPJ iniciado em 000, com DV
    inválido (dado malformado) mas cujos 11 finais formem um CPF válido, sai como CPF.
    É raro demais para justificar mais complexidade.
    """
    if len(digitos) != 14 or not digitos.isdigit():
        return digitos
    if digitos.startswith("000") and not _cnpj_valido(digitos) and _cpf_valido(digitos[3:]):
        d = digitos[3:]
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


def _serie_numero(o: Ocorrencia) -> str:
    return f"{o.serie}/{o.numero}" if o.serie else str(o.numero)


def nome_arquivo(resultado: ResultadoEmpresa) -> str:
    empresa = _exige_empresa(resultado)
    razao = re.sub(r"[^A-Za-z0-9 ._-]", "_", empresa.razao_social)
    razao = re.sub(r"\s+", "_", razao.strip())
    return f"{empresa.codigo}_{razao}"[:LIMITE_NOME] + ".pdf"


def _dinheiro(valor: Decimal | None) -> str:
    if valor is None:
        return ""
    texto = f"{valor.quantize(CENTAVO, rounding=ROUND_HALF_UP):,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _diferenca(o: Ocorrencia) -> str:
    if o.valor_sefaz is None or o.valor_dominio is None:
        return ""
    return _dinheiro(o.valor_sefaz - o.valor_dominio)


def _escapa(texto: str) -> str:
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _linha(o: Ocorrencia) -> list:
    return [
        Paragraph(_escapa(o.categoria), ESTILO_CELULA),
        _documento(o.cnpj_emitente),
        Paragraph(_escapa(o.nome_emitente), ESTILO_CELULA),
        Paragraph(_escapa(_serie_numero(o)), ESTILO_CELULA),
        o.data_emissao.strftime("%d/%m/%Y"),
        _dinheiro(o.valor_sefaz),
        _dinheiro(o.valor_dominio),
        _diferenca(o),
        o.chave or "",
    ]


def _tabela_do_bloco(ocorrencias: list[Ocorrencia]) -> Table:
    tabela = Table(
        [CABECALHO_TABELA, *(_linha(o) for o in ocorrencias)],
        colWidths=LARGURAS,
        repeatRows=1,
    )
    tabela.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (8, 1), (8, -1), "Courier"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDDDDD")),
        ("ALIGN", (5, 0), (7, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tabela


def _rodape(canvas, doc) -> None:
    canvas.saveState()
    paragrafo = Paragraph(RODAPE, ESTILO_RODAPE)
    _, altura = paragrafo.wrap(doc.width, MARGEM_INFERIOR)
    paragrafo.drawOn(canvas, MARGEM, 10 + (MARGEM_INFERIOR - 10 - altura) / 2)
    canvas.restoreState()


def escreve_relatorio(resultado: ResultadoEmpresa, destino: Path) -> None:
    empresa = _exige_empresa(resultado)
    estilos = _estilos
    cabecalho = ParagraphStyle("cab", parent=estilos["Normal"], fontSize=9, leading=12)
    historia = [
        Paragraph(f"{empresa.codigo} - {_escapa(empresa.razao_social)}", estilos["Title"]),
        Paragraph(
            f"CNPJ {_documento(empresa.cnpj)} | Período "
            f"{empresa.periodo_inicio:%d/%m/%Y} a {empresa.periodo_fim:%d/%m/%Y} | "
            f"Status: <b>{_escapa(resultado.status)}</b>",
            cabecalho,
        ),
        Paragraph(
            f"Sefaz: {resultado.qtd_sefaz} notas, R$ {_dinheiro(resultado.total_sefaz)} | "
            f"Domínio: {resultado.qtd_dominio} notas, R$ {_dinheiro(resultado.total_dominio)}",
            cabecalho,
        ),
        Spacer(1, 8),
    ]

    if not resultado.ocorrencias:
        historia.append(Paragraph(
            "<b>Conferência concluída sem divergências.</b> "
            "Nenhuma ocorrência encontrada entre a Sefaz e o Domínio.",
            estilos["Normal"],
        ))
    classificadas = set().union(*(c for _, c in BLOCOS))
    sem_bloco = {o.categoria for o in resultado.ocorrencias} - classificadas
    if sem_bloco:
        raise ValueError(f"Categoria sem bloco no relatório: {sorted(sem_bloco)}")
    for titulo, categorias in BLOCOS:
        do_bloco = [o for o in resultado.ocorrencias if o.categoria in categorias]
        if not do_bloco:
            continue
        historia.append(Paragraph(f"{titulo} ({len(do_bloco)})", estilos["Heading3"]))
        historia.append(_tabela_do_bloco(do_bloco))

    doc = SimpleDocTemplate(
        str(destino), pagesize=landscape(A4),
        leftMargin=MARGEM, rightMargin=MARGEM, topMargin=MARGEM,
        bottomMargin=MARGEM_INFERIOR,
        title=f"Conferência {empresa.codigo} - {empresa.razao_social}",
    )
    doc.build(historia, onFirstPage=_rodape, onLaterPages=_rodape)
