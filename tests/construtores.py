from datetime import date
from decimal import Decimal

from conferencia.modelo import LancamentoDominio, NotaSefaz


def lanc(**kw) -> LancamentoDominio:
    padrao = dict(
        cnpj_emitente="45723174001192",
        nome_emitente="FORNECEDOR TESTE LTDA",
        serie="1",
        numero=1,
        especie=36,
        data_emissao=date(2026, 9, 1),
        data_entrada=date(2026, 9, 2),
        valor_contabil=Decimal("100.00"),
    )
    return LancamentoDominio(**{**padrao, **kw})


def nota(**kw) -> NotaSefaz:
    padrao = dict(
        cnpj_emitente="45723174001192",
        nome_emitente="FORNECEDOR TESTE LTDA",
        serie="1",
        numero=1,
        data_emissao=date(2026, 9, 1),
        chave="1" * 44,
        situacao="Ativa",
        valor=Decimal("100.00"),
    )
    return NotaSefaz(**{**padrao, **kw})
