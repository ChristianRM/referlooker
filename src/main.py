import os
import sys
import json
import shutil
import pandas as pd

# Añadir directorio actual al path por si acaso
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from query_generator import generate_search_query
from search_engine import search_candidates
from linkedin_scraper import scrape_linkedin_profile, ensure_linkedin_session
from evaluator import evaluate_candidate

class Tee:
    def __init__(self, filename, mode="a"):
        self.file = open(filename, mode, encoding="utf-8")
        self.stdout = sys.stdout
        self.stderr = sys.stderr

    def write(self, message):
        self.stdout.write(message)
        self.file.write(message)
        self.file.flush()

    def flush(self):
        self.stdout.flush()
        self.file.flush()

def load_config():
    """Carga config.json si existe."""
    config_path = "config.json"
    if not os.path.exists(config_path):
        print(f"[Error] No se encontró el archivo de configuración {config_path}")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def setup_directories():
    """Crea los directorios necesarios si no existen."""
    os.makedirs("vacantes", exist_ok=True)
    os.makedirs("procesadas/vacantes_viejas", exist_ok=True)
    os.makedirs("output", exist_ok=True)

def load_processed_urls() -> dict:
    """Carga el historial de URLs procesadas para evitar repetirlas."""
    history_path = "output/processed_urls.json"
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            print("[Advertencia] No se pudo leer processed_urls.json. Se creará uno nuevo.")
            return {}
    return {}

def save_processed_urls(processed_dict: dict):
    """Guarda el historial de URLs procesadas."""
    history_path = "output/processed_urls.json"
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(processed_dict, f, indent=2, ensure_ascii=False)

def update_json_report(candidate_info: dict):
    """
    Agrega o actualiza un candidato en el archivo consolidado de candidatos (output/candidatos.json).
    Clasifica en 'candidatos_deseables' si el score es >= 85%, de lo contrario en 'candidatos_no_deseables'.
    """
    json_path = "output/candidatos.json"
    
    # Inicializar estructura vacía del reporte
    report = {
        "candidatos_deseables": [],
        "candidatos_no_deseables": []
    }
    
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    report["candidatos_deseables"] = loaded.get("candidatos_deseables", [])
                    report["candidatos_no_deseables"] = loaded.get("candidatos_no_deseables", [])
        except Exception:
            pass
            
    url = candidate_info.get("linkedin_url")
    
    # Remover duplicados previos del mismo candidato en ambas listas
    report["candidatos_deseables"] = [c for c in report["candidatos_deseables"] if c.get("linkedin_url") != url]
    report["candidatos_no_deseables"] = [c for c in report["candidatos_no_deseables"] if c.get("linkedin_url") != url]
    
    score = candidate_info.get("score", 0)
    
    # Guardar en la lista correspondiente
    if score >= 85:
        report["candidatos_deseables"].append(candidate_info)
        print(f"[Reporte JSON] Candidato '{candidate_info.get('nombre')}' agregado a 'candidatos_deseables' (Score: {score}%)")
    else:
        report["candidatos_no_deseables"].append(candidate_info)
        print(f"[Reporte JSON] Candidato '{candidate_info.get('nombre')}' agregado a 'candidatos_no_deseables' (Score: {score}%)")
        
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def main():
    setup_directories()
    # Inicializar Tee para escribir a consola y archivo de log
    tee = Tee("output/referral_bot.log", mode="w")
    sys.stdout = tee
    sys.stderr = tee
    
    config = load_config()
    
    # Obtener archivos de vacantes
    vacancy_files = [f for f in os.listdir("vacantes") if f.endswith(".txt")]
    
    if not vacancy_files:
        print("No se encontraron archivos de vacantes (.txt) en la carpeta 'vacantes/'.")
        print("Coloca descripciones de puestos allí y vuelve a ejecutar.")
        return
        
    processed_history = load_processed_urls()
    excel_path = "output/candidatos_deseables.xlsx"
    txt_path = "output/candidatos_deseables.txt"
    min_score = config.get("evaluation", {}).get("min_score", 80)
    
    print(f"Iniciando procesamiento de {len(vacancy_files)} vacante(s)...")
    
    for vac_file in vacancy_files:
        vac_path = os.path.join("vacantes", vac_file)
        print(f"\n" + "-" * 50)
        print(f"Procesando vacante: {vac_file}")
        print("-" * 50)
        
        with open(vac_path, "r", encoding="utf-8") as f:
            vacancy_text = f.read().strip()
            
        if not vacancy_text:
            print(f"[Advertencia] El archivo {vac_file} está vacío. Omitiendo.")
            continue
            
        # 1. Generar la consulta X-Ray con el LLM
        print("Generando consulta X-Ray con Ollama...")
        analysis = generate_search_query(vacancy_text, config)
        role = analysis.get("role", "Desconocido")
        query = analysis.get("search_query", "")
        target_country = analysis.get("target_country", "Any")
        
        print(f"Rol detectado: {role}")
        print(f"País objetivo de la vacante: {target_country}")
        print(f"Query generada: {query}")
        
        if not query:
            print("[Error] No se pudo generar una consulta de búsqueda válida. Omitiendo vacante.")
            continue
            
        satisfied = False
        refined_query = query
        
        while not satisfied:
            # 2. Ejecutar búsqueda en Google / SerpAPI
            print(f"\nBuscando perfiles en Google con query: {refined_query}...")
            candidate_urls = search_candidates(refined_query, config)
            
            if not candidate_urls:
                print(f"[Advertencia] No se encontraron perfiles de LinkedIn con la consulta actual.")
            else:
                # 3. Asegurar que la sesión de LinkedIn esté iniciada (asistiendo de forma visible si expiró)
                if any(url not in processed_history for url in candidate_urls):
                    ensure_linkedin_session(config)
                    
                # 4. Scrapear y evaluar candidatos
                for url in candidate_urls:
                    # Evitar reprocesar candidatos ya evaluados para esta vacante
                    if url in processed_history:
                        print(f"[Saltado] Candidato ya procesado anteriormente: {url}")
                        continue
                        
                    # Scrapear perfil (pasando target_country para filtrado en Fase 1)
                    profile = scrape_linkedin_profile(url, target_country, config)
                    
                    # Registrar URL en el historial
                    processed_history[url] = {
                        "vacante": vac_file,
                        "status": profile["status"],
                        "name": profile["name"],
                        "timestamp": pd.Timestamp.now().isoformat()
                    }
                    save_processed_urls(processed_history)
                    
                    # Si se descartó por ubicación en Fase 1
                    if profile["status"] == "location_mismatch":
                        candidate_record = {
                            "vacante": vac_file,
                            "nombre": profile["name"] or "Desconocido",
                            "titular": profile["headline"] or "Sin titular",
                            "score": 0,
                            "open_to_work": False,
                            "resumen_evaluacion": f"Descartado automáticamente por Ollama: ubicación fuera del país. (Ubicación: '{profile.get('location')}', Vacante requiere: '{target_country}').",
                            "linkedin_url": url,
                            "location": profile.get("location") or "No especificada",
                            "timestamp": pd.Timestamp.now().isoformat()
                        }
                        update_json_report(candidate_record)
                        continue
                        
                    # Si hubo otro error en el scraper
                    if profile["status"] != "success":
                        print(f"[Error Scraper] No se pudo procesar {url}: {profile['error_message']}")
                        candidate_record = {
                            "vacante": vac_file,
                            "nombre": profile["name"] or "Desconocido",
                            "titular": profile["headline"] or "Sin titular",
                            "score": 0,
                            "open_to_work": False,
                            "resumen_evaluacion": f"Error al scrapear perfil: {profile['error_message']}",
                            "linkedin_url": url,
                            "location": profile.get("location") or "No especificada",
                            "timestamp": pd.Timestamp.now().isoformat()
                        }
                        update_json_report(candidate_record)
                        continue
                        
                    # Evaluar match completo con Ollama
                    print(f"Evaluando perfil de '{profile['name']}' contra la vacante...")
                    evaluation = evaluate_candidate(profile, vacancy_text, config)
                    score = evaluation["match_score"]
                    open_to_work = evaluation["open_to_work"]
                    eval_resumen = evaluation["resumen_evaluacion"]
                    
                    print(f"--> Puntuación Match: {score}% | OpenToWork: {open_to_work}")
                    
                    # Registrar record en JSON consolidado
                    candidate_record = {
                        "vacante": vac_file,
                        "nombre": profile["name"] or "Desconocido",
                        "titular": profile["headline"] or "Sin titular",
                        "score": int(score),
                        "open_to_work": bool(open_to_work),
                        "resumen_evaluacion": eval_resumen,
                        "linkedin_url": url,
                        "location": profile.get("location") or "No especificada",
                        "timestamp": pd.Timestamp.now().isoformat()
                    }
                    update_json_report(candidate_record)

            # Mostrar resumen interactivo de candidatos para esta vacante hasta ahora
            print(f"\n" + "=" * 60)
            print(f"   RESUMEN DE CANDIDATOS PARA LA VACANTE: {vac_file}")
            print(f"   (País requerido: {target_country})")
            print(f"=" * 60)
            
            vacancy_candidates = []
            if os.path.exists("output/candidatos.json"):
                try:
                    with open("output/candidatos.json", "r", encoding="utf-8") as f:
                        report = json.load(f)
                        all_cands = report.get("candidatos_deseables", []) + report.get("candidatos_no_deseables", [])
                        vacancy_candidates = [c for c in all_cands if c.get("vacante") == vac_file]
                except Exception:
                    pass
            
            if vacancy_candidates:
                # Ordenar por score descendente
                vacancy_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
                for c in vacancy_candidates:
                    print(f"- {c.get('nombre')} | Score: {c.get('score')}% | Ubicación: {c.get('location')} | URL: {c.get('linkedin_url')}")
            else:
                print("No hay candidatos procesados para esta vacante aún.")
            print("=" * 60)
            
            satisfy_input = input(f"\n¿Estás satisfecho con los resultados obtenidos para la vacante '{vac_file}'? (S/N) [S]: ").strip().lower()
            if satisfy_input in ("", "s", "si", "yes"):
                satisfied = True
                # Mover al histórico
                dest_path = os.path.join("procesadas/vacantes_viejas", vac_file)
                try:
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                    shutil.move(vac_path, dest_path)
                    print(f"Archivo de vacante movido a históricos: {dest_path}")
                except Exception as e:
                    print(f"[Error] No se pudo mover la vacante a históricos: {e}")
            else:
                refine_input = input("¿Deseas continuar la búsqueda refinando la consulta o cargando más perfiles? (S/N) [N]: ").strip().lower()
                if refine_input == "s":
                    extra_terms = input("Ingresa palabras clave adicionales para la búsqueda (ej: 'Tulsa' o 'SRE' o 'Reading'): ").strip()
                    if extra_terms:
                        refined_query = f"{query} AND ({extra_terms})"
                        print(f"[Refinamiento] Nueva consulta de búsqueda: {refined_query}")
                    else:
                        print("[Info] No ingresaste nuevos términos. Terminando refinamiento.")
                        break
                else:
                    print(f"[Info] Manteniendo la vacante '{vac_file}' en 'vacantes/' para futuras corridas.")
                    break
            
    print("\nProcesamiento terminado.")

if __name__ == "__main__":
    main()
