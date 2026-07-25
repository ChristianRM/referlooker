import os
import json
import time
from playwright.sync_api import sync_playwright

def get_section_text(page, section_id: str) -> str:
    """
    Busca una sección de la página de LinkedIn basándose en el ID del ancla semántica.
    Si falla, intenta buscar por encabezados de texto comunes (en inglés o español)
    para ser compatible con múltiples layouts.
    """
    # 1. Intentar por ID (selector clásico de escritorio)
    xpath = f"//section[.//div[@id='{section_id}'] or .//span[@id='{section_id}'] or .//a[@id='{section_id}'] or .//*[@id='{section_id}']]"
    try:
        locator = page.locator(xpath)
        if locator.count() > 0:
            return locator.first.inner_text().strip()
    except Exception:
        pass
        
    # 2. Fallback por texto del encabezado (h2)
    headings = []
    if section_id == "about":
        headings = ["About", "Acerca de", "Extracto"]
    elif section_id == "experience":
        headings = ["Experience", "Experiencia"]
    elif section_id == "skills":
        headings = ["Skills", "Habilidades", "Aptitudes"]
        
    for heading in headings:
        xpath_h = f"//section[.//h2[contains(text(), '{heading}')] or .//h3[contains(text(), '{heading}')] or .//*[contains(text(), '{heading}')]]"
        try:
            locator = page.locator(xpath_h)
            if locator.count() > 0:
                return locator.first.inner_text().strip()
        except Exception:
            pass
            
    return ""

def expand_collapsed_sections(page):
    """
    Busca y hace clic en todos los botones de 'ver más', 'see more' o 'show more'
    para expandir las descripciones y secciones colapsadas del perfil.
    """
    try:
        # Selectores comunes de botones "ver más"
        selectors = [
            "button:has-text('see more')",
            "button:has-text('ver más')",
            "button:has-text('ver mas')",
            "button:has-text('show more')",
            "button.inline-show-more-text",
            "span:has-text('...see more')",
            "span:has-text('...ver más')"
        ]
        
        for selector in selectors:
            try:
                buttons = page.locator(selector)
                count = buttons.count()
                for i in range(count):
                    btn = buttons.nth(i)
                    if btn.is_visible():
                        btn.click(timeout=1000, force=True)
                        page.wait_for_timeout(300)
            except Exception:
                pass
    except Exception:
        pass

def scrape_linkedin_profile(profile_url: str, target_country: str, config: dict) -> dict:
    """
    Scrapea un perfil de LinkedIn utilizando el perfil persistente de Chrome.
    Implementa un flujo en dos fases:
    Fase 1: Extrae la ubicación y pregunta a Ollama si es compatible con el país requerido.
    Fase 2: Si es compatible, realiza el scraping completo de secciones y texto raw.
    """
    profile_data = {
        "url": profile_url,
        "name": "",
        "headline": "",
        "location": "",
        "about": "",
        "experience": "",
        "skills": "",
        "raw_text": "",
        "status": "error",
        "error_message": ""
    }
    
    user_data_dir = os.path.abspath("linkedin_profile_context")
    
    with sync_playwright() as p:
        try:
            # Lanzamos Chromium con el perfil persistente en modo visible (headless=False)
            context = p.chromium.launch_persistent_context(
                user_data_dir,
                headless=False,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = context.pages[0] if context.pages else context.new_page()
            
            # Navegar a la página del perfil con un tiempo de espera de 30 segundos
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            
            # Esperar a que cargue el elemento h1 (nombre del perfil) en el DOM
            try:
                page.wait_for_selector("h1", timeout=10000)
            except Exception:
                pass
                
            # Dar un margen de 2 segundos para permitir que cargue la cabecera
            page.wait_for_timeout(2000)
            
            current_url = page.url
            # Comprobar si LinkedIn nos redirigió a la página de login o desafío de seguridad
            if "linkedin.com/login" in current_url or "checkpoint" in current_url or "authwall" in current_url:
                error_msg = "Sesión cerrada o expirada en el perfil persistente."
                print(f"[Error] {error_msg}")
                profile_data["error_message"] = error_msg
                profile_data["status"] = "session_expired"
                context.close()
                return profile_data
                
            # --- FASE 1: EXTRACCIÓN DE CABECERA Y FILTRADO RÁPIDO DE PAÍS ---
            # Extraer Nombre (normalmente la primera etiqueta h1 en la página)
            try:
                name_locator = page.locator("h1").first
                if name_locator.count() > 0:
                    profile_data["name"] = name_locator.inner_text().strip()
            except Exception:
                pass
                
            # Fallback: Extraer el Nombre del título de la página si no se pudo de la etiqueta h1
            if not profile_data["name"] or profile_data["name"].lower() in ("", "join linkedin", "iniciar sesión", "sign in", "welcome to linkedin"):
                title = page.title()
                if " | LinkedIn" in title:
                    raw_name = title.split(" | LinkedIn")[0]
                    if " - " in raw_name:
                        raw_name = raw_name.split(" - ")[0]
                    profile_data["name"] = raw_name.strip()
                    
            # Extraer el Headline/Titular
            try:
                headline_locator = page.locator(".text-body-medium").first
                if headline_locator.count() > 0:
                    profile_data["headline"] = headline_locator.inner_text().strip()
            except Exception:
                pass
                
            # Extraer el texto de la cabecera (primeros 2500 caracteres de la página, que garantizan tener la ubicación y nombre)
            header_text = ""
            try:
                body_locator = page.locator("body")
                if body_locator.count() > 0:
                    header_text = body_locator.inner_text()[:2500].strip()
            except Exception:
                pass

            # Usar Ollama para extraer la ubicación y evaluar la compatibilidad geográfica
            from evaluator import evaluate_location_with_llm
            res = evaluate_location_with_llm(header_text, target_country, config)
            profile_data["location"] = res.get("extracted_location", "No detectada")
            is_compatible = res.get("compatible", False)
            
            if not is_compatible:
                print(f"[Descarte Geográfico] Candidato '{profile_data['name']}' descartado por Ollama por estar fuera del país (Ubicación detectada: '{profile_data['location']}', Requerido: '{target_country}').")
                profile_data["status"] = "location_mismatch"
                profile_data["error_message"] = f"Ubicación incompatible con Ollama: {profile_data['location']}"
                context.close()
                return profile_data
                
            # --- FASE 2: SCRAPING COMPLETO ---
            # Hacer scroll hacia abajo de forma progresiva para disparar la carga asíncrona (lazy-load) de LinkedIn
            print("Cargando secciones completas del perfil (haciendo scroll)...")
            try:
                for i in range(1, 5):
                    page.evaluate(f"window.scrollTo(0, {i * 800})")
                    page.wait_for_timeout(1200)
            except Exception as e:
                print(f"[Depuración] Error al hacer scroll: {e}")
            
            # Expandir los bloques de texto colapsados ("ver más" / "see more")
            expand_collapsed_sections(page)
            
            # Extraer secciones usando los anclajes de ID
            profile_data["about"] = get_section_text(page, "about")
            profile_data["experience"] = get_section_text(page, "experience")
            profile_data["skills"] = get_section_text(page, "skills")
            
            # Obtener el URL base del perfil sin sufijos (ej. https://www.linkedin.com/in/username)
            base_profile_url = profile_url
            if "/in/" in profile_url:
                try:
                    parts = profile_url.split("/in/")
                    username = parts[1].split("/")[0].split("?")[0]
                    base_profile_url = f"https://www.linkedin.com/in/{username}"
                except Exception:
                    pass
            
            # Autocuración: Si la experiencia está vacía, navegar directamente al sub-enlace de detalles
            if not profile_data["experience"] or len(profile_data["experience"].strip()) < 15:
                print(f"[Autocuración] Experiencia vacía en página principal. Navegando a detalles de experiencia...")
                try:
                    exp_url = base_profile_url.rstrip("/") + "/details/experience/"
                    page.goto(exp_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    # Scroll usando teclado para activar carga
                    for _ in range(3):
                        page.keyboard.press("PageDown")
                        page.wait_for_timeout(600)
                    # Extraer texto del contenedor main o body
                    main_text = page.locator("main").inner_text() or page.locator("body").inner_text()
                    if len(main_text.strip()) > 100:
                        profile_data["experience"] = main_text.strip()
                        print("[Autocuración] Experiencia recuperada con éxito de la subpágina de detalles.")
                except Exception as e:
                    print(f"[Autocuración] Error al intentar recuperar experiencia: {e}")
                    
            # Autocuración: Si las habilidades están vacías, navegar directamente al sub-enlace de habilidades
            if not profile_data["skills"] or len(profile_data["skills"].strip()) < 15:
                print(f"[Autocuración] Habilidades vacías en página principal. Navegando a detalles de habilidades...")
                try:
                    skills_url = base_profile_url.rstrip("/") + "/details/skills/"
                    page.goto(skills_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    for _ in range(3):
                        page.keyboard.press("PageDown")
                        page.wait_for_timeout(600)
                    main_text = page.locator("main").inner_text() or page.locator("body").inner_text()
                    if len(main_text.strip()) > 100:
                        profile_data["skills"] = main_text.strip()
                        print("[Autocuración] Habilidades recuperadas con éxito de la subpágina de detalles.")
                except Exception as e:
                    print(f"[Autocuración] Error al intentar recuperar habilidades: {e}")
            
            # Volver a la página principal del perfil o tomar el texto general acumulado
            # Si no pudimos obtener nada con selectores, extraemos el texto general del body como fallback
            try:
                # Si terminamos en una subpágina de detalles, volver a la principal para dejar el navegador listo
                if page.url != profile_url:
                    page.goto(profile_url, wait_until="domcontentloaded", timeout=20000)
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
            
            # Si el nombre es un nombre real y pudimos obtener el texto del body, es exitoso (incluso si son conexiones lejanas)
            if profile_data["name"] and not is_login_wall and len(profile_data["raw_text"]) > 200:
                profile_data["status"] = "success"
                print(f"Perfil de '{profile_data['name']}' scrapeado con éxito.")
            else:
                # Comprobar si se detectó pantalla de restricción real (no el footer público)
                body_text = profile_data["raw_text"].lower()
                # Un muro de login real suele ser muy corto o no tener secciones principales
                if (is_login_wall or "join linkedin" in body_text or "iniciar sesión" in body_text) and len(body_text) < 1500:
                    profile_data["status"] = "session_expired"
                    profile_data["error_message"] = "LinkedIn solicitó iniciar sesión o registrarse. La sesión del perfil persistente ha expirado o no es válida."
                else:
                    profile_data["status"] = "empty"
                    profile_data["error_message"] = "No se encontraron datos en el perfil público/privado."
                    
            context.close()
            
        except Exception as e:
            error_msg = f"Excepción durante el scraping: {e}"
            print(f"[Error] {error_msg}")
            profile_data["error_message"] = error_msg
            profile_data["status"] = "error"
            
    return profile_data

def ensure_linkedin_session(config: dict):
    """
    Verifica de forma automática si existe una sesión válida de LinkedIn en el perfil persistente.
    Si no existe o si ha expirado, abre una ventana de Chrome visible para que el usuario
    inicie sesión, persistiendo el estado directamente de forma nativa.
    """
    user_data_dir = os.path.abspath("linkedin_profile_context")
    session_valid = False
    
    if os.path.exists(user_data_dir):
        print("Verificando si tu sesión de LinkedIn sigue activa...")
        with sync_playwright() as p:
            try:
                # Corremos en headless para verificar en segundo plano de forma silenciosa
                context = p.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=True,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                page = context.pages[0] if context.pages else context.new_page()
                
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
                context.close()
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
                context = p.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=False,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 720}
                )
                page = context.pages[0] if context.pages else context.new_page()
                
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
                
                # Cerrar guarda automáticamente todo en user_data_dir
                print(f"\n[Éxito] Sesión de LinkedIn iniciada y guardada de forma persistente en {user_data_dir}")
                context.close()
            except Exception as e:
                print(f"[Error] Falló la autenticación asistida: {e}")

