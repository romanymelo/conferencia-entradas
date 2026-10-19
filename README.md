# Conferência de Entradas

Confere, em massa, se todas as notas fiscais de entrada que a Sefaz de Alagoas
registrou estão lançadas no sistema Domínio. A Sefaz é a fonte de verdade.

## O problema

Todo mês, um escritório de contabilidade precisa garantir que cada nota fiscal
emitida contra seus clientes foi lançada no sistema. A Sefaz publica a lista
oficial; o Domínio tem o que o escritório efetivamente lançou. Os dois têm que
bater — e uma nota que ficou de fora é omissão de informação ao fisco.

Conferir isso na mão significa cruzar centenas de linhas por empresa, toda
empresa, todo mês. E os dois relatórios não se alinham linha a linha:

- **O Domínio quebra uma nota em várias linhas, uma por CFOP.** Uma nota de
  R$ 192,40 pode aparecer como 52,10 e 140,30 em linhas separadas. É preciso
  somar antes de comparar.
- **Os dois cortam o período por datas diferentes.** A Sefaz corta pela data de
  emissão, o Domínio pela data de entrada. Uma nota emitida em 31/08 e lançada
  em 01/09 aparece num relatório e não no outro — e está correta nos dois.
- **Casar por nome de fornecedor não funciona.** A Sefaz trunca a razão social,
  e o mesmo fornecedor aparece sob vários CNPJs. O casamento tem que ser pelo
  CNPJ.
- **Nota cancelada também precisa estar lançada**, com valor zerado. A ausência
  dela é omissão, não um não-evento.
- **Os dois relatórios escrevem números em formatos diferentes** — a Sefaz usa
  `1,234.56` e o Domínio `1.234,56`.

## O que esta automação faz

Recebe uma pasta com os PDFs de todas as empresas misturados, pareia cada
empresa pelo CNPJ lido de dentro dos arquivos, e produz um PDF por empresa
listando apenas as divergências — cada uma com a chave de acesso da nota, que é
o que permite ir buscar o XML e corrigir. Em paralelo, gera uma planilha
consolidada para triagem: quais empresas estão corretas e quais precisam de
atenção.

A decisão de projeto mais importante é o que acontece quando a leitura falha.
Uma linha ignorada em silêncio seria uma nota que nunca poderia ser reportada
como faltante, e a empresa sairia "conferida" com uma omissão real. Por isso
cada relatório é reconciliado contra os totais que ele próprio declara no
rodapé: se a contagem ou a soma não fecharem, a empresa é marcada como erro de
leitura em vez de passar como correta. O documento verifica o leitor, a cada
execução, com dado real.

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

## O que sai em `saida/`

Cada empresa vai para `saida/<AAAA-MM>/`, o mês do período declarado nos relatórios (não da data de hoje); meses misturados na mesma rodada geram uma pasta por mês, cada uma com a própria planilha. Resultados sem período (`SEM PAR`, `DUPLICADO`, `PERÍODO DIVERGENTE`, arquivo ilegível) ficam em `saida/_sem_periodo/`.

- `resumo_conferencia_<AAAA-MM>.xlsx` : aba `Resumo` (uma linha por empresa, inclusive as corretas
  e as com problema de arquivo) e aba `Detalhe` (uma linha por ocorrência).
  A coluna `Diferença` costuma ser diferente de zero mesmo em empresa `OK`, porque
  corresponde às notas `FORA DO PERÍODO` (na 101, −2.815,35 com status `OK`). A
  coluna `Período` mostra o período de cada empresa conferida.
- Um PDF por empresa conferida, `<código>_<razão social>.pdf`, inclusive as sem
  divergência (serve de comprovante). Contém só as ocorrências, com a chave de
  acesso.
- `saida/log_execucao.txt` (um por rodada): arquivos lidos, pares, problemas e tempo total.

Empresas com status `SEM PAR`, `PERÍODO DIVERGENTE`, `DUPLICADO` ou
`ERRO DE LEITURA` não geram PDF; aparecem só no `Resumo`, com a explicação na
coluna `Observação`. Uma falha de leitura em uma empresa não interrompe as demais.

## Executável para Windows (sem Python)

Gerar (precisa de Python e `pip install pyinstaller`):

```
python -m PyInstaller conferencia-entradas.spec --noconfirm
```

O resultado é `dist/conferencia-entradas.exe` (arquivo único, cerca de 34 MB).

Uso: copie o `.exe` para uma pasta qualquer, crie a pasta `entrada` ao lado dele (se
não existir, ele cria na primeira execução e avisa), coloque nela os PDFs e dê duplo
clique. Os resultados aparecem em `saida/`, também ao lado do `.exe`. A
janela espera um Enter antes de fechar, para dar tempo de ler o resumo.

Observações: por ser um arquivo único, ele se descompacta a cada execução e leva
alguns segundos para começar. Alguns antivírus marcam executáveis de arquivo único do
PyInstaller como suspeitos; é um falso positivo conhecido.

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

Os testes versionados usam apenas dados fabricados — nenhum documento de cliente
entra no repositório.

O teste de ouro é a exceção: ele roda a automação inteira contra PDFs reais e
verifica, para **cada** empresa encontrada, que o resultado fecha com os totais
que os próprios relatórios declaram. Isso é o que prova que os leitores
entendem documentos de verdade, e não apenas as suposições de quem os escreveu.

Para rodá-lo, crie a pasta local `tests/amostras/` (ignorada pelo git) e coloque
nela os pares de PDFs que quiser — qualquer quantidade de empresas, com
quaisquer nomes de arquivo, já que o pareamento é pelo CNPJ do cabeçalho. Sem
essa pasta, esses testes aparecem como `SKIPPED` com a instrução.
