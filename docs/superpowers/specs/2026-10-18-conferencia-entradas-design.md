# Conferência de Entradas — Sefaz AL × Domínio

Spec de design — 18/10/2026

## 1. Objetivo

Conferir, em massa, se as notas fiscais de entrada registradas pela Sefaz de
Alagoas estão lançadas no sistema Domínio, para várias empresas em uma única
execução.

O relatório da Sefaz é a fonte de verdade. O relatório do Domínio precisa
refleti-lo. A pergunta central da automação é: **toda nota da Sefaz está no
Domínio?** As demais diferenças são informadas, mas não definem o status da
empresa.

Saídas: um PDF por empresa e uma planilha Excel consolidada.

## 2. Entradas

Dois PDFs por empresa, do mesmo período, depositados numa pasta única e
misturada. A automação identifica o tipo pelo conteúdo e pareia as empresas
pelo CNPJ lido de dentro do arquivo — nunca pelo nome do arquivo.

### 2.1 Relatório da Sefaz

Identificado pela presença de `SECRETARIA DE ESTADO DA FAZENDA DE ALAGOAS`.

Cabeçalho: `Período`, `CNPJ`, `Razão Social`, `Nome Fantasia`.
Rodapé: `Quantidade de Notas` e valor total.

Uma linha por nota, com as colunas:

| Coluna | Uso |
|---|---|
| `Emissão` | data e hora; só a data é usada |
| `CNPJ/CPF` | CNPJ do emitente — compõe a chave |
| `Razão Social Emissor` | exibição (vem truncado) |
| `Série/Num.` | formato `1 / 1004582` |
| `Chave de Acesso` | 44 dígitos; vai para o PDF de saída |
| `Tipo` | `Saída` ou `Entrada`; não filtra nada |
| `Situação` | `Ativa` ou `Cancelada`; define o valor esperado |
| `Valor (R$)` | valor da nota |

O corte do período da Sefaz é por **data de emissão**.

### 2.2 Relatório do Domínio

`ACOMPANHAMENTO DE ENTRADAS`, no layout ordenado por série/nota.

Cabeçalho: `<código> - <razão social>`, `CNPJ`, `Insc Est.`, `Período`.
Rodapé: `Total Série` por bloco e `Total Geral`.

Colunas usadas: `Data Emissão`, `Data Entrada`, `Nota`, `Série`, `Espécie`,
`CNPJ/CPF/CEI/CAEPF`, `Valor Contábil`. As demais (`Código`, `Código
Fornecedor`, `Insc. Est.`, `CFOP`, `AC.`, `UF`, `Tipo`, `Base Cálculo`,
`Alíq.`, `Valor`, `IPI`, `Sub. Trib.`, `Isentas`, `Outras`) são ignoradas.

O corte do período do Domínio é por **data de entrada**, diferente da Sefaz.
A automação reconcilia essa diferença usando sempre a data de emissão (§3.4).

**Uma nota ocupa várias linhas**, uma por CFOP. Precisa ser agregada antes de
comparar.

### 2.3 Observações de parsing

O CNPJ formatado (`\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}`) serve de âncora para
segmentar a linha do Domínio: antes dele vêm código, datas, nota, série,
espécie e nome do fornecedor; depois vêm Insc. Est., CFOP, UF e os valores.
Isso torna o parse imune ao tamanho variável do nome do fornecedor.

A listra zebrada do PDF do Domínio injeta um `1` solto no início de algumas
linhas na camada de texto. O parser precisa descartá-lo.

No PDF da Sefaz, a chave de acesso gruda no texto da linha seguinte na camada
de texto. A extração deve ser por posição de coluna (coordenadas das palavras),
não por quebra de linha.

Valores monetários usam `Decimal`, nunca `float`.

## 3. Regras de conferência

### 3.1 Chave de casamento

`CNPJ do emitente` + `número da nota`.

CNPJ normalizado para apenas dígitos. Número normalizado para inteiro (sem
zeros à esquerda).

Se o mesmo CNPJ + número aparecer mais de uma vez em um dos lados — o que só
ocorre com séries distintas, por causa de §3.2 — desempatar pela série. Se
nenhum candidato tiver a série da nota da Sefaz, não casar: registrar o caso
como alerta `AMBÍGUO`, carregando a chave de acesso da nota da Sefaz para que
ela não desapareça do relatório, e deixar os candidatos do Domínio caírem em
`SOBRANDO`.

### 3.2 Agregação do Domínio

Antes do casamento, somar o `Valor Contábil` de todas as linhas que
compartilham CNPJ + número + série. A data de emissão é a da primeira linha
do grupo (é igual dentro do grupo).

A série integra a chave de agregação — e não a chave de casamento (§3.1) —
porque a quebra por CFOP de uma mesma nota sempre repete a série. Verificado
nos 21 grupos multi-linha da amostra 101 (notas 205, 4871, 90312, 1004582,
1500233 e as demais): em nenhum a série varia entre as linhas. Agrupar só por
CNPJ + número fundiria notas de séries distintas, que são notas diferentes, e
destruiria a informação de que o desempate de §3.1 depende.

Validado na amostra: nota 1004582 de `45.723.174/0011-92` ocupa duas linhas no
Domínio (52,10 em CFOP 1-102 e 140,30 em 1-403); a soma 192,40 é exatamente o
valor da Sefaz.

### 3.3 Universo comparado

Do lado do Domínio, entram no casamento apenas lançamentos de **espécie 36**
(NF-e). Outras espécies (39, 40, 42 — serviços, energia, etc.) nunca constam no
relatório de NF-e da Sefaz; vão para a lista informativa `NÃO-NFe`, nunca são
descartadas em silêncio.

O conjunto de espécies consideradas NF-e é configurável, com padrão `{36}`.

### 3.4 Corte de período

O período de referência é o declarado no cabeçalho da Sefaz. A data que vale é
sempre a **data de emissão**, dos dois lados.

Nota do Domínio sem par cuja data de emissão está fora do período não é
`SOBRANDO`: é `FORA DO PERÍODO`, informativa.

Validado na amostra: as notas 7700121, 7700188 e 7700189 da SC Distribuição
foram emitidas em 31/08/2026 e entraram em 01/09/2026. Estão no Domínio de
setembro e não na Sefaz de setembro, e isso está correto.

**Limitação conhecida:** o inverso não é detectável com os dados disponíveis.
Nota emitida no fim do período e lançada no Domínio apenas no mês seguinte
aparece como `FALTANDO` sem ser erro. O PDF exibe a data de emissão em cada
linha e traz uma nota de rodapé alertando para esse caso.

### 3.5 Valor esperado por situação

| Situação na Sefaz | Esperado no Domínio |
|---|---|
| `Ativa` | presente, valor contábil igual ao da Sefaz (tolerância R$ 0,01) |
| `Cancelada` | presente, valor contábil igual a **0,00** |

Nota cancelada na Sefaz **precisa estar lançada** no Domínio, zerada. A
ausência é omissão de informação.

### 3.6 Categorias de ocorrência

| Categoria | Definição | Peso |
|---|---|---|
| `FALTANDO` | nota da Sefaz, ativa ou cancelada, ausente no Domínio | **ERRO** |
| `CANCELADA NÃO ZERADA` | cancelada na Sefaz, presente no Domínio com valor ≠ 0,00 | **ERRO** |
| `VALOR DIVERGENTE` | nota ativa, casada, com diferença de valor > R$ 0,01 | alerta |
| `SOBRANDO` | nota no Domínio, emitida dentro do período, ausente na Sefaz | alerta |
| `AMBÍGUO` | CNPJ + número repetido e indistinguível por série | alerta |
| `FORA DO PERÍODO` | nota no Domínio com emissão fora do período da Sefaz | informativo |
| `NÃO-NFe` | lançamento do Domínio com espécie fora do conjunto NF-e | informativo |

Diferença de data de emissão entre os dois lados **não gera ocorrência**.
Batendo CNPJ, número e valor, a nota está conferida.

### 3.7 Status da empresa

- **OK** — nenhum erro. Pode haver alertas.
- **DIVERGENTE** — pelo menos um erro.
- **SEM PAR** — falta um dos dois PDFs.
- **PERÍODO DIVERGENTE** — os dois PDFs existem, mas declaram períodos
  diferentes. A empresa não é conferida.

## 4. Saídas

```
<raiz>/
├── entrada/                       PDFs de todas as empresas, misturados
└── saida/
    └── <AAAA-MM>/
        ├── resumo_conferencia_<AAAA-MM>.xlsx
        ├── <código>_<RAZAO_SOCIAL>.pdf     (um por empresa)
        └── log_execucao.txt
```

O subdiretório `<AAAA-MM>` vem do período declarado nos relatórios.

### 4.1 PDF por empresa

Gerado para **todas** as empresas conferidas, inclusive as corretas, servindo
de comprovante de conferência.

Cabeçalho: código Domínio, razão social, CNPJ, período, quantidade de notas e
total de cada lado, status.

Corpo: apenas as ocorrências — nunca a lista completa de notas. Primeiro a
seção de erros, em destaque; depois os alertas; depois os informativos. Cada
seção traz sua contagem.

Colunas de cada linha: categoria, CNPJ do emitente, fornecedor, série/número,
data de emissão, valor Sefaz, valor Domínio, diferença e **chave de acesso**.

A chave de acesso vem da Sefaz. Ocorrências que só existem do lado do Domínio
— `SOBRANDO`, `FORA DO PERÍODO`, `NÃO-NFe` e `AMBÍGUO` originado no Domínio —
ficam com a coluna de chave vazia.

Empresa sem nenhuma ocorrência recebe um PDF de uma página declarando a
conferência sem divergências.

Rodapé: nota sobre a limitação de virada de mês descrita em §3.4.

### 4.2 Planilha consolidada

Aba `Resumo` — uma linha por empresa, **inclusive as corretas**: código, CNPJ,
razão social, status, qtd de erros, qtd de alertas, qtd por categoria,
quantidade e total de notas da Sefaz, quantidade e total do Domínio (espécie
NF-e), diferença de valor.

Aba `Detalhe` — uma linha por ocorrência, de todas as empresas: código da
empresa, CNPJ da empresa, categoria, CNPJ do emitente, fornecedor,
série/número, data de emissão, valor Sefaz, valor Domínio, diferença, chave de
acesso.

### 4.3 Log

Texto simples: arquivos lidos e classificados, empresas pareadas, empresas sem
par, divergências de período, erros de leitura, tempo total.

## 5. Arquitetura

```
modelo.py           dataclasses: Empresa, NotaSefaz, LancamentoDominio,
                    NotaDominio, Ocorrencia, ResultadoEmpresa
leitor_sefaz.py     PDF da Sefaz    → cabeçalho + lista de NotaSefaz
leitor_dominio.py   PDF do Domínio  → cabeçalho + lista de LancamentoDominio
conferencia.py      agrega, casa, classifica — núcleo puro, sem I/O
relatorio_pdf.py    ResultadoEmpresa → PDF
planilha.py         lista de ResultadoEmpresa → XLSX
descoberta.py       varre a pasta, classifica os PDFs, pareia por CNPJ
main.py             CLI e orquestração
```

`conferencia.py` recebe listas e devolve ocorrências. Não conhece PDF, Excel
nem sistema de arquivos — é onde mora a regra e é o que fica testável de forma
isolada.

Dependências: `pdfplumber` (leitura), `reportlab` (PDF), `openpyxl` (Excel).
Sem pandas.

### 5.1 Execução

Python 3.11+ em linha de comando, Windows. Processamento sequencial, uma
empresa por vez, com progresso no terminal.

```
python main.py [--entrada entrada] [--saida saida]
```

Sequencial atende qualquer volume porque o trabalho por empresa é pequeno. Se
medições futuras mostrarem necessidade, paralelizar por empresa é direto, já
que não há estado compartilhado. Não será feito agora.

### 5.2 Tratamento de erros

Falha em uma empresa — PDF ilegível, cabeçalho irreconhecível, período
divergente — não interrompe a rodada. A empresa recebe o status
correspondente no Resumo, a falha vai para o log, e as demais seguem.

## 6. Verificação

### 6.1 Teste de ouro: cada empresa da amostra contra os próprios rodapés

O teste de ouro roda o pipeline completo sobre os PDFs reais de `tests/amostras`
(ou `tests/amostra`), pasta local e nunca versionada. Ele não fixa cifras de uma
empresa: o pareamento usa o módulo `descoberta` (por CNPJ, independente dos nomes
dos arquivos) e o teste é parametrizado sobre todos os pares encontrados. Com
menos de dois PDFs na pasta, é pulado com mensagem pedindo os pares reais.

Para cada empresa, as expectativas vêm dos próprios documentos, lidos por
`le_sefaz` e `le_dominio` (que já reconciliam as linhas lidas com os rodapés):

1. O status não é `ERRO DE LEITURA` nem `SEM PAR`: os dois documentos foram lidos até o fim.
2. `Qtd Sefaz` e `Total Sefaz` do Resumo são iguais à quantidade e ao total declarados no rodapé da Sefaz.
3. `Total Domínio` mais a soma das ocorrências `NÃO-NFe` da empresa é igual ao `Total Geral` declarado no Domínio.
4. Existe um PDF cujo nome começa com o código da empresa.

O teste não afirma contagens de `FALTANDO`, `SOBRANDO` etc.: são resultados de
negócio que variam por empresa e por mês, e o valor correto não é conhecido pelo teste.

#### Exemplo ilustrativo (uma empresa, um mês)

Não são asserções do teste. É a conferência manual de uma empresa específica
(farmácia, código 101) no período 01/09/2026 a 30/09/2026, que fechava exatamente:

```
Domínio — Total Geral ................. 128.450,60
(−) espécies fora de NF-e (39/40/42) ..... 1.480,20
= Domínio espécie 36 .................. 126.970,40
(−) emitidas em 31/08/2026 ............... 2.815,35
= ..................................... 124.155,05
Sefaz — total ......................... 124.155,05   ✓
```

Resultado naquele mês:

| Categoria | Qtd |
|---|---|
| `FALTANDO` | 0 |
| `CANCELADA NÃO ZERADA` | 0 |
| `VALOR DIVERGENTE` | 0 |
| `SOBRANDO` | 0 |
| `AMBÍGUO` | 0 |
| `FORA DO PERÍODO` | 3 — notas 7700121, 7700188 e 7700189 |
| `NÃO-NFe` | 3 — Plano de Saúde Modelo 1.280,20; Serviços Técnicos Delta 140,00 e 60,00 |

Status: **OK**. Notas na Sefaz: 204. Total Sefaz: 124.155,05. Total Domínio
espécie 36: 126.970,40.

### 6.2 Testes sintéticos

A amostra real é 100% `Ativa` e não exercita o caminho de cancelada. Casos
derivados dela, alterando uma cópia:

1. Remover do Domínio uma nota ativa da Sefaz → `FALTANDO`.
2. Alterar em R$ 0,02 o valor de uma nota casada → `VALOR DIVERGENTE`.
3. Alterar em R$ 0,01 o valor de uma nota casada → nenhuma ocorrência.
4. Acrescentar no Domínio uma nota de espécie 36 emitida dentro do período e
   inexistente na Sefaz → `SOBRANDO`.
5. Marcar uma nota da Sefaz como `Cancelada`, ausente no Domínio → `FALTANDO`.
6. Marcar uma nota da Sefaz como `Cancelada`, presente no Domínio com valor →
   `CANCELADA NÃO ZERADA`.
7. Marcar uma nota da Sefaz como `Cancelada`, presente no Domínio com 0,00 →
   nenhuma ocorrência.
8. Alterar a data de emissão no Domínio de uma nota casada, mantendo CNPJ,
   número e valor → nenhuma ocorrência.
9. Trocar a ordem dos arquivos na pasta de entrada → resultado idêntico.
10. Pasta com o PDF de apenas um dos lados → status `SEM PAR`, rodada conclui.

### 6.3 Validação cruzada da chave de acesso

A chave de 44 dígitos da Sefaz carrega o CNPJ do emitente nas posições 7 a 20,
a série em 23 a 25 e o número em 26 a 34. O leitor da Sefaz confere esses três
campos contra as colunas correspondentes e registra divergência no log.
Conferido na amostra: a chave `27260945723174001192550010010045821234567890`
decompõe em CNPJ `45723174001192`, série `001`, número `001004582`, batendo com
a linha.

## 7. Fora de escopo

- Interface gráfica. (O empacotamento em `.exe` entrou depois, a pedido do dono: ver README, seção "Executável para Windows".)
- Leitura de XML, consulta a webservice ou qualquer acesso à internet.
- Correção automática de lançamentos no Domínio.
- Conferência de saídas, impostos, CFOP, base de cálculo ou alíquota.
- Comparação entre meses para resolver a virada de mês descrita em §3.4.
- Entrada em Excel/CSV. Só PDF nesta versão.

## 8. Decisões registradas

**Sem inteligência artificial.** A conferência é determinística: casamento
exato por CNPJ e número, e soma de valores. Um modelo de linguagem não
acrescentaria capacidade, introduziria risco de erro numérico em dado fiscal,
tornaria o resultado não reprodutível entre execuções e enviaria relatórios de
clientes para servidor de terceiro. Custo de API: zero. O único ponto que
poderia exigir julgamento difuso — casar nomes de fornecedor grafados de forma
diferente entre os dois relatórios — foi eliminado ao usar o CNPJ como chave,
que é exato nos dois lados.

**Chave por CNPJ + número, não por nome.** O relatório da Sefaz trunca a razão
social (`OMEGA INDUSTRIAL COMERCIAL E ALIM`) e o mesmo nome cobre CNPJs
distintos: Distribuidora Alfa aparece sob dois CNPJs, Beta Medicamentos sob dois, Gama Comércio sob dois,
Ômega Industrial sob três. Casar por nome seria aproximação; por CNPJ é exato.

**Série fora da chave.** A numeração de nota é única por CNPJ dentro do
período, e nenhuma colisão aparece na amostra. A série fica como critério de
desempate (§3.1), não como parte da chave.

**Pareamento pelo CNPJ interno, não pelo nome do arquivo.** Os nomes variam
(`Entradas_101_092026.pdf`, `Entradas 101.pdf`, `Notas fiscais entrada
101.pdf`). O CNPJ no cabeçalho é estável nos dois relatórios.

**Processamento sequencial.** O volume por rodada ainda não é conhecido.
Sequencial resolve qualquer quantidade; paralelizar sem medição seria
complexidade especulativa.
