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

QUERY_RULES = """
Rules for building the "search_query":
1. Start the query directly with the site filter:
   - For Mexico: `site:mx.linkedin.com/in/`
   - For Spain: `site:es.linkedin.com/in/`
   - For United States (USA): Use `site:linkedin.com/in/` and you MUST append `AND ("United States" OR "USA")` to the search query.
   - For other countries: Use the corresponding LinkedIn country subdomain if one exists, or use `site:linkedin.com/in/` and append the country in quotes, e.g., `AND "CountryName"`.
2. Wrap ALL multi-word phrases, role titles, and status terms in double quotes (e.g., "open to work" instead of open to work, "Senior Software Engineer" instead of Senior Software Engineer, "AI/ML Software Engineer").
3. Include common variations for active job seeking wrapped in quotes, e.g., `("open to work" OR "open to opportunities")`.
4. Determine appropriate role titles based on required seniority, making sure all multi-word titles are in double quotes:
   - If the job description requires extremely high seniority (e.g., 12-15+ YOE) but demands hands-on coding/technical fluency, expand search titles to: `("Principal" OR "Staff" OR "Architect" OR "Lead")` combined with the role name. Do NOT include managerial-only titles like "Director" as they are typically not hands-on.
   - Otherwise, use common industry titles (e.g., `"AWS Architect"`, `"Cloud Engineer"`, `"Python Developer"`).
   - Never use internal project names, proprietary company codes (like AgentCore, IRC292142), or overly specific internal tags.
5. Extract literal, specific technologies and frameworks from the "Good-to-Have", "Technical Fluency", or "Qualifications" sections (e.g., "LangChain", "AutoGen", "Copilot", "MCP" in double quotes).
6. Do NOT assume or add external technologies by inertia (e.g., do NOT add generic tools like Kubernetes, Terraform, AWS, Docker unless they are explicitly written in the job description), as it limits the search and filters out ideal candidates.
7. Keep the query short and simple. Use only 1 or 2 essential technologies or criteria from the JD with boolean OR.
8. Every term in the query should follow this structure pattern:
   `site:linkedin.com/in/ ("open to work" OR "open to opportunities") AND ("Principal" OR "Staff" OR "Architect" OR "Lead") AND ("AI/ML Software Engineer" OR "Senior Software Engineer") AND ("LangChain" OR "AutoGen" OR "Copilot") AND ("United States" OR "USA")`
"""

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

{QUERY_RULES}

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

{QUERY_RULES}

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
