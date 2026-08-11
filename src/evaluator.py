import os
import json
import ollama

def clean_json_response(text: str) -> str:
    """
    Cleans the LLM response text to extract only the JSON block,
    removing any markdown delimiters (```json ... ```).
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
    Analyzes the LinkedIn profile and the job description using Ollama
    to calculate structured sub-scores and enforce strict Open to Work filtering.
    """
    # 1. Python-based quick check for active search signals
    text_to_check = " ".join([
        profile_data.get("headline", "") or "",
        profile_data.get("about", "") or "",
        profile_data.get("experience", "") or "",
        profile_data.get("raw_text", "") or ""
    ]).lower()
    
    signals = [
        "open to work",
        "open to opportunities",
        "looking for",
        "seeking",
        "disponible",
        "disponibilidad",
        "búsqueda activa",
        "busqueda activa",
        "nuevos retos",
        "opentowork",
        "new challenges",
        "new opportunities",
        "open to new"
    ]
    
    has_active_signal = any(sig in text_to_check for sig in signals)
    
    if not has_active_signal:
        return {
            "technical_score": 0,
            "experience_score": 0,
            "auxiliary_score": 0,
            "match_score": 0,
            "open_to_work": False,
            "evaluation_summary": "Candidate discarded: No active job search indicators (Open to Work, looking for, seeking, etc.) found in the profile headline, about, or experience text."
        }
        
    # 2. Proceed to LLM evaluation if a signal is found
    model_name = config.get("ollama", {}).get("model", "llama3.1:8b")
    ollama_host = config.get("ollama", {}).get("host", "http://localhost:11434")
    
    # Initialize Ollama client
    client = ollama.Client(host=ollama_host)
    
    # Build structured text representation of candidate profile
    profile_summary = f"""
URL: {profile_data.get('url')}
Name: {profile_data.get('name')}
Headline: {profile_data.get('headline')}
"""
    
    if profile_data.get('about') or profile_data.get('experience'):
        profile_summary += f"""
[About / Summary]
{profile_data.get('about')}

[Experience]
{profile_data.get('experience')}

[Skills]
{profile_data.get('skills')}
"""
    else:
        profile_summary += f"""
[Full Profile Content (Raw Text)]
{profile_data.get('raw_text')}
"""

    prompt = f"""
You are an expert technical recruiter and HR specialist.
Evaluate the candidate's LinkedIn profile against the requirements of the job description.

Strictly return a valid JSON object (and NOTHING else) in the following format:
{{
  "open_to_work": [true or false],
  "technical_score": [integer, 0-40],
  "experience_score": [integer, 0-40],
  "auxiliary_score": [integer, 0-20],
  "match_score": [integer, 0-100],
  "evaluation_summary": "[2-3 sentences evaluation summary in English]"
}}

Instructions & Rules:
1. **Open to Work Verification**:
   Verify if the candidate is open to new opportunities or actively looking for work. Check the profile for explicit indicators (such as 'open to work', 'open to opportunities', 'seeking', 'looking for', 'disponible', 'disponibilidad', 'new challenges', etc.).
   * If the profile contains such indicators, set "open_to_work" to true.
   * If there are no active search indicators, set "open_to_work" to false.
   * If "open_to_work" is false, set all scores (technical_score, experience_score, auxiliary_score, match_score) strictly to 0, and state in the "evaluation_summary" that the candidate is discarded because they are not looking for new opportunities.

2. **Scoring Rubric (Only if open_to_work is true)**:
   * **technical_score** (0-40): Fit for core programming languages, tools, libraries, and frameworks in the job description.
   * **experience_score** (0-40): Fit for seniority level, leadership, and overall years of experience.
   * **auxiliary_score** (0-20): Fit for databases, cloud platforms, DevOps, and other auxiliary tools.
   * **match_score**: MUST be equal to technical_score + experience_score + auxiliary_score.

3. **Geographic Location Check**:
   If the job description specifies a mandatory location/country (e.g. USA, United States, Mexico), check if the candidate lives there. If they live in a different country, set the match_score and all sub-scores to 0.

Job Description:
\"\"\"
{vacancy_text}
\"\"\"

Candidate Profile (Extracted from LinkedIn):
\"\"\"
{profile_summary}
\"\"\"

Respond ONLY with the JSON object.
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
            "technical_score": int(data.get("technical_score", 0)),
            "experience_score": int(data.get("experience_score", 0)),
            "auxiliary_score": int(data.get("auxiliary_score", 0)),
            "match_score": int(data.get("match_score", 0)),
            "open_to_work": bool(data.get("open_to_work", False)),
            "evaluation_summary": data.get("evaluation_summary", "Evaluation completed successfully.")
        }
    except Exception as e:
        print(f"[Warning] Error evaluating candidate with Ollama: {e}")
        # Attempt rescue
        try:
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx+1]
                data = json.loads(json_str)
                return {
                    "technical_score": int(data.get("technical_score", 0)),
                    "experience_score": int(data.get("experience_score", 0)),
                    "auxiliary_score": int(data.get("auxiliary_score", 0)),
                    "match_score": int(data.get("match_score", 0)),
                    "open_to_work": bool(data.get("open_to_work", False)),
                    "evaluation_summary": data.get("evaluation_summary", "Evaluation recovered from response text.")
                }
        except Exception:
            pass
            
        return {
            "technical_score": 0,
            "experience_score": 0,
            "auxiliary_score": 0,
            "match_score": 0,
            "open_to_work": False,
            "evaluation_summary": f"Error processing evaluation with the model: {e}"
        }

def evaluate_location_with_llm(header_text: str, target_country: str, config: dict) -> dict:
    """
    Asks Ollama if the candidate's location is compatible with the required one.
    Returns a dictionary with 'compatible' (bool) and 'extracted_location' (str).
    """
    model_name = config.get("ollama", {}).get("model", "llama3.1:8b")
    ollama_host = config.get("ollama", {}).get("host", "http://localhost:11434")
    client = ollama.Client(host=ollama_host)
    
    required = target_country if target_country.lower() not in ("any", "global", "remoto", "remote", "") else "Mexico or United States"
    
    req_lower = required.lower()
    if req_lower in ("usa", "us", "united states", "united states of america"):
        normalized_required = "United States / USA"
    elif req_lower in ("mexico", "mx", "méxico"):
        normalized_required = "Mexico"
    else:
        normalized_required = required

    prompt = f"""
You are an expert technical recruitment assistant specializing in international talent geolocation.
Your exclusive task is to analyze a candidate's LinkedIn header info and determine if their current location is compatible with the location required for the job.

Job Location Requirement: "{normalized_required}"

Candidate LinkedIn Header Information:
\"\"\"
{header_text}
\"\"\"

Mandatory Reasoning & Location Resolution Rules:
1. Identify the country required by the job (e.g., 'United States', 'Mexico', 'Spain', etc.).
2. Resolve the candidate's current country of residence from their header info. Note that:
   - Metropolitan areas, states, and cities belong to their respective countries. E.g., "Los Angeles Metropolitan Area", "San Francisco Bay Area", "Orange County", "Texas", "California", "New York" are all in the "United States / USA".
   - "Jalisco", "Nuevo Leon", "CDMX", "Mexico City", "Guadalajara", "Monterrey" are all in "Mexico".
   - If the header info lists a city/region without a country, use your general knowledge to infer the country.
3. Compare the candidate's resolved country with the required country. Note that "United States", "USA", and "US" are the same country.
4. Set "compatible" to:
   - true: If the candidate's resolved country matches the required country (or is either Mexico or the United States if the requirement was "Mexico or United States").
   - false: If they do not match (e.g., candidate is in El Salvador, India, or Costa Rica, but the job requires 'United States / USA').

You must strictly return a valid JSON object (and absolutely NOTHING else, no comments, no explanations, no free text) in the following exact format:
{{
  "vacancy_country": "Country required by the job (e.g., 'United States')",
  "candidate_country": "Resolved candidate country of residence (e.g., 'United States' or 'Mexico')",
  "compatible": false,
  "extracted_location": "Full extracted location of the candidate (e.g., 'Los Angeles Metropolitan Area' or 'Hermosillo, Sonora, Mexico')"
}}

Respond ONLY with the JSON object.
"""
    
    try:
        response = client.generate(
            model=model_name,
            prompt=prompt,
            options={"temperature": 0.0}  # Zero temperature for maximum accuracy and determinism
        )
        response_text = response.get("response", "")
        cleaned_text = clean_json_response(response_text)
        data = json.loads(cleaned_text)
        return {
            "compatible": bool(data.get("compatible", False)),
            "extracted_location": data.get("extracted_location", "Not detected")
        }
    except Exception as e:
        print(f"[Warning] Error evaluating location with Ollama: {e}")
        # Attempt rescue
        try:
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx+1]
                data = json.loads(json_str)
                return {
                    "compatible": bool(data.get("compatible", False)),
                    "extracted_location": data.get("extracted_location", "Not detected")
                }
        except Exception:
            pass
            
        # Simple fallback
        return {
            "compatible": True,
            "extracted_location": "Error during extraction (Allowed by fallback)"
        }
