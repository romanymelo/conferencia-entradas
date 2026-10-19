# Conferência de Entradas Sefaz × Domínio — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Conferir em massa se as notas fiscais de entrada da Sefaz AL estão lançadas no Domínio, gerando um PDF por empresa e uma planilha consolidada.

**Architecture:** Dois leitores de PDF produzem dataclasses; um núcleo puro (`conferencia.py`) agrega, casa por CNPJ+número e classifica as divergências sem tocar em I/O; dois escritores transformam o resultado em PDF e Excel. A orquestração pareia os arquivos pelo CNPJ lido de dentro do PDF e isola falhas por empresa.

**Tech Stack:** Python 3.11+, pdfplumber, reportlab, openpyxl, pytest.

**Spec:** `docs/superpowers/specs/2026-10-18-conferencia-entradas-design.md`

## Global Constraints

- Python 3.11+ em Windows, linha de comando, processamento sequencial.
- Valores monetários sempre `Decimal`, nunca `float`.
- Tolerância de comparação de valor: `Decimal("0.01")`.
- Espécies NF-e: padrão `frozenset({36})`, parâmetro configurável em toda a cadeia.
- Dependências permitidas: `pdfplumber`, `reportlab`, `openpyxl`, `pytest`. Sem pandas.
- Sem chamadas de rede, sem IA, sem leitura de XML.
- Nenhum PDF ou XLSX de cliente entra no repositório.
- Categorias e status são constantes em `modelo.py`; nenhum literal de string solto no código.

## Review Focus

Classes de entrada que a spec implica e que precisam de teste no dono do código:

1. **Dois PDFs do mesmo tipo e mesma empresa na pasta** (`Entradas 101.pdf` e `Entradas 101 novo.pdf` coexistindo) — tem que virar status `DUPLICADO` com os caminhos no log, nunca escolher um em silêncio. → Task 6.
2. **Série `0`** (Delta e Gama usam série 0) — não pode ser tratada como série ausente nem virar string vazia na normalização. → Task 1.
3. **Lançamento com valor contábil `0,00`** (cancelada zerada) — não pode ser descartado como linha inválida pelo parser nem pela agregação. → Tasks 2 e 5.
4. **Página de PDF sem linhas de dados** (página 7 da Sefaz tem uma nota só; páginas do Domínio podem começar com `Total Série`) — o leitor tem que devolver lista vazia para a página, não estourar. → Tasks 4 e 5.
5. **Razão social com caractere inválido em nome de arquivo no Windows** (`BETA & CIA. S.A`, `Gama & Filhos Distribuidora`, `DELTA DIST. IMPORT E EXPORT. LTDA-MATRIZ`) — o nome do PDF de saída precisa ser sanitizado. → Task 8.

---

### Task 1: Esqueleto do projeto, modelo de dados e normalização

**Files:**
- Create: `requirements.txt`, `conferencia/__init__.py`, `conferencia/modelo.py`, `conferencia/parsing.py`
- Modify: `.gitignore`
- Test: `tests/test_parsing.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `modelo.Cabecalho(codigo: str | None, cnpj: str, razao_social: str, periodo_inicio: date, periodo_fim: date)` — frozen dataclass
  - `modelo.Empresa(codigo: str, cnpj: str, razao_social: str, periodo_inicio: date, periodo_fim: date)` — frozen
  - `modelo.NotaSefaz(cnpj_emitente: str, nome_emitente: str, serie: str, numero: int, data_emissao: date, chave: str, situacao: str, valor: Decimal)` — frozen
  - `modelo.LancamentoDominio(cnpj_emitente: str, nome_emitente: str, serie: str, numero: int, especie: int, data_emissao: date, data_entrada: date, valor_contabil: Decimal)` — frozen
  - `modelo.NotaDominio(cnpj_emitente: str, nome_emitente: str, serie: str, numero: int, especie: int, data_emissao: date, valor_contabil: Decimal, linhas: int)` — frozen
  - `modelo.Ocorrencia(categoria: str, cnpj_emitente: str, nome_emitente: str, serie: str, numero: int, data_emissao: date, valor_sefaz: Decimal | None, valor_dominio: Decimal | None, chave: str | None)` — frozen
  - `modelo.ResultadoEmpresa(empresa: Empresa | None, status: str, ocorrencias: list[Ocorrencia], qtd_sefaz: int, total_sefaz: Decimal, qtd_dominio: int, total_dominio: Decimal, erro: str | None)` — mutável
  - `modelo.Categoria` com constantes `FALTANDO`, `CANCELADA_NAO_ZERADA`, `VALOR_DIVERGENTE`, `SOBRANDO`, `AMBIGUO`, `FORA_DO_PERIODO`, `NAO_NFE` (valores: as grafias da spec §3.6)
  - `modelo.Status` com constantes `OK`, `DIVERGENTE`, `SEM_PAR`, `PERIODO_DIVERGENTE`, `DUPLICADO`, `ERRO_LEITURA`
  - `modelo.CATEGORIAS_ERRO: frozenset[str]` = `{FALTANDO, CANCELADA_NAO_ZERADA}`
  - `modelo.ESPECIES_NFE: frozenset[int]` = `{36}`
  - `modelo.TOLERANCIA: Decimal` = `Decimal("0.01")`
  - `parsing.normaliza_cnpj(texto: str) -> str` — só dígitos, zero-padded a 14
  - `parsing.normaliza_numero(texto: str) -> int`
  - `parsing.normaliza_serie(texto: str) -> str` — dígitos sem zeros à esquerda, preservando `"0"`
  - `parsing.parse_valor_br(texto: str) -> Decimal` — `"1.532,66"` → `Decimal("1532.66")`
  - `parsing.parse_data_br(texto: str) -> date` — `"31/08/2026"` → `date(2026, 8, 31)`

- [ ] **Step 1: Escrever os testes de normalização que falham**

```python
# tests/test_parsing.py
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
    assert normaliza_cnpj("5.239.450/0024-84") == "00523945002484"

def test_normaliza_numero_descarta_zeros_a_esquerda():
    assert normaliza_numero("001004582") == 1004582

def test_normaliza_serie_zero_continua_zero():
    # Delta e Gama emitem na serie 0; nao pode virar string vazia
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
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_parsing.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'conferencia'`

- [ ] **Step 3: Criar `requirements.txt`**

Conteúdo exato: `pdfplumber`, `reportlab`, `openpyxl`, `pytest`, um por linha, sem pin de versão.

- [ ] **Step 4: Criar `conferencia/__init__.py` (vazio) e `conferencia/modelo.py`**

Só as dataclasses e constantes listadas no bloco Interfaces. Nenhuma lógica.

- [ ] **Step 5: Criar `conferencia/parsing.py`**

As cinco funções do bloco Interfaces. `parse_valor_br` levanta `ValueError` em texto que não casa com `^-?[\d.]+,\d{2}$` após `strip()`.

- [ ] **Step 6: Rodar e confirmar que passa**

Run: `pytest tests/test_parsing.py -v`
Expected: PASS, 11 testes

- [ ] **Step 7: Ajustar `.gitignore`**

Trocar a linha `!tests/fixtures/**/*.pdf` por `tests/amostra/`, com o comentário: amostra real de cliente, usada pelo teste de ouro, nunca versionada.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .gitignore conferencia/ tests/
git commit -m "feat: modelo de dados e normalizacao de campos"
```

---

### Task 2: Agregação do Domínio por nota

**Files:**
- Create: `conferencia/conferencia.py`, `tests/construtores.py`
- Test: `tests/test_agregacao.py`

**Interfaces:**
- Consumes: `modelo.LancamentoDominio`, `modelo.NotaDominio`, `modelo.ESPECIES_NFE`.
- Produces:
  - `conferencia.agrega_dominio(lancamentos: list[LancamentoDominio], especies_nfe: frozenset[int] = ESPECIES_NFE) -> tuple[list[NotaDominio], list[LancamentoDominio]]` — devolve `(notas_nfe_agregadas, lancamentos_fora_do_conjunto_nfe)`. Agrupa por `(cnpj_emitente, numero, serie)`, soma `valor_contabil`, e toma `nome_emitente`, `especie` e `data_emissao` da primeira linha do grupo. `linhas` recebe a contagem do grupo. A ordem de saída é a de primeira aparição. A série entra na chave de agregação porque a quebra por CFOP sempre a repete (spec §3.2).
  - `tests/construtores.py`: `lanc(**kw) -> LancamentoDominio` e `nota(**kw) -> NotaSefaz`, fábricas com valores padrão plausíveis sobrescrevíveis por keyword.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/test_agregacao.py
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

def test_separa_especies_fora_do_conjunto_nfe():
    linhas = [
        lanc(numero=7421, especie=42, valor_contabil=Decimal("152.00")),
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
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_agregacao.py -v`
Expected: FAIL com `ImportError: cannot import name 'agrega_dominio'`

- [ ] **Step 3: Criar `tests/construtores.py`**

Duas fábricas com padrões: CNPJ `"45723174001192"`, nome `"FORNECEDOR TESTE LTDA"`, série `"1"`, número `1`, espécie `36`, datas em setembro de 2026, valor `Decimal("100.00")`, situação `"Ativa"`, chave com 44 dígitos.

- [ ] **Step 4: Implementar `agrega_dominio` em `conferencia/conferencia.py`**

- [ ] **Step 5: Rodar e confirmar que passa**

Run: `pytest tests/test_agregacao.py -v`
Expected: PASS, 6 testes

- [ ] **Step 6: Commit**

```bash
git add conferencia/conferencia.py tests/
git commit -m "feat: agregacao de lancamentos do Dominio por nota"
```

---

### Task 3: Casamento e classificação das divergências

**Files:**
- Modify: `conferencia/conferencia.py`
- Test: `tests/test_conferencia.py`

**Interfaces:**
- Consumes: `agrega_dominio`, `modelo.Categoria`, `modelo.Status`, `modelo.CATEGORIAS_ERRO`, `modelo.TOLERANCIA`.
- Produces:
  - `conferencia.confere(notas_sefaz: list[NotaSefaz], lancamentos: list[LancamentoDominio], periodo_inicio: date, periodo_fim: date, especies_nfe: frozenset[int] = ESPECIES_NFE, tolerancia: Decimal = TOLERANCIA) -> list[Ocorrencia]`
  - `conferencia.status_de(ocorrencias: list[Ocorrencia]) -> str` — `Status.DIVERGENTE` se alguma categoria estiver em `CATEGORIAS_ERRO`, senão `Status.OK`.

Algoritmo, na ordem (a spec §3.1–§3.6 fixa; o resto é escolha do implementador):

1. `agrega_dominio` separa as notas NF-e dos lançamentos de outras espécies; cada lançamento fora do conjunto vira `NAO_NFE`.
2. Indexar as notas do Domínio por `(cnpj_emitente, numero)`. Chave com mais de uma nota: desempatar pela série da nota da Sefaz; se nenhuma série bater ou mais de uma bater, emitir `AMBIGUO` e não casar.
3. Para cada nota da Sefaz: sem par → `FALTANDO`. Com par e `situacao == "Cancelada"` → `CANCELADA_NAO_ZERADA` se `valor_contabil != 0`, senão nada. Com par e ativa → `VALOR_DIVERGENTE` se `abs(valor_sefaz - valor_contabil) > tolerancia`, senão nada.
4. Notas do Domínio que não foram casadas: `FORA_DO_PERIODO` se `data_emissao` estiver fora de `[periodo_inicio, periodo_fim]`, senão `SOBRANDO`.

- [ ] **Step 1: Escrever os testes que falham**

Os dez casos da spec §6.2, mais o status. Partir sempre de uma base casada e alterar um fato.

```python
# tests/test_conferencia.py
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

def test_nota_casada_e_igual_nao_gera_ocorrencia():
    s = nota(numero=1004582, valor=Decimal("192.40"))
    d = [lanc(numero=1004582, valor_contabil=Decimal("192.40"))]
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

def test_ordem_das_entradas_nao_muda_o_resultado():
    s = [nota(numero=1), nota(numero=2)]
    d = [lanc(numero=2), lanc(numero=3)]
    direto = sorted(categorias(confere_par(s, d)))
    invertido = sorted(categorias(confere_par(s[::-1], d[::-1])))
    assert direto == invertido

def test_status_ok_sem_erros():
    d = [lanc(numero=7421, especie=42)]
    assert status_de(confere_par([], d)) == Status.OK

def test_status_divergente_com_faltando():
    assert status_de(confere_par([nota(numero=1)], [])) == Status.DIVERGENTE
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_conferencia.py -v`
Expected: FAIL com `ImportError: cannot import name 'confere'`

- [ ] **Step 3: Implementar `confere` e `status_de` em `conferencia/conferencia.py`**

Seguir a ordem de quatro passos do bloco Interfaces. `valor_sefaz` e `valor_dominio` da `Ocorrencia` ficam `None` quando o lado não existe; `chave` só é preenchida a partir da nota da Sefaz.

- [ ] **Step 4: Rodar a suíte inteira**

Run: `pytest -v`
Expected: PASS, todos

- [ ] **Step 5: Commit**

```bash
git add conferencia/conferencia.py tests/test_conferencia.py
git commit -m "feat: casamento por CNPJ+numero e classificacao das divergencias"
```

---

### Task 4: Leitor do PDF da Sefaz

**Files:**
- Create: `conferencia/leitor_sefaz.py`
- Test: `tests/test_leitor_sefaz.py`

**Interfaces:**
- Consumes: `parsing.*`, `modelo.Cabecalho`, `modelo.NotaSefaz`.
- Produces:
  - `leitor_sefaz.e_sefaz(texto_primeira_pagina: str) -> bool` — procura `SECRETARIA DE ESTADO DA FAZENDA DE ALAGOAS`
  - `leitor_sefaz.le_cabecalho(texto: str) -> Cabecalho` — `codigo=None`; período de `Período: 01/09/2026 - 30/09/2026`; CNPJ e razão social dos rótulos `CNPJ:` e `Razão Social:`
  - `leitor_sefaz.parse_linha(palavras: list[dict]) -> NotaSefaz | None` — recebe as palavras de uma linha com coordenadas (saída de `page.extract_words()`), devolve `None` para linha que não é de dados
  - `leitor_sefaz.decompoe_chave(chave: str) -> tuple[str, str, int]` — devolve `(cnpj_emitente, serie, numero)` lidos das posições 7–20, 23–25 e 26–34 da chave de 44 dígitos (spec §6.3)
  - `leitor_sefaz.le_sefaz(caminho: Path) -> tuple[Cabecalho, list[NotaSefaz]]`

A chave de acesso tem 44 dígitos e, na camada de texto, gruda no conteúdo da linha seguinte. Extrair por coordenada: a palavra da coluna da chave é a que tem 44 dígitos consecutivos; validar com `re.fullmatch(r"\d{44}", ...)`.

`le_sefaz` confere cada nota lida contra `decompoe_chave` e registra divergência via `logging.warning`, sem interromper a leitura.

- [ ] **Step 1: Escrever os testes que falham**

Linhas fabricadas no layout real — não usar dados de cliente em teste versionado.

```python
# tests/test_leitor_sefaz.py
from datetime import date
from decimal import Decimal
import pytest
from conferencia.leitor_sefaz import e_sefaz, le_cabecalho, parse_linha

def palavras(*textos):
    """Simula page.extract_words(): uma palavra por item, x crescente."""
    return [{"text": t, "x0": i * 10.0, "x1": i * 10.0 + 5.0} for i, t in enumerate(textos)]

LINHA = palavras(
    "01/09/2026", "08:52:43", "11.222.333/0001-44", "FORNECEDOR", "TESTE", "LTDA",
    "1", "/", "1004582", "2" * 44, "Saída", "Ativa", "192,40",
)

def test_e_sefaz_reconhece_o_cabecalho():
    assert e_sefaz("SECRETARIA DE ESTADO DA FAZENDA DE ALAGOAS\nNotas Fiscais de Entrada")

def test_e_sefaz_rejeita_dominio():
    assert not e_sefaz("ACOMPANHAMENTO DE ENTRADAS")

def test_le_cabecalho():
    texto = (
        "Período: 01/09/2026 - 30/09/2026\n"
        "CNPJ: 12.345.678/0001-95\n"
        "Razão Social: FARMACIA MODELO LTDA\n"
    )
    c = le_cabecalho(texto)
    assert c.codigo is None
    assert c.cnpj == "12345678000195"
    assert c.razao_social == "FARMACIA MODELO LTDA"
    assert (c.periodo_inicio, c.periodo_fim) == (date(2026, 9, 1), date(2026, 9, 30))

def test_parse_linha_extrai_todos_os_campos():
    n = parse_linha(LINHA)
    assert n.cnpj_emitente == "11222333000144"
    assert n.serie == "1"
    assert n.numero == 1004582
    assert n.data_emissao == date(2026, 9, 1)
    assert n.chave == "2" * 44
    assert n.situacao == "Ativa"
    assert n.valor == Decimal("192.40")

def test_parse_linha_le_situacao_cancelada():
    linha = palavras(
        "01/09/2026", "08:52:43", "11.222.333/0001-44", "FORNECEDOR",
        "1", "/", "99", "3" * 44, "Saída", "Cancelada", "500,00",
    )
    assert parse_linha(linha).situacao == "Cancelada"

@pytest.mark.parametrize("texto", [
    "Quantidade de Notas: 204",
    "Emissão CNPJ/CPF Razão Social Emissor Série/Num. Chave de Acesso",
    "",
])
def test_parse_linha_ignora_linha_que_nao_e_dado(texto):
    assert parse_linha(palavras(*texto.split())) is None

def test_decompoe_chave_extrai_cnpj_serie_e_numero():
    # chave ficticia da nota 1004582, serie 1, emitente 45.723.174/0011-92
    chave = "27260945723174001192550010010045821234567890"
    assert decompoe_chave(chave) == ("45723174001192", "1", 1004582)

def test_decompoe_chave_rejeita_tamanho_errado():
    with pytest.raises(ValueError):
        decompoe_chave("123")
```

Acrescentar `decompoe_chave` à linha de `import` do início do arquivo.

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_leitor_sefaz.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'conferencia.leitor_sefaz'`

- [ ] **Step 3: Implementar `conferencia/leitor_sefaz.py`**

`le_sefaz` abre com `pdfplumber`, lê o cabeçalho da primeira página e percorre as páginas agrupando `extract_words()` por `top` arredondado. Página sem nenhuma linha de dados contribui com lista vazia.

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `pytest tests/test_leitor_sefaz.py -v`
Expected: PASS, 10 testes

- [ ] **Step 5: Commit**

```bash
git add conferencia/leitor_sefaz.py tests/test_leitor_sefaz.py
git commit -m "feat: leitor do relatorio de notas de entrada da Sefaz AL"
```

---

### Task 5: Leitor do PDF do Domínio

**Files:**
- Create: `conferencia/leitor_dominio.py`
- Test: `tests/test_leitor_dominio.py`

**Interfaces:**
- Consumes: `parsing.*`, `modelo.Cabecalho`, `modelo.LancamentoDominio`.
- Produces:
  - `leitor_dominio.e_dominio(texto_primeira_pagina: str) -> bool` — procura `ACOMPANHAMENTO DE ENTRADAS`
  - `leitor_dominio.le_cabecalho(texto: str) -> Cabecalho` — `codigo` da linha `101 - FARMACIA MODELO LTDA`; CNPJ do rótulo `CNPJ:`; período de `01/09/2026 até 30/09/2026`
  - `leitor_dominio.parse_linha(texto: str) -> LancamentoDominio | None`
  - `leitor_dominio.le_dominio(caminho: Path) -> tuple[Cabecalho, list[LancamentoDominio]]`

`parse_linha` usa o CNPJ formatado como âncora: `re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto)`. Antes da âncora vêm, nesta ordem, código, data de emissão, data de entrada, nota, série, espécie, código do fornecedor e nome; depois vêm Insc. Est., CFOP, AC., UF e os valores, sendo o `Valor Contábil` o primeiro campo monetário após a sigla da UF. Descartar um `1` solto no início da linha (artefato da listra zebrada) antes de interpretar.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/test_leitor_dominio.py
from datetime import date
from decimal import Decimal
import pytest
from conferencia.leitor_dominio import e_dominio, le_cabecalho, parse_linha

BASE = ("775 01/09/2026 01/09/2026 1004582 1 36 6 FORNECEDOR TESTE LTDA "
        "11.222.333/0001-44 240000015 1-102 101 AL 52,10 ICMS "
        "0,00 0,00 0,00 0,00 0,00 0,00 52,10")

def test_e_dominio_reconhece_o_cabecalho():
    assert e_dominio("ACOMPANHAMENTO DE ENTRADAS")

def test_e_dominio_rejeita_sefaz():
    assert not e_dominio("SECRETARIA DE ESTADO DA FAZENDA DE ALAGOAS")

def test_le_cabecalho():
    texto = ("101 - FARMACIA MODELO LTDA\n"
             "CNPJ: 12.345.678/0001-95\n"
             "Período: 01/09/2026 até 30/09/2026\n")
    c = le_cabecalho(texto)
    assert c.codigo == "101"
    assert c.cnpj == "12345678000195"
    assert c.razao_social == "FARMACIA MODELO LTDA"
    assert (c.periodo_inicio, c.periodo_fim) == (date(2026, 9, 1), date(2026, 9, 30))

def test_parse_linha_extrai_todos_os_campos():
    l = parse_linha(BASE)
    assert l.cnpj_emitente == "11222333000144"
    assert l.nome_emitente == "FORNECEDOR TESTE LTDA"
    assert l.numero == 1004582
    assert l.serie == "1"
    assert l.especie == 36
    assert l.data_emissao == date(2026, 9, 1)
    assert l.data_entrada == date(2026, 9, 1)
    assert l.valor_contabil == Decimal("52.10")

def test_parse_linha_descarta_o_um_solto_da_listra_zebrada():
    assert parse_linha("1 " + BASE) == parse_linha(BASE)

def test_parse_linha_le_datas_de_emissao_e_entrada_distintas():
    texto = BASE.replace("775 01/09/2026 01/09/2026", "197 31/08/2026 01/09/2026", 1)
    l = parse_linha(texto)
    assert l.data_emissao == date(2026, 8, 31)
    assert l.data_entrada == date(2026, 9, 1)

def test_parse_linha_aceita_serie_zero():
    texto = BASE.replace("1004582 1 36", "300215 0 36", 1)
    assert parse_linha(texto).serie == "0"

def test_parse_linha_aceita_valor_contabil_zerado():
    texto = BASE.replace("AL 52,10 ICMS", "AL 0,00 ICMS", 1)
    assert parse_linha(texto).valor_contabil == Decimal("0.00")

def test_parse_linha_le_especie_fora_de_nfe_sem_coluna_tipo():
    # espécie 42 nao traz "ICMS" na coluna Tipo
    texto = ("926 01/09/2026 01/09/2026 7421 39 42 SUPER TESTE LTDA "
             "30.306.294/0001-45 1-933 106 AL 140,00 0,00 0,00 0,00 0,00 0,00")
    l = parse_linha(texto)
    assert l.especie == 42
    assert l.valor_contabil == Decimal("152.00")

@pytest.mark.parametrize("texto", [
    "Total Série",
    "1Total Série",
    "Total Geral",
    "Código Data Emissão Data Entrada Nota Série Espécie Código Fornecedor",
    "Sistema licenciado para EMPRESA EXEMPLO LTDA - ME",
    "",
])
def test_parse_linha_ignora_linha_que_nao_e_dado(texto):
    assert parse_linha(texto) is None
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_leitor_dominio.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'conferencia.leitor_dominio'`

- [ ] **Step 3: Implementar `conferencia/leitor_dominio.py`**

`le_dominio` abre com `pdfplumber` e aplica `parse_linha` a cada linha de `extract_text().splitlines()` de cada página, descartando os `None`.

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `pytest tests/test_leitor_dominio.py -v`
Expected: PASS, 14 testes

- [ ] **Step 5: Commit**

```bash
git add conferencia/leitor_dominio.py tests/test_leitor_dominio.py
git commit -m "feat: leitor do relatorio de acompanhamento de entradas do Dominio"
```

---

### Task 6: Descoberta e pareamento dos arquivos

**Files:**
- Create: `conferencia/descoberta.py`
- Test: `tests/test_descoberta.py`

**Interfaces:**
- Consumes: `leitor_sefaz.e_sefaz/le_cabecalho`, `leitor_dominio.e_dominio/le_cabecalho`, `modelo.Status`, `modelo.Empresa`.
- Produces:
  - `descoberta.ArquivoIdentificado(caminho: Path, tipo: str, cabecalho: Cabecalho)` — frozen; `tipo` é `"sefaz"` ou `"dominio"`
  - `descoberta.Par(empresa: Empresa, caminho_sefaz: Path, caminho_dominio: Path)` — frozen
  - `descoberta.identifica(caminho: Path) -> ArquivoIdentificado | None` — `None` para PDF que não é nenhum dos dois
  - `descoberta.pareia(arquivos: list[ArquivoIdentificado]) -> tuple[list[Par], list[ResultadoEmpresa]]` — o segundo elemento traz um `ResultadoEmpresa` com `empresa=None`, `ocorrencias=[]` e `erro` preenchido para cada empresa não conferível

Regras de pareamento, por CNPJ:
- um de cada tipo, períodos iguais → `Par`, com `Empresa` combinando `codigo` e `razao_social` do Domínio e o período comum;
- só um dos tipos → `Status.SEM_PAR`, `erro` nomeando o tipo ausente;
- um de cada tipo com períodos diferentes → `Status.PERIODO_DIVERGENTE`, `erro` com os dois períodos;
- mais de um arquivo do mesmo tipo → `Status.DUPLICADO`, `erro` listando os caminhos.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/test_descoberta.py
from datetime import date
from pathlib import Path
from conferencia.descoberta import ArquivoIdentificado, pareia
from conferencia.modelo import Cabecalho, Status

def cab(cnpj="12345678000195", codigo=None, fim=date(2026, 9, 30)):
    return Cabecalho(codigo, cnpj, "FARMACIA MODELO LTDA", date(2026, 9, 1), fim)

def arq(tipo, nome, **kw):
    return ArquivoIdentificado(Path(nome), tipo, cab(**kw))

def test_pareia_um_de_cada_tipo():
    pares, problemas = pareia([
        arq("sefaz", "s.pdf"),
        arq("dominio", "d.pdf", codigo="101"),
    ])
    assert problemas == []
    assert len(pares) == 1
    assert pares[0].empresa.codigo == "101"
    assert pares[0].caminho_sefaz == Path("s.pdf")

def test_so_um_dos_tipos_vira_sem_par():
    pares, problemas = pareia([arq("sefaz", "s.pdf")])
    assert pares == []
    assert problemas[0].status == Status.SEM_PAR
    assert "dominio" in problemas[0].erro.lower()

def test_periodos_diferentes_viram_periodo_divergente():
    pares, problemas = pareia([
        arq("sefaz", "s.pdf"),
        arq("dominio", "d.pdf", codigo="101", fim=date(2026, 10, 31)),
    ])
    assert pares == []
    assert problemas[0].status == Status.PERIODO_DIVERGENTE

def test_dois_arquivos_do_mesmo_tipo_viram_duplicado():
    # caso real: "Entradas 101.pdf" e "Entradas 101 novo.pdf" na mesma pasta
    pares, problemas = pareia([
        arq("sefaz", "s.pdf"),
        arq("dominio", "d1.pdf", codigo="101"),
        arq("dominio", "d2.pdf", codigo="101"),
    ])
    assert pares == []
    assert problemas[0].status == Status.DUPLICADO
    assert "d1.pdf" in problemas[0].erro and "d2.pdf" in problemas[0].erro

def test_varias_empresas_sao_pareadas_independentemente():
    pares, problemas = pareia([
        arq("sefaz", "s1.pdf"),
        arq("dominio", "d1.pdf", codigo="101"),
        arq("sefaz", "s2.pdf", cnpj="11222333000144"),
    ])
    assert len(pares) == 1 and len(problemas) == 1
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_descoberta.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'conferencia.descoberta'`

- [ ] **Step 3: Implementar `conferencia/descoberta.py`**

`identifica` abre o PDF, extrai o texto da primeira página e consulta `e_sefaz` e `e_dominio` nessa ordem.

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `pytest tests/test_descoberta.py -v`
Expected: PASS, 5 testes

- [ ] **Step 5: Commit**

```bash
git add conferencia/descoberta.py tests/test_descoberta.py
git commit -m "feat: identificacao e pareamento dos PDFs por CNPJ"
```

---

### Task 7: Planilha consolidada

**Files:**
- Create: `conferencia/planilha.py`, `tests/conftest.py`
- Test: `tests/test_planilha.py`

**Interfaces:**
- Consumes: `modelo.ResultadoEmpresa`, `modelo.Categoria`, `modelo.Status`.
- Produces: `planilha.escreve_planilha(resultados: list[ResultadoEmpresa], destino: Path) -> None`

Aba `Resumo`, uma linha por empresa inclusive as sem ocorrência, nesta ordem de colunas: Código, CNPJ, Razão Social, Status, Erros, Alertas, e uma coluna por categoria na ordem de `Categoria`, Qtd Sefaz, Total Sefaz, Qtd Domínio, Total Domínio, Diferença, Observação (o campo `erro`).

Aba `Detalhe`, uma linha por ocorrência de todas as empresas: Código, CNPJ Empresa, Categoria, CNPJ Emitente, Fornecedor, Série, Número, Data Emissão, Valor Sefaz, Valor Domínio, Diferença, Chave de Acesso.

Ambas com a primeira linha congelada e autofiltro. Valores monetários gravados como número com formato `#,##0.00`.

- [ ] **Step 1: Escrever os testes que falham**

Ler de volta com `openpyxl.load_workbook` e conferir conteúdo.

```python
# tests/test_planilha.py
from decimal import Decimal
from openpyxl import load_workbook
from conferencia.planilha import escreve_planilha
from conferencia.modelo import Status

def test_resumo_tem_uma_linha_por_empresa_inclusive_as_corretas(tmp_path, resultados_exemplo):
    destino = tmp_path / "r.xlsx"
    escreve_planilha(resultados_exemplo, destino)
    aba = load_workbook(destino)["Resumo"]
    assert aba.max_row == 1 + len(resultados_exemplo)

def test_detalhe_tem_uma_linha_por_ocorrencia(tmp_path, resultados_exemplo):
    destino = tmp_path / "r.xlsx"
    escreve_planilha(resultados_exemplo, destino)
    aba = load_workbook(destino)["Detalhe"]
    total = sum(len(r.ocorrencias) for r in resultados_exemplo)
    assert aba.max_row == 1 + total

def test_valores_sao_numericos_e_nao_texto(tmp_path, resultados_exemplo):
    destino = tmp_path / "r.xlsx"
    escreve_planilha(resultados_exemplo, destino)
    aba = load_workbook(destino)["Resumo"]
    cabecalho = [c.value for c in aba[1]]
    coluna = cabecalho.index("Total Sefaz") + 1
    assert isinstance(aba.cell(row=2, column=coluna).value, (int, float, Decimal))

def test_empresa_sem_par_aparece_no_resumo_com_observacao(tmp_path, resultados_exemplo):
    destino = tmp_path / "r.xlsx"
    escreve_planilha(resultados_exemplo, destino)
    aba = load_workbook(destino)["Resumo"]
    status = [aba.cell(row=l, column=4).value for l in range(2, aba.max_row + 1)]
    assert Status.SEM_PAR in status

def test_planilha_vazia_nao_quebra(tmp_path):
    destino = tmp_path / "r.xlsx"
    escreve_planilha([], destino)
    assert load_workbook(destino)["Resumo"].max_row == 1
```

Criar `tests/conftest.py` com quatro fixtures, usadas também pela Task 8:

- `resultado_ok` — `Status.OK`, `ocorrencias=[]`, empresa código `"101"`;
- `resultado_divergente` — `Status.DIVERGENTE`, com uma ocorrência `FALTANDO` (chave preenchida) e uma `NAO_NFE` (chave `None`);
- `resultado_sem_par` — `Status.SEM_PAR`, `empresa=None`, `erro` preenchido;
- `resultados_exemplo` — a lista com os três acima, nessa ordem.

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_planilha.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'conferencia.planilha'`

- [ ] **Step 3: Implementar `conferencia/planilha.py`**

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `pytest tests/test_planilha.py -v`
Expected: PASS, 5 testes

- [ ] **Step 5: Commit**

```bash
git add conferencia/planilha.py tests/
git commit -m "feat: planilha consolidada com abas Resumo e Detalhe"
```

---

### Task 8: Relatório PDF por empresa

**Files:**
- Create: `conferencia/relatorio_pdf.py`
- Test: `tests/test_relatorio_pdf.py`

**Interfaces:**
- Consumes: `modelo.ResultadoEmpresa`, `modelo.Categoria`, `modelo.CATEGORIAS_ERRO`.
- Produces:
  - `relatorio_pdf.nome_arquivo(resultado: ResultadoEmpresa) -> str` — `"<codigo>_<RAZAO_SANITIZADA>.pdf"`; troca por `_` tudo que não for `[A-Za-z0-9 ._-]`, colapsa espaços em `_`, corta em 80 caracteres
  - `relatorio_pdf.escreve_relatorio(resultado: ResultadoEmpresa, destino: Path) -> None`

Gerado para toda empresa conferida, inclusive as sem ocorrência. Cabeçalho: código, razão social, CNPJ, período, status, quantidade e total de cada lado. Corpo: só as ocorrências, em três blocos nesta ordem — erros (`CATEGORIAS_ERRO`), alertas (`VALOR_DIVERGENTE`, `SOBRANDO`, `AMBIGUO`), informativos (`FORA_DO_PERIODO`, `NAO_NFE`) — cada bloco com sua contagem no título. Colunas: Categoria, CNPJ Emitente, Fornecedor, Série/Nº, Emissão, Valor Sefaz, Valor Domínio, Diferença, Chave de Acesso. Empresa sem ocorrência recebe uma página declarando a conferência sem divergências. Rodapé fixo em todas as páginas:

> A Sefaz corta o período por data de emissão e o Domínio por data de entrada. Nota emitida no fim do período e lançada no Domínio apenas no mês seguinte aparece aqui como FALTANDO sem ser erro. Confira a data de emissão antes de corrigir.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/test_relatorio_pdf.py
from datetime import date
import pdfplumber
from conferencia.relatorio_pdf import nome_arquivo, escreve_relatorio
from conferencia.modelo import Empresa, Status

def texto_do_pdf(caminho):
    with pdfplumber.open(caminho) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)

def test_nome_arquivo_sanitiza_caractere_invalido_no_windows(resultado_divergente):
    resultado_divergente.empresa = Empresa(
        "18", "11444777002539", "BETA & CIA. S.A",
        date(2026, 9, 1), date(2026, 9, 30),
    )
    nome = nome_arquivo(resultado_divergente)
    assert not set(nome) & set('<>:"/\\|?*&')
    assert nome.startswith("18_") and nome.endswith(".pdf")

def test_relatorio_traz_a_chave_de_acesso(tmp_path, resultado_divergente):
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    chaves = [o.chave for o in resultado_divergente.ocorrencias if o.chave]
    assert chaves and chaves[0] in texto_do_pdf(destino).replace(" ", "")

def test_relatorio_nao_lista_notas_conferidas(tmp_path, resultado_divergente):
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    texto = texto_do_pdf(destino)
    assert str(len(resultado_divergente.ocorrencias)) in texto

def test_empresa_sem_ocorrencia_gera_pdf_de_conferencia_limpa(tmp_path, resultado_ok):
    destino = tmp_path / "ok.pdf"
    escreve_relatorio(resultado_ok, destino)
    assert "sem divergências" in texto_do_pdf(destino).lower()

def test_rodape_alerta_sobre_a_virada_de_mes(tmp_path, resultado_divergente):
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    assert "data de entrada" in texto_do_pdf(destino).lower()

def test_relatorio_exibe_o_status(tmp_path, resultado_divergente):
    destino = tmp_path / "r.pdf"
    escreve_relatorio(resultado_divergente, destino)
    assert Status.DIVERGENTE in texto_do_pdf(destino)
```

As fixtures `resultado_divergente` e `resultado_ok` vêm de `tests/conftest.py` (Task 7).

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_relatorio_pdf.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'conferencia.relatorio_pdf'`

- [ ] **Step 3: Implementar `conferencia/relatorio_pdf.py`**

Usar `reportlab.platypus` com `SimpleDocTemplate` em paisagem A4 e `Table` por bloco. O rodapé entra por `onPage` do template.

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `pytest tests/test_relatorio_pdf.py -v`
Expected: PASS, 6 testes

- [ ] **Step 5: Commit**

```bash
git add conferencia/relatorio_pdf.py tests/
git commit -m "feat: relatorio PDF por empresa com chave de acesso"
```

---

### Task 9: Orquestração, CLI e teste de ouro

**Files:**
- Create: `main.py`, `README.md`
- Test: `tests/test_ponta_a_ponta.py`

**Interfaces:**
- Consumes: todos os módulos anteriores.
- Produces: `main.executa(entrada: Path, saida: Path) -> int` — devolve a quantidade de empresas com status `DIVERGENTE`; usado como código de saída do processo, saturado em 125.

Fluxo: varrer `entrada/*.pdf` → `identifica` cada um → `pareia` → para cada par, ler os dois PDFs, `confere`, montar `ResultadoEmpresa` → escrever o PDF da empresa → acumular. Ao final, escrever a planilha e o log em `saida/<AAAA-MM>/`, com `<AAAA-MM>` vindo do período. Exceção ao processar uma empresa vira `ResultadoEmpresa` com `Status.ERRO_LEITURA` e segue para a próxima. Progresso impresso por empresa.

- [ ] **Step 1: Escrever os testes que falham**

O teste de ouro depende dos PDFs reais, que não são versionados: `tests/amostra/` precisa conter `Entradas 101.pdf` e `Notas fiscais entrada 101.pdf`. Sem eles, o teste é pulado com mensagem explícita.

```python
# tests/test_ponta_a_ponta.py
import shutil
from decimal import Decimal
from pathlib import Path
import pytest
from openpyxl import load_workbook
from main import executa
from conferencia.modelo import Categoria, Status

AMOSTRA = Path(__file__).parent / "amostra"

@pytest.fixture
def pasta_amostra(tmp_path):
    pdfs = sorted(AMOSTRA.glob("*.pdf")) if AMOSTRA.exists() else []
    if len(pdfs) < 2:
        pytest.skip(f"coloque os dois PDFs reais da empresa 101 em {AMOSTRA}")
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    for p in pdfs:
        shutil.copy(p, entrada)
    return entrada, tmp_path / "saida"

def test_teste_de_ouro_empresa_101(pasta_amostra):
    entrada, saida = pasta_amostra
    assert executa(entrada, saida) == 0

    aba = load_workbook(next(saida.rglob("*.xlsx")))["Resumo"]
    cabecalho = [c.value for c in aba[1]]
    linha = {cabecalho[i]: c.value for i, c in enumerate(aba[2])}

    assert linha["Código"] == "101"
    assert linha["Status"] == Status.OK
    assert linha["Qtd Sefaz"] == 204
    assert Decimal(str(linha["Total Sefaz"])) == Decimal("133721.36")
    assert Decimal(str(linha["Total Domínio"])) == Decimal("137112.13")
    assert linha[Categoria.FALTANDO] == 0
    assert linha[Categoria.SOBRANDO] == 0
    assert linha[Categoria.VALOR_DIVERGENTE] == 0
    assert linha[Categoria.CANCELADA_NAO_ZERADA] == 0
    assert linha[Categoria.AMBIGUO] == 0
    assert linha[Categoria.FORA_DO_PERIODO] == 3
    assert linha[Categoria.NAO_NFE] == 3

def test_gera_pdf_para_a_empresa_conferida(pasta_amostra):
    entrada, saida = pasta_amostra
    executa(entrada, saida)
    assert [p.name for p in saida.rglob("101_*.pdf")]

def test_gera_log_de_execucao(pasta_amostra):
    entrada, saida = pasta_amostra
    executa(entrada, saida)
    logs = list(saida.rglob("log_execucao.txt"))
    assert logs and "101" in logs[0].read_text(encoding="utf-8")

def test_arquivo_ilegivel_nao_derruba_a_rodada(pasta_amostra):
    # spec §5.2: falha em uma empresa nao interrompe as demais
    entrada, saida = pasta_amostra
    (entrada / "quebrado.pdf").write_bytes(b"isto nao e um PDF")
    executa(entrada, saida)
    aba = load_workbook(next(saida.rglob("*.xlsx")))["Resumo"]
    assert aba.max_row >= 2
    assert "quebrado.pdf" in next(saida.rglob("log_execucao.txt")).read_text(encoding="utf-8")

def test_pasta_vazia_nao_quebra(tmp_path):
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    saida = tmp_path / "saida"
    assert executa(entrada, saida) == 0
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_ponta_a_ponta.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Implementar `main.py`**

`argparse` com `--entrada` (padrão `entrada`) e `--saida` (padrão `saida`). Bloco `if __name__ == "__main__":` chamando `sys.exit(min(executa(...), 125))`.

- [ ] **Step 4: Rodar a suíte inteira**

Run: `pytest -v`
Expected: PASS. Se `tests/amostra/` estiver vazia, o teste de ouro aparece como SKIPPED com a mensagem apontando a pasta.

- [ ] **Step 5: Colocar os PDFs reais em `tests/amostra/` e rodar o teste de ouro**

Run: `pytest tests/test_ponta_a_ponta.py -v`
Expected: PASS, nenhum SKIPPED. Este é o critério de aceite da automação inteira — se os sete contadores e os dois totais baterem com a spec §6.1, a conferência está correta.

- [ ] **Step 6: Escrever o `README.md`**

Instalação (`pip install -r requirements.txt`), como rodar, o que cai em `saida/`, o significado de cada categoria, e a limitação de virada de mês da spec §3.4. Mencionar que `tests/amostra/` é local e não versionada.

- [ ] **Step 7: Commit**

```bash
git add main.py README.md tests/test_ponta_a_ponta.py
git commit -m "feat: orquestracao, CLI e teste de ouro da empresa 101"
```
