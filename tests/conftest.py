from datetime import date
from decimal import Decimal

import pytest

from conferencia.modelo import Categoria, Empresa, Ocorrencia, ResultadoEmpresa, Status


def _empresa(codigo: str, cnpj: str, razao: str) -> Empresa:
    return Empresa(codigo, cnpj, razao, date(2026, 9, 1), date(2026, 9, 30))


@pytest.fixture
def resultado_ok() -> ResultadoEmpresa:
    return ResultadoEmpresa(
        empresa=_empresa("101", "11222333000181", "EMPRESA CORRETA LTDA"),
        status=Status.OK,
        ocorrencias=[],
        qtd_sefaz=3,
        total_sefaz=Decimal("1500.50"),
        qtd_dominio=3,
        total_dominio=Decimal("1500.50"),
        erro=None,
    )


@pytest.fixture
def resultado_divergente() -> ResultadoEmpresa:
    return ResultadoEmpresa(
        empresa=_empresa("701", "44555666000172", "EMPRESA COM ERRO LTDA"),
        status=Status.DIVERGENTE,
        ocorrencias=[
            Ocorrencia(
                categoria=Categoria.FALTANDO,
                cnpj_emitente="45723174001192",
                nome_emitente="FORNECEDOR TESTE LTDA",
                serie="1",
                numero=1234,
                data_emissao=date(2026, 9, 10),
                valor_sefaz=Decimal("250.75"),
                valor_dominio=None,
                chave="2" * 44,
            ),
            Ocorrencia(
                categoria=Categoria.NAO_NFE,
                cnpj_emitente="45723174001192",
                nome_emitente="FORNECEDOR TESTE LTDA",
                serie="U",
                numero=55,
                data_emissao=date(2026, 9, 12),
                valor_sefaz=None,
                valor_dominio=Decimal("80.00"),
                chave=None,
            ),
        ],
        qtd_sefaz=5,
        total_sefaz=Decimal("2000.00"),
        qtd_dominio=5,
        total_dominio=Decimal("1829.25"),
        erro=None,
    )


@pytest.fixture
def resultado_sem_par() -> ResultadoEmpresa:
    return ResultadoEmpresa(
        empresa=None,
        status=Status.SEM_PAR,
        ocorrencias=[],
        qtd_sefaz=0,
        total_sefaz=Decimal("0"),
        qtd_dominio=0,
        total_dominio=Decimal("0"),
        erro="Sem relatório do Domínio para o CNPJ 99888777000155",
    )


@pytest.fixture
def resultados_exemplo(resultado_ok, resultado_divergente, resultado_sem_par):
    return [resultado_ok, resultado_divergente, resultado_sem_par]
