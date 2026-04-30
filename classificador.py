"""
Classifica decisões judiciais como favoráveis ou desfavoráveis
ao segurado que pediu benefício do INSS.
"""

import re
from dataclasses import dataclass
from typing import Optional

import config
from extrator import Decisao


@dataclass
class ResultadoClassificacao:
    decisao: Decisao
    favoravel: bool
    score_favoravel: int
    score_desfavoravel: int
    termos_favoraveis_encontrados: list[str]
    termos_desfavoraveis_encontrados: list[str]
    confianca: str  # "alta", "media", "baixa"


def _normalizar(texto: str) -> str:
    """Converte para minúsculas e remove acentuação para comparação robusta."""
    texto = texto.lower()
    substituicoes = {
        "á": "a", "à": "a", "ã": "a", "â": "a",
        "é": "e", "ê": "e",
        "í": "i", "î": "i",
        "ó": "o", "ô": "o", "õ": "o",
        "ú": "u", "û": "u",
        "ç": "c",
    }
    for orig, rep in substituicoes.items():
        texto = texto.replace(orig, rep)
    return texto


def _contar_ocorrencias(texto_norm: str, keywords: list[str]) -> tuple[int, list[str]]:
    """
    Retorna (contagem, lista de termos encontrados) para os keywords no texto.
    """
    encontrados: list[str] = []
    for kw in keywords:
        kw_norm = _normalizar(kw)
        # Word-boundary simples: verifica se está rodeado por não-letra
        padrao = r"(?<![a-z])" + re.escape(kw_norm) + r"(?![a-z])"
        if re.search(padrao, texto_norm):
            encontrados.append(kw)
    return len(encontrados), encontrados


def _extrair_contexto_resultado(texto: str) -> Optional[str]:
    """
    Tenta localizar o parágrafo/frase que contém o resultado do julgamento.
    Útil para debug e transparência.
    """
    padroes = [
        r"ACORD[AÃ][OA][^\.]{0,400}\.",
        r"(NEGO|DOU|JULGO|DEFIRO|INDEFIRO)[^\.]{0,300}\.",
        r"(proc[ea]d[ea]nte|improcedente|provido|improvido)[^\.]{0,200}\.",
    ]
    for p in padroes:
        m = re.search(p, texto, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(0).strip()
    return None


def classificar(decisao: Decisao) -> ResultadoClassificacao:
    """
    Classifica uma decisão como favorável ou desfavorável ao segurado.
    Usa contagem ponderada de palavras-chave no texto completo + ementa.
    """
    texto_base = f"{decisao.ementa} {decisao.texto_completo}"
    texto_norm = _normalizar(texto_base)

    score_fav, termos_fav = _contar_ocorrencias(texto_norm, config.KEYWORDS_FAVORAVEIS)
    score_desfav, termos_desfav = _contar_ocorrencias(texto_norm, config.KEYWORDS_DESFAVORAVEIS)

    # Regra de desempate: desfavorável vence em caso de igualdade
    favoravel = score_fav > score_desfav

    # Confiança baseada na diferença de scores
    diferenca = abs(score_fav - score_desfav)
    if diferenca >= 3:
        confianca = "alta"
    elif diferenca >= 1:
        confianca = "media"
    else:
        confianca = "baixa"

    return ResultadoClassificacao(
        decisao=decisao,
        favoravel=favoravel,
        score_favoravel=score_fav,
        score_desfavoravel=score_desfav,
        termos_favoraveis_encontrados=termos_fav,
        termos_desfavoraveis_encontrados=termos_desfav,
        confianca=confianca,
    )


def classificar_lote(decisoes: list[Decisao]) -> tuple[list[ResultadoClassificacao], list[ResultadoClassificacao]]:
    """
    Classifica uma lista de decisões.
    Retorna (favoraveis, desfavoraveis).
    """
    favoraveis: list[ResultadoClassificacao] = []
    desfavoraveis: list[ResultadoClassificacao] = []

    for d in decisoes:
        resultado = classificar(d)
        if resultado.favoravel:
            favoraveis.append(resultado)
        else:
            desfavoraveis.append(resultado)

    return favoraveis, desfavoraveis
