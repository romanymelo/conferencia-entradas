import argparse
import sys
import time
from decimal import Decimal
from pathlib import Path

from conferencia import leitor_dominio, leitor_sefaz
from conferencia.conferencia import agrega_dominio, confere, status_de
from conferencia.descoberta import ArquivoIdentificado, Par, identifica, pareia
from conferencia.modelo import ESPECIES_NFE, ResultadoEmpresa, Status
from conferencia.planilha import escreve_planilha
from conferencia.relatorio_pdf import escreve_relatorio, nome_arquivo

LIMITE_CODIGO_SAIDA = 125
CODIGO_ENTRADA_INVALIDA = 126  # 1..125 = nº de empresas divergentes (LIMITE_CODIGO_SAIDA)


def _erro_leitura(erro: str) -> ResultadoEmpresa:
    return ResultadoEmpresa(
        None, Status.ERRO_LEITURA, [], 0, Decimal("0"), 0, Decimal("0"), erro
    )


def _confere_par(par: Par) -> ResultadoEmpresa:
    """Lê os dois PDFs e confere. Falha de leitura sobe de
    propósito: dado parcial nunca vira conferência (nota pulada não poderia ser FALTANDO)."""
    _, notas_sefaz = leitor_sefaz.le_sefaz(par.caminho_sefaz)
    _, lancamentos = leitor_dominio.le_dominio(par.caminho_dominio)
    empresa = par.empresa
    # mesmo conjunto de espécies na classificação e nos totais do Resumo
    ocorrencias = confere(
        notas_sefaz, lancamentos, empresa.periodo_inicio, empresa.periodo_fim, ESPECIES_NFE
    )
    notas_dominio, _ = agrega_dominio(lancamentos, ESPECIES_NFE)
    resultado = ResultadoEmpresa(
        empresa=empresa,
        status=status_de(ocorrencias),
        ocorrencias=ocorrencias,
        qtd_sefaz=len(notas_sefaz),
        total_sefaz=sum((n.valor for n in notas_sefaz), Decimal("0")),
        qtd_dominio=len(notas_dominio),
        total_dominio=sum((n.valor_contabil for n in notas_dominio), Decimal("0")),
        erro=None,
    )
    return resultado


def executa(entrada: Path, saida: Path) -> int:
    """Confere todas as empresas de `entrada`; devolve quantas ficaram DIVERGENTE."""
    if not entrada.is_dir():
        raise NotADirectoryError(f"pasta de entrada não encontrada: {entrada}")
    inicio = time.monotonic()
    log: list[str] = []

    def anota(msg: str) -> None:
        print(msg)
        log.append(msg)

    identificados: list[ArquivoIdentificado] = []
    falhas: list[ResultadoEmpresa] = []
    for caminho in sorted(entrada.glob("*.pdf")):
        try:
            arquivo = identifica(caminho)
        except Exception as e:
            anota(f"ERRO ao ler {caminho}: {e}")
            falhas.append(_erro_leitura(f"{caminho}: {e}"))
            continue
        if arquivo is None:
            anota(f"ignorado (não é relatório da Sefaz nem do Domínio): {caminho}")
            continue
        anota(f"{arquivo.tipo}: {caminho} (CNPJ {arquivo.cabecalho.cnpj})")
        identificados.append(arquivo)

    pares, problemas = pareia(identificados)

    # O mês vem do período declarado; vale o do primeiro arquivo quando há mais de um.
    if identificados:
        mes = f"{identificados[0].cabecalho.periodo_inicio:%Y-%m}"
        pasta = saida / mes
        nome_planilha = f"resumo_conferencia_{mes}.xlsx"
        meses = {a.cabecalho.periodo_inicio.strftime("%Y-%m") for a in identificados}
        if len(meses) > 1:
            anota(f"AVISO: períodos de meses diferentes; saída em {pasta}")
    else:
        pasta = saida
        nome_planilha = "resumo_conferencia.xlsx"
    pasta.mkdir(parents=True, exist_ok=True)

    resultados: list[ResultadoEmpresa] = []
    for par in pares:
        rotulo = f"{par.empresa.codigo} - {par.empresa.razao_social}"
        try:
            resultado = _confere_par(par)
        except Exception as e:
            erro = f"{rotulo}: falha ao ler {par.caminho_sefaz} / {par.caminho_dominio}: {e}"
            anota(f"ERRO {erro}")
            resultados.append(_erro_leitura(erro))
            continue
        try:
            escreve_relatorio(resultado, pasta / nome_arquivo(resultado))
        except Exception as e:
            # a conferência está válida e entra na planilha; só o PDF falhou
            anota(f"ERRO ao gravar o PDF de {rotulo}: {e}")
            resultado.erro = f"conferência feita, mas o PDF não foi gravado: {e}"
        anota(f"{rotulo}: {resultado.status} ({len(resultado.ocorrencias)} ocorrências)")
        resultados.append(resultado)
    for problema in problemas:
        anota(f"{problema.status}: {problema.erro}")
    resultados += problemas + falhas

    divergentes = sum(1 for r in resultados if r.status == Status.DIVERGENTE)
    anota(f"{len(resultados)} linha(s) no Resumo, {divergentes} divergente(s), "
          f"{time.monotonic() - inicio:.1f}s")
    # log primeiro: com a planilha aberta no Excel, escreve_planilha levanta PermissionError
    (pasta / "log_execucao.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    escreve_planilha(resultados, pasta / nome_planilha)
    return divergentes


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Confere entradas da Sefaz contra o Domínio.")
    ap.add_argument("--entrada", type=Path, default=Path("entrada"))
    ap.add_argument("--saida", type=Path, default=Path("saida"))
    args = ap.parse_args()
    try:
        sys.exit(min(executa(args.entrada, args.saida), LIMITE_CODIGO_SAIDA))
    except NotADirectoryError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        sys.exit(CODIGO_ENTRADA_INVALIDA)
