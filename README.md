# Conferência de Entradas

Confere o relatório de notas fiscais de entrada da Sefaz de Alagoas contra o
relatório "Acompanhamento de Entradas" do sistema Domínio, empresa por empresa.
A Sefaz é a fonte de verdade.

## Instalação

Python 3.11 ou superior.

```
pip install -r requirements.txt
```

## Como rodar

Coloque na pasta `entrada/` os PDFs de todas as empresas (um da Sefaz e um do
Domínio por empresa; o nome do arquivo não importa, o pareamento é pelo CNPJ do
cabeçalho) e execute:

```
python main.py
python main.py --entrada outra_pasta --saida outra_saida
```

O código de saída é a quantidade de empresas `DIVERGENTE` (no máximo 125); 126 é reservado
para pasta de entrada inexistente.
PDFs que não são relatórios da Sefaz nem do Domínio são ignorados e registrados
no log.

## O que sai em `saida/<AAAA-MM>/`

O mês vem do período declarado nos relatórios, não da data de hoje.

- `resumo_conferencia_<AAAA-MM>.xlsx` (sem nenhum relatório identificado, `resumo_conferencia.xlsx` direto em `saida/`): aba `Resumo` (uma linha por empresa, inclusive as corretas
  e as com problema de arquivo) e aba `Detalhe` (uma linha por ocorrência).
  A coluna `Diferença` costuma ser diferente de zero mesmo em empresa `OK`, porque
  corresponde às notas `FORA DO PERÍODO` (na 101, −2.815,35 com status `OK`). A
  coluna `Período` mostra o período de cada empresa conferida.
- Um PDF por empresa conferida, `<código>_<razão social>.pdf`, inclusive as sem
  divergência (serve de comprovante). Contém só as ocorrências, com a chave de
  acesso.
- `log_execucao.txt`: arquivos lidos, pares, problemas e tempo total.

Empresas com status `SEM PAR`, `PERÍODO DIVERGENTE`, `DUPLICADO` ou
`ERRO DE LEITURA` não geram PDF; aparecem só no `Resumo`, com a explicação na
coluna `Observação`. Uma falha de leitura em uma empresa não interrompe as demais.

## Status

| Status | Significado |
|---|---|
| `OK` | Nenhuma ocorrência de erro. |
| `DIVERGENTE` | Há ao menos uma ocorrência de erro (`FALTANDO` ou `CANCELADA NÃO ZERADA`). |
| `SEM PAR` | Falta o relatório da Sefaz ou do Domínio. |
| `PERÍODO DIVERGENTE` | Os dois relatórios cobrem períodos diferentes. |
| `DUPLICADO` | Mais de um arquivo do mesmo tipo para o mesmo CNPJ. |
| `ERRO DE LEITURA` | PDF ilegível, linha de dados fora do layout esperado, ou leitura que não fecha com o rodapé do próprio relatório (Quantidade de Notas / valor total da Sefaz; Total Geral do Domínio). |

## Categorias de ocorrência

Erros (definem o status `DIVERGENTE`):

- `FALTANDO`: nota da Sefaz, ativa ou cancelada, sem lançamento no Domínio. Nota cancelada também precisa estar lançada, zerada; a ausência dela é omissão de informação, não falso positivo.
- `CANCELADA NÃO ZERADA`: nota cancelada na Sefaz, lançada no Domínio com valor diferente de zero.

Alertas:

- `VALOR DIVERGENTE`: valores diferem em mais de R$ 0,01.
- `SOBRANDO`: nota de NF-e no Domínio, emitida dentro do período, que não existe na Sefaz.
- `AMBÍGUO`: não foi possível escolher entre vários lançamentos candidatos para a mesma nota.

Informativas:

- `FORA DO PERÍODO`: nota do Domínio sem par, emitida antes ou depois do período (a Sefaz corta por emissão, o Domínio por entrada).
- `NÃO-NFe`: lançamento de espécie diferente de NF-e (padrão: só a espécie 36 é NF-e).

## Limitação conhecida: virada de mês

O corte de período usa a data de emissão. Uma nota emitida no fim do mês e
lançada no Domínio só no mês seguinte aparece como `FALTANDO` sem ser erro, e
isso não é detectável com os dados de um único mês. O caso inverso (emitida no
mês anterior e lançada neste) é tratado como `FORA DO PERÍODO`. Cada PDF traz
uma nota de rodapé alertando para isso: confira a data de emissão antes de corrigir.

## Testes

```
pytest
```

Os testes versionados usam apenas dados fabricados. O teste de ouro (empresa 101,
setembro de 2026) depende dos PDFs reais de cliente, que nunca entram no
repositório: crie `tests/amostra/` (pasta local, ignorada pelo git) e coloque
nela `Entradas 101.pdf` (Domínio) e `Notas fiscais entrada 101.pdf`
(Sefaz). Sem eles, esses testes aparecem como `SKIPPED` com essa instrução.
