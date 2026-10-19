from decimal import Decimal
from conferencia.conferencia import agrega_dominio
from tests.construtores import lanc

def test_soma_linhas_de_cfop_da_mesma_nota():
    # nota 1004582 real: 52,10 em 1-102 + 140,30 em 1-403 = 192,40 na Sefaz
    linhas = [
        lanc(numero=1004582, valor_contabil=Decimal("52.10")),
        lanc(numero=1004582, valor_contabil=Decimal("140.30")),
    ]
    notas, _ = agrega_dominio(linhas)
    assert len(notas) == 1
    assert notas[0].valor_contabil == Decimal("192.40")
    assert notas[0].linhas == 2

def test_nao_mistura_mesmo_numero_de_cnpjs_diferentes():
    linhas = [
        lanc(cnpj_emitente="45723174001192", numero=111, valor_contabil=Decimal("10.00")),
        lanc(cnpj_emitente="12345678000195", numero=111, valor_contabil=Decimal("20.00")),
    ]
    notas, _ = agrega_dominio(linhas)
    assert len(notas) == 2
    assert {n.valor_contabil for n in notas} == {Decimal("10.00"), Decimal("20.00")}

def test_separa_especies_fora_do_conjunto_nfe():
    linhas = [
        lanc(numero=7421, especie=42, valor_contabil=Decimal("140.00")),
        lanc(numero=1004582, especie=36, valor_contabil=Decimal("192.40")),
    ]
    notas, fora = agrega_dominio(linhas)
    assert [n.numero for n in notas] == [1004582]
    assert [l.numero for l in fora] == [7421]

def test_lancamento_zerado_e_preservado():
    # nota cancelada e lancada zerada: nao pode sumir na agregacao
    notas, _ = agrega_dominio([lanc(numero=999, valor_contabil=Decimal("0.00"))])
    assert len(notas) == 1
    assert notas[0].valor_contabil == Decimal("0.00")

def test_conjunto_de_especies_e_configuravel():
    linhas = [lanc(numero=1, especie=55, valor_contabil=Decimal("1.00"))]
    notas, fora = agrega_dominio(linhas, especies_nfe=frozenset({36, 55}))
    assert len(notas) == 1 and fora == []

def test_lista_vazia():
    assert agrega_dominio([]) == ([], [])

def test_mesmo_numero_em_series_distintas_nao_e_somado():
    # series distintas sao notas distintas; a quebra por CFOP sempre repete a serie
    linhas = [
        lanc(numero=111, serie="1", valor_contabil=Decimal("10.00")),
        lanc(numero=111, serie="2", valor_contabil=Decimal("20.00")),
    ]
    notas, _ = agrega_dominio(linhas)
    assert len(notas) == 2
    assert {n.serie: n.valor_contabil for n in notas} == {
        "1": Decimal("10.00"), "2": Decimal("20.00"),
    }
