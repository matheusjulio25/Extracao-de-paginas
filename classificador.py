"""
Classifica decisões judiciais como favoráveis ou desfavoráveis
ao segurado que pediu benefício do INSS.

Lógica contextual:
  - "recurso do INSS improvido"   → FAVORÁVEL  ao segurado
  - "recurso do segurado improvido" → DESFAVORÁVEL ao segurado
  - "indeferido" no histórico dos fatos → neutro (só contexto)
  - A classificação prioriza o DISPOSITIVO da decisão
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from extrator import Decisao


# ── Normalização ──────────────────────────────────────────────────────────────

_ACENTOS = str.maketrans(
    "áàãâäéèêëíìîïóòõôöúùûüç",
    "aaaaaeeeeiiiiooooouuuuc",
)

def _norm(texto: str) -> str:
    return texto.lower().translate(_ACENTOS)


# ── Identificação de partes ───────────────────────────────────────────────────

# Termos que identificam o INSS/réu como recorrente
_INSS_PARTE = r"""
    (?:
        inss | autarquia | instituto\s+nacional | previdencia\s+social |
        reu | re | apelado(?!\s+e\s+apelante) | recorrido(?!\s+e\s+recorrente) |
        parte\s+re | agravado(?!\s+e\s+agravante)
    )
"""

# Termos que identificam o segurado/autor como recorrente
_SEGURADO_PARTE = r"""
    (?:
        segurado | autor | autora | requerente | apelante(?!\s+e\s+apelado) |
        recorrente(?!\s+e\s+recorrido) | parte\s+autora | impetrante |
        agravante(?!\s+e\s+agravado) | embargante
    )
"""

_F = re.IGNORECASE | re.VERBOSE


# ── Padrões contextuais: FAVORÁVEIS ao segurado ───────────────────────────────
#
# Cada padrão captura uma frase do dispositivo/ementa que indica que
# o segurado ganhou, diretamente ou porque o INSS perdeu o recurso.

_PADROES_FAVORAVEIS: list[re.Pattern] = [
    # ── Recurso do INSS negado/improvido ──────────────────────────────────────
    # "nao provido" explícito — sem tornar "nao" opcional para não casar com "provido"
    re.compile(
        rf"recurso\s+d[ao]\s+{_INSS_PARTE}\s+(?:a\s+que\s+se\s+)?nao\s+(?:e\s+)?(?:provido|conhecido)\b",
        _F,
    ),
    re.compile(
        rf"recurso\s+d[ao]\s+{_INSS_PARTE}\s+im?provido\b",
        _F,
    ),
    re.compile(
        rf"recurso\s+d[ao]\s+{_INSS_PARTE}\s+desprovido\b",
        _F,
    ),
    re.compile(
        rf"(?:negar?|nego|negado|nega-se)\s+provimento\s+ao?\s+recurso\s+d[ao]\s+{_INSS_PARTE}",
        _F,
    ),
    re.compile(
        rf"apelac[ao]{{1,2}}\s+d[ao]\s+{_INSS_PARTE}\s+"
        r"(?:a\s+que\s+se\s+)?(?:im?provida|desprovida|nao\s+(?:e\s+)?provida)\b",
        _F,
    ),
    re.compile(
        r"(?:negar?|nego|negado)\s+provimento\s+(?:ao?\s+)?(?:apelo|apelacao|agravo|recurso)"
        rf"\s+d[ao]\s+{_INSS_PARTE}",
        _F,
    ),

    # ── Recurso do segurado provido ───────────────────────────────────────────
    re.compile(
        rf"recurso\s+d[ao]\s+{_SEGURADO_PARTE}\s+"
        r"(?:a\s+que\s+se\s+)?(?:e\s+)?provido\b",
        _F,
    ),
    re.compile(
        rf"(?:dar?|dou|dado|dando)\s+provimento\s+ao?\s+recurso\s+d[ao]\s+{_SEGURADO_PARTE}",
        _F,
    ),
    re.compile(
        rf"apelac[ao]{{1,2}}\s+d[ao]\s+{_SEGURADO_PARTE}\s+"
        r"(?:a\s+que\s+se\s+)?(?:e\s+)?provida\b",
        _F,
    ),

    # ── Pedido julgado procedente ─────────────────────────────────────────────
    # Negative lookbehind para não casar "improcedente"
    re.compile(r"(?<![a-z])(?:julgo?|julgado|pedido|acao)\s+procedente\b", _F),
    re.compile(r"(?<![a-z])procedente\s+(?:o\s+)?(?:pedido|a\s+acao|o\s+recurso)\b", _F),
    re.compile(r"\bparcialmente\s+procedente\b", _F),

    # ── Concessão/implantação/restabelecimento direta ─────────────────────────
    re.compile(r"\b(?:conceder?|concedo|concedido|concedida)\s+o?\s*beneficio\b", _F),
    re.compile(r"\bconcessao\s+d[oa]\s+beneficio\b", _F),
    re.compile(r"\bimplantar?\s+o?\s*beneficio\b", _F),
    re.compile(r"\bimplantacao\s+d[oa]\s*beneficio\b", _F),
    re.compile(r"\brestabelecer?\s+o?\s*beneficio\b", _F),
    re.compile(r"\brestabelecimento\s+d[oa]\s*beneficio\b", _F),
    re.compile(r"\b(?:deferir?|deferido|deferida|defiro)\s+o?\s*beneficio\b", _F),
    re.compile(r"\bbeneficio\s+(?:previdenciario\s+)?(?:e\s+)?(?:concedido|deferido|implantado|restabelecido)\b", _F),

    # ── Aposentadoria / auxílio / BPC específicos ─────────────────────────────
    re.compile(r"\baposentadoria\s+(?:por\s+invalidez\s+)?(?:concedida|deferida)\b", _F),
    re.compile(r"\bauxilio.doenca\s+(?:concedido|deferido)\b", _F),
    re.compile(r"\b(?:bpc|loas)\s+(?:concedido|deferido)\b", _F),
    re.compile(r"\bpensao\s+por\s+morte\s+(?:concedida|deferida)\b", _F),

    # ── Sentença de 1º grau mantida (procedente mantida = favorável) ──────────
    re.compile(r"sentenca\s+(?:de\s+primeiro\s+grau\s+)?mantida.*?procedente", _F),
    re.compile(r"confirmo?\s+a\s+sentenca.*?procedente", _F),
]

# ── Padrões contextuais: DESFAVORÁVEIS ao segurado ───────────────────────────

_PADROES_DESFAVORAVEIS: list[re.Pattern] = [
    # ── Recurso do INSS provido ───────────────────────────────────────────────
    re.compile(
        rf"recurso\s+d[ao]\s+{_INSS_PARTE}\s+"
        r"(?:a\s+que\s+se\s+)?(?:e\s+)?provido\b",
        _F,
    ),
    re.compile(
        rf"(?:dar?|dou|dado)\s+provimento\s+ao?\s+recurso\s+d[ao]\s+{_INSS_PARTE}",
        _F,
    ),
    re.compile(
        rf"apelac[ao]{{1,2}}\s+d[ao]\s+{_INSS_PARTE}\s+"
        r"(?:a\s+que\s+se\s+)?(?:e\s+)?provida\b",
        _F,
    ),

    # ── Recurso do segurado negado/improvido ──────────────────────────────────
    re.compile(
        rf"recurso\s+d[ao]\s+{_SEGURADO_PARTE}\s+"
        r"(?:a\s+que\s+se\s+)?(?:nao\s+(?:e\s+)?)?(?:provido|conhecido)\b|"
        rf"recurso\s+d[ao]\s+{_SEGURADO_PARTE}\s+im?provido\b|"
        rf"recurso\s+d[ao]\s+{_SEGURADO_PARTE}\s+desprovido\b",
        _F,
    ),
    re.compile(
        rf"(?:negar?|nego|negado)\s+provimento\s+ao?\s+recurso\s+d[ao]\s+{_SEGURADO_PARTE}",
        _F,
    ),

    # ── Pedido julgado improcedente ───────────────────────────────────────────
    re.compile(r"\bimprocedente\b", _F),
    re.compile(r"\b(?:julgo?|julgado|pedido)\s+improcedente\b", _F),

    # ── Negativa direta de benefício ──────────────────────────────────────────
    re.compile(r"\b(?:negar?|nego|negado|negada)\s+o?\s*beneficio\b", _F),
    re.compile(r"\bbeneficio\s+(?:e\s+)?(?:negado|indeferido)\b", _F),
    re.compile(r"\b(?:indefiro?|indeferido|indeferida)\s+o?\s*(?:pedido|beneficio|requerimento)\b", _F),

    # ── Capacidade laboral intacta ────────────────────────────────────────────
    re.compile(r"\bcapacidade\s+laborativa\s+(?:preservada|mantida|nao\s+(?:afastada|comprometida))\b", _F),
    re.compile(r"\bnao\s+(?:ha|existe|foi\s+comprovada)\s+incapacidade\b", _F),
    re.compile(r"\binexistencia\s+de\s+incapacidade\b", _F),

    # ── Sentença desfavorável mantida ────────────────────────────────────────
    re.compile(r"sentenca\s+(?:de\s+primeiro\s+grau\s+)?mantida.*?improcedente", _F),
]


# ── Extração do dispositivo ───────────────────────────────────────────────────

_MARCADORES_DISPOSITIVO = re.compile(
    r"(?:acordam?\b|pelo\s+exposto|diante\s+do\s+exposto|"
    r"ante\s+o\s+exposto|isso\s+posto|em\s+face\s+do\s+exposto|"
    r"ex\s+positis|ex\s+positis|vistos?\s+e\s+relatados?\b)",
    re.IGNORECASE,
)

def _extrair_dispositivo(texto: str) -> str:
    """
    Tenta isolar o dispositivo/acordão.
    Se não encontrar marcador, usa os últimos 1500 caracteres
    (o dispositivo costuma vir no fim).
    """
    m = _MARCADORES_DISPOSITIVO.search(texto)
    if m:
        return texto[m.start():]
    return texto[-1500:]


# ── Aplicação dos padrões ─────────────────────────────────────────────────────

def _aplicar_padroes(
    texto_norm: str,
    padroes: list[re.Pattern],
) -> list[str]:
    """Retorna lista de trechos do texto que casaram com algum padrão."""
    encontrados: list[str] = []
    for p in padroes:
        m = p.search(texto_norm)
        if m:
            encontrados.append(m.group(0).strip())
    return encontrados


# ── Interface pública ─────────────────────────────────────────────────────────

@dataclass
class ResultadoClassificacao:
    decisao: Decisao
    favoravel: bool
    score_favoravel: int
    score_desfavoravel: int
    trechos_favoraveis: list[str] = field(default_factory=list)
    trechos_desfavoraveis: list[str] = field(default_factory=list)
    confianca: str = "baixa"   # "alta", "media", "baixa"
    dispositivo_extraido: str = ""


def classificar(decisao: Decisao) -> ResultadoClassificacao:
    """
    Classifica uma decisão como favorável ou desfavorável ao segurado.

    Estratégia em duas etapas:
    1. Extrai o dispositivo (parágrafo conclusivo) — parte mais confiável.
    2. Aplica padrões contextuais que consideram quem ganhou/perdeu o recurso.
    """
    texto_completo = f"{decisao.ementa} {decisao.texto_completo}"
    dispositivo = _extrair_dispositivo(texto_completo)

    # Normaliza para comparação sem acentos/maiúsculas
    disp_norm = _norm(dispositivo)
    full_norm = _norm(texto_completo)

    # Aplica padrões primeiro no dispositivo (mais confiável)
    trechos_fav = _aplicar_padroes(disp_norm, _PADROES_FAVORAVEIS)
    trechos_desfav = _aplicar_padroes(disp_norm, _PADROES_DESFAVORAVEIS)

    # Se não achou nada no dispositivo, tenta no texto completo
    if not trechos_fav and not trechos_desfav:
        trechos_fav = _aplicar_padroes(full_norm, _PADROES_FAVORAVEIS)
        trechos_desfav = _aplicar_padroes(full_norm, _PADROES_DESFAVORAVEIS)

    score_fav = len(trechos_fav)
    score_desfav = len(trechos_desfav)

    # Desfavorável vence empate (conservador: não classificar como vitória na dúvida)
    favoravel = score_fav > score_desfav

    diferenca = abs(score_fav - score_desfav)
    confianca = "alta" if diferenca >= 2 else ("media" if diferenca == 1 else "baixa")

    return ResultadoClassificacao(
        decisao=decisao,
        favoravel=favoravel,
        score_favoravel=score_fav,
        score_desfavoravel=score_desfav,
        trechos_favoraveis=trechos_fav,
        trechos_desfavoraveis=trechos_desfav,
        confianca=confianca,
        dispositivo_extraido=dispositivo[:500],
    )


def classificar_lote(
    decisoes: list[Decisao],
) -> tuple[list[ResultadoClassificacao], list[ResultadoClassificacao]]:
    favoraveis: list[ResultadoClassificacao] = []
    desfavoraveis: list[ResultadoClassificacao] = []
    for d in decisoes:
        r = classificar(d)
        (favoraveis if r.favoravel else desfavoraveis).append(r)
    return favoraveis, desfavoraveis
