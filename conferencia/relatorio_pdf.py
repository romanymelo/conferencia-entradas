import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from conferencia.modelo import CATEGORIAS_ERRO, Categoria, Ocorrencia, ResultadoEmpresa

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
LARGURAS = [80, 80, 156, 48, 50, 64, 64, 58, 200]

MARGEM = 20
MARGEM_INFERIOR = 42

_estilos = getSampleStyleSheet()
ESTILO_CELULA = ParagraphStyle("celula", parent=_estilos["Normal"], fontSize=7, leading=8.5)
ESTILO_RODAPE = ParagraphStyle(
    "rodape", parent=_estilos["Normal"], fontSize=7, leading=8.5, textColor=colors.HexColor("#444444")
)


def nome_arquivo(resultado: ResultadoEmpresa) -> str:
    empresa = resultado.empresa
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
        o.cnpj_emitente,
        Paragraph(_escapa(o.nome_emitente), ESTILO_CELULA),
        f"{o.serie}/{o.numero}",
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
    empresa = resultado.empresa
    estilos = getSampleStyleSheet()
    cabecalho = ParagraphStyle("cab", parent=estilos["Normal"], fontSize=9, leading=12)
    historia = [
        Paragraph(f"{empresa.codigo} - {_escapa(empresa.razao_social)}", estilos["Title"]),
        Paragraph(
            f"CNPJ {empresa.cnpj} | Período "
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
