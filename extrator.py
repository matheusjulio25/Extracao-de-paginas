"""
Extrator de jurisprudência do CJF Unificado.
Realiza a busca, navega pelas páginas e retorna os textos das decisões.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)


@dataclass
class Decisao:
    tribunal: str = ""
    processo: str = ""
    relator: str = ""
    data_julgamento: str = ""
    ementa: str = ""
    texto_completo: str = ""
    url: str = ""
    pagina_origem: int = 0


class ExtratorCJF:
    """
    Extrator para o sistema JSF do CJF Unificado.
    Mantém sessão HTTP e gerencia o ViewState entre requisições.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(config.HEADERS)
        self._view_state: Optional[str] = None
        self._form_id: Optional[str] = None

    # ── Utilitários internos ──────────────────────────────────────────────────

    def _get_soup(self, url: str, **kwargs) -> BeautifulSoup:
        resp = self.session.get(url, timeout=30, **kwargs)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    def _post_soup(self, url: str, data: dict, **kwargs) -> BeautifulSoup:
        resp = self.session.post(url, data=data, timeout=30, **kwargs)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    def _extrair_view_state(self, soup: BeautifulSoup) -> str:
        tag = soup.find("input", {"name": "javax.faces.ViewState"})
        if not tag:
            raise RuntimeError(
                "ViewState não encontrado na página. "
                "O site pode ter mudado sua estrutura."
            )
        return tag["value"]

    def _extrair_form_id(self, soup: BeautifulSoup) -> str:
        """Detecta o id do formulário de busca."""
        for form in soup.find_all("form"):
            fid = form.get("id", "")
            if any(kw in fid.lower() for kw in ("pesquis", "busca", "search", "form")):
                return fid
        # Fallback: primeiro formulário
        form = soup.find("form")
        return form.get("id", "") if form else ""

    def _montar_payload_busca(
        self, soup: BeautifulSoup, termos: str, tribunais: list[str]
    ) -> dict:
        """
        Constrói o payload POST para a busca no sistema CJF.
        Inspeciona o formulário para identificar os campos corretos.
        """
        form_id = self._form_id or ""
        view_state = self._view_state or self._extrair_view_state(soup)

        # Monta campos base que o JSF sempre exige
        payload: dict = {
            "javax.faces.ViewState": view_state,
            "javax.faces.partial.ajax": "false",
        }

        # Localiza campos de texto/select dentro do formulário
        form = soup.find("form", {"id": form_id}) if form_id else soup.find("form")
        if not form:
            raise RuntimeError("Formulário de busca não encontrado.")

        # Preenche todos os inputs hidden e checkboxes visíveis por padrão
        for inp in form.find_all("input"):
            name = inp.get("name", "")
            itype = inp.get("type", "text").lower()
            if not name or name == "javax.faces.ViewState":
                continue
            if itype == "hidden":
                payload[name] = inp.get("value", "")
            elif itype == "checkbox" and inp.get("checked"):
                payload[name] = inp.get("value", "on")

        # Preenche selects com o valor padrão (primeiro option ou "")
        for sel in form.find_all("select"):
            name = sel.get("name", "")
            if not name:
                continue
            selected = sel.find("option", selected=True)
            payload[name] = selected["value"] if selected else ""

        # Injeta o termo de busca no campo correto
        campo_texto = self._detectar_campo_texto(form)
        if campo_texto:
            payload[campo_texto] = termos
            logger.debug("Campo de busca detectado: %s", campo_texto)
        else:
            logger.warning(
                "Não foi possível detectar o campo de busca automaticamente. "
                "Inspecione o HTML e defina CAMPO_BUSCA em config.py."
            )

        # Injeta os tribunais selecionados (se houver)
        if tribunais:
            campo_tribunal = self._detectar_campo_tribunal(form)
            if campo_tribunal:
                for t in tribunais:
                    payload[campo_tribunal] = t

        # Botão de pesquisa
        btn = form.find("input", {"type": "submit"}) or form.find(
            "button", {"type": "submit"}
        )
        if btn and btn.get("name"):
            payload[btn["name"]] = btn.get("value", "Pesquisar")

        return payload

    def _detectar_campo_texto(self, form) -> Optional[str]:
        """Detecta o campo de texto livre de busca."""
        candidatos = [
            "palavrasChave", "pesquisa", "busca", "query", "q",
            "termoBusca", "texto", "ementa", "inteiro",
        ]
        for inp in form.find_all("input", {"type": ["text", "search", None]}):
            name = inp.get("name", "")
            if not name:
                continue
            parte = name.split(":")[-1].lower()  # remove prefixo JSF
            for c in candidatos:
                if c.lower() in parte:
                    return name
        # Fallback: primeiro input type=text
        for inp in form.find_all("input"):
            if inp.get("type", "text").lower() in ("text", "search"):
                return inp.get("name")
        return None

    def _detectar_campo_tribunal(self, form) -> Optional[str]:
        """Detecta o select/checkbox de tribunal."""
        for sel in form.find_all("select"):
            name = sel.get("name", "")
            if "tribunal" in name.lower() or "orgao" in name.lower():
                return name
        return None

    # ── Extração de resultados ────────────────────────────────────────────────

    def _extrair_decisoes_da_pagina(
        self, soup: BeautifulSoup, pagina: int
    ) -> list[Decisao]:
        decisoes: list[Decisao] = []

        # Estratégia 1: tabela de resultados
        tabela = soup.find("table", {"class": re.compile(r"result|dado|lista", re.I)})
        if not tabela:
            tabela = soup.find("table")

        if tabela:
            linhas = tabela.find_all("tr")
            for linha in linhas[1:]:  # pula cabeçalho
                cols = linha.find_all(["td", "th"])
                if len(cols) < 2:
                    continue
                texto_linha = " | ".join(c.get_text(strip=True) for c in cols)
                if not texto_linha.strip():
                    continue

                d = Decisao(pagina_origem=pagina)
                d.texto_completo = texto_linha

                # Tenta extrair link para decisão completa
                link = linha.find("a", href=True)
                if link:
                    d.url = urljoin(config.BASE_URL, link["href"])
                    d.ementa = link.get_text(strip=True)

                # Campos comuns nas colunas
                self._preencher_campos_tabela(d, cols)
                decisoes.append(d)

        # Estratégia 2: divs/articles de resultado
        if not decisoes:
            containers = soup.find_all(
                ["div", "article", "li"],
                {"class": re.compile(r"result|acordao|ementa|julgado", re.I)},
            )
            for c in containers:
                d = Decisao(pagina_origem=pagina)
                d.texto_completo = c.get_text(separator=" ", strip=True)
                link = c.find("a", href=True)
                if link:
                    d.url = urljoin(config.BASE_URL, link["href"])
                    d.ementa = link.get_text(strip=True)
                decisoes.append(d)

        logger.info("Página %d: %d decisões encontradas.", pagina, len(decisoes))
        return decisoes

    def _preencher_campos_tabela(self, d: Decisao, cols: list) -> None:
        """Heurística para mapear colunas a campos conhecidos."""
        rotulos = {
            "tribunal": ("tribunal", "orgao", "órgão"),
            "processo": ("processo", "número", "numero", "proc"),
            "relator": ("relator", "desembargador", "ministro"),
            "data_julgamento": ("data", "julgamento", "publicação"),
            "ementa": ("ementa", "decisão", "acórdão"),
        }
        for col in cols:
            texto = col.get_text(strip=True)
            # Tenta cabeçalho anterior se disponível
            header = col.get("data-label", "").lower()
            for campo, palavras in rotulos.items():
                if any(p in header for p in palavras):
                    setattr(d, campo, texto)
                    break

    def _extrair_texto_decisao_completa(self, url: str) -> str:
        """Acessa a URL da decisão e extrai o texto integral."""
        try:
            soup = self._get_soup(url)
            # Procura área principal de conteúdo
            for seletor in [
                {"id": re.compile(r"content|principal|corpo|texto", re.I)},
                {"class": re.compile(r"content|principal|corpo|texto|acord", re.I)},
            ]:
                container = soup.find(["div", "main", "section"], seletor)
                if container:
                    return container.get_text(separator="\n", strip=True)
            return soup.get_text(separator="\n", strip=True)
        except Exception as exc:
            logger.warning("Erro ao buscar decisão %s: %s", url, exc)
            return ""

    # ── Navegação entre páginas ───────────────────────────────────────────────

    def _proximo_payload_paginacao(
        self, soup: BeautifulSoup, pagina_atual: int
    ) -> Optional[dict]:
        """
        Monta o payload para avançar para a próxima página.
        Suporta links diretos (GET) e botões JSF (POST com ViewState).
        """
        padroes_proximo = re.compile(
            r"(próxim|proxim|next|avançar|avancar|»\s*$|>\s*$)", re.I
        )

        # ── 1. Links com href direto (não precisam de ViewState) ──────────────
        for a in soup.find_all("a"):
            texto = a.get_text(strip=True)
            href = a.get("href", "")
            if padroes_proximo.search(texto) and href and not href.startswith("#"):
                return {"_link": urljoin(config.BASE_URL, href)}

        # ── 2. Paginação numérica por href direto ─────────────────────────────
        proxima = str(pagina_atual + 1)
        for a in soup.find_all("a"):
            if a.get_text(strip=True) == proxima:
                href = a.get("href", "")
                if href and not href.startswith("#"):
                    return {"_link": urljoin(config.BASE_URL, href)}

        # ── 3. Navegação JSF (precisa de ViewState) ───────────────────────────
        try:
            view_state = self._extrair_view_state(soup)
        except RuntimeError:
            # Página de resultados não tem ViewState — sem mais páginas via JSF
            logger.debug("ViewState ausente na página %d; sem paginação JSF.", pagina_atual)
            view_state = None

        if view_state:
            # Links com onclick JSF
            for a in soup.find_all("a"):
                texto = a.get_text(strip=True)
                onclick = a.get("onclick", "")
                jsf_id = self._extrair_id_jsf(onclick)
                if jsf_id and (padroes_proximo.search(texto) or texto == proxima):
                    return self._payload_jsf_click(jsf_id, view_state)

            # Botões de submit com label "próximo"
            for btn in soup.find_all(["input", "button"]):
                label = (btn.get("value", "") + " " + btn.get_text()).strip()
                if padroes_proximo.search(label):
                    name = btn.get("name", "")
                    if name:
                        return {"javax.faces.ViewState": view_state, name: btn.get("value", "")}

        return None  # Sem próxima página

    def _extrair_id_jsf(self, onclick: str) -> Optional[str]:
        """Extrai o component id de uma chamada JSF em onclick."""
        m = re.search(r"['\"]([^'\"]+)['\"]", onclick)
        return m.group(1) if m else None

    def _payload_jsf_click(self, component_id: str, view_state: str) -> dict:
        return {
            "javax.faces.ViewState": view_state,
            "javax.faces.source": component_id,
            "javax.faces.partial.ajax": "true",
            "javax.faces.partial.execute": "@all",
            "javax.faces.partial.render": "@all",
            component_id: component_id,
        }

    # ── Interface pública ─────────────────────────────────────────────────────

    def buscar(
        self, termos: str, tribunais: list[str] | None = None
    ) -> Generator[Decisao, None, None]:
        """
        Realiza a busca e itera pelas páginas, gerando objetos Decisao.
        """
        tribunais = tribunais or []
        logger.info("Iniciando busca: '%s' | Tribunais: %s", termos, tribunais or "todos")

        # Carrega a página inicial
        logger.info("Carregando página inicial...")
        soup = self._get_soup(config.SEARCH_URL)
        self._form_id = self._extrair_form_id(soup)
        self._view_state = self._extrair_view_state(soup)
        logger.debug("Form ID: %s | ViewState (primeiros 20 chars): %s...", self._form_id, self._view_state[:20])

        # Envia a busca
        payload = self._montar_payload_busca(soup, termos, tribunais)
        logger.info("Enviando formulário de busca...")
        time.sleep(config.DELAY_REQUISICOES)
        resp = self.session.post(config.SEARCH_URL, data=payload, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Salva HTML da página de resultados para diagnóstico
        debug_path = Path(config.OUTPUT_DIR) / "debug_pagina_resultados.html"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(resp.text, encoding="utf-8")
        logger.info("HTML de resultados salvo em: %s", debug_path)

        pagina = 1
        max_p = config.MAX_PAGINAS or float("inf")

        while pagina <= max_p:
            logger.info("── Processando página %d ──", pagina)

            # Detecta mensagem de "sem resultados"
            texto_pagina = soup.get_text().lower()
            if any(
                msg in texto_pagina
                for msg in ("nenhum resultado", "sem resultados", "não encontrad", "0 resultado")
            ):
                logger.info("Nenhum resultado encontrado. Encerrando.")
                break

            decisoes = self._extrair_decisoes_da_pagina(soup, pagina)
            if not decisoes:
                logger.info("Página %d sem decisões. Verificando paginação...", pagina)

            for d in decisoes:
                # Busca texto completo se a ementa estiver vazia
                if d.url and not d.texto_completo.strip():
                    logger.debug("Buscando texto completo: %s", d.url)
                    d.texto_completo = self._extrair_texto_decisao_completa(d.url)
                    time.sleep(config.DELAY_REQUISICOES / 2)
                yield d

            # Tenta avançar de página
            proximo = self._proximo_payload_paginacao(soup, pagina)
            if not proximo:
                logger.info("Última página alcançada (página %d).", pagina)
                break

            time.sleep(config.DELAY_REQUISICOES)

            if "_link" in proximo:
                # Navegação por link direto (GET)
                url_proxima = proximo["_link"]
                logger.debug("Próxima página via GET: %s", url_proxima)
                soup = self._get_soup(url_proxima)
            else:
                # Navegação via POST/JSF
                logger.debug("Próxima página via POST JSF.")
                soup = self._post_soup(config.SEARCH_URL, data=proximo)

            pagina += 1

        logger.info("Extração concluída. Total de páginas processadas: %d.", pagina)
