import os
import sys

# Add root directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import get_db_connection, init_db

def seed_showcase():
    init_db()
    
    # 1. Create Showcase Vacancy
    vac_title = "Senior Full-Stack AI Engineer (Python / LLM / React)"
    vac_desc = """Job Description:
We are looking for a Senior Full-Stack AI Engineer to build next-generation autonomous agent platforms.

Responsibilities:
- Architect and deploy local LLM inference pipelines (Ollama, vLLM, LangChain) with sub-second response times.
- Build high-performance backend microservices using Python (FastAPI / Flask) and PostgreSQL / SQLite.
- Develop interactive, real-time reactive user interfaces in modern JavaScript/React.
- Design Chain-of-Thought (CoT) multi-criteria decision frameworks and automated RAG/retrieval systems.

Requirements:
- 5+ years of professional backend software engineering experience with Python.
- Proven track record integrating Large Language Models (LLMs), prompt orchestration, and autonomous agents.
- Strong full-stack web development skills (REST APIs, WebSockets/SSE, modern JS).
- Location: Mexico / LATAM (Remote). Fluent in English."""
    
    vac_location = "Mexico"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO vacancies (title, description, target_country, status, is_starred, created_at, updated_at, last_opened_at)
            VALUES (?, ?, ?, 'active', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (vac_title, vac_desc, vac_location))
        vac_id = cursor.lastrowid
        
        # 2. Showcase Candidates
        candidates = [
            {
                "name": "Sofia Alarcón",
                "headline": "Senior AI & Full-Stack Architect • 7+ yrs Python/FastAPI, Local LLMs (Ollama) & React",
                "url": "https://www.linkedin.com/in/sofia-alarcon-ai-engineer",
                "location": "Mexico City, Mexico",
                "score": 96,
                "technical_score": 98,
                "experience_score": 95,
                "auxiliary_score": 95,
                "status": "new",
                "location_compatible": 1,
                "summary": "Outstanding fit: 7 years Python backend expertise, deep production experience with local LLM pipelines (Ollama/vLLM) and full-stack React. Based in Mexico City.",
                "skills": "Python, FastAPI, Ollama, LangChain, React, PostgreSQL, Docker, CoT Reasoning",
                "message": """Hi Sofia,

I came across your profile and was thoroughly impressed by your work architecting local LLM agent workflows and FastAPI microservices. 

We are currently scaling our Autonomous AI Platforms engineering team and looking for a Senior Full-Stack AI Engineer based in Mexico. Given your 7+ years of expertise in Python distributed systems and agent orchestration, your background aligns exceptionally well with what we are building.

Would you be open to a brief 15-minute sync this week to explore this opportunity?

Best regards,
Christian Rincón"""
            },
            {
                "name": "Mateo Hernández",
                "headline": "Lead Python & MLOps Engineer • Specializing in distributed backend systems & LangChain",
                "url": "https://www.linkedin.com/in/mateo-hernandez-dev",
                "location": "Guadalajara, Mexico",
                "score": 92,
                "technical_score": 94,
                "experience_score": 90,
                "auxiliary_score": 92,
                "status": "contacted",
                "location_compatible": 1,
                "summary": "Strong match: 6+ years in Python distributed architectures, excellent MLOps & LLM integration experience, located in Guadalajara (Mexico).",
                "skills": "Python, Flask, PyTorch, Docker, Kubernetes, Redis, LLM Fine-Tuning",
                "message": """Hi Mateo,

I was impressed by your extensive experience in distributed Python architectures and real-time streaming systems. We are building an enterprise AI platform and think your background would be a great fit. Let's connect!"""
            },
            {
                "name": "Elena Rostova",
                "headline": "Senior Software Engineer • AI Systems & Backend Infrastructure • Python, FastAPI, TypeScript",
                "url": "https://www.linkedin.com/in/elena-rostova-tech",
                "location": "Monterrey, Mexico (Remote)",
                "score": 88,
                "technical_score": 90,
                "experience_score": 85,
                "auxiliary_score": 88,
                "status": "interviewing",
                "location_compatible": 1,
                "summary": "High alignment: 5+ years building scalable backend APIs and AI copilot features. Located in Monterrey, Mexico.",
                "skills": "Python, FastAPI, TypeScript, React, SQLite, Prompt Engineering, SSE",
                "message": """Hi Elena, loved your background with AI copilot systems and FastAPI. Would love to share more details about our Senior Full-Stack AI role."""
            },
            {
                "name": "Lucas Silva",
                "headline": "Staff Software Engineer • Distributed Systems, Agentic Workflows & Cloud Architecture",
                "url": "https://www.linkedin.com/in/lucas-silva-staff",
                "location": "LATAM Remote (Bogota, Colombia)",
                "score": 85,
                "technical_score": 88,
                "experience_score": 82,
                "auxiliary_score": 85,
                "status": "hired",
                "location_compatible": 1,
                "summary": "Solid fit: Strong senior engineering background with autonomous agents, scalable cloud services, and LATAM remote availability.",
                "skills": "Python, Go, AWS, LangChain, Microservices, Event-Driven Architecture",
                "message": """Hi Lucas, your experience with agentic workflows and distributed systems stands out. Let's chat about our opening."""
            },
            {
                "name": "Carlos Pujol",
                "headline": "Frontend Specialist & React Developer at Digital Studio",
                "url": "https://www.linkedin.com/in/carlos-pujol-frontend",
                "location": "Barcelona, Spain",
                "score": 42,
                "technical_score": 50,
                "experience_score": 40,
                "auxiliary_score": 35,
                "status": "discarded",
                "location_compatible": 0,
                "summary": "Location Mismatch & Skill Gap: Candidate is located in Barcelona, Spain (Vacancy strictly requires Mexico/LATAM). Primary focus is pure UI with limited Python/LLM backend.",
                "skills": "React, CSS, JavaScript, Webpack, Figma",
                "message": ""
            },
            {
                "name": "David Chen",
                "headline": "Junior Data Analyst & Python Enthusiast • 1 year experience in reporting",
                "url": "https://www.linkedin.com/in/david-chen-analytics",
                "location": "Mexico City, Mexico",
                "score": 38,
                "technical_score": 35,
                "experience_score": 40,
                "auxiliary_score": 40,
                "status": "discarded",
                "location_compatible": 1,
                "summary": "Experience Level Gap: Role requires 5+ years of senior full-stack and LLM architecture. Candidate currently has 1 year of junior analyst experience.",
                "skills": "Python (Pandas), Excel, SQL, Tableau",
                "message": ""
            }
        ]

        for c in candidates:
            cursor.execute("""
                INSERT OR REPLACE INTO candidates (
                    vacancy_id, vacancy, name, headline, linkedin_url, location, score,
                    technical_score, experience_score, auxiliary_score, status,
                    location_compatible, evaluation_summary, suggested_message, skills,
                    timestamp, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (
                vac_id, vac_title, c["name"], c["headline"], c["url"], c["location"],
                c["score"], c["technical_score"], c["experience_score"], c["auxiliary_score"],
                c["status"], c["location_compatible"], c["summary"], c["message"], c["skills"]
            ))
            
        conn.commit()

    print(f"Successfully seeded showcase vacancy ID: {vac_id}")
    return vac_id

if __name__ == "__main__":
    vac_id = seed_showcase()
    print(f"SHOWCASE_VACANCY_ID={vac_id}")
