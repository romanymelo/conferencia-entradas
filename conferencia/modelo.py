from dataclasses import dataclass
from datetime import date
from decimal import Decimal


class Categoria:
    FALTANDO = "FALTANDO"
    CANCELADA_NAO_ZERADA = "CANCELADA NÃO ZERADA"
    VALOR_DIVERGENTE = "VALOR DIVERGENTE"
    SOBRANDO = "SOBRANDO"
    AMBIGUO = "AMBÍGUO"
    FORA_DO_PERIODO = "FORA DO PERÍODO"
    NAO_NFE = "NÃO-NFe"


class Status:
    OK = "OK"
    DIVERGENTE = "DIVERGENTE"
    SEM_PAR = "SEM PAR"
    PERIODO_DIVERGENTE = "PERÍODO DIVERGENTE"
    DUPLICADO = "DUPLICADO"
    ERRO_LEITURA = "ERRO DE LEITURA"


CATEGORIAS_ERRO: frozenset[str] = frozenset(
    {Categoria.FALTANDO, Categoria.CANCELADA_NAO_ZERADA}
)
CATEGORIAS_ALERTA: frozenset[str] = frozenset(
    {Categoria.VALOR_DIVERGENTE, Categoria.SOBRANDO, Categoria.AMBIGUO}
)
CATEGORIAS_INFORMATIVA: frozenset[str] = frozenset(
    {Categoria.FORA_DO_PERIODO, Categoria.NAO_NFE}
)
ESPECIES_NFE: frozenset[int] = frozenset({36})
TOLERANCIA: Decimal = Decimal("0.01")


@dataclass(frozen=True)
class Cabecalho:
    codigo: str | None
    cnpj: str
    razao_social: str
    periodo_inicio: date
    periodo_fim: date


@dataclass(frozen=True)
class Empresa:
    codigo: str
    cnpj: str
    razao_social: str
    periodo_inicio: date
    periodo_fim: date


@dataclass(frozen=True)
class NotaSefaz:
    cnpj_emitente: str
    nome_emitente: str
    serie: str
    numero: int
    data_emissao: date
    chave: str
    situacao: str
    valor: Decimal


@dataclass(frozen=True)
class LancamentoDominio:
    cnpj_emitente: str
    nome_emitente: str
    serie: str
    numero: int
    especie: int
    data_emissao: date
    data_entrada: date
    valor_contabil: Decimal


@dataclass(frozen=True)
class NotaDominio:
    cnpj_emitente: str
    nome_emitente: str
    serie: str
    numero: int
    especie: int
    data_emissao: date
    valor_contabil: Decimal
    linhas: int


@dataclass(frozen=True)
class Ocorrencia:
    categoria: str
    cnpj_emitente: str
    nome_emitente: str
    serie: str
    numero: int
    data_emissao: date
    valor_sefaz: Decimal | None
    valor_dominio: Decimal | None
    chave: str | None


@dataclass
class ResultadoEmpresa:
    empresa: Empresa | None
    status: str
    ocorrencias: list[Ocorrencia]
    qtd_sefaz: int
    total_sefaz: Decimal
    qtd_dominio: int
    total_dominio: Decimal
    erro: str | None
