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

# ── Palavras-chave: decisões FAVORÁVEIS ao segurado ──────────────────────────
KEYWORDS_FAVORAVEIS = [
    # Resultado
    "procedente",
    "procedência",
    "parcialmente procedente",
    # Deferimento
    "deferido",
    "deferimento",
    "deferir",
    # Recurso
    "recurso provido",
    "provimento ao recurso",
    "dar provimento",
    "deu provimento",
    "provido",
    # Concessão do benefício
    "concessão do benefício",
    "concessão de benefício",
    "conceder o benefício",
    "concedido o benefício",
    "benefício concedido",
    "direito ao benefício",
    # Implantação / restabelecimento
    "implantação do benefício",
    "implantação de benefício",
    "restabelecimento do benefício",
    "restabelecer o benefício",
    "restabelecido o benefício",
    # Aposentadoria / auxílio / pensão específicos
    "aposentadoria concedida",
    "aposentadoria deferida",
    "auxílio-doença concedido",
    "auxílio doença concedido",
    "benefício de prestação continuada",
    "bpc concedido",
    "loas concedido",
    "pensão por morte concedida",
    # Reforma
    "reforma da sentença",
    "reformar a sentença",
    "sentença reformada",
]

# ── Palavras-chave: decisões DESFAVORÁVEIS ao segurado ───────────────────────
KEYWORDS_DESFAVORAVEIS = [
    "improcedente",
    "improcedência",
    "indeferido",
    "indeferimento",
    "negar provimento",
    "negado provimento",
    "recurso não provido",
    "recurso improvido",
    "improvido",
    "não provido",
    "manutenção da sentença",
    "mantida a sentença",
    "mantém a sentença",
    "confirmada a sentença",
    "benefício negado",
    "negado o benefício",
    "inexistência de incapacidade",
    "capacidade laborativa",
    "não há direito",
]

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
