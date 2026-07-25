import os
import json
import ollama

def clean_json_response(text: str) -> str:
    """
    Cleans the LLM response text to extract only the JSON block,
    removing any markdown delimiters (```json ... ```).
    """
    text = text.strip()
    # Remove markdown code block markers if present
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def generate_search_query(vacancy_text: str, config: dict) -> dict:
    """
    Calls local Ollama instance to analyze the vacancy description,
    extract key terms, and generate an optimized Google X-Ray search query.
    """
    model_name = config.get("ollama", {}).get("model", "llama3.1:8b")
    ollama_host = config.get("ollama", {}).get("host", "http://localhost:11434")
    
    # Initialize Ollama client
    client = ollama.Client(host=ollama_host)
    
    prompt = f"""
You are an expert technical recruiter and talent sourcing specialist.
Your task is to analyze the provided job description and extract key information to generate an optimized Google X-Ray search query.

Job Description:
\"\"\"
{vacancy_text}
\"\"\"

You must return a valid JSON object (and NOTHING else, no introductions, no markdown comments) with the following structure:
{{
  "role": "Simplified job title (e.g., Senior Python Developer)",
  "target_country": "Target country of the vacancy if specified, e.g., 'Mexico' or 'United States'. If not specified or if the role is remote/global, write 'Any'",
  "keywords": ["keyword1", "keyword2", ...],
  "search_query": "Optimized Google X-Ray search query"
}}

Rules for building the "search_query":
1. Start the query directly with `site:linkedin.com/in/`. Do NOT put parentheses around it (e.g., write `site:linkedin.com/in/ ("open to work" ...)` and NEVER `(site:linkedin.com/in/)`).
2. REGIONAL LOCATION RULE: If the job description specifies a mandatory work country, adjust the start of the query to use the corresponding LinkedIn subdomain (e.g., if in Mexico, use `site:mx.linkedin.com/in/`. If in Spain, use `site:es.linkedin.com/in/`. If in the United States or global, use `site:linkedin.com/in/` and include the country or region in the search query, e.g., `AND ("United States" OR "USA")`).
3. Include common variations for active job seeking, such as: `("open to work" OR "open to opportunities" OR "looking for opportunities")`.
4. Include the simplified main role. Use common and generic job titles in the industry (e.g., `("AWS Architect" OR "Cloud Engineer" OR "DevOps")`). NEVER use internal project names, highly specific tools, or proprietary company codes (e.g., NEVER use 'AgentCore', 'IRC292142', etc.) as no candidate will have them in their headline.
5. Add only 1 or 2 essential technologies using Boolean operators (e.g., `("Terraform" OR "Kubernetes")`). Keep the query short and simple; if you add too many mandatory AND operators, Google will return zero results. A broader search is preferred, allowing the evaluator module to filter details later.
6. Avoid unnecessary quotes or overly long queries that break Google search.

Respond ONLY with the JSON object.
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
        print(f"[Warning] Error calling Ollama in query_generator: {e}")
        # Try to extract basic JSON if extra text was returned
        try:
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx+1]
                return json.loads(json_str)
        except Exception:
            pass
            
        # Simple fallback
        return {
            "role": "Software Developer",
            "keywords": [],
            "search_query": 'site:linkedin.com/in/ ("open to work" OR "seeking opportunities")'
        }

def generate_refined_search_query(vacancy_text: str, previous_query: str, config: dict) -> str:
    """
    Asks Ollama to generate an alternative and refined Google X-Ray search query
    based on the vacancy text and the previous query that yielded no satisfactory results.
    """
    model_name = config.get("ollama", {}).get("model", "llama3.1:8b")
    ollama_host = config.get("ollama", {}).get("host", "http://localhost:11434")
    client = ollama.Client(host=ollama_host)
    
    prompt = f"""
You are an expert technical recruiter specializing in boolean search strings and Google X-Ray operators.
The previous search query we generated yielded no satisfactory results or was too restrictive.

Job Description:
\"\"\"
{vacancy_text}
\"\"\"

Previous Search Query:
"{previous_query}"

Your goal is to generate a new, optimized, and alternative X-Ray search query.
Follow these strict rules:
1. Start directly with `site:linkedin.com/in/` (or the corresponding country subdomain if a specific country is required).
2. Change terms to make it broader, or use alternative synonyms for the role and technologies.
3. If the previous query had too many AND operators, reduce them to allow Google to return more profiles.
4. Return only a valid JSON object (and absolutely NOTHING else) in the following exact format:
{{
  "search_query": "New optimized query"
}}
Respond ONLY with the JSON object.
"""
    
    try:
        response = client.generate(
            model=model_name,
            prompt=prompt,
            options={"temperature": 0.3}
        )
        response_text = response.get("response", "")
        # Clean and parse JSON
        cleaned = clean_json_response(response_text)
        data = json.loads(cleaned)
        return data.get("search_query", "")
    except Exception as e:
        print(f"[Warning] Error refining query with Ollama: {e}")
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
