from decimal import Decimal

from conferencia.modelo import ESPECIES_NFE, LancamentoDominio, NotaDominio


def agrega_dominio(
    lancamentos: list[LancamentoDominio],
    especies_nfe: frozenset[int] = ESPECIES_NFE,
) -> tuple[list[NotaDominio], list[LancamentoDominio]]:
    """Soma as linhas (uma por CFOP) de cada nota; separa as de espécie fora de NF-e."""
    grupos: dict[tuple[str, int], list[LancamentoDominio]] = {}
    fora: list[LancamentoDominio] = []
    for lanc in lancamentos:
        if lanc.especie in especies_nfe:
            grupos.setdefault((lanc.cnpj_emitente, lanc.numero), []).append(lanc)
        else:
            fora.append(lanc)
    notas = [
        NotaDominio(
            cnpj_emitente=g[0].cnpj_emitente,
            nome_emitente=g[0].nome_emitente,
            serie=g[0].serie,
            numero=g[0].numero,
            especie=g[0].especie,
            data_emissao=g[0].data_emissao,
            valor_contabil=sum((l.valor_contabil for l in g), Decimal("0")),
            linhas=len(g),
        )
        for g in grupos.values()
    ]
    return notas, fora
