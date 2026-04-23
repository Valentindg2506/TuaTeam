"""
Enriquecimiento de leads v5 — estrategia probada y funcional.
Fuentes en cascada:
  1. Bing search → snippets + links a la web oficial
  2. Web oficial de la empresa → página de contacto
  3. DuckDuckGo HTML como fallback
  4. Bing para licitaciones

Nota: eleconomista ficha (429), einforma/infoempresa (JS-required),
axesor/infocif (timeout/bloqueo) no son accesibles sin navegador real.
La estrategia más efectiva es Bing → web propia.
"""
import re, time, requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin, urlparse
import unicodedata

# Rotar User-Agents para evitar bloqueos
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]
_ua_idx = 0

def _next_ua():
    global _ua_idx
    ua = USER_AGENTS[_ua_idx % len(USER_AGENTS)]
    _ua_idx += 1
    return ua

def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": _next_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",  # Removed 'br' because requests can't natively decode it, causing garbled text
        "DNT": "1",
        "Connection": "keep-alive",
    })
    return s

def _get(url, timeout=12, retries=2):
    for i in range(retries + 1):
        try:
            s = _session()
            r = s.get(url, timeout=timeout, allow_redirects=True)
            # Accept 404 and 403 because many corporate sites have valid footers on error pages
            if r.status_code in (200, 404, 403):
                return r.text
            if r.status_code in (429, 503, 202) and i < retries:
                time.sleep(4 * (i + 1)); continue
        except requests.Timeout:
            if i < retries: time.sleep(2)
        except Exception:
            if i < retries: time.sleep(2)
    return None


# ── Patrones de extracción ────────────────────────────────────────────────────
RE_TEL   = re.compile(r"(?<!\d)(?:\+34[\s.\-]?)?[6789]\d{2}[\s.\-]?\d{3}[\s.\-]?\d{3}(?!\d)")
RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
RE_WEB   = re.compile(r"https?://(?:www\.)?([a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,})")

EXCLUIDOS_DOM = {
    "bing.com", "google.com", "google.es", "duckduckgo.com",
    "eleconomista.es", "ranking-empresas.eleconomista.es",
    "einforma.com", "infoempresa.com", "axesor.es", "infocif.es",
    "boe.es", "borme.net", "linkedin.com", "facebook.com",
    "instagram.com", "twitter.com", "x.com", "youtube.com",
    "wikipedia.org", "paginasamarillas.es", "maps.google.com",
    "amazon.es", "ebay.es", "mercadolibre.es",
}

EXCLUIDOS_EMAIL = {
    "example.com", "sentry.io", "duckduckgo.com", "w3.org",
    "schema.org", "apple.com", "microsoft.com",
}

def _limpiar_tel(t):
    t = re.sub(r"[\s.\-]", "", str(t))
    if t.startswith("+34"): t = t[3:]
    if t.startswith("0034"): t = t[4:]
    return t if (len(t) == 9 and t[0] in "679") else None

def _dominio(url):
    try:
        return urlparse(url).netloc.replace("www.", "").lower()
    except Exception:
        return ""

def _es_excluido(url_o_dom):
    dom = _dominio(url_o_dom) if url_o_dom.startswith("http") else url_o_dom.lower()
    return any(exc in dom for exc in EXCLUIDOS_DOM)

def _primer_tel(texto):
    for m in RE_TEL.finditer(texto):
        t = _limpiar_tel(m.group(0))
        if t: return t
    return None

def _primer_email(texto):
    for m in RE_EMAIL.finditer(texto):
        e = m.group(0).lower()
        dom = e.split("@")[-1]
        if not any(x in dom for x in EXCLUIDOS_EMAIL | EXCLUIDOS_DOM):
            return e
    return None

def _primer_web_externa(soup):
    """Extrae la primera URL que sea una web real (no de directorios/RRSS)."""
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"): continue
        if not _es_excluido(href):
            return href
    return None


# ── 1. Bing Search ────────────────────────────────────────────────────────────
def enrich_from_bing(nombre, provincia=""):
    """
    Busca en Bing y extrae datos de los snippets de resultados.
    Estrategia en 2 pasos: primero buscar web oficial, luego contacto.
    """
    data = {}

    def _bing_query(q):
        url = f"https://www.bing.com/search?q={quote_plus(q)}&setlang=es&count=10"
        return _get(url, timeout=10)

    # Paso 1: Buscar la web oficial
    html = _bing_query(f'"{nombre}" {provincia} web oficial contacto')
    if html:
        soup = BeautifulSoup(html, "lxml")
        texto = soup.get_text(" ", strip=True)

        # Teléfono en snippets
        if not data.get("telefono"):
            data["telefono"] = _primer_tel(texto)

        # Email en snippets
        if not data.get("email"):
            data["email"] = _primer_email(texto)

        # Web: buscar en resultados de Bing
        for a in soup.select("li.b_algo h2 a, cite, .b_attribution cite"):
            href = a.get("href") or a.get_text(strip=True)
            
            # Decodificar el enlace oculto de Bing si existe
            if "bing.com/ck" in href and "&u=a1" in href:
                try:
                    import base64
                    b64 = href.split("&u=a1")[1].split("&")[0]
                    href = base64.b64decode(b64 + "==").decode("utf-8", errors="ignore")
                except: pass
                
            # Limpiar separadores visuales de breadcrumbs
            href = re.sub(r'\s*›\s*', '/', href)
            
            if href.startswith("http") and not _es_excluido(href):
                data["web"] = href
                break

        # Extraer desde Knowledge Panel de Bing (si aparece)
        kp = soup.select_one(".b_entityTP, .b_rich, [data-tag='LocalBusiness']")
        if kp:
            kp_text = kp.get_text(" ", strip=True)
            if not data.get("telefono"):
                data["telefono"] = _primer_tel(kp_text)
            if not data.get("direccion"):
                # El panel de Bing suele tener dirección en texto limpio
                m = re.search(
                    r"(?:C(?:alle|/)?\.?\s+|Av(?:enida)?\.?\s+|Plaza\s+|"
                    r"Pol(?:ígono)?\.?\s+|Pso\.?\s+|Carretera\s+)"
                    r"[^,\n\r]{5,80}(?:,\s*\d{5})?",
                    kp_text, re.I)
                if m: data["direccion"] = m.group(0).strip()[:250]

    time.sleep(1.5)

    # Paso 2: Buscar específicamente el gerente/administrador
    if not data.get("gerente"):
        html2 = _bing_query(
            f'"{nombre}" administrador OR gerente OR "director general" OR CEO'
        )
        if html2:
            texto2 = BeautifulSoup(html2, "lxml").get_text(" ", strip=True)
            m = re.search(
                r"(?:Administrador[a]?(?:\s+[Úu]nico)?|Gerente|Director[a]?\s+General"
                r"|CEO|Presidente[a]?|Socio\s+Director|Apoderado|Fundador[a]?)"
                r"[:\s]+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ]+(?:\s+"
                r"(?:de\s+(?:la\s+|los\s+|las\s+|el\s+)?)?"
                r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ]+){1,4})",
                texto2)
            if m:
                cand = m.group(1).strip()
                if 2 <= len(cand.split()) <= 5 and len(cand) < 65:
                    data["gerente"] = cand

    return data


# ── 2. Web oficial de la empresa (Deep Crawl) ─────────────────────────────────
def enrich_from_web_propia(web_url, nombre=""):
    """
    Raspa la web oficial y páginas internas clave (legal, contacto, about)
    para buscar agresivamente teléfonos, emails, direcciones y gerentes.
    """
    data = {}
    if not web_url: return data

    base_dominio = _dominio(web_url)
    
    # Expresiones regulares mejoradas
    re_tel = re.compile(r"(?i)(?:tel[é]?[f]?[.:\s]*)?(?:\+34\s*)?([6789](?:[\s.-]*\d){8})")
    re_email = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    re_dir = re.compile(r"(?i)(?:C/|Cl\.|Calle|Avda\.|Avenida|Pol\.\s*Ind\.|Pol[íi]gono\s+Industrial|Paseo|Plaza|Sita en|Domiciliada en|Domicilio)[^|:<\n\r]{5,100}?(?:\b\d{5}\b)[^|:<\n\r]{0,50}")
    re_gerente = re.compile(r"(?i)(?:Administrador[a]?(?:\s+[Úu]nico)?|Gerente|Director[a]?\s+General|CEO|Presidente[a]?|Fundador[a]?|Socio\s+Director)[\s.:]+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ]+(?:\s+(?:de\s+)?[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ]+){1,3})")

    # 1. Obtener la página principal
    html_home = _get(web_url, timeout=5)
    if not html_home: return data
    soup_home = BeautifulSoup(html_home, "lxml")
    
    # 2. Extraer enlaces internos interesantes
    links_to_check = {web_url}
    for a in soup_home.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        txt = a.get_text().lower()
        # Buscar palabras clave en URL o Texto
        if any(x in href.lower() or x in txt for x in ["contacto", "contact", "about", "nosotros", "legal", "aviso", "privacidad"]):
            full_url = href if href.startswith("http") else web_url.rstrip("/") + ("/" + href.lstrip("/") if not href.startswith("/") else href)
            # Solo añadir si pertenece al mismo dominio
            if _dominio(full_url) == base_dominio:
                links_to_check.add(full_url)
                
    # Limitar a máximo 5 páginas para no demorar mucho
    links_to_check = list(links_to_check)[:5]

    for link in links_to_check:
        html = _get(link, timeout=10)
        if not html: continue
        soup = BeautifulSoup(html, "lxml")
        texto = soup.get_text(" ", strip=True)

        # -- Extracción de Teléfono --
        if not data.get("telefono"):
            for a in soup.find_all("a", href=re.compile(r"^tel:")):
                t = _limpiar_tel(a["href"].replace("tel:", "").strip())
                if t: data["telefono"] = t; break
        if not data.get("telefono"):
            tels = [re.sub(r"[\s.-]", "", m) for m in re_tel.findall(texto)]
            for t in tels:
                if len(t) == 9 and t[0] in "6789":
                    data["telefono"] = t; break

        # -- Extracción de Email --
        if not data.get("email"):
            for a in soup.find_all("a", href=re.compile(r"^mailto:")):
                e = a["href"].replace("mailto:", "").split("?")[0].strip().lower()
                if "@" in e and base_dominio in e:
                    data["email"] = e; break
        if not data.get("email"):
            emails = re_email.findall(texto)
            for e in emails:
                e = e.lower()
                if not any(x in e for x in EXCLUIDOS_EMAIL | EXCLUIDOS_DOM):
                    data["email"] = e; break

        # -- Extracción de Dirección --
        if not data.get("direccion"):
            m = re_dir.search(texto)
            if m:
                # Limpiar texto de la dirección
                d = m.group(0).strip().replace("Sita en", "").replace("Domiciliada en", "").replace("Domicilio", "").strip(" :.,")
                if len(d) > 8: data["direccion"] = d[:250]

        # -- Extracción de Gerente --
        if not data.get("gerente"):
            m = re_gerente.search(texto)
            if m:
                cand = m.group(1).strip()
                if 2 <= len(cand.split()) <= 5:
                    data["gerente"] = cand

        # Si ya tenemos todo, parar
        if all(data.get(k) for k in ("telefono", "email", "direccion", "gerente")):
            break
        
        time.sleep(0.5)

    return data


# ── 3. Bing search para encontrar la web oficial ──────────────────────────────
def encontrar_web_oficial(nombre, provincia=""):
    """Usa Bing para encontrar la URL de la web oficial."""
    try:
        q = quote_plus(f'"{nombre}" {provincia} -site:linkedin.com -site:facebook.com')
        html = _get(f"https://www.bing.com/search?q={q}&setlang=es&count=5", timeout=8)
        if not html: return None
        soup = BeautifulSoup(html, "lxml")
        for a in soup.select("li.b_algo h2 a"):
            href = a.get("href", "")
            if href.startswith("http") and not _es_excluido(href):
                return href
        # Buscar en cites
        for cite in soup.select("cite"):
            txt = cite.get_text(strip=True)
            if txt.startswith("http") and not _es_excluido(txt):
                return txt
            # A veces solo muestra el dominio sin https
            if "." in txt and not _es_excluido(txt) and not " " in txt:
                return "https://" + txt.split("/")[0]
    except Exception as e:
        print(f"[encontrar_web] {nombre}: {e}")
    return None


# ── 4. Licitaciones via Bing ──────────────────────────────────────────────────
def check_licita(nombre):
    try:
        q = quote_plus(
            f'"{nombre}" '
            f'(licitación OR adjudicación OR adjudicatario OR PLACSP OR "sector público")'
        )
        html = _get(f"https://www.bing.com/search?q={q}&setlang=es&count=5", timeout=8)
        if not html: return "?"
        html_low = html.lower()
        nombre_low = nombre.lower()[:25]
        indicadores = ["contrataciondelestado", "placsp", "adjudicatario",
                       "adjudicacion", "licitacion", "boe.es"]
        hits = sum(1 for t in indicadores if t in html_low)
        if hits >= 2: return "sí"
        if hits >= 1 and nombre_low in html_low: return "sí"
        return "no"
    except Exception:
        return "?"


# ── Domain Finder (Clearbit API + Heurística) ─────────────────────────────────
def _slugificar(nombre):
    """Convierte nombre de empresa a slug DNS-friendly."""
    txt = unicodedata.normalize("NFKD", nombre)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    txt = txt.lower()
    for sufijo in [" s.a.u.", " s.a.", " s.l.u.", " s.l.", " sau", " slu",
                   " sa", " sl", " slp", " s.a", " s.l", " s.l.p"]:
        if txt.endswith(sufijo):
            txt = txt[:-len(sufijo)]
    for palabra in [" grupo", " group", " holding", " iberia", " españa", " spain"]:
        txt = txt.replace(palabra, "")
    txt = re.sub(r"[^a-z0-9\s\-]", "", txt)
    txt = re.sub(r"\s+", "-", txt.strip()).strip("-")
    return txt

def encontrar_web_clearbit(nombre):
    """
    Utiliza la API abierta de Clearbit Autocomplete para encontrar el dominio
    oficial de la empresa probando varias variaciones del nombre.
    """
    intentos = [nombre]
    # Nombre sin sufijos legales
    limpio = re.sub(r'(?i)\s+(S\.?A\.?U?|S\.?L\.?U?|S\.?L\.?P|GROUP|GRUPO|SA|SL)$', '', nombre).strip()
    if limpio != nombre: intentos.append(limpio)
    
    # Solo la primera palabra (muy útil para nombres largos como "FERROTALL MAQUINAS-HERRAMIENTA SL")
    p1 = limpio.split()[0].split('-')[0]
    if len(p1) > 4 and p1 != limpio: intentos.append(p1)

    for query in intentos:
        try:
            url = f"https://autocomplete.clearbit.com/v1/companies/suggest?query={quote_plus(query)}"
            r = _session().get(url, timeout=4)
            if r.status_code == 200:
                data = r.json()
                if data and len(data) > 0:
                    domain = data[0].get("domain")
                    if domain:
                        return f"https://www.{domain}"
        except Exception:
            pass
    return None

def enrich_from_domain_guess(nombre):
    """
    Encuentra el dominio exacto vía Clearbit y lo raspa profundamente.
    """
    data = {}
    
    # 1. Intentar Clearbit
    web_url = encontrar_web_clearbit(nombre)
    
    # 2. Si falla, usar heurística de slug
    if not web_url:
        slug = _slugificar(nombre)
        if slug:
            for tld in [".es", ".com"]:
                url = f"https://www.{slug}{tld}"
                try:
                    r = _session().get(url, timeout=3, allow_redirects=True)
                    if r.status_code == 200:
                        web_url = r.url
                        break
                except:
                    pass

    if web_url:
        data["web"] = web_url
        merge_web = enrich_from_web_propia(web_url, nombre)
        for k in ("telefono", "email", "direccion", "gerente"):
            if merge_web.get(k):
                data[k] = merge_web[k]
                
    return data


def enrich_from_google_places(nombre, provincia):
    import os
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key: return {}
    
    data = {}
    try:
        # 1. Búsqueda de texto para obtener el Place ID
        query = f"{nombre} {provincia} España"
        url_search = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={quote_plus(query)}&key={api_key}"
        r1 = _session().get(url_search, timeout=8)
        if r1.status_code == 200:
            res1 = r1.json()
            if res1.get("results"):
                place_id = res1["results"][0]["place_id"]
                # 2. Detalles del lugar para teléfono, web y dirección
                url_details = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=formatted_phone_number,website,formatted_address&key={api_key}"
                r2 = _session().get(url_details, timeout=8)
                if r2.status_code == 200:
                    res2 = r2.json()
                    if res2.get("result"):
                        det = res2["result"]
                        if det.get("formatted_phone_number"):
                            t = _limpiar_tel(det["formatted_phone_number"])
                            if t: data["telefono"] = t
                        if det.get("website"):
                            data["web"] = det["website"]
                        if det.get("formatted_address"):
                            data["direccion"] = det["formatted_address"]
    except Exception as e:
        print(f"[google_places] Error: {e}")
    return data

def enrich_from_social_and_directories(nombre, provincia):
    """
    Usa Bing para buscar en Facebook, Páginas Amarillas y sitios de empresas
    y extrae el teléfono y email directamente de los snippets de resultados
    sin tener que visitar la página (que suele bloquear bots).
    """
    data = {}
    q = quote_plus(f"{nombre} {provincia} telefono email site:facebook.com OR site:paginasamarillas.es OR site:einforma.com OR site:empresia.es")
    url = f"https://www.bing.com/search?q={q}&setlang=es&count=20"
    html = _get(url, timeout=10)
    if html:
        soup = BeautifulSoup(html, "lxml")
        texto = soup.get_text(" ", strip=True)
        # Extraer telefono y email del texto completo de la página de resultados
        data["telefono"] = _primer_tel(texto)
        data["email"] = _primer_email(texto)
    return data

# ── Función principal ─────────────────────────────────────────────────────────
def enrich_lead(lead_dict):
    """
    Enriquece un lead en cascada:
      1. Domain guessing → web oficial directa (más efectivo en IPs servidor)
      2. Bing search como fallback (cuando no está bloqueado)
      3. Web oficial raspar si la encontramos por Bing
      4. Google Places API (Último recurso pagado)
      5. Licitaciones via Bing
    """
    resultado = {"telefono": None, "email": None, "web": None,
                 "direccion": None, "gerente": None, "licita": "?"}

    nombre    = lead_dict.get("nombre", "")
    provincia = lead_dict.get("provincia", "")

    def merge(fuente):
        for k in ("telefono", "email", "web", "direccion", "gerente"):
            if not resultado[k] and fuente.get(k):
                resultado[k] = fuente[k]

    def faltan_contacto():
        return not resultado["telefono"] or not resultado["email"]

    # 1. Domain guessing (funciona aunque Bing/Google bloqueen)
    try:
        merge(enrich_from_domain_guess(nombre))
        time.sleep(1)
    except Exception as e:
        print(f"[domain_guess] {nombre}: {e}")

    # 2. Bing search como fallback
    if faltan_contacto():
        try:
            merge(enrich_from_bing(nombre, provincia))
            time.sleep(1)
        except Exception as e:
            print(f"[bing] {nombre}: {e}")

    # 4. Raspar web oficial si la tenemos pero nos faltan datos
    if resultado.get("web") and faltan_contacto():
        try:
            merge(enrich_from_web_propia(resultado["web"], nombre))
            time.sleep(1)
        except Exception as e:
            print(f"[web_propia] {nombre}: {e}")

    # 5. Nuevo Bot Avanzado: Snippets Sociales y de Directorios
    if faltan_contacto():
        try:
            merge(enrich_from_social_and_directories(nombre, provincia))
            time.sleep(1)
        except Exception as e:
            print(f"[social_directorios] {nombre}: {e}")

    # 6. Fallback Pagado de Google Places API
    if faltan_contacto() or not resultado["direccion"] or not resultado["web"]:
        try:
            merge(enrich_from_google_places(nombre, provincia))
            time.sleep(1)
        except Exception as e:
            print(f"[google_places_fallback] {nombre}: {e}")

    # 7. Licitaciones
    try:
        resultado["licita"] = check_licita(nombre)
        time.sleep(0.5)
    except Exception as e:
        print(f"[licita] {nombre}: {e}")

    return resultado
