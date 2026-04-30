"""
Extrator e Classificador de Jurisprudência do INSS — CJF Unificado
Uso: python main.py [--termos "..."] [--tribunais TRF1 TRF4] [--paginas N]
     Ou simplesmente: python main.py  (abre menu interativo)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

import config
from classificador import ResultadoClassificacao, classificar
from extrator import Decisao, ExtratorCJF


# ── Logging ───────────────────────────────────────────────────────────────────

def _configurar_log(output_dir: Path) -> None:
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(output_dir / config.ARQUIVO_LOG, encoding="utf-8"),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


# ── Persistência ──────────────────────────────────────────────────────────────

def _decisao_para_dict(r: ResultadoClassificacao) -> dict:
    d = r.decisao
    return {
        "tribunal": d.tribunal,
        "processo": d.processo,
        "relator": d.relator,
        "data_julgamento": d.data_julgamento,
        "ementa": d.ementa,
        "url": d.url,
        "pagina_origem": d.pagina_origem,
        "favoravel": r.favoravel,
        "confianca": r.confianca,
        "score_favoravel": r.score_favoravel,
        "score_desfavoravel": r.score_desfavoravel,
        "trechos_favoraveis": "; ".join(r.trechos_favoraveis),
        "trechos_desfavoraveis": "; ".join(r.trechos_desfavoraveis),
        "dispositivo": r.dispositivo_extraido,
        "texto_completo": d.texto_completo[:2000],
    }


def _salvar_csv(registros: list[dict], caminho: Path) -> None:
    if not registros:
        logging.getLogger(__name__).warning("Nenhum registro para salvar em %s.", caminho)
        return
    df = pd.DataFrame(registros)
    df.to_csv(caminho, index=False, encoding="utf-8-sig")
    logging.getLogger(__name__).info("Salvo: %s (%d linhas)", caminho, len(df))


def _salvar_json(registros: list[dict], caminho: Path) -> None:
    if not registros:
        return
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(registros, f, ensure_ascii=False, indent=2)
    logging.getLogger(__name__).info("Salvo: %s (%d registros)", caminho, len(registros))


# ── Relatório resumo ──────────────────────────────────────────────────────────

def _imprimir_resumo(total: int, n_fav: int, n_desfav: int, output_dir: Path) -> None:
    print("\n" + "=" * 60)
    print("  RESUMO DA EXTRAÇÃO")
    print("=" * 60)
    print(f"  Total de decisões extraídas : {total}")
    print(f"  Favoráveis ao segurado      : {n_fav}")
    print(f"  Desfavoráveis               : {n_desfav}")
    if total:
        print(f"  Taxa de favorabilidade      : {100 * n_fav / total:.1f}%")
    print(f"\n  Arquivos gerados em: {output_dir.resolve()}")
    print("=" * 60 + "\n")


# ── Menu interativo ───────────────────────────────────────────────────────────

_TRIBUNAIS_VALIDOS = ["TRF1", "TRF2", "TRF3", "TRF4", "TRF5", "STJ"]

def _perguntar(pergunta: str, padrao: str = "") -> str:
    """Exibe uma pergunta e retorna a resposta, ou o padrão se vazio."""
    dica = f" [{padrao}]" if padrao else ""
    try:
        resposta = input(f"{pergunta}{dica}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return resposta if resposta else padrao


def _menu_interativo() -> argparse.Namespace:
    """Exibe o menu no terminal e coleta os parâmetros do usuário."""
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   Extrator de Jurisprudência INSS — CJF Unificado        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    # ── Termos de busca ───────────────────────────────────────────────────────
    print("  Exemplos de termos:")
    print("    auxílio-doença incapacidade")
    print("    aposentadoria por invalidez")
    print("    BPC LOAS benefício assistencial")
    print("    pensão por morte dependente")
    print()
    termos = _perguntar("  Termos de busca", config.TERMOS_BUSCA)

    # ── Tribunais ─────────────────────────────────────────────────────────────
    print()
    print(f"  Tribunais disponíveis: {', '.join(_TRIBUNAIS_VALIDOS)}")
    print("  (deixe em branco para pesquisar em todos)")
    entrada_tribunais = _perguntar("  Tribunais", "")

    tribunais: list[str] = []
    if entrada_tribunais:
        for t in entrada_tribunais.upper().replace(",", " ").split():
            if t in _TRIBUNAIS_VALIDOS:
                tribunais.append(t)
            else:
                print(f"  ! Tribunal '{t}' não reconhecido — ignorado.")

    # ── Número máximo de páginas ──────────────────────────────────────────────
    print()
    paginas_str = _perguntar("  Número máximo de páginas", str(config.MAX_PAGINAS))
    try:
        paginas = int(paginas_str)
        if paginas <= 0:
            raise ValueError
    except ValueError:
        print(f"  ! Valor inválido, usando padrão ({config.MAX_PAGINAS}).")
        paginas = config.MAX_PAGINAS

    # ── Pasta de saída ────────────────────────────────────────────────────────
    print()
    saida = _perguntar("  Pasta de saída", config.OUTPUT_DIR)

    # ── Confirmação ───────────────────────────────────────────────────────────
    print()
    print("  ┌─ Configuração ──────────────────────────────────────┐")
    print(f"  │  Termos   : {termos}")
    print(f"  │  Tribunais: {', '.join(tribunais) if tribunais else 'todos'}")
    print(f"  │  Páginas  : {paginas}")
    print(f"  │  Saída    : {saida}")
    print("  └────────────────────────────────────────────────────┘")
    print()

    confirmacao = _perguntar("  Iniciar extração? (s/n)", "s").lower()
    if confirmacao not in ("s", "sim", "y", "yes", ""):
        print("  Cancelado.")
        sys.exit(0)

    print()

    ns = argparse.Namespace()
    ns.termos = termos
    ns.tribunais = tribunais
    ns.paginas = paginas
    ns.saida = saida
    return ns


# ── CLI (argumentos de linha de comando) ──────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrai jurisprudência do CJF Unificado e filtra decisões favoráveis ao segurado INSS.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python main.py
  python main.py --termos "auxílio-doença incapacidade"
  python main.py --termos "aposentadoria por invalidez" --tribunais TRF4 STJ
  python main.py --paginas 10 --saida meus_resultados
        """,
    )
    parser.add_argument("--termos", default=None,
                        help="Termos de busca")
    parser.add_argument("--tribunais", nargs="*", default=None, metavar="TRIBUNAL",
                        help="TRF1 TRF2 TRF3 TRF4 TRF5 STJ (padrão: todos)")
    parser.add_argument("--paginas", type=int, default=None,
                        help="Número máximo de páginas")
    parser.add_argument("--saida", default=None,
                        help="Diretório de saída")
    return parser.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    cli = _parse_args()

    # Se nenhum argumento foi passado, abre o menu interativo
    if cli.termos is None and cli.tribunais is None and cli.paginas is None and cli.saida is None:
        args = _menu_interativo()
    else:
        # Preenche valores padrão para argumentos omitidos
        args = argparse.Namespace(
            termos=cli.termos or config.TERMOS_BUSCA,
            tribunais=cli.tribunais or config.TRIBUNAIS,
            paginas=cli.paginas or config.MAX_PAGINAS,
            saida=cli.saida or config.OUTPUT_DIR,
        )

    output_dir = Path(args.saida)
    output_dir.mkdir(parents=True, exist_ok=True)

    _configurar_log(output_dir)
    log = logging.getLogger(__name__)

    config.MAX_PAGINAS = args.paginas

    log.info("Iniciando extração | Termos: '%s' | Tribunais: %s | Máx. páginas: %d",
             args.termos, args.tribunais or "todos", args.paginas)

    extrator = ExtratorCJF()
    todas: list[dict] = []
    favoraveis: list[dict] = []

    try:
        for decisao in extrator.buscar(termos=args.termos, tribunais=args.tribunais):
            resultado = classificar(decisao)
            registro = _decisao_para_dict(resultado)
            todas.append(registro)

            if resultado.favoravel:
                favoraveis.append(registro)
                log.info("[FAVORÁVEL (%s)] %s | %s",
                         resultado.confianca,
                         decisao.processo or "s/n",
                         decisao.tribunal or "s/tribunal")
            else:
                log.debug("[desfavorável] %s | %s",
                          decisao.processo or "s/n",
                          decisao.tribunal or "s/tribunal")

    except KeyboardInterrupt:
        log.warning("Extração interrompida pelo usuário.")
    except Exception as exc:
        log.error("Erro durante a extração: %s", exc, exc_info=True)
        raise
    finally:
        _salvar_csv(todas, output_dir / config.ARQUIVO_TODAS)
        _salvar_csv(favoraveis, output_dir / config.ARQUIVO_FAVORAVEIS)
        _salvar_json(favoraveis, output_dir / config.ARQUIVO_JSON)
        _imprimir_resumo(len(todas), len(favoraveis), len(todas) - len(favoraveis), output_dir)


if __name__ == "__main__":
    main()
