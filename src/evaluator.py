import os
import json
import ollama

def clean_json_response(text: str) -> str:
    """
    Limpia el texto de respuesta del LLM para extraer únicamente el bloque JSON,
    removiendo posibles delimitadores de markdown (```json ... ```).
    """
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def evaluate_candidate(profile_data: dict, vacancy_text: str, config: dict) -> dict:
    """
    Analiza el perfil de LinkedIn y la vacante usando Ollama para calcular
    el score de match, verificar la disponibilidad 'open to work' y redactar un resumen.
    """
    model_name = config.get("ollama", {}).get("model", "llama3.1:8b")
    ollama_host = config.get("ollama", {}).get("host", "http://localhost:11434")
    
    # Crear cliente de Ollama
    client = ollama.Client(host=ollama_host)
    
    # Armamos una representación textual estructurada del perfil del candidato
    profile_summary = f"""
URL: {profile_data.get('url')}
Nombre: {profile_data.get('name')}
Titular: {profile_data.get('headline')}
"""
    
    # Si logramos extraer secciones estructuradas las priorizamos, de lo contrario usamos el texto completo del body
    if profile_data.get('about') or profile_data.get('experience'):
        profile_summary += f"""
[Extracto / Acerca de]
{profile_data.get('about')}

[Experiencia]
{profile_data.get('experience')}

[Habilidades]
{profile_data.get('skills')}
"""
    else:
        profile_summary += f"""
[Contenido Completo del Perfil (Texto Completo)]
{profile_data.get('raw_text')}
"""

    prompt = f"""
Eres un reclutador experto y técnico de recursos humanos.
Tu objetivo es evaluar el perfil de LinkedIn de un candidato en comparación con los requerimientos de la descripción de la vacante de empleo.

Descripción de la Vacante:
\"\"\"
{vacancy_text}
\"\"\"

Perfil del Candidato (Extraído de LinkedIn):
\"\"\"
{profile_summary}
\"\"\"

Debes devolver estrictamente un objeto JSON (y NADA más) con el siguiente formato exacto:
{{
  "match_score": 85,
  "open_to_work": true,
  "resumen_evaluacion": "Un párrafo breve y descriptivo (2-3 oraciones) sobre las fortalezas del candidato para este puesto, si cumple con la experiencia y tecnologías indicadas, y cualquier brecha importante que detectes."
}}

Reglas de evaluación:
1. "match_score" debe ser un número entero de 0 a 100. Sé objetivo. Si no cumple con las tecnologías esenciales o el nivel de experiencia requerido, baja el puntaje.
2. "open_to_work" debe ser un booleano (true/false) que indique si hay evidencia de que el candidato está en búsqueda activa (mención de 'open to work', 'en búsqueda', 'disponible', 'looking for', etc. en su titular o secciones).
3. "resumen_evaluacion" debe estar redactado en español.
4. FILTRO DE UBICACIÓN GEOGRÁFICA (PAÍS): Revisa si la descripción de la vacante especifica un país o región obligatoria de trabajo (por ejemplo, México o Estados Unidos). Si es así, identifica el país del candidato en el perfil de LinkedIn. Si el candidato se encuentra físicamente en un país diferente al requerido por la vacante, debes calificar su "match_score" estrictamente como 0, y colocar en el "resumen_evaluacion" la justificación indicando que fue descartado por discrepancia de ubicación geográfica (ejemplo: vacante requiere México pero candidato está en la India).

Responde ÚNICAMENTE con el objeto JSON.
"""

    try:
        response = client.generate(
            model=model_name,
            prompt=prompt,
            options={
                "temperature": 0.1
            }
        )
        response_text = response.get("response", "")
        cleaned_text = clean_json_response(response_text)
        data = json.loads(cleaned_text)
        
        return {
            "match_score": int(data.get("match_score", 0)),
            "open_to_work": bool(data.get("open_to_work", False)),
            "resumen_evaluacion": data.get("resumen_evaluacion", "Evaluación completada con éxito.")
        }
    except Exception as e:
        print(f"[Advertencia] Error al evaluar con Ollama: {e}")
        # Intento de rescate si el JSON viene envuelto en texto libre
        try:
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx+1]
                data = json.loads(json_str)
                return {
                    "match_score": int(data.get("match_score", 0)),
                    "open_to_work": bool(data.get("open_to_work", False)),
                    "resumen_evaluacion": data.get("resumen_evaluacion", "Evaluación recuperada del log.")
                }
        except Exception:
            pass
            
        return {
            "match_score": 0,
            "open_to_work": False,
            "resumen_evaluacion": f"Error al procesar la evaluación con el modelo: {e}"
        }
