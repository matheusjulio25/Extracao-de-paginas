"""
Configurações do extrator de jurisprudência do CJF Unificado.
Ajuste os parâmetros de busca e os caminhos de saída conforme necessário.
"""

# ── URL base do sistema CJF Unificado ────────────────────────────────────────
BASE_URL = "https://jurisprudencia.cjf.jus.br/unificada"
SEARCH_URL = f"{BASE_URL}/index.xhtml"

# ── Parâmetros de busca ───────────────────────────────────────────────────────
TERMOS_BUSCA = "INSS benefício previdenciário"

# Tribunais disponíveis no CJF Unificado (deixe vazio para todos)
# Exemplos: "TRF1", "TRF2", "TRF3", "TRF4", "TRF5", "STJ"
TRIBUNAIS = []

# Máximo de páginas a percorrer (None = sem limite)
MAX_PAGINAS = 100

# Intervalo entre requisições em segundos (respeitar o servidor)
DELAY_REQUISICOES = 2.0

# ── Saída ─────────────────────────────────────────────────────────────────────
OUTPUT_DIR = "resultados"
ARQUIVO_TODAS = "todas_decisoes.csv"
ARQUIVO_FAVORAVEIS = "decisoes_favoraveis.csv"
ARQUIVO_JSON = "decisoes_favoraveis.json"
ARQUIVO_LOG = "extrator.log"

# ── Cabeçalhos HTTP ───────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}
