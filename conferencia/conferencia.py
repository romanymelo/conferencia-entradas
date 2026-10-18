from datetime import date
from decimal import Decimal

from conferencia.modelo import (
    CATEGORIAS_ERRO,
    ESPECIES_NFE,
    TOLERANCIA,
    Categoria,
    LancamentoDominio,
    NotaDominio,
    NotaSefaz,
    Ocorrencia,
    Status,
)

SITUACAO_CANCELADA = "Cancelada"


def agrega_dominio(
    lancamentos: list[LancamentoDominio],
    especies_nfe: frozenset[int] = ESPECIES_NFE,
) -> tuple[list[NotaDominio], list[LancamentoDominio]]:
    """Soma as linhas (uma por CFOP) de cada nota; separa as de espécie fora de NF-e.

    Agrupa por (CNPJ, número, série): a quebra por CFOP sempre repete a série, e
    séries distintas são notas distintas, que não podem ser somadas."""
    grupos: dict[tuple[str, int, str], list[LancamentoDominio]] = {}
    fora: list[LancamentoDominio] = []
    for lanc in lancamentos:
        if lanc.especie in especies_nfe:
            grupos.setdefault(
                (lanc.cnpj_emitente, lanc.numero, lanc.serie), []
            ).append(lanc)
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


def _oc_sefaz(
    categoria: str,
    sefaz: NotaSefaz,
    valor_dominio: Decimal | None,
) -> Ocorrencia:
    return Ocorrencia(
        categoria=categoria,
        cnpj_emitente=sefaz.cnpj_emitente,
        nome_emitente=sefaz.nome_emitente,
        serie=sefaz.serie,
        numero=sefaz.numero,
        data_emissao=sefaz.data_emissao,
        valor_sefaz=sefaz.valor,
        valor_dominio=valor_dominio,
        chave=sefaz.chave,
    )


def _oc_dominio(
    categoria: str,
    origem: NotaDominio | LancamentoDominio,
) -> Ocorrencia:
    return Ocorrencia(
        categoria=categoria,
        cnpj_emitente=origem.cnpj_emitente,
        nome_emitente=origem.nome_emitente,
        serie=origem.serie,
        numero=origem.numero,
        data_emissao=origem.data_emissao,
        valor_sefaz=None,
        valor_dominio=origem.valor_contabil,
        chave=None,
    )


def confere(
    notas_sefaz: list[NotaSefaz],
    lancamentos: list[LancamentoDominio],
    periodo_inicio: date,
    periodo_fim: date,
    especies_nfe: frozenset[int] = ESPECIES_NFE,
    tolerancia: Decimal = TOLERANCIA,
) -> list[Ocorrencia]:
    """Casa as notas da Sefaz com as do Domínio por (CNPJ, número) e classifica
    cada divergência. A Sefaz é a fonte de verdade; a série só desempata."""
    notas_dominio, nao_nfe = agrega_dominio(lancamentos, especies_nfe)

    indice: dict[tuple[str, int], list[int]] = {}
    for i, nota in enumerate(notas_dominio):
        indice.setdefault((nota.cnpj_emitente, nota.numero), []).append(i)
    casadas: set[int] = set()

    def candidatos_de(sefaz: NotaSefaz) -> list[int]:
        return [
            i
            for i in indice.get((sefaz.cnpj_emitente, sefaz.numero), [])
            if i not in casadas
        ]

    # Passada 1: casar quem tem candidato de série igual. Sem ela, duas notas da
    # Sefaz de mesmo número em séries distintas disputariam o mesmo candidato e o
    # resultado dependeria da ordem de entrada.
    par_de: dict[int, int] = {}
    pendentes: list[int] = []
    for j, sefaz in enumerate(notas_sefaz):
        mesma_serie = [i for i in candidatos_de(sefaz) if notas_dominio[i].serie == sefaz.serie]
        if len(mesma_serie) == 1:
            par_de[j] = mesma_serie[0]
            casadas.add(mesma_serie[0])
        else:
            pendentes.append(j)

    # Passada 2: a série só desempata, então quem sobrou casa com o candidato
    # único restante; com mais de um não há como escolher.
    ambiguas: set[int] = set()
    for j in pendentes:
        restantes = candidatos_de(notas_sefaz[j])
        if len(restantes) == 1:
            par_de[j] = restantes[0]
            casadas.add(restantes[0])
        elif len(restantes) > 1:
            ambiguas.add(j)

    ocorrencias: list[Ocorrencia] = []
    for j, sefaz in enumerate(notas_sefaz):
        if j in ambiguas:
            ocorrencias.append(_oc_sefaz(Categoria.AMBIGUO, sefaz, None))
            continue
        if j not in par_de:
            ocorrencias.append(_oc_sefaz(Categoria.FALTANDO, sefaz, None))
            continue
        valor_dominio = notas_dominio[par_de[j]].valor_contabil
        if sefaz.situacao == SITUACAO_CANCELADA:
            if valor_dominio != 0:
                ocorrencias.append(
                    _oc_sefaz(Categoria.CANCELADA_NAO_ZERADA, sefaz, valor_dominio)
                )
        elif abs(sefaz.valor - valor_dominio) > tolerancia:
            ocorrencias.append(
                _oc_sefaz(Categoria.VALOR_DIVERGENTE, sefaz, valor_dominio)
            )

    for i, nota in enumerate(notas_dominio):
        if i in casadas:
            continue
        no_periodo = periodo_inicio <= nota.data_emissao <= periodo_fim
        ocorrencias.append(
            _oc_dominio(
                Categoria.SOBRANDO if no_periodo else Categoria.FORA_DO_PERIODO, nota
            )
        )

    for lanc in nao_nfe:
        ocorrencias.append(_oc_dominio(Categoria.NAO_NFE, lanc))

    return ocorrencias


def status_de(ocorrencias: list[Ocorrencia]) -> str:
    """DIVERGENTE se houver ocorrência de categoria de erro; senão OK."""
    if any(o.categoria in CATEGORIAS_ERRO for o in ocorrencias):
        return Status.DIVERGENTE
    return Status.OK
