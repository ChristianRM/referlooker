import os
import sys
import json
import shutil
import pandas as pd

# Asegurar importación de módulos hermanos
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from query_generator import generate_search_query
from evaluator import evaluate_candidate
from main import update_excel_report, regenerate_reports

def run_mock_integration_test():
    """
    Ejecuta una simulación completa del sistema sin requerir APIs externas ni cookies de LinkedIn.
    Utiliza el modelo local de Ollama para la evaluación y genera los reportes de salida reales.
    """
    print("=" * 60)
    print("INICIANDO PRUEBA DE INTEGRACIÓN SIMULADA (MOCK TEST)")
    print("=" * 60)
    
    # 1. Preparar directorios y configuración ficticia
    os.makedirs("vacantes", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    os.makedirs("procesadas/vacantes_viejas", exist_ok=True)
    
    config = {
        "ollama": {
            "model": "llama3.1:8b",
            "host": "http://localhost:11434"
        },
        "evaluation": {
            "min_score": 80
        }
    }
    
    # Cargar la vacante de prueba
    vacancy_file = os.path.join("vacantes", "backend_sr.txt")
    if not os.path.exists(vacancy_file):
        # Crear de emergencia si no existiera
        with open(vacancy_file, "w", encoding="utf-8") as f:
            f.write("Vacante de Prueba: Senior Python Developer (FastAPI, Docker, AWS, PostgreSQL)")
            
    with open(vacancy_file, "r", encoding="utf-8") as f:
        vacancy_text = f.read().strip()
        
    print(f"[1/4] Vacante de prueba cargada: {vacancy_file}")
    
    # 2. Generar query con Ollama
    print("\n[2/4] Generando consulta de búsqueda X-Ray simulada con Ollama...")
    query_data = generate_search_query(vacancy_text, config)
    print(f"-> Rol extraído: {query_data.get('role')}")
    print(f"-> Query X-Ray generada: {query_data.get('search_query')}")
    
    # 3. Datos simulados de candidatos (Mock Profiles)
    print("\n[3/4] Cargando perfiles simulados de LinkedIn...")
    mock_profiles = [
        {
            "url": "https://www.linkedin.com/in/juan-perez-backend",
            "name": "Juan Pérez",
            "headline": "Senior Backend Developer | Django | FastAPI | Cloud Architect",
            "about": "Desarrollador backend apasionado con más de 6 años de experiencia construyendo APIs escalables y robustas con Python, Django y FastAPI. Busco activamente nuevos retos profesionales (Open to Work).",
            "experience": "Senior Backend Engineer en Tech Solutions (2021 - Presente).\nLideré la migración de microservicios monolíticos a FastAPI y Docker en la nube AWS.\nBackend Developer en Software Factory (2018 - 2021).\nDesarrollo de APIs REST con Python y bases de datos PostgreSQL.",
            "skills": "Python, FastAPI, Django, PostgreSQL, Docker, AWS, Git, Scrum",
            "status": "success"
        },
        {
            "url": "https://www.linkedin.com/in/maria-gomez-data-eng",
            "name": "María Gómez",
            "headline": "Lead Data Engineer | Spark | Snowflake",
            "about": "Ingeniera de datos con amplia experiencia liderando equipos técnicos y diseñando pipelines ETL complejas e infraestructura de datos moderna en Snowflake y Spark.",
            "experience": "Lead Data Engineer en Data Corp (2020 - Presente).\nModelado de datos distribuidos usando Spark sobre AWS.\nData Engineer en Analytics Inc (2017 - 2020).\nCreación de ETLs en Python y optimización de data warehouses.",
            "skills": "Spark, Snowflake, SQL, Python, ETL, AWS",
            "status": "success"
        }
    ]
    
    # 4. Procesar y Evaluar Candidatos
    excel_path = "output/candidatos_deseables.xlsx"
    txt_path = "output/candidatos_deseables.txt"
    min_score = config["evaluation"]["min_score"]
    
    # Inicializar o cargar historial procesado simulado
    history_path = "output/processed_urls.json"
    processed_history = {}
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                processed_history = json.load(f)
        except Exception:
            pass
            
    print(f"\n[4/4] Evaluando {len(mock_profiles)} candidatos simulados con Ollama...")
    
    for profile in mock_profiles:
        url = profile["url"]
        
        # Evaluar candidato real usando Ollama
        print(f"\nEvaluando candidato: '{profile['name']}' ({profile['headline']})")
        evaluation = evaluate_candidate(profile, vacancy_text, config)
        score = evaluation["match_score"]
        open_to_work = evaluation["open_to_work"]
        eval_resumen = evaluation["resumen_evaluacion"]
        
        print(f"--> Puntuación Match (Ollama): {score}% | OpenToWork: {open_to_work}")
        print(f"--> Resumen: {eval_resumen}")
        
        # Actualizar historial
        processed_history[url] = {
            "vacante": "backend_sr.txt",
            "status": "success",
            "name": profile["name"],
            "timestamp": pd.Timestamp.now().isoformat()
        }
        
        if score >= min_score:
            print(f"[Aceptado] Candidato califica para el reporte ({score}% >= {min_score}%)")
            candidate_record = {
                "Vacante Asociada": "backend_sr.txt",
                "Candidato / Titular": f"{profile['name']} | {profile['headline']}",
                "Score": f"{score}%",
                "Resumen de Evaluación (LLM)": eval_resumen,
                "URL LinkedIn": url,
                "Estado": "Pendiente"
            }
            update_excel_report(candidate_record, excel_path)
        else:
            print(f"[Descartado] Candidato no supera la puntuación mínima.")
            
    # Guardar historial
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(processed_history, f, indent=2, ensure_ascii=False)
        
    # Mover la vacante procesada al histórico
    dest_path = os.path.join("procesadas/vacantes_viejas", "backend_sr.txt")
    try:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        shutil.copy(vacancy_file, dest_path)  # Usamos copy en el test para no eliminar el archivo de entrada original
        print(f"\n[Test] Copia de vacante de prueba archivada en: {dest_path}")
    except Exception as e:
        print(f"[Advertencia] No se pudo archivar la vacante: {e}")
        
    # Regenerar reportes consolidando la información
    regenerate_reports(excel_path, txt_path)
    
    print("\n" + "=" * 60)
    print("TEST FINALIZADO CON ÉXITO.")
    print("Por favor revisa la carpeta 'output/' para validar los resultados generados:")
    print(f"- Excel: {os.path.abspath(excel_path)}")
    print(f"- Texto plano: {os.path.abspath(txt_path)}")
    print("=" * 60)

if __name__ == "__main__":
    run_mock_integration_test()
