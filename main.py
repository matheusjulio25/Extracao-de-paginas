"""
Extrator e Classificador de Jurisprudência do INSS — CJF Unificado
Uso: python main.py [--termos "..."] [--tribunais TRF1 TRF4] [--paginas N]
"""

import argparse
import csv
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
        "termos_favoraveis": "; ".join(r.termos_favoraveis_encontrados),
        "termos_desfavoraveis": "; ".join(r.termos_desfavoraveis_encontrados),
        "texto_completo": d.texto_completo[:2000],  # trunca para CSV legível
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

def _imprimir_resumo(
    total: int, n_fav: int, n_desfav: int, output_dir: Path
) -> None:
    print("\n" + "=" * 60)
    print("  RESUMO DA EXTRAÇÃO")
    print("=" * 60)
    print(f"  Total de decisões extraídas : {total}")
    print(f"  Favoráveis ao segurado      : {n_fav}")
    print(f"  Desfavoráveis               : {n_desfav}")
    if total:
        pct = 100 * n_fav / total
        print(f"  Taxa de favorabilidade      : {pct:.1f}%")
    print(f"\n  Arquivos gerados em: {output_dir.resolve()}")
    print("=" * 60 + "\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

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
    parser.add_argument(
        "--termos",
        default=config.TERMOS_BUSCA,
        help=f'Termos de busca (padrão: "{config.TERMOS_BUSCA}")',
    )
    parser.add_argument(
        "--tribunais",
        nargs="*",
        default=config.TRIBUNAIS,
        metavar="TRIBUNAL",
        help="Tribunais a filtrar: TRF1 TRF2 TRF3 TRF4 TRF5 STJ (padrão: todos)",
    )
    parser.add_argument(
        "--paginas",
        type=int,
        default=config.MAX_PAGINAS,
        help=f"Número máximo de páginas (padrão: {config.MAX_PAGINAS})",
    )
    parser.add_argument(
        "--saida",
        default=config.OUTPUT_DIR,
        help=f'Diretório de saída (padrão: "{config.OUTPUT_DIR}")',
    )
    return parser.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()

    output_dir = Path(args.saida)
    output_dir.mkdir(parents=True, exist_ok=True)

    _configurar_log(output_dir)
    log = logging.getLogger(__name__)

    # Sobrescreve config com args da linha de comando
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
                log.info(
                    "[FAVORÁVEL (%s)] %s | %s",
                    resultado.confianca,
                    decisao.processo or "s/n",
                    decisao.tribunal or "s/tribunal",
                )
            else:
                log.debug(
                    "[desfavorável] %s | %s",
                    decisao.processo or "s/n",
                    decisao.tribunal or "s/tribunal",
                )

    except KeyboardInterrupt:
        log.warning("Extração interrompida pelo usuário.")
    except Exception as exc:
        log.error("Erro durante a extração: %s", exc, exc_info=True)
        raise

    finally:
        # Salva resultados mesmo se houver erro parcial
        _salvar_csv(todas, output_dir / config.ARQUIVO_TODAS)
        _salvar_csv(favoraveis, output_dir / config.ARQUIVO_FAVORAVEIS)
        _salvar_json(favoraveis, output_dir / config.ARQUIVO_JSON)
        _imprimir_resumo(len(todas), len(favoraveis), len(todas) - len(favoraveis), output_dir)


if __name__ == "__main__":
    main()
