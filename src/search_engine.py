import requests
import urllib.parse

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
        api_key = engine_config.get("google_api_key", "")
        cx = engine_config.get("google_cx", "")
        
        if not api_key or not cx or api_key == "YOUR_GOOGLE_API_KEY" or cx == "YOUR_GOOGLE_CSE_ID":
            print("[Advertencia] Google Custom Search API Key o CX no configurados correctamente en config.json.")
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
        api_key = engine_config.get("serpapi_key", "")
        
        if not api_key or api_key == "YOUR_SERPAPI_KEY":
            print("[Advertencia] SerpAPI Key no configurada correctamente en config.json.")
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
