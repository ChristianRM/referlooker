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
  "target_country": "País objetivo de la vacante si se menciona, ej: 'Mexico' o 'United States'. Si no se especifica o es remoto/global, escribe 'Any'",
  "keywords": ["palabra_clave1", "palabra_clave2", ...],
  "search_query": "Consulta de búsqueda X-Ray de Google optimizada"
}}

Reglas para construir el "search_query":
1. De forma predeterminada, comienza la consulta con `site:linkedin.com/in/` de forma directa, sin colocarle paréntesis alrededor. Por ejemplo, escribe `site:linkedin.com/in/ ("open to work" ...)` y NUNCA `(site:linkedin.com/in/)`.
2. REGLA DE UBICACIÓN REGIONAL: Si la vacante especifica un país de trabajo obligatorio, ajusta el inicio de la consulta para usar el subdominio correspondiente de LinkedIn (por ejemplo, si es en México, usa `site:mx.linkedin.com/in/`. Si es en España, usa `site:es.linkedin.com/in/`. Si es en Estados Unidos o global, usa `site:linkedin.com/in/` e incluye el país o región en la consulta de búsqueda, por ejemplo: `AND ("United States" OR "USA")`).
3. Incluye variantes comunes de búsqueda activa de empleo como `("open to work" OR "open to opportunities" OR "búsqueda activa")`.
4. Incluye el rol principal simplificado. Utiliza nombres de puestos genéricos y muy comunes en la industria (ej: `("AWS Architect" OR "Cloud Engineer" OR "DevOps")`). NUNCA utilices nombres de proyectos internos, herramientas ultra-específicas o siglas propietarias de la empresa vacante (ej: NUNCA uses 'AgentCore', 'IRC292142', etc.) ya que ningún candidato las tendrá en su titular.
5. Agrega solo 1 o 2 tecnologías indispensables usando operadores booleanos (ej: `("Terraform" OR "Kubernetes")`). Mantén la consulta corta y simple; si agregas demasiados operadores AND obligatorios, el buscador de Google retornará cero resultados. Es mejor una búsqueda amplia y dejar que el evaluador filtre los detalles finos.
6. Evita comillas innecesarias o consultas demasiado largas que rompan el buscador.

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

def generate_refined_search_query(vacancy_text: str, previous_query: str, config: dict) -> str:
    """
    Pide a Ollama que genere una consulta de búsqueda X-Ray de Google refinada y alternativa
    basándose en la vacante y en la consulta anterior que no dio resultados satisfactorios.
    """
    model_name = config.get("ollama", {}).get("model", "llama3.1:8b")
    ollama_host = config.get("ollama", {}).get("host", "http://localhost:11434")
    import ollama
    client = ollama.Client(host=ollama_host)
    
    prompt = f"""
    Eres un reclutador técnico experto en búsquedas booleanas y operadores X-Ray de Google.
    La consulta de búsqueda anterior que generamos no arrojó resultados satisfactorios o fue demasiado restrictiva.
    
    Descripción de la Vacante:
    \"\"\"
    {vacancy_text}
    \"\"\"
    
    Consulta de Búsqueda Anterior:
    "{previous_query}"
    
    Tu objetivo es generar una nueva consulta de búsqueda X-Ray optimizada y alternativa.
    Sigue estas reglas estrictas:
    1. Debe comenzar directamente con `site:linkedin.com/in/` (o el subdominio correspondiente si hay país requerido).
    2. Cambia los términos para hacerla más amplia o usa sinónimos alternativos para el rol y las tecnologías.
    3. Si la consulta anterior tenía demasiados operadores AND, redúcelos para permitir que Google traiga más perfiles.
    4. Devuelve únicamente un objeto JSON válido (y absolutamente NADA más) con el siguiente formato exacto:
    {{
      "search_query": "Nueva consulta optimizada"
    }}
    Responde ÚNICAMENTE con el objeto JSON.
    """
    
    try:
        response = client.generate(
            model=model_name,
            prompt=prompt,
            options={"temperature": 0.3}
        )
        response_text = response.get("response", "")
        # Limpiar y parsear JSON
        from evaluator import clean_json_response
        cleaned = clean_json_response(response_text)
        data = json.loads(cleaned)
        return data.get("search_query", "")
    except Exception as e:
        print(f"[Advertencia] Error al refinar consulta con Ollama: {e}")
        try:
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx+1]
                data = json.loads(json_str)
                return data.get("search_query", "")
        except Exception:
            pass
        return ""
