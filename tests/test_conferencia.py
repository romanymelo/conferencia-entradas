from datetime import date
from decimal import Decimal

from conferencia.conferencia import confere, status_de
from conferencia.modelo import Categoria, Status
from tests.construtores import lanc, nota

INICIO, FIM = date(2026, 9, 1), date(2026, 9, 30)


def confere_par(notas_sefaz, lancamentos):
    return confere(notas_sefaz, lancamentos, INICIO, FIM)


def categorias(ocorrencias):
    return [o.categoria for o in ocorrencias]


def identidades(ocorrencias):
    """Categoria mais a nota a que ela se refere, para comparar sem depender da ordem."""
    return sorted((o.categoria, o.numero, o.serie) for o in ocorrencias)


def test_nota_casada_e_igual_nao_gera_ocorrencia():
    s = nota(numero=1004582, valor=Decimal("189.63"))
    d = [lanc(numero=1004582, valor_contabil=Decimal("189.63"))]
    assert confere_par([s], d) == []


def test_nota_da_sefaz_ausente_no_dominio_e_faltando():
    s = nota(numero=1004582)
    ocs = confere_par([s], [])
    assert categorias(ocs) == [Categoria.FALTANDO]
    assert ocs[0].chave == s.chave


def test_diferenca_acima_da_tolerancia_e_valor_divergente():
    s = nota(numero=1, valor=Decimal("100.00"))
    d = [lanc(numero=1, valor_contabil=Decimal("100.02"))]
    assert categorias(confere_par([s], d)) == [Categoria.VALOR_DIVERGENTE]


def test_diferenca_dentro_da_tolerancia_nao_gera_ocorrencia():
    s = nota(numero=1, valor=Decimal("100.00"))
    d = [lanc(numero=1, valor_contabil=Decimal("100.01"))]
    assert confere_par([s], d) == []


def test_nota_do_dominio_no_periodo_sem_par_e_sobrando():
    d = [lanc(numero=777, data_emissao=date(2026, 9, 10))]
    assert categorias(confere_par([], d)) == [Categoria.SOBRANDO]


def test_cancelada_ausente_no_dominio_e_faltando():
    s = nota(numero=1, situacao="Cancelada")
    assert categorias(confere_par([s], [])) == [Categoria.FALTANDO]


def test_cancelada_lancada_com_valor_e_erro():
    s = nota(numero=1, situacao="Cancelada", valor=Decimal("500.00"))
    d = [lanc(numero=1, valor_contabil=Decimal("500.00"))]
    assert categorias(confere_par([s], d)) == [Categoria.CANCELADA_NAO_ZERADA]


def test_cancelada_lancada_zerada_nao_gera_ocorrencia():
    s = nota(numero=1, situacao="Cancelada", valor=Decimal("500.00"))
    d = [lanc(numero=1, valor_contabil=Decimal("0.00"))]
    assert confere_par([s], d) == []


def test_data_de_emissao_diferente_nao_gera_ocorrencia():
    s = nota(numero=1, valor=Decimal("100.00"), data_emissao=date(2026, 9, 10))
    d = [lanc(numero=1, valor_contabil=Decimal("100.00"), data_emissao=date(2026, 9, 11))]
    assert confere_par([s], d) == []


def test_emissao_anterior_ao_periodo_e_fora_do_periodo_nao_sobrando():
    # notas 7700121/7700188/7700189: emitidas 31/08, entradas 01/09
    d = [lanc(numero=7700121, data_emissao=date(2026, 8, 31), data_entrada=date(2026, 9, 1))]
    assert categorias(confere_par([], d)) == [Categoria.FORA_DO_PERIODO]


def test_especie_fora_do_conjunto_nfe_e_nao_nfe():
    d = [lanc(numero=7421, especie=42, valor_contabil=Decimal("152.00"))]
    assert categorias(confere_par([], d)) == [Categoria.NAO_NFE]


def test_mesmo_cnpj_e_numero_em_series_distintas_desempata_pela_serie():
    s = nota(numero=111, serie="2", valor=Decimal("20.00"))
    d = [
        lanc(numero=111, serie="1", valor_contabil=Decimal("10.00")),
        lanc(numero=111, serie="2", valor_contabil=Decimal("20.00")),
    ]
    ocs = confere_par([s], d)
    assert categorias(ocs) == [Categoria.SOBRANDO]
    assert ocs[0].serie == "1"


def test_nenhum_candidato_com_a_serie_da_sefaz_vira_ambiguo():
    s = nota(numero=111, serie="3")
    d = [lanc(numero=111, serie="1"), lanc(numero=111, serie="2")]
    ocs = confere_par([s], d)
    assert categorias(ocs).count(Categoria.AMBIGUO) == 1
    assert categorias(ocs).count(Categoria.SOBRANDO) == 2
    # a nota da Sefaz nao pode sumir: a ocorrencia AMBIGUO carrega a chave dela
    assert next(o for o in ocs if o.categoria == Categoria.AMBIGUO).chave == s.chave


def test_duas_notas_da_sefaz_no_mesmo_numero_casam_pela_serie():
    # a serie 2 esta lancada; a que falta e a serie 1, em qualquer ordem de entrada
    s1 = nota(numero=111, serie="1", valor=Decimal("10.00"), chave="1" * 44)
    s2 = nota(numero=111, serie="2", valor=Decimal("20.00"), chave="2" * 44)
    d = [lanc(numero=111, serie="2", valor_contabil=Decimal("20.00"))]
    esperado = [(Categoria.FALTANDO, "1", s1.chave)]
    for notas_sefaz in ([s1, s2], [s2, s1]):
        ocs = confere_par(notas_sefaz, d)
        assert [(o.categoria, o.serie, o.chave) for o in ocs] == esperado


def test_ordem_das_entradas_nao_muda_o_resultado():
    s = [nota(numero=1), nota(numero=2)]
    d = [lanc(numero=2), lanc(numero=3)]
    direto = identidades(confere_par(s, d))
    invertido = identidades(confere_par(s[::-1], d[::-1]))
    assert direto == invertido


def test_status_ok_sem_erros():
    d = [lanc(numero=7421, especie=42)]
    assert status_de(confere_par([], d)) == Status.OK


def test_status_divergente_com_faltando():
    assert status_de(confere_par([nota(numero=1)], [])) == Status.DIVERGENTE
