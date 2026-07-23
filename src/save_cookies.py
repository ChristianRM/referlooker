import os
import sys
import json
from playwright.sync_api import sync_playwright

def main():
    cookies_path = "cookies.json"
    print("Iniciando navegador para iniciar sesión en LinkedIn...")
    
    with sync_playwright() as p:
        # Abrimos el navegador en modo visible (headless=False) para permitir la interacción del usuario
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        print("Navegando a la página de inicio de sesión de LinkedIn...")
        page.goto("https://www.linkedin.com/login")
        
        print("\n" + "=" * 60)
        print("INSTRUCCIONES:")
        print("1. Inicia sesión en LinkedIn en la ventana del navegador que se acaba de abrir.")
        print("2. Resuelve cualquier verificación de seguridad (MFA, CAPTCHA) si es requerida.")
        print("3. Una vez que te encuentres en la página de inicio (feed) de LinkedIn,")
        print("   regresa a esta terminal y presiona ENTER.")
        print("=" * 60 + "\n")
        
        input("Presiona ENTER cuando hayas iniciado sesión...")
        
        # Guardar el estado de almacenamiento completo (cookies + local storage)
        context.storage_state(path=cookies_path)
            
        print(f"\n[Éxito] Sesión guardada exitosamente en: {os.path.abspath(cookies_path)}")
        browser.close()

if __name__ == "__main__":
    main()
