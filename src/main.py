import os
import sys
import json
import shutil
import pandas as pd

# Añadir directorio actual al path por si acaso
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from query_generator import generate_search_query
from search_engine import search_candidates
from linkedin_scraper import scrape_linkedin_profile
from evaluator import evaluate_candidate

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

def regenerate_reports(excel_path: str, txt_path: str):
    """
    Lee el archivo Excel, ordena a los candidatos por vacante y score,
    reescribe el Excel y genera una versión limpia en formato texto (.txt).
    """
    if not os.path.exists(excel_path):
        return
        
    try:
        df = pd.read_excel(excel_path)
        if df.empty:
            return
            
        # Crear columna numérica temporal para ordenar el Score (ej: "94%" -> 94)
        df["Score_Num"] = df["Score"].astype(str).str.rstrip("%").astype(float, errors="ignore")
        
        # Ordenar por Vacante (alfabético) y luego por Score_Num (descendente)
        df = df.sort_values(by=["Vacante Asociada", "Score_Num"], ascending=[True, False])
        df = df.drop(columns=["Score_Num"])
        
        # Guardar archivo Excel ordenado
        df.to_excel(excel_path, index=False)
        
        # Escribir reporte en TXT
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("============================================================\n")
            f.write("      REPORTE CONSOLIDADO DE CANDIDATOS DESEABLES\n")
            f.write("============================================================\n")
            f.write(f"Total Candidatos: {len(df)}\n")
            
            current_vacancy = None
            for _, row in df.iterrows():
                vac = row["Vacante Asociada"]
                if vac != current_vacancy:
                    current_vacancy = vac
                    f.write(f"\n============================================================\n")
                    f.write(f"VACANTE: {current_vacancy}\n")
                    f.write(f"============================================================\n")
                
                f.write(f"Candidato: {row['Candidato / Titular']}\n")
                f.write(f"Score: {row['Score']}\n")
                f.write(f"LinkedIn: {row['URL LinkedIn']}\n")
                f.write(f"Estado: {row['Estado']}\n")
                f.write(f"Resumen de Evaluación: {row['Resumen de Evaluación (LLM)']}\n")
                f.write(f"------------------------------------------------------------\n")
                
        print(f"[Reporte] Reportes actualizados con éxito en 'output/'.")
    except Exception as e:
        print(f"[Error] No se pudieron regenerar los reportes: {e}")

def update_excel_report(candidate_info: dict, excel_path: str):
    """Inserta o actualiza un candidato en el reporte de Excel."""
    columns = ["Vacante Asociada", "Candidato / Titular", "Score", "Resumen de Evaluación (LLM)", "URL LinkedIn", "Estado"]
    
    if os.path.exists(excel_path):
        try:
            df = pd.read_excel(excel_path)
        except Exception:
            df = pd.DataFrame(columns=columns)
    else:
        df = pd.DataFrame(columns=columns)
        
    url = candidate_info["URL LinkedIn"]
    exists = df["URL LinkedIn"] == url
    
    new_row = pd.DataFrame([candidate_info])
    
    if exists.any():
        # Actualizar fila existente
        idx = df[exists].index[0]
        for col in columns:
            df.at[idx, col] = candidate_info[col]
    else:
        # Concatenar la nueva fila
        df = pd.concat([df, new_row], ignore_index=True)
        
    df.to_excel(excel_path, index=False)

def main():
    config = load_config()
    setup_directories()
    
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
        
        print(f"Rol detectado: {role}")
        print(f"Query generada: {query}")
        
        if not query:
            print("[Error] No se pudo generar una consulta de búsqueda válida. Omitiendo vacante.")
            continue
            
        # 2. Ejecutar búsqueda en Google / SerpAPI
        print("Buscando perfiles en Google...")
        candidate_urls = search_candidates(query, config)
        
        # 3. Scrapear y evaluar candidatos
        for url in candidate_urls:
            # Evitar reprocesar candidatos ya evaluados para esta vacante
            if url in processed_history:
                print(f"[Saltado] Candidato ya procesado anteriormente: {url}")
                continue
                
            # Scrapear perfil
            profile = scrape_linkedin_profile(url, config)
            
            # Registrar URL en el historial (independiente de si fue exitoso o falló para no volver a intentar)
            processed_history[url] = {
                "vacante": vac_file,
                "status": profile["status"],
                "name": profile["name"],
                "timestamp": pd.Timestamp.now().isoformat()
            }
            save_processed_urls(processed_history)
            
            if profile["status"] != "success":
                print(f"[Error Scraper] No se pudo procesar {url}: {profile['error_message']}")
                continue
                
            # Evaluar match con Ollama
            print(f"Evaluando perfil de '{profile['name']}' contra la vacante...")
            evaluation = evaluate_candidate(profile, vacancy_text, config)
            score = evaluation["match_score"]
            open_to_work = evaluation["open_to_work"]
            eval_resumen = evaluation["resumen_evaluacion"]
            
            print(f"--> Puntuación Match: {score}% | OpenToWork: {open_to_work}")
            
            # Si supera el score mínimo
            if score >= min_score:
                print(f"[Aceptado] Candidato califica con {score}% de match.")
                
                candidate_record = {
                    "Vacante Asociada": vac_file,
                    "Candidato / Titular": f"{profile['name']} | {profile['headline']}",
                    "Score": f"{score}%",
                    "Resumen de Evaluación (LLM)": eval_resumen,
                    "URL LinkedIn": url,
                    "Estado": "Pendiente"
                }
                
                # Actualizar Excel
                update_excel_report(candidate_record, excel_path)
            else:
                print(f"[Descartado] Match de {score}% es menor al mínimo de {min_score}%.")
                
        # 4. Mover la vacante procesada al histórico
        dest_path = os.path.join("procesadas/vacantes_viejas", vac_file)
        try:
            # En Windows shutil.move puede fallar si el archivo de destino existe. Lo removemos si es así.
            if os.path.exists(dest_path):
                os.remove(dest_path)
            shutil.move(vac_path, dest_path)
            print(f"Archivo de vacante movido a: {dest_path}")
        except Exception as e:
            print(f"[Error] No se pudo mover la vacante a procesadas: {e}")
            
    # Regenerar ambos reportes ordenados
    regenerate_reports(excel_path, txt_path)
    print("\nProcesamiento terminado con éxito.")

if __name__ == "__main__":
    main()
