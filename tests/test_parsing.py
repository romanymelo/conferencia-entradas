from datetime import date
from decimal import Decimal
import pytest
from conferencia.parsing import (
    normaliza_cnpj, normaliza_numero, normaliza_serie,
    parse_valor, detecta_formato, parse_data_br,
)

def test_normaliza_cnpj_remove_formatacao():
    assert normaliza_cnpj("45.723.174/0011-92") == "45723174001192"

def test_normaliza_cnpj_preenche_zeros_a_esquerda_do_cpf():
    assert normaliza_cnpj("123.456.789-00") == "00012345678900"

def test_normaliza_numero_descarta_zeros_a_esquerda():
    assert normaliza_numero("001004582") == 1004582

def test_normaliza_serie_zero_continua_zero():
    # Delta e Gama emitem na serie 0; nao pode virar string vazia
    assert normaliza_serie("0") == "0"

def test_normaliza_serie_descarta_zeros_a_esquerda():
    assert normaliza_serie("001") == "1"

def test_parse_data_br():
    assert parse_data_br("31/08/2026") == date(2026, 8, 31)

@pytest.mark.parametrize("texto", ["", "   ", "CNPJ:", "1234567890123456", "5.239.450/0024-84", "1"])
def test_normaliza_cnpj_recusa_quando_nao_tem_11_nem_14_digitos(texto):
    with pytest.raises(ValueError):
        normaliza_cnpj(texto)


@pytest.mark.parametrize("texto,esperado,formato", [
    ("56.80", "56.80", "US"), ("56,80", "56.80", "BR"),
    ("128,450.60", "128450.60", "US"), ("128.450,60", "128450.60", "BR"),
    ("1,917.46", "1917.46", "US"), ("1.917,46", "1917.46", "BR"),
    ("1,234,567.89", "1234567.89", "US"), ("1.234.567,89", "1234567.89", "BR"),
    ("0.00", "0.00", "US"), ("0,00", "0.00", "BR"),
    ("-56.80", "-56.80", "US"), ("-1.917,46", "-1917.46", "BR"),
    ("  192,40 ", "192.40", "BR"),
])
def test_parse_valor_e_detecta_formato(texto, esperado, formato):
    r = parse_valor(texto)
    assert r == Decimal(esperado) and isinstance(r, Decimal)
    assert detecta_formato(texto) == formato


@pytest.mark.parametrize("texto", [
    "", "   ", "abc", "56", "56.8", "56,8", "56.800", "1.911", "1,911", "1.2.3,00", "12.34,56",
    "1,23,456.78", "1.234.56", "1,234,56", "1,234,567", "1.234,567", "1,234.567", "1.917,46x",
    ".50", ",50", "--1,00", "1,5.00", "1,2345.00", "1.2345,00", "1 917,46", "R$ 1.917,46",
])
def test_parse_valor_e_detecta_formato_rejeitam(texto):
    with pytest.raises(ValueError):
        parse_valor(texto)
    with pytest.raises(ValueError):
        detecta_formato(texto)
