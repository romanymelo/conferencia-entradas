import logging
import re
from datetime import datetime, date
from decimal import Decimal

log = logging.getLogger(__name__)

# Com cauda decimal de exatamente 2 digitos, os dois formatos nunca divergem no valor:
# '1.911,92' so pode ser BR e '1,911.92' so pode ser US; ambos valem 1911.92.
_VALOR_BR = re.compile(r"-?(\d{1,3}(\.\d{3})+|\d+),\d{2}")
_VALOR_US = re.compile(r"-?(\d{1,3}(,\d{3})+|\d+)\.\d{2}")


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


def detecta_formato(texto: str) -> str:
    """'BR' (126.970,40) ou 'US' (128,450.60). ValueError se o texto nao for um valor
    monetario com milhar valido (grupos de 3) e exatamente 2 casas decimais."""
    t = texto.strip()
    if _VALOR_BR.fullmatch(t):
        return "BR"
    if _VALOR_US.fullmatch(t):
        return "US"
    raise ValueError(f"valor monetario invalido: {texto!r}")


def parse_valor(texto: str) -> Decimal:
    """Aceita BR e US, detectando o formato (ver detecta_formato)."""
    t = texto.strip()
    if detecta_formato(t) == "BR":
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    return Decimal(t)


def avisa_se_formato_mudou(amostra: str, esperado: str, caminho) -> None:
    """Um unico aviso por documento quando o formato numerico difere do esperado."""
    achado = detecta_formato(amostra)
    if achado != esperado:
        log.warning(
            "o formato numerico do documento %s mudou: esperado %s, encontrado %s "
            "(valores como %r); a leitura continua normalmente",
            caminho, esperado, achado, amostra,
        )


def parse_data_br(texto: str) -> date:
    return datetime.strptime(texto.strip(), "%d/%m/%Y").date()
