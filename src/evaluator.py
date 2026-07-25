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
    to calculate a match score, check open-to-work status, and write a summary.
    """
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
    
    # If structured sections are extracted, prioritize them; otherwise, use raw body text
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
Your goal is to evaluate a candidate's LinkedIn profile against the requirements of the job description.

Job Description:
\"\"\"
{vacancy_text}
\"\"\"

Candidate Profile (Extracted from LinkedIn):
\"\"\"
{profile_summary}
\"\"\"

You must strictly return a valid JSON object (and NOTHING else) in the following exact format:
{{
  "match_score": 85,
  "open_to_work": true,
  "evaluation_summary": "A brief and descriptive paragraph (2-3 sentences) in English about the candidate's strengths for this position, whether they meet the required experience and technologies, and any important gaps detected."
}}

Evaluation Rules:
1. "match_score" must be an integer from 0 to 100. Be objective. If they do not meet essential technologies or the required experience level, lower the score accordingly.
2. "open_to_work" must be a boolean (true/false) indicating if there is evidence that the candidate is actively seeking opportunities (mention of 'open to work', 'seeking roles', 'open to opportunities', 'disponible', 'looking for', etc. in their headline or profile sections).
3. "evaluation_summary" must be written in English.
4. GEOGRAPHIC LOCATION FILTER (COUNTRY): Check if the job description specifies a mandatory work country or region (e.g., Mexico or United States). If so, identify the candidate's country in their LinkedIn profile. If the candidate is physically in a different country than required by the vacancy, you must strictly score their "match_score" as 0, and write in the "evaluation_summary" the justification indicating they were discarded due to location mismatch (e.g., job requires Mexico but candidate is in India).

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
            "match_score": int(data.get("match_score", 0)),
            "open_to_work": bool(data.get("open_to_work", False)),
            "evaluation_summary": data.get("evaluation_summary", "Evaluation completed successfully.")
        }
    except Exception as e:
        print(f"[Warning] Error evaluating candidate with Ollama: {e}")
        # Attempt rescue if JSON is wrapped in free text
        try:
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx+1]
                data = json.loads(json_str)
                return {
                    "match_score": int(data.get("match_score", 0)),
                    "open_to_work": bool(data.get("open_to_work", False)),
                    "evaluation_summary": data.get("evaluation_summary", "Evaluation recovered from response text.")
                }
        except Exception:
            pass
            
        return {
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
    
    prompt = f"""
You are an expert technical recruitment assistant specializing in international talent geolocation.
Your exclusive task is to analyze a candidate's LinkedIn header info and determine if their current location is compatible with the location required for the job.

Job Location Requirement: "{required}"

Candidate LinkedIn Header Information:
\"\"\"
{header_text}
\"\"\"

Mandatory Reasoning Process:
1. Identify the country required by the job (e.g., 'United States', 'Mexico', 'Spain', etc.). If the Job Location Requirement is "Mexico or United States", the permitted countries are Mexico or the United States.
2. Identify the candidate's current country of residence from their header info (e.g., 'Mexico', 'Spain', 'Nigeria', 'India', etc.).
3. Check if the candidate's country matches the required country (or is either Mexico or the United States in the default rule case).
4. If the countries do not match (e.g., candidate is in Mexico or Spain but the job requires 'United States'), the value of "compatible" MUST strictly be false.

You must strictly return a valid JSON object (and absolutely NOTHING else, no comments, no explanations, no free text) in the following exact format:
{{
  "vacancy_country": "Country required by the job (e.g., 'United States')",
  "candidate_country": "Candidate country of residence (e.g., 'Mexico' or 'Spain')",
  "compatible": false,
  "extracted_location": "Full extracted location of the candidate (e.g., 'Lagos, Nigeria' or 'Hermosillo, Sonora, Mexico')"
}}

Replace "compatible" with true if they are in the same country/region, or false if they are in different countries.
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
