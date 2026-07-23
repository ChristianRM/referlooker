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
            # Lanzamos Chromium cargando el estado de almacenamiento guardado (cookies + session/local storage)
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=cookies_path)
            
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
                
            # Validar si logramos extraer información sustancial y no caímos en un muro de registro/login
            name_lower = profile_data["name"].lower()
            is_login_wall = (
                name_lower in ("", "join linkedin", "iniciar sesión", "sign in", "welcome to linkedin") or
                "join linkedin" in name_lower or
                "iniciar sesión" in name_lower
            )
            
            if (profile_data["name"] or profile_data["about"] or profile_data["experience"]) and not is_login_wall:
                profile_data["status"] = "success"
                print(f"Perfil de '{profile_data['name']}' scrapeado con éxito.")
            else:
                # Comprobar si se detectó pantalla de restricción o muro de registro
                body_text = profile_data["raw_text"].lower()
                if "join linkedin" in body_text or "iniciar sesión" in body_text or "sign in" in body_text or is_login_wall:
                    profile_data["status"] = "session_expired"
                    profile_data["error_message"] = "LinkedIn solicitó iniciar sesión o registrarse. Las cookies de sesión son inválidas, expiraron o no se cargaron correctamente."
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

def ensure_linkedin_session(config: dict):
    """
    Verifica de forma automática si existe una sesión válida de LinkedIn.
    Si no existe o si ha expirado, abre una ventana de Chrome visible para que el usuario
    inicie sesión, guardando el estado de almacenamiento antes de proceder.
    """
    cookies_path = config.get("scraping", {}).get("cookies_path", "cookies.json")
    session_valid = False
    
    if os.path.exists(cookies_path):
        print("Verificando si tu sesión de LinkedIn sigue activa...")
        with sync_playwright() as p:
            try:
                # Corremos en headless para verificar en segundo plano de forma silenciosa
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(storage_state=cookies_path)
                page = context.new_page()
                page.set_extra_http_headers({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                })
                
                # Ir a la página de feed que requiere autenticación
                page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(3000)
                
                # Comprobar la URL y que no nos mande al login wall
                body_text = page.locator("body").inner_text().lower()
                if "linkedin.com/feed" in page.url and "join linkedin" not in body_text and "iniciar sesión" not in body_text:
                    session_valid = True
                    print("[Sesión] Tu sesión de LinkedIn está ACTIVA y es válida.")
                else:
                    print("[Sesión] Sesión de LinkedIn EXPIRADA o no válida.")
                browser.close()
            except Exception as e:
                print(f"[Sesión] Error comprobando sesión: {e}")
                
    if not session_valid:
        print("\n" + "=" * 70)
        print("[SESIÓN DE LINKEDIN REQUERIDA]")
        print("No se encontró una sesión activa de LinkedIn en tu equipo.")
        print("Se abrirá una ventana de Chrome para que inicies sesión manualmente.")
        print("=" * 70 + "\n")
        
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()
                
                print("Navegando a la página de inicio de sesión de LinkedIn...")
                page.goto("https://www.linkedin.com/login")
                
                print("\n" + "=" * 70)
                print("INSTRUCCIONES:")
                print("1. Inicia sesión en tu cuenta en la ventana de Chrome.")
                print("2. Resuelve cualquier verificación (MFA o CAPTCHA) si aparece.")
                print("3. Una vez que cargue tu página principal (Feed), regresa aquí.")
                print("4. Presiona ENTER en esta terminal para continuar.")
                print("=" * 70 + "\n")
                
                input("Presiona ENTER cuando estés listo...")
                
                # Guardar estado de almacenamiento completo (cookies + local storage)
                context.storage_state(path=cookies_path)
                print(f"\n[Éxito] Sesión de LinkedIn iniciada y guardada en {cookies_path}")
                browser.close()
            except Exception as e:
                print(f"[Error] Falló la autenticación asistida: {e}")

