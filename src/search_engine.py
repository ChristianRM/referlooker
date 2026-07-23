import os
import requests
import urllib.parse

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
    
    if engine == "google_cse":
        # Priorizar variables de entorno (desde el archivo .env)
        api_key = os.getenv("GOOGLE_API_KEY") or engine_config.get("google_api_key", "")
        cx = os.getenv("GOOGLE_CX") or engine_config.get("google_cx", "")
        
        if not api_key or not cx or api_key in ("YOUR_GOOGLE_API_KEY", "Ver archivo .env", "") or cx in ("YOUR_GOOGLE_CSE_ID", "Ver archivo .env", ""):
            print("[Advertencia] Google Custom Search API Key o CX no configurados. Configúralos en tu archivo '.env'.")
            return []
            
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
