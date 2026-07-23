import os
import time
import requests
import urllib.parse
from playwright.sync_api import sync_playwright

def search_candidates_via_playwright(query: str, max_results: int, config: dict) -> list:
    """
    Busca directamente en Google usando Playwright sin requerir llaves de API externas.
    Sirve como mecanismo de contingencia si Google CSE falla con errores 403 o límites de cuota.
    """
    urls = []
    # Forzar headless=False para la búsqueda en Google para evitar la detección automática de bots y permitir resolver CAPTCHAs
    print(f"[Fallback] Iniciando búsqueda directa en Google con Playwright en modo visible (headless=False)...")
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = context.new_page()
            
            # Formatear la consulta de búsqueda para Google
            encoded_query = urllib.parse.quote(query)
            google_url = f"https://www.google.com/search?q={encoded_query}"
            
            page.goto(google_url, wait_until="domcontentloaded", timeout=30000)
            
            # Detectar si Google arrojó un CAPTCHA (redirección a google.com/sorry)
            if "google.com/sorry" in page.url:
                print("\n" + "!" * 50)
                print("[Acción Requerida] Google ha solicitado una verificación humana (CAPTCHA).")
                print("Por favor, resuélvelo en la ventana del navegador que se acaba de abrir.")
                print("El script esperará a que lo completes para continuar automáticamente...")
                print("!" * 50 + "\n")
                
                # Esperar hasta 2 minutos a que la URL ya no sea la de CAPTCHA
                try:
                    for _ in range(120):
                        page.wait_for_timeout(1000) # Permitir que Playwright procese eventos y actualice la URL
                        if "google.com/sorry" not in page.url:
                            print("[Éxito] CAPTCHA resuelto. Continuando con la extracción...")
                            break
                except Exception:
                    pass
            
            # Esperar a que el contenedor de resultados de Google (#search) se renderice
            try:
                page.wait_for_selector("#search", timeout=5000)
            except Exception:
                # Fallback por si no renderiza pero hay enlaces
                page.wait_for_timeout(2000)
            
            # Extraer todas las URLs de los enlaces (a) que correspondan a perfiles de LinkedIn
            hrefs = page.eval_on_selector_all("a", "elements => elements.map(el => el.href)")
            
            for href in hrefs:
                cleaned = clean_linkedin_url(href)
                if cleaned:
                    urls.append(cleaned)
                    if len(urls) >= max_results:
                        break
                        
            browser.close()
        except Exception as e:
            print(f"[Error Fallback] Falló la búsqueda directa en Google: {e}")
            
    return urls


def load_dotenv(dotenv_path=".env"):
    """
    Parsea de manera sencilla el archivo .env si existe y carga las variables en os.environ.
    Evita dependencias de terceros como python-dotenv.
    """
    if os.path.exists(dotenv_path):
        try:
            with open(dotenv_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        # Remover comillas si existen en el valor
                        val = val.strip().strip("'").strip('"')
                        os.environ[key.strip()] = val
        except Exception as e:
            print(f"[Advertencia] No se pudo leer el archivo .env: {e}")

# Cargar variables del entorno al importar el módulo
load_dotenv()

def clean_linkedin_url(url: str) -> str:
    """
    Limpia y valida que la URL corresponda a un perfil individual de LinkedIn.
    Remueve parámetros adicionales de búsqueda (?miniProfile=..., etc.).
    """
    try:
        # Decodificar URL en caso de que venga codificada
        decoded_url = urllib.parse.unquote(url)
        parsed = urllib.parse.urlparse(decoded_url)
        
        # Comprobar si es un enlace de perfil de LinkedIn
        if "linkedin.com/in/" in parsed.netloc + parsed.path:
            # Reconstruir la URL limpia usando solo el path (ej: /in/nombre-candidato/)
            path = parsed.path
            # Quitar barras diagonales sobrantes al final
            path = path.rstrip("/")
            clean_url = f"https://www.linkedin.com{path}"
            return clean_url
    except Exception:
        pass
    return ""

def search_candidates(query: str, config: dict) -> list:
    """
    Ejecuta la consulta de búsqueda en Google a través de Google Custom Search o SerpAPI.
    Retorna una lista de URLs únicas de perfiles de LinkedIn.
    """
    engine_config = config.get("search_engine", {})
    engine = engine_config.get("engine", "google_cse")
    max_results = config.get("search_limits", {}).get("max_results_per_vacancy", 5)
    
    urls = []
    
    print(f"Iniciando búsqueda usando motor '{engine}' con query: {query}")
    
    if engine in ("google_playwright", "direct"):
        return list(dict.fromkeys(search_candidates_via_playwright(query, max_results, config)))
        
    if engine == "google_cse":
        # Priorizar variables de entorno (desde el archivo .env)
        api_key = os.getenv("GOOGLE_API_KEY") or engine_config.get("google_api_key", "")
        cx = os.getenv("GOOGLE_CX") or engine_config.get("google_cx", "")
        
        if not api_key or not cx or api_key in ("YOUR_GOOGLE_API_KEY", "Ver archivo .env", "") or cx in ("YOUR_GOOGLE_CSE_ID", "Ver archivo .env", ""):
            print("[Advertencia] Google Custom Search API Key o CX no configurados. Configúralos en tu archivo '.env'.")
            print("[Advertencia] Activando búsqueda de contingencia vía Playwright...")
            return list(dict.fromkeys(search_candidates_via_playwright(query, max_results, config)))
            
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": api_key,
            "cx": cx,
            "q": query,
            "num": max_results
        }
        
        try:
            response = requests.get(url, params=params, timeout=15)
            if response.status_code != 200:
                try:
                    error_json = response.json()
                    error_msg = error_json.get("error", {}).get("message", "Sin mensaje detallado")
                    print(f"[Error] Google CSE retornó código {response.status_code}: {error_msg}")
                except Exception:
                    print(f"[Error] Google CSE retornó código {response.status_code}: {response.text}")
                
                # Fallback automático ante error 403 o 400
                if response.status_code in (400, 403):
                    print("[Advertencia] Se detectó error en Google CSE. Activando búsqueda alternativa directa vía Playwright...")
                    return list(dict.fromkeys(search_candidates_via_playwright(query, max_results, config)))
                return []
                
            response.raise_for_status()
            data = response.json()
            items = data.get("items", [])
            for item in items:
                link = item.get("link", "")
                cleaned = clean_linkedin_url(link)
                if cleaned:
                    urls.append(cleaned)
        except Exception as e:
            print(f"[Error] Falló la búsqueda con Google CSE: {e}")
            
    elif engine == "serpapi":
        # Priorizar variables de entorno (desde el archivo .env)
        api_key = os.getenv("SERPAPI_KEY") or engine_config.get("serpapi_key", "")
        
        if not api_key or api_key in ("YOUR_SERPAPI_KEY", "Ver archivo .env", ""):
            print("[Advertencia] SerpAPI Key no configurada. Configúrala en tu archivo '.env'.")
            return []
            
        url = "https://serpapi.com/search"
        params = {
            "engine": "google",
            "q": query,
            "api_key": api_key,
            "num": max_results
        }
        
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            results = data.get("organic_results", [])
            for result in results:
                link = result.get("link", "")
                cleaned = clean_linkedin_url(link)
                if cleaned:
                    urls.append(cleaned)
        except Exception as e:
            print(f"[Error] Falló la búsqueda con SerpAPI: {e}")
            
    else:
        print(f"[Error] Motor de búsqueda no reconocido: {engine}")
        
    # Deduplicar preservando el orden original
    unique_urls = list(dict.fromkeys(urls))
    print(f"Se encontraron {len(unique_urls)} perfiles de LinkedIn únicos.")
    return unique_urls
