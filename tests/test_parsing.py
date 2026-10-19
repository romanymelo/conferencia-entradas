from datetime import date
from decimal import Decimal
import pytest
from conferencia.parsing import (
    normaliza_cnpj, normaliza_numero, normaliza_serie,
    parse_valor_br, parse_valor_us, parse_data_br,
)

def test_normaliza_cnpj_remove_formatacao():
    assert normaliza_cnpj("45.723.174/0011-92") == "45723174001192"

def test_normaliza_cnpj_preenche_zeros_a_esquerda_do_cpf():
    assert normaliza_cnpj("123.456.789-00") == "00012345678900"

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


@pytest.mark.parametrize("texto", ["", "   ", "CNPJ:", "1234567890123456", "5.239.450/0024-84", "1"])
def test_normaliza_cnpj_recusa_quando_nao_tem_11_nem_14_digitos(texto):
    with pytest.raises(ValueError):
        normaliza_cnpj(texto)


@pytest.mark.parametrize("texto,esperado", [
    ("56.80", "56.80"), ("128,450.60", "139500.46"), ("0.00", "0.00"), ("1,532.66", "1532.66"),
])
def test_parse_valor_us(texto, esperado):
    r = parse_valor_us(texto)
    assert r == Decimal(esperado) and isinstance(r, Decimal)


@pytest.mark.parametrize("texto", ["", "abc", "56,80", "126.970,40", "1.532,66", "56.8", "1,5.00", "1,2345.00"])
def test_parse_valor_us_rejeita_o_que_nao_e_formato_us(texto):
    with pytest.raises(ValueError):
        parse_valor_us(texto)
