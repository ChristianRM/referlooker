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

def is_location_compatible(candidate_text: str, target_country: str) -> bool:
    """
    Verifica si el candidato está en el país objetivo de la vacante.
    Si la vacante no especifica país (o es Any/Remoto), el candidato de forma obligatoria
    debe residir en México o Estados Unidos. Si reside fuera, se descarta.
    """
    candidate_text_lower = candidate_text.lower()
    
    # Términos comunes y subregiones para México y Estados Unidos
    mexico_terms = [
        "mexico", "méxico", "mx", "jalisco", "monterrey", "guadalajara", "cdmx", 
        "queretaro", "querétaro", "nl", "nuevo leon", "ciudad de méxico", "sinaloa", 
        "puebla", "yucatan", "yucatán", "veracruz", "guanajuato", "chihuahua", "sonora",
        "baja california", "bc", "b.c.", "tijuana", "leon", "león", "san luis potosi"
    ]
    us_terms = [
        "united states", "usa", "u.s.", "america", "chicago", "new york", "texas", 
        "california", "florida", "austin", "seattle", "illinois", "boston", "denver", 
        "atlanta", "dallas", "houston", "miami", "san francisco", "los angeles", 
        "ny", "tx", "ca", "fl", "wa", "il", "ma", "co", "ga", "az", "phoenix"
    ]
    
    # 1. Si la vacante requiere un país específico
    if target_country and target_country.lower() not in ("any", "global", "remoto", "remote", ""):
        target_lower = target_country.lower()
        if "mexico" in target_lower or "méxico" in target_lower or target_lower == "mx":
            return any(term in candidate_text_lower for term in mexico_terms)
        elif "united states" in target_lower or "usa" in target_lower or target_lower == "us":
            return any(term in candidate_text_lower for term in us_terms)
        else:
            # Si pide otro país específico (ej. España), buscar ese término directamente
            return target_lower in candidate_text_lower
            
    # 2. Si la vacante no especifica país (es Any), el candidato OBLIGATORIAMENTE
    # debe ser de México o Estados Unidos. Si no es de ninguno de los dos, se descarta.
    is_mexico = any(term in candidate_text_lower for term in mexico_terms)
    is_us = any(term in candidate_text_lower for term in us_terms)
    
    if is_mexico or is_us:
        # Aún si coincide con MX/US, descartamos si menciona explícitamente otros países lejanos como residencia principal
        other_countries = ["india", "pakistan", "egypt", "tunisia", "bangladesh", "ukraine", "poland", "nigeria", "brazil", "argentina", "colombia", "peru", "venezuela", "chile", "ecuador", "spain", "españa"]
        other_countries = [c for c in other_countries if c not in ("mexico", "mexic", "méxico", "united states", "usa")]
        
        has_other_mention = any(c in candidate_text_lower for c in other_countries)
        if has_other_mention:
            has_strong_local = ("mexico" in candidate_text_lower or "méxico" in candidate_text_lower or 
                                "united states" in candidate_text_lower or "usa" in candidate_text_lower)
            if not has_strong_local:
                return False
        return True
        
    return False

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

            # Evaluar ubicación primero de forma determinista en Python
            is_compatible = is_location_compatible(header_text, target_country)
            
            # Usar Ollama para extraer el nombre bonito de la ubicación para el reporte
            from evaluator import evaluate_location_with_llm
            res = evaluate_location_with_llm(header_text, target_country, config)
            profile_data["location"] = res.get("extracted_location", "No detectada")
            
            if not is_compatible:
                print(f"[Descarte Geográfico] Candidato '{profile_data['name']}' descartado por estar fuera del país (Ubicación detectada: '{profile_data['location']}', Requerido: '{target_country}').")
                profile_data["status"] = "location_mismatch"
                profile_data["error_message"] = f"Ubicación incompatible: {profile_data['location']}"
                context.close()
                return profile_data
                
            # --- FASE 2: SCRAPING COMPLETO ---
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

