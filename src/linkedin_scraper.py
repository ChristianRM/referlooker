import os
import json
import time
from playwright.sync_api import sync_playwright

def get_section_text(page, section_id: str) -> str:
    """
    Busca una sección de la página de LinkedIn basándose en el ID del ancla semántica.
    Esto permite extraer secciones como 'about', 'experience', 'skills', etc.,
    siendo altamente resistente a cambios en los nombres de clases CSS de LinkedIn.
    """
    # XPaths que buscan el elemento con el ID indicado dentro de un contenedor <section>
    xpath = f"//section[.//div[@id='{section_id}'] or .//span[@id='{section_id}'] or .//a[@id='{section_id}'] or .//*[@id='{section_id}']]"
    try:
        locator = page.locator(xpath)
        if locator.count() > 0:
            # Retorna el texto interno estructurado
            return locator.first.inner_text().strip()
    except Exception as e:
        print(f"[Depuración] No se pudo extraer la sección '{section_id}': {e}")
    return ""

def scrape_linkedin_profile(profile_url: str, config: dict) -> dict:
    """
    Navega al perfil de LinkedIn y extrae los datos utilizando Playwright y cookies.
    """
    cookies_path = config.get("scraping", {}).get("cookies_path", "cookies.json")
    headless = config.get("scraping", {}).get("headless", True)
    
    profile_data = {
        "url": profile_url,
        "name": "",
        "headline": "",
        "about": "",
        "experience": "",
        "skills": "",
        "raw_text": "",
        "status": "error",
        "error_message": ""
    }
    
    if not os.path.exists(cookies_path):
        error_msg = f"Archivo de cookies '{cookies_path}' no encontrado. Ejecuta 'python src/save_cookies.py' primero."
        print(f"[Error] {error_msg}")
        profile_data["error_message"] = error_msg
        profile_data["status"] = "cookies_missing"
        return profile_data
        
    print(f"Scrapeando perfil: {profile_url}")
    
    with sync_playwright() as p:
        try:
            # Lanzamos Chromium
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            
            # Cargar cookies de sesión
            with open(cookies_path, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            context.add_cookies(cookies)
            
            page = context.new_page()
            # Configurar un User-Agent realista para evitar bloqueos
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            
            # Navegar a la página del perfil con un tiempo de espera de 30 segundos
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            # Esperar a que cargue el elemento h1 (nombre del perfil) en el DOM
            try:
                page.wait_for_selector("h1", timeout=10000)
            except Exception:
                pass
                
            # Dar un margen de 2 segundos para permitir que carguen las secciones dinámicas (About, Experience)
            page.wait_for_timeout(2000)
            
            current_url = page.url
            # Comprobar si LinkedIn nos redirigió a la página de login o desafío de seguridad
            if "linkedin.com/login" in current_url or "checkpoint" in current_url:
                error_msg = "Cookies vencidas o sesión cerrada por LinkedIn. Por favor ejecuta 'python src/save_cookies.py' para renovar sesión."
                print(f"[Error] {error_msg}")
                profile_data["error_message"] = error_msg
                profile_data["status"] = "session_expired"
                browser.close()
                return profile_data
                
            # Extraer el Nombre (normalmente la primera etiqueta h1 en la página)
            try:
                name_locator = page.locator("h1").first
                if name_locator.count() > 0:
                    profile_data["name"] = name_locator.inner_text().strip()
            except Exception:
                pass
                
            # Extraer el Headline/Titular
            # LinkedIn suele tener el titular justo debajo del nombre, a menudo en un elemento con clase text-body-medium
            try:
                headline_locator = page.locator(".text-body-medium").first
                if headline_locator.count() > 0:
                    profile_data["headline"] = headline_locator.inner_text().strip()
            except Exception:
                pass
                
            # Extraer secciones usando los anclajes de ID
            profile_data["about"] = get_section_text(page, "about")
            profile_data["experience"] = get_section_text(page, "experience")
            profile_data["skills"] = get_section_text(page, "skills")
            
            # Si no pudimos obtener nada con selectores, extraemos el texto general del body como fallback
            try:
                profile_data["raw_text"] = page.locator("body").inner_text()
            except Exception:
                pass
                
            # Validar si logramos extraer información sustancial
            if profile_data["name"] or profile_data["about"] or profile_data["experience"]:
                profile_data["status"] = "success"
                print(f"Perfil de '{profile_data['name']}' scrapeado con éxito.")
            else:
                # Comprobar si se detectó pantalla de restricción
                body_text = profile_data["raw_text"]
                if "join linkedin" in body_text.lower() or "iniciar sesión" in body_text.lower():
                    profile_data["status"] = "session_expired"
                    profile_data["error_message"] = "LinkedIn solicitó iniciar sesión. Las cookies son inválidas o insuficientes."
                else:
                    profile_data["status"] = "empty"
                    profile_data["error_message"] = "No se encontraron datos en el perfil público/privado."
                    
            browser.close()
            
        except Exception as e:
            error_msg = f"Excepción durante el scraping: {e}"
            print(f"[Error] {error_msg}")
            profile_data["error_message"] = error_msg
            profile_data["status"] = "error"
            
    return profile_data
