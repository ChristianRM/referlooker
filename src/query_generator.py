import os
import json
import ollama

def clean_json_response(text: str) -> str:
    """
    Limpia el texto de respuesta del LLM para extraer únicamente el bloque JSON,
    removiendo posibles delimitadores de markdown (```json ... ```).
    """
    text = text.strip()
    # Remover marcas de código markdown si existen
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def generate_search_query(vacancy_text: str, config: dict) -> dict:
    """
    Llama a Ollama localmente para analizar la descripción de la vacante,
    extraer palabras clave y generar la consulta de búsqueda X-Ray de Google.
    """
    model_name = config.get("ollama", {}).get("model", "llama3.1:8b")
    ollama_host = config.get("ollama", {}).get("host", "http://localhost:11434")
    
    # Inicializar cliente de Ollama
    client = ollama.Client(host=ollama_host)
    
    prompt = f"""
Eres un reclutador experto y especialista en sourcing de talento técnico.
Tu tarea es analizar la descripción de la vacante provista y extraer la información clave para generar una consulta de búsqueda tipo X-Ray para Google.

Vacante:
\"\"\"
{vacancy_text}
\"\"\"

Debes devolver obligatoriamente un objeto JSON válido (y NADA más, sin introducciones ni explicaciones) con la siguiente estructura:
{{
  "role": "Nombre simplificado del puesto (ej: Senior Python Developer)",
  "keywords": ["palabra_clave1", "palabra_clave2", ...],
  "search_query": "Consulta de búsqueda X-Ray de Google optimizada"
}}

Reglas para construir el "search_query":
1. Usa `site:linkedin.com/in/` para buscar perfiles individuales de personas.
2. Incluye variantes comunes de búsqueda activa de empleo como `("open to work" OR "open to opportunities" OR "búsqueda activa")`.
3. Incluye el rol principal (ej: `("Backend Developer" OR "Backend Engineer")`).
4. Agrega tecnologías indispensables usando operadores booleanos (ej: `("Django" OR "FastAPI")`).
5. Evita comillas innecesarias o consultas demasiado largas que rompan el buscador.

Responde ÚNICAMENTE con el objeto JSON.
"""

    try:
        response = client.generate(
            model=model_name,
            prompt=prompt,
            options={
                "temperature": 0.2
            }
        )
        response_text = response.get("response", "")
        cleaned_text = clean_json_response(response_text)
        data = json.loads(cleaned_text)
        return data
    except Exception as e:
        print(f"[Advertencia] Error al llamar a Ollama en query_generator: {e}")
        # Intentar extraer JSON básico si hay texto extra
        try:
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx+1]
                return json.loads(json_str)
        except Exception:
            pass
            
        # Fallback simple
        return {
            "role": "Software Developer",
            "keywords": [],
            "search_query": 'site:linkedin.com/in/ ("open to work" OR "búsqueda activa")'
        }
