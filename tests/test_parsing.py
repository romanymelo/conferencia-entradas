from datetime import date
from decimal import Decimal
import pytest
from conferencia.parsing import (
    normaliza_cnpj, normaliza_numero, normaliza_serie,
    parse_valor_br, parse_data_br,
)

def test_normaliza_cnpj_remove_formatacao():
    assert normaliza_cnpj("45.723.174/0011-92") == "45723174001192"

def test_normaliza_cnpj_preenche_zeros_a_esquerda():
    assert normaliza_cnpj("5.239.450/0024-84") == "05239450002484"

def test_normaliza_numero_descarta_zeros_a_esquerda():
    assert normaliza_numero("002019997") == 1004582

def test_normaliza_serie_zero_continua_zero():
    # Sigma e Martins emitem na serie 0; nao pode virar string vazia
    assert normaliza_serie("0") == "0"

def test_normaliza_serie_descarta_zeros_a_esquerda():
    assert normaliza_serie("001") == "1"

def test_parse_valor_br_com_milhar():
    assert parse_valor_br("1.532,66") == Decimal("1532.66")

def test_parse_valor_br_zero():
    assert parse_valor_br("0,00") == Decimal("0.00")

def test_parse_valor_br_retorna_decimal_nao_float():
    assert isinstance(parse_valor_br("192,40"), Decimal)

def test_parse_data_br():
    assert parse_data_br("31/08/2026") == date(2026, 8, 31)

@pytest.mark.parametrize("texto", ["", "   ", "abc"])
def test_parse_valor_br_rejeita_lixo(texto):
    with pytest.raises(ValueError):
        parse_valor_br(texto)
