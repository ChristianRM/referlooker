import os
import json
import ollama

def clean_json_response(text: str) -> str:
    """
    Cleans the LLM response text to extract only the JSON block,
    removing any markdown delimiters (```json ... ```) or conversational preambles.
    """
    text = text.strip()
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end != -1:
            text = text[start:end]
        else:
            text = text[start:]
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end != -1:
            text = text[start:end]
        else:
            text = text[start:]

    text = text.strip()
    start_brace = text.find("{")
    end_brace = text.rfind("}")
    if start_brace != -1 and end_brace != -1 and end_brace >= start_brace:
        return text[start_brace:end_brace + 1].strip()
    return text

QUERY_RULES = """
Rules for building the "search_query":
1. ALWAYS start the query directly with `site:linkedin.com/in/`. NEVER use country subdomains like `mx.linkedin.com/in/` or `es.linkedin.com/in/`.
   - If a specific country is required (e.g. Mexico, United States, Spain), append the country filter at the end of the query:
     - For Mexico: `AND ("Mexico" OR "México")`
     - For Spain: `AND ("Spain" OR "España")`
     - For United States: `AND ("United States" OR "USA")`
     - For other countries: `AND "CountryName"`
2. Wrap ALL multi-word phrases and role titles in double quotes.
3. Target all qualified talent: Focus the core search on role titles and key technologies. You can include common active phrases as optional OR terms only if broad search is needed, but do not make OpenToWork terms mandatory in every query so that both active and top passive candidates are discovered.
4. Determine appropriate role titles based on required seniority and tech stack:
   - Group role title variations together with OR (e.g. `("Senior Full Stack Engineer" OR "Senior Software Engineer" OR "Senior Full Stack Developer")`).
   - Do not create conflicting AND clauses for seniority titles.
   - Never use internal company codes (e.g., IRC292142, Gtech) or overly specific internal tags.
5. Extract only 1 or 2 essential core technologies from the JD (e.g., `("Java" OR "Kotlin")`).
6. Keep the query clean and concise with boolean OR groups to allow Google to return relevant profiles.
7. Standard query structure pattern:
   `site:linkedin.com/in/ ("Senior Full Stack Engineer" OR "Senior Software Engineer" OR "Senior Full Stack Developer") AND ("Java" OR "Kotlin") AND ("Mexico" OR "México")`
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
1. Start directly with `site:linkedin.com/in/`.
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

def chat_refine_search_query(
    history: list,
    vacancy_text: str,
    current_query: str = "",
    target_country: str = "Any",
    config: dict = None
) -> dict:
    """
    Interactive conversation handler between the Recruiter and the AI Copilot.
    Receives chat history and returns a response in English with an updated Google X-Ray query.
    """
    if config is None:
        config = {}
    model_name = config.get("ollama", {}).get("model", "llama3.1:8b")
    ollama_host = config.get("ollama", {}).get("host", "http://localhost:11434")
    client = ollama.Client(host=ollama_host)
    
    # Format chat history for context
    conversation_formatted = ""
    for msg in history:
        role = "Recruiter" if msg.get("role") in ("user", "human") else "AI Copilot"
        content = msg.get("content", "").strip()
        conversation_formatted += f"{role}: {content}\n"
        
    prompt = f"""You are an elite Technical Sourcing Copilot and boolean search expert.
You are collaborating live with a technical recruiter to craft and fine-tune the ultimate Google X-Ray search query for LinkedIn profiles.

CONTEXT & JOB REQUISITION:
\"\"\"
{vacancy_text[:2500]}
\"\"\"

TARGET COUNTRY/REGION: {target_country or 'Any'}
CURRENT SEARCH QUERY: "{current_query or 'None'}"

CONVERSATION HISTORY:
{conversation_formatted}

INSTRUCTIONS:
1. Act as a friendly, expert sourcing specialist.
2. In your reply (in English), explain clearly and concisely what adjustments you made to the boolean query and why. You can ask a brief clarifying question or offer a helpful sourcing tip if useful.
3. Formulate the optimal, updated Google X-Ray search string according to the recruiter's feedback.
4. Return ONLY a valid JSON object with this exact structure (NO extra markdown, NO other text):
{{
  "reply": "Explanation for the recruiter about the adjustments made and rationale...",
  "search_query": "site:linkedin.com/in/ ...",
  "target_country": "Country detected or requested (e.g. Mexico, Colombia, USA, Any)",
  "tips": ["Short tip 1", "Short tip 2"]
}}

{QUERY_RULES}
"""

    response_text = ""
    try:
        response = client.generate(
            model=model_name,
            prompt=prompt,
            options={"temperature": 0.3}
        )
        response_text = response.get("response", "")
        cleaned = clean_json_response(response_text)
        data = json.loads(cleaned)
        
        # Ensure fallback defaults if fields missing
        if "reply" not in data:
            data["reply"] = "I have updated the search query according to your instructions."
        if "search_query" not in data or not data["search_query"]:
            data["search_query"] = current_query or 'site:linkedin.com/in/ ("open to work" OR "opentowork")'
        if "tips" not in data:
            data["tips"] = []
            
        return data
    except Exception as e:
        print(f"[Warning] Error in chat_refine_search_query with Ollama: {e}")
        try:
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx+1]
                data = json.loads(json_str)
                return data
        except Exception:
            pass
            
        # Resilient fallback response
        return {
            "reply": "I have analyzed your requirements and adjusted the search query accordingly.",
            "search_query": current_query or 'site:linkedin.com/in/ ("open to work" OR "opentowork")',
            "target_country": target_country,
            "tips": ["You can ask me to adjust seniority, technologies, or location at any time."]
        }

def diagnose_sourcing_issues(vacancy_text: str, current_query: str, target_country: str, discarded_samples: list, config: dict) -> dict:
    """
    Analyzes discarded profiles and current search query during an active sourcing run,
    diagnoses why candidates are being rejected (e.g. location mismatch, title drift, scrape error),
    and suggests an optimized revised query with actionable advice.
    """
    model_name = config.get("ollama", {}).get("model", "llama3.1:8b")
    ollama_host = config.get("ollama", {}).get("host", "http://localhost:11434")
    client = ollama.Client(host=ollama_host)
    
    # Format discarded samples
    discards_text = ""
    for idx, d in enumerate(discarded_samples[:10]):
        name = d.get("name", "Unknown")
        loc = d.get("location", "Unknown")
        reason = d.get("reason", "Unknown")
        dtype = d.get("type", "discarded")
        discards_text += f"{idx+1}. Candidate: '{name}' | Location: '{loc}' | Issue: {reason} (Type: {dtype})\n"
        
    if not discards_text:
        discards_text = "No discarded candidate profiles recorded yet."

    prompt = f"""You are an elite Technical Sourcing Copilot and boolean search expert.
The recruiter paused an active candidate sourcing search because several profiles were discarded or not matching expectations.

JOB REQUISITION DETAILS:
\"\"\"
{vacancy_text[:2000]}
\"\"\"

TARGET COUNTRY/REGION: {target_country or 'Any'}
ACTIVE SEARCH QUERY: "{current_query}"

RECENT DISCARDED PROFILES IN THIS RUN:
{discards_text}

TASK:
1. Diagnose why profiles were rejected (e.g., location mismatch, wrong seniority, unrelated tech stack, missing boolean operators).
2. Write a clear, friendly, and helpful diagnostic message (in English) for the recruiter explaining what happened and how to improve the search.
3. Generate an improved Google X-Ray search query that fixes these issues (e.g. adding strict location filters, adjusting role titles, or removing restrictive terms).
4. Provide 2-3 specific tips.

Return ONLY a valid JSON object with this exact structure (NO other text, NO markdown codeblock wrapper):
{{
  "reply": "Diagnostic analysis and proposed fix...",
  "search_query": "site:linkedin.com/in/ ...",
  "target_country": "{target_country or 'Any'}",
  "tips": ["Tip 1", "Tip 2"]
}}

{QUERY_RULES}
"""

    response_text = ""
    try:
        response = client.generate(
            model=model_name,
            prompt=prompt,
            options={"temperature": 0.2}
        )
        response_text = response.get("response", "")
        cleaned = clean_json_response(response_text)
        data = json.loads(cleaned)
        
        if "reply" not in data:
            data["reply"] = "I analyzed the discarded candidates and updated the query to better match the target criteria."
        if "search_query" not in data or not data["search_query"]:
            data["search_query"] = current_query
        if "tips" not in data:
            data["tips"] = []
            
        return data
    except Exception as e:
        print(f"[Warning] Error in diagnose_sourcing_issues with Ollama: {e}")
        try:
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx+1]
                data = json.loads(json_str)
                return data
        except Exception:
            pass
            
        # Resilient fallback diagnostic response
        loc_clause = f' AND ("{target_country}")' if target_country and target_country not in ("Any", "Remote", "") else ""
        return {
            "reply": f"I reviewed the discarded candidates. To reduce mismatches, I recommend refining the location constraints and tightening role titles in the search query.",
            "search_query": current_query + loc_clause if loc_clause and loc_clause not in current_query else current_query,
            "target_country": target_country,
            "tips": ["Add specific country/region names to the query", "Check if candidates have Open to Work status"]
        }

