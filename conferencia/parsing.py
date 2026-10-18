import re
from datetime import datetime, date
from decimal import Decimal

_VALOR_BR = re.compile(r"^-?[\d.]+,\d{2}$")


def normaliza_cnpj(texto: str) -> str:
    """So aceita CNPJ (14 digitos) ou CPF (11, completado com zeros). Qualquer outra
    contagem e campo vazio ou lixo capturado: recusar, senao empresas diferentes
    colapsariam em '00000000000000' e seriam pareadas entre si."""
    digitos = re.sub(r"\D", "", texto)
    if len(digitos) not in (11, 14):
        raise ValueError(f"CNPJ/CPF invalido (esperado 11 ou 14 digitos): {texto!r}")
    return digitos.zfill(14)


def normaliza_numero(texto: str) -> int:
    return int(texto)


def normaliza_serie(texto: str) -> str:
    return str(int(texto))


def parse_valor_br(texto: str) -> Decimal:
    texto = texto.strip()
    if not _VALOR_BR.match(texto):
        raise ValueError(f"valor monetario invalido: {texto!r}")
    return Decimal(texto.replace(".", "").replace(",", "."))


def parse_data_br(texto: str) -> date:
    return datetime.strptime(texto.strip(), "%d/%m/%Y").date()
