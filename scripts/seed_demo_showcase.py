import os
import sys

# Add root directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import get_db_connection, init_db

def seed_complete_showcase():
    init_db()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Clean previous data to ensure 0 confidential data remains
        cursor.execute("DELETE FROM candidates")
        cursor.execute("DELETE FROM vacancies")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('vacancies', 'candidates')")
        
        # 2. Seed 6 Rich, Modern Tech Vacancies
        vacancies = [
            {
                "title": "Senior Full-Stack AI Engineer (Python / LLM / React)",
                "target_country": "Mexico",
                "is_starred": 1,
                "status": "active",
                "description": """Job Description:
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
            },
            {
                "title": "Lead Cloud Infrastructure Architect (AWS / Kubernetes)",
                "target_country": "United States",
                "is_starred": 1,
                "status": "active",
                "description": """Job Description:
Seeking a Lead Cloud Infrastructure Architect to scale high-availability multi-region cloud systems.

Responsibilities:
- Design terraform IaC pipelines, Kubernetes clusters (EKS), and zero-trust service mesh networking.
- Optimize cloud expenditures and implement automated auto-scaling for high-throughput microservices.
- Ensure 99.99% system availability with automated failover and distributed monitoring (Prometheus / Grafana)."""
            },
            {
                "title": "Staff Data Platform Engineer (Spark / Kafka / Python)",
                "target_country": "Remote - Americas",
                "is_starred": 1,
                "status": "active",
                "description": """Job Description:
Looking for a Staff Data Platform Engineer to lead real-time streaming architectures.

Responsibilities:
- Build low-latency event-driven data streaming pipelines processing billions of daily events with Kafka and Apache Spark.
- Design declarative data contracts and columnar lakehouse schemas (Iceberg / Delta Lake)."""
            },
            {
                "title": "Principal Mobile Engineer (Android / Kotlin / Compose)",
                "target_country": "Mexico",
                "is_starred": 1,
                "status": "active",
                "description": """Job Description:
Join our mobile core team to lead the next evolution of our flagship Android application.

Responsibilities:
- Architect modern reactive Android apps with Kotlin Coroutines, Flow, Jetpack Compose, and Clean Architecture.
- Integrate on-device local machine learning models for offline image intelligence and low-latency processing."""
            },
            {
                "title": "Senior Site Reliability Engineer - Core Infrastructure",
                "target_country": "Global / Remote",
                "is_starred": 0,
                "status": "active",
                "description": """Job Description:
Lead reliability engineering for distributed edge platforms, CI/CD automation, and disaster recovery orchestration."""
            },
            {
                "title": "Machine Learning Research Engineer - NLP & Agents",
                "target_country": "United States",
                "is_starred": 0,
                "status": "active",
                "description": """Job Description:
Conduct applied research in LLM fine-tuning, synthetic data generation, and autonomous reasoning agents."""
            }
        ]

        vac_ids = {}
        for v in vacancies:
            cursor.execute("""
                INSERT INTO vacancies (title, description, target_country, status, is_starred, created_at, updated_at, last_opened_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (v["title"], v["description"], v["target_country"], v["status"], v["is_starred"]))
            vac_ids[v["title"]] = cursor.lastrowid

        main_vac_id = vac_ids["Senior Full-Stack AI Engineer (Python / LLM / React)"]
        main_vac_title = "Senior Full-Stack AI Engineer (Python / LLM / React)"

        # 3. Candidates for Main Showcase Vacancy (Distribution: 4 New, 2 Contacted, 1 Interviewing, 1 Hired + 3 Discarded)
        main_candidates = [
            # 4 TO CONTACT (new)
            {
                "name": "Sofia Alarcón",
                "headline": "Senior AI & Full-Stack Architect • 7+ yrs Python/FastAPI, Local LLMs (Ollama) & React",
                "url": "https://www.linkedin.com/in/sofia-alarcon-ai-engineer",
                "location": "Mexico City, Mexico",
                "score": 96,
                "technical_score": 38,
                "experience_score": 39,
                "auxiliary_score": 19,
                "status": "new",
                "location_compatible": 1,
                "open_to_work": 1,
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
                "name": "Gabriel Valenzuela",
                "headline": "Senior Full-Stack AI Engineer • Python, FastAPI, React & Agent Orchestration",
                "url": "https://www.linkedin.com/in/gabriel-valenzuela-dev",
                "location": "Guadalajara, Mexico",
                "score": 91,
                "technical_score": 36,
                "experience_score": 37,
                "auxiliary_score": 18,
                "status": "new",
                "location_compatible": 1,
                "open_to_work": 1,
                "summary": "Exceptional candidate: 6+ years building Python microservices, LLM application frameworks, and responsive React web interfaces.",
                "skills": "Python, FastAPI, React, TypeScript, Docker, LangChain, Redis",
                "message": "Hi Gabriel, your experience building Python AI agent platforms and React web apps caught our attention. Let's connect!"
            },
            {
                "name": "Mariana Costa",
                "headline": "Senior Backend & AI Systems Developer • Python, PostgreSQL, LangChain",
                "url": "https://www.linkedin.com/in/mariana-costa-ai",
                "location": "Monterrey, Mexico",
                "score": 87,
                "technical_score": 35,
                "experience_score": 34,
                "auxiliary_score": 18,
                "status": "new",
                "location_compatible": 1,
                "open_to_work": 0,
                "summary": "Solid technical background: 5+ years of distributed backend systems, vector search pipelines, and PostgreSQL database optimization.",
                "skills": "Python, Flask, PostgreSQL, Docker, Vector DBs, LangChain",
                "message": "Hi Mariana, loved your background with AI search pipelines and backend systems. We'd love to chat about our opening."
            },
            {
                "name": "Rodrigo Navarro",
                "headline": "Lead Backend Engineer • Distributed Python Architectures & REST APIs",
                "url": "https://www.linkedin.com/in/rodrigo-navarro-tech",
                "location": "Puebla, Mexico",
                "score": 85,
                "technical_score": 34,
                "experience_score": 35,
                "auxiliary_score": 16,
                "status": "new",
                "location_compatible": 1,
                "open_to_work": 1,
                "summary": "Strong engineering profile: 6 years in scalable Python services, asynchronous task processing, and cloud-native deployment.",
                "skills": "Python, FastAPI, Celery, Redis, Kubernetes, AWS",
                "message": "Hi Rodrigo, your experience with scalable Python architectures is a great match for our engineering team."
            },

            # 2 CONTACTED (contacted)
            {
                "name": "Mateo Hernández",
                "headline": "Lead Python & MLOps Engineer • Specializing in distributed backend systems & LangChain",
                "url": "https://www.linkedin.com/in/mateo-hernandez-dev",
                "location": "Guadalajara, Mexico",
                "score": 94,
                "technical_score": 38,
                "experience_score": 37,
                "auxiliary_score": 19,
                "status": "contacted",
                "location_compatible": 1,
                "open_to_work": 1,
                "summary": "Strong match: 6+ years in Python distributed architectures, excellent MLOps & LLM integration experience, located in Guadalajara (Mexico).",
                "skills": "Python, Flask, PyTorch, Docker, Kubernetes, Redis, LLM Fine-Tuning",
                "message": "Hi Mateo, I was impressed by your extensive experience in distributed Python architectures and real-time streaming systems. Let's connect!"
            },
            {
                "name": "Camila Morales",
                "headline": "Senior Distributed Systems & AI Engineer • Python, Docker, Cloud Platforms",
                "url": "https://www.linkedin.com/in/camila-morales-systems",
                "location": "Mexico City, Mexico",
                "score": 89,
                "technical_score": 36,
                "experience_score": 35,
                "auxiliary_score": 18,
                "status": "contacted",
                "location_compatible": 1,
                "open_to_work": 1,
                "summary": "High alignment: 5+ years building resilient microservices and deploying local LLM inference engines in production environments.",
                "skills": "Python, FastAPI, Docker, Ollama, React, GCP",
                "message": "Hi Camila, your background with local LLM deployments and cloud infrastructure is fantastic. Let's discuss our Senior AI opening!"
            },

            # 1 IN DISCUSSION (interviewing)
            {
                "name": "Elena Rostova",
                "headline": "Senior Software Engineer • AI Systems & Backend Infrastructure • Python, FastAPI, TypeScript",
                "url": "https://www.linkedin.com/in/elena-rostova-tech",
                "location": "Monterrey, Mexico (Remote)",
                "score": 92,
                "technical_score": 37,
                "experience_score": 36,
                "auxiliary_score": 19,
                "status": "interviewing",
                "location_compatible": 1,
                "open_to_work": 1,
                "summary": "High alignment: 5+ years building scalable backend APIs, reactive web frontends, and AI copilot features. Located in Monterrey, Mexico.",
                "skills": "Python, FastAPI, TypeScript, React, SQLite, Prompt Engineering, SSE",
                "message": "Hi Elena, loved your background with AI copilot systems and FastAPI. Would love to share more details about our Senior Full-Stack AI role."
            },

            # 1 HIRED / TOP MATCH (hired)
            {
                "name": "Lucas Silva",
                "headline": "Staff AI Systems Engineer • Distributed Architectures, Agentic Workflows & Cloud Scale",
                "url": "https://www.linkedin.com/in/lucas-silva-staff",
                "location": "LATAM Remote (Mexico / Colombia)",
                "score": 98,
                "technical_score": 40,
                "experience_score": 39,
                "auxiliary_score": 19,
                "status": "hired",
                "location_compatible": 1,
                "open_to_work": 1,
                "summary": "Top Candidate / Perfect Alignment: 8+ years leading distributed systems, autonomous multi-agent pipelines, and enterprise-scale Python architectures. Successfully placed into team.",
                "skills": "Python, Go, LangChain, Ollama, EKS, React, Event-Driven Architecture, CoT Reasoning",
                "message": "Hi Lucas, your stellar track record with autonomous agents and distributed systems made you an ideal fit for our Staff AI role. Welcome aboard!"
            },

            # 3 UNSUITABLE / DISCARDED (discarded)
            {
                "name": "Carlos Pujol",
                "headline": "Frontend Specialist & React Developer at Digital Studio",
                "url": "https://www.linkedin.com/in/carlos-pujol-frontend",
                "location": "Barcelona, Spain",
                "score": 42,
                "technical_score": 20,
                "experience_score": 15,
                "auxiliary_score": 7,
                "status": "discarded",
                "location_compatible": 0,
                "open_to_work": 1,
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
                "technical_score": 15,
                "experience_score": 15,
                "auxiliary_score": 8,
                "status": "discarded",
                "location_compatible": 1,
                "open_to_work": 1,
                "summary": "Experience Level Gap: Role requires 5+ years of senior full-stack and LLM architecture. Candidate currently has 1 year of junior analyst experience.",
                "skills": "Python (Pandas), Excel, SQL, Tableau",
                "message": ""
            },
            {
                "name": "Alexandre Dubois",
                "headline": "PHP & WordPress Developer • Web Agency Specialist",
                "url": "https://www.linkedin.com/in/alexandre-dubois-web",
                "location": "Paris, France",
                "score": 30,
                "technical_score": 12,
                "experience_score": 12,
                "auxiliary_score": 6,
                "status": "discarded",
                "location_compatible": 0,
                "open_to_work": 0,
                "summary": "Tech Stack & Location Mismatch: Candidate located in France; primary stack is legacy PHP/CMS with no Python or AI systems experience.",
                "skills": "PHP, WordPress, MySQL, HTML5",
                "message": ""
            }
        ]

        for c in main_candidates:
            cursor.execute("""
                INSERT INTO candidates (
                    vacancy_id, vacancy, name, headline, linkedin_url, location, score,
                    technical_score, experience_score, auxiliary_score, status, open_to_work,
                    location_compatible, evaluation_summary, suggested_message, skills,
                    timestamp, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (
                main_vac_id, main_vac_title, c["name"], c["headline"], c["url"], c["location"],
                c["score"], c["technical_score"], c["experience_score"], c["auxiliary_score"],
                c["status"], c.get("open_to_work", 1), c["location_compatible"], c["summary"],
                c["message"], c["skills"]
            ))

        # 4. Seed realistic candidate counts for other vacancies
        other_vac_data = [
            ("Lead Cloud Infrastructure Architect (AWS / Kubernetes)", [
                ("Daniel Wright", "Principal Cloud Architect • AWS, Terraform, EKS", 95, "new", "USA", 1),
                ("Sarah Jenkins", "Staff SRE & Kubernetes Lead", 91, "contacted", "USA", 1),
                ("Michael Chang", "Senior DevOps Engineer • CI/CD & Cloud", 88, "interviewing", "USA", 1),
                ("Jessica Miller", "Cloud Systems Engineer", 84, "new", "USA", 1),
                ("Tomás Alvarez", "DevOps Specialist", 48, "discarded", "Spain", 0),
            ]),
            ("Staff Data Platform Engineer (Spark / Kafka / Python)", [
                ("Andrés Morales", "Staff Data Architect • Kafka, Spark, Flink", 96, "interviewing", "Remote - LATAM", 1),
                ("Juliana Restrepo", "Senior Data Engineer • Streaming Pipelines", 92, "contacted", "Colombia", 1),
                ("Felipe Santos", "Big Data Engineer • PySpark & Delta Lake", 86, "new", "Brazil", 1),
                ("Diego Vera", "Data Platform Specialist", 82, "new", "Mexico", 1),
                ("Jean Paul", "Junior SQL Reporter", 35, "discarded", "France", 0),
            ]),
            ("Principal Mobile Engineer (Android / Kotlin / Compose)", [
                ("Fernando Gomez", "Principal Android Engineer • Kotlin, Compose, Architecture", 97, "hired", "Mexico", 1),
                ("Valeria Rios", "Lead Mobile Developer • Android SDK & Jetpack", 93, "interviewing", "Mexico", 1),
                ("Alejandro Cruz", "Senior Android Developer • Clean Arch", 89, "contacted", "Mexico", 1),
                ("Renata Lima", "Android Engineer • Kotlin Coroutines", 86, "new", "Mexico", 1),
                ("Markus Schmidt", "iOS Swift Specialist", 40, "discarded", "Germany", 0),
            ]),
            ("Senior Site Reliability Engineer - Core Infrastructure", [
                ("Arturo Mendoza", "Senior SRE • Observability & Kubernetes", 92, "contacted", "Mexico", 1),
                ("Beatriz Silva", "Infrastructure & Reliability Engineer", 88, "new", "Chile", 1),
                ("Carlos Ruiz", "Systems Administrator", 52, "discarded", "Argentina", 1),
            ]),
            ("Machine Learning Research Engineer - NLP & Agents", [
                ("Dr. Liam Vance", "Research Scientist • LLMs, RLHF & Reasoning", 95, "contacted", "USA", 1),
                ("Emily Zhang", "Applied AI Engineer • Prompt Orchestration", 89, "new", "USA", 1),
                ("Lucas Becker", "Junior Python Developer", 45, "discarded", "Germany", 0),
            ])
        ]

        for title, c_list in other_vac_data:
            vac_id = vac_ids.get(title)
            if not vac_id:
                continue
            for name, headline, score, status, loc, loc_comp in c_list:
                cursor.execute("""
                    INSERT INTO candidates (
                        vacancy_id, vacancy, name, headline, linkedin_url, location, score,
                        technical_score, experience_score, auxiliary_score, status, open_to_work,
                        location_compatible, evaluation_summary, suggested_message, skills,
                        timestamp, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 'Tech Stack', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    vac_id, title, name, headline, f"https://www.linkedin.com/in/{name.lower().replace(' ', '-')}", loc,
                    score, int(score * 0.4), int(score * 0.4), int(score * 0.2),
                    status, loc_comp, f"Candidate evaluation for {title}: {score}% score match.",
                    f"Hi {name.split()[0]}, we are reaching out regarding the {title} role."
                ))

        conn.commit()

    print("Successfully seeded all 6 showcase vacancies and rich candidate distribution!")
    return main_vac_id

if __name__ == "__main__":
    main_id = seed_complete_showcase()
    print(f"MAIN_VACANCY_ID={main_id}")
