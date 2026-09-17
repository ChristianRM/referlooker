import os
import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

DB_PATH = os.path.join("output", "referlooker.db")

def get_db_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Returns a connection to the SQLite database with Row row_factory."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db(db_path: str = DB_PATH):
    """Creates or updates the database schema."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Check existing vacancies table schema
        cursor.execute("PRAGMA table_info(vacancies)")
        v_cols = {row["name"]: row for row in cursor.fetchall()}
        
        if v_cols and "id" not in v_cols:
            # Old schema detected (filename PRIMARY KEY), migrate to new schema with id INTEGER PRIMARY KEY
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vacancies_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    target_country TEXT DEFAULT 'Any',
                    status TEXT DEFAULT 'active',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            desc_col = "description" if "description" in v_cols else ("content" if "content" in v_cols else "''")
            title_col = "title" if "title" in v_cols else "filename"
            status_expr = "CASE WHEN archived = 1 THEN 'archived' ELSE 'active' END" if "archived" in v_cols else "'active'"
            
            cursor.execute(f"""
                INSERT INTO vacancies_new (title, description, status, created_at)
                SELECT 
                    COALESCE({title_col}, filename), 
                    COALESCE({desc_col}, ''), 
                    {status_expr},
                    CURRENT_TIMESTAMP
                FROM vacancies
            """)
            cursor.execute("DROP TABLE vacancies")
            cursor.execute("ALTER TABLE vacancies_new RENAME TO vacancies")
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vacancies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    target_country TEXT DEFAULT 'Any',
                    status TEXT DEFAULT 'active', -- 'active', 'archived', 'closed'
                    is_starred BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_opened_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

        # Check and migrate columns if missing
        cursor.execute("PRAGMA table_info(vacancies)")
        current_v_cols = [row["name"] for row in cursor.fetchall()]
        if "last_opened_at" not in current_v_cols:
            try:
                cursor.execute("ALTER TABLE vacancies ADD COLUMN last_opened_at DATETIME")
                cursor.execute("UPDATE vacancies SET last_opened_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)")
            except Exception:
                pass
        if "is_starred" not in current_v_cols:
            try:
                cursor.execute("ALTER TABLE vacancies ADD COLUMN is_starred BOOLEAN DEFAULT 0")
            except Exception:
                pass

        # 2. Candidates table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vacancy_id INTEGER,
                vacancy TEXT NOT NULL,
                name TEXT NOT NULL,
                headline TEXT,
                linkedin_url TEXT UNIQUE NOT NULL,
                location TEXT,
                open_to_work BOOLEAN DEFAULT 0,
                location_compatible BOOLEAN DEFAULT 1,
                score INTEGER DEFAULT 0,
                technical_score INTEGER DEFAULT 0,
                experience_score INTEGER DEFAULT 0,
                auxiliary_score INTEGER DEFAULT 0,
                evaluation_summary TEXT,
                suggested_message TEXT,
                status TEXT DEFAULT 'new', -- 'new', 'contacted', 'interviewing', 'discarded', 'hired', 'location_mismatch'
                notes TEXT DEFAULT '',
                about TEXT,
                experience TEXT,
                skills TEXT,
                timestamp TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (vacancy_id) REFERENCES vacancies(id) ON DELETE SET NULL
            )
        """)
        
        # Schema migration check: ensure vacancy_id and location_compatible exist
        cursor.execute("PRAGMA table_info(candidates)")
        c_columns = [row["name"] for row in cursor.fetchall()]
        if "vacancy_id" not in c_columns:
            try:
                cursor.execute("ALTER TABLE candidates ADD COLUMN vacancy_id INTEGER")
            except Exception:
                pass
        if "location_compatible" not in c_columns:
            try:
                cursor.execute("ALTER TABLE candidates ADD COLUMN location_compatible BOOLEAN DEFAULT 1")
            except Exception:
                pass
        
        # Indexes for fast search and filtering
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vacancies_status ON vacancies(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vacancies_starred ON vacancies(is_starred)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_candidates_vacancy_id ON candidates(vacancy_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_candidates_vacancy ON candidates(vacancy)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_candidates_score ON candidates(score)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_candidates_loc_comp ON candidates(location_compatible)")
        
        # Retroactive update for location mismatch candidates
        cursor.execute("""
            UPDATE candidates 
            SET location_compatible = 0,
                status = CASE WHEN status = 'new' THEN 'location_mismatch' ELSE status END
            WHERE (
                evaluation_summary LIKE '%location mismatch%' 
                OR evaluation_summary LIKE '%location incompatible%'
                OR status = 'location_mismatch'
            ) AND location_compatible = 1
        """)
        
        conn.commit()

def migrate_txt_vacancies_to_db(db_path: str = DB_PATH):
    """
    Imports all existing .txt vacancy files into the SQLite vacancies table
    if they do not already exist, and links candidates.
    """
    active_dir = "vacancies"
    archived_dir = os.path.join("processed", "archived_vacancies")
    
    init_db(db_path)
    
    all_files = []
    if os.path.exists(active_dir):
        for f in os.listdir(active_dir):
            if f.endswith(".txt") and f != ".gitkeep":
                all_files.append((os.path.join(active_dir, f), "active", f))
                
    if os.path.exists(archived_dir):
        for f in os.listdir(archived_dir):
            if f.endswith(".txt") and f != ".gitkeep":
                all_files.append((os.path.join(archived_dir, f), "archived", f))
                
    if not all_files:
        return
        
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        for filepath, initial_status, filename in all_files:
            clean_title = filename.replace(".txt", "").strip()
            
            # Check if this vacancy already exists in SQLite
            cursor.execute("SELECT id FROM vacancies WHERE title = ? OR title = ?", (clean_title, filename))
            existing = cursor.fetchone()
            
            if not existing:
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                except Exception:
                    content = ""
                    
                country = "Any"
                first_lines = content[:400].lower()
                if "mexico" in first_lines or "méxico" in first_lines:
                    country = "Mexico"
                elif "colombia" in first_lines:
                    country = "Colombia"
                elif "argentina" in first_lines:
                    country = "Argentina"
                elif "spain" in first_lines or "españa" in first_lines:
                    country = "Spain"
                elif "latam" in first_lines:
                    country = "LATAM"
                elif "remote" in first_lines:
                    country = "Remote"

                cursor.execute("""
                    INSERT INTO vacancies (title, description, target_country, status, is_starred, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (clean_title, content, country, initial_status))
                vac_id = cursor.lastrowid
            else:
                vac_id = existing["id"]
                
            # Link existing candidates who have this vacancy name
            cursor.execute("""
                UPDATE candidates 
                SET vacancy_id = ?
                WHERE (vacancy_id IS NULL OR vacancy_id = 0)
                  AND (vacancy = ? OR vacancy = ? OR vacancy = ? || '.txt' OR vacancy LIKE ? || '%')
            """, (vac_id, clean_title, filename, clean_title, clean_title))
            
        conn.commit()

# --- VACANCIES CRUD OPERATIONS ---

def create_vacancy(title: str, description: str, target_country: str = "Any", status: str = "active", is_starred: bool = False, db_path: str = DB_PATH) -> int:
    """Creates a new vacancy directly in SQLite."""
    init_db(db_path)
    clean_title = title.strip()
    clean_desc = description.strip()
    clean_country = target_country.strip() if target_country else "Any"
    clean_status = status.strip() if status in ("active", "archived", "closed") else "active"
    starred_val = 1 if is_starred else 0
    
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO vacancies (title, description, target_country, status, is_starred, created_at, updated_at, last_opened_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (clean_title, clean_desc, clean_country, clean_status, starred_val))
        conn.commit()
        return cursor.lastrowid

def update_vacancy(vacancy_id: int, title: Optional[str] = None, description: Optional[str] = None, 
                   target_country: Optional[str] = None, status: Optional[str] = None, 
                   is_starred: Optional[bool] = None, db_path: str = DB_PATH) -> bool:
    """Updates fields or status of an existing vacancy."""
    init_db(db_path)
    updates = []
    params = []
    
    if title is not None and title.strip():
        updates.append("title = ?")
        params.append(title.strip())
        
    if description is not None:
        updates.append("description = ?")
        params.append(description.strip())
        
    if target_country is not None:
        updates.append("target_country = ?")
        params.append(target_country.strip() or "Any")
        
    if status is not None and status in ("active", "archived", "closed"):
        updates.append("status = ?")
        params.append(status)

    if is_starred is not None:
        updates.append("is_starred = ?")
        params.append(1 if is_starred else 0)
        
    if not updates:
        return False
        
    updates.append("updated_at = CURRENT_TIMESTAMP")
    updates.append("last_opened_at = CURRENT_TIMESTAMP")
    params.append(vacancy_id)
    
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE vacancies SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        return cursor.rowcount > 0

def toggle_vacancy_starred(vacancy_id: int, db_path: str = DB_PATH) -> Optional[bool]:
    """Toggles the starred status (0 to 1 or 1 to 0) of a vacancy and returns the new boolean value."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_starred FROM vacancies WHERE id = ?", (vacancy_id,))
        row = cursor.fetchone()
        if not row:
            return None
        current_val = bool(row["is_starred"]) if row["is_starred"] is not None else False
        new_val = 0 if current_val else 1
        cursor.execute("UPDATE vacancies SET is_starred = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_val, vacancy_id))
        conn.commit()
        return bool(new_val)

def touch_vacancy(vacancy_id: int, db_path: str = DB_PATH) -> bool:
    """Updates last_opened_at timestamp to now when a user opens/accesses a vacancy."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE vacancies SET last_opened_at = CURRENT_TIMESTAMP WHERE id = ?", (vacancy_id,))
        conn.commit()
        return cursor.rowcount > 0

def get_vacancy_by_id(vacancy_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Retrieves single vacancy by ID."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vacancies WHERE id = ?", (vacancy_id,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["is_starred"] = bool(d.get("is_starred", 0))
        d["is_active"] = (d.get("status") == "active")
        return d

def delete_vacancy(vacancy_id: int, db_path: str = DB_PATH) -> bool:
    """Deletes a vacancy from SQLite and cleans up any linked candidates."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title FROM vacancies WHERE id = ?", (vacancy_id,))
        row = cursor.fetchone()
        if not row:
            return False
        title = row["title"]
        
        # 1. Cascade delete candidates linked to this vacancy
        cursor.execute("""
            DELETE FROM candidates 
            WHERE vacancy_id = ? 
               OR vacancy = ? 
               OR vacancy = ? 
               OR vacancy LIKE ?
        """, (vacancy_id, title, f"{title}.txt", f"{title}%"))
        
        # 2. Delete the vacancy itself
        cursor.execute("DELETE FROM vacancies WHERE id = ?", (vacancy_id,))
        conn.commit()
        
        # 3. Clean up legacy disk files if any exist
        for folder in ["vacancies", os.path.join("processed", "archived_vacancies")]:
            for fname in [title, f"{title}.txt", f"{title}.txt.txt"]:
                fpath = os.path.join(folder, fname)
                if os.path.exists(fpath) and fname != ".gitkeep":
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
                        
        return True

def get_vacancies(status: Optional[str] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """
    Returns all vacancies from SQLite along with aggregated candidate statistics,
    ordered by active first, then starred first, then most recently opened / created.
    """
    init_db(db_path)
    
    query = """
        SELECT 
            v.id,
            v.title,
            v.description,
            v.target_country,
            v.status,
            v.is_starred,
            v.created_at,
            v.updated_at,
            v.last_opened_at,
            COUNT(CASE WHEN c.location_compatible = 1 THEN 1 END) as total_candidates,
            SUM(CASE WHEN c.score >= 85 AND c.location_compatible = 1 THEN 1 ELSE 0 END) as desirable_count,
            SUM(CASE WHEN c.score < 85 AND c.location_compatible = 1 THEN 1 ELSE 0 END) as undesirable_count,
            SUM(CASE WHEN c.status = 'contacted' AND c.location_compatible = 1 THEN 1 ELSE 0 END) as contacted_count,
            SUM(CASE WHEN c.status = 'interviewing' AND c.location_compatible = 1 THEN 1 ELSE 0 END) as interviewing_count,
            SUM(CASE WHEN c.status = 'hired' AND c.location_compatible = 1 THEN 1 ELSE 0 END) as hired_count,
            SUM(CASE WHEN c.location_compatible = 0 THEN 1 ELSE 0 END) as location_mismatch_count,
            AVG(CASE WHEN c.location_compatible = 1 THEN c.score END) as avg_score
        FROM vacancies v
        LEFT JOIN candidates c ON (c.vacancy_id = v.id OR c.vacancy = v.title OR c.vacancy LIKE v.title || '%')
    """
    params = []
    if status and status != "all":
        query += " WHERE v.status = ?"
        params.append(status)
        
    query += """
        GROUP BY v.id 
        ORDER BY (CASE WHEN v.status = 'active' THEN 0 ELSE 1 END), 
                 COALESCE(v.is_starred, 0) DESC,
                 COALESCE(v.last_opened_at, v.updated_at, v.created_at) DESC, 
                 v.id DESC
    """
    
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        result = []
        for r in rows:
            d = dict(r)
            d["is_active"] = (d.get("status") == "active")
            d["is_starred"] = bool(d.get("is_starred", 0))
            d["avg_score"] = round(d["avg_score"], 1) if d.get("avg_score") is not None else 0.0
            desc = d.get("description") or ""
            d["snippet"] = desc[:280].strip().replace("\n", " ")
            result.append(d)
        return result

# --- CANDIDATES CRUD OPERATIONS ---

def generate_default_outreach_message(name: str, vacancy_title: str, summary: str = "") -> str:
    """Fallback generator for personalized outreach message in English."""
    first_name = name.split()[0] if name and name != "Unknown" else "there"
    clean_vac = vacancy_title.replace(".txt", "").replace("IRC", "").strip(" -_0123456789")
    if not clean_vac:
        clean_vac = "our open position"
    
    return (
        f"Hi {first_name}, hope you are doing well! I came across your profile and was very impressed by your technical background. "
        f"We are actively sourcing for a {clean_vac} role and believe your experience would be a great fit for our team. "
        f"Would you be open to a quick 10-minute chat this week to discuss?"
    )

def upsert_candidate(candidate_info: dict, db_path: str = DB_PATH) -> int:
    """
    Inserts or updates candidate information exclusively in SQLite.
    Preserves user notes and custom status if updating an existing candidate.
    """
    init_db(db_path)
    
    url = candidate_info.get("linkedin_url", "").strip()
    if not url:
        return -1

    name = candidate_info.get("name", "Unknown")
    vacancy = candidate_info.get("vacancy", "General")
    vacancy_id = candidate_info.get("vacancy_id")
    headline = candidate_info.get("headline", "")
    location = candidate_info.get("location", "")
    open_to_work = bool(candidate_info.get("open_to_work", False))
    
    raw_status = candidate_info.get("status", "new")
    evaluation_summary = candidate_info.get("evaluation_summary", "")
    
    # Check geographic compatibility
    if "location_compatible" in candidate_info:
        location_compatible = bool(candidate_info["location_compatible"])
        is_loc_mismatch = not location_compatible
        status = "location_mismatch" if (is_loc_mismatch and raw_status == "new") else raw_status
    else:
        is_loc_mismatch = (
            raw_status == "location_mismatch" or
            "location mismatch" in evaluation_summary.lower() or
            "location incompatible" in evaluation_summary.lower()
        )
        location_compatible = not is_loc_mismatch
        status = "location_mismatch" if (is_loc_mismatch and raw_status == "new") else raw_status
    
    try:
        score = int(candidate_info.get("score", 0))
    except (ValueError, TypeError):
        score = 0
        
    try:
        tech_score = int(candidate_info.get("technical_score", 0))
    except (ValueError, TypeError):
        tech_score = 0

    try:
        exp_score = int(candidate_info.get("experience_score", 0))
    except (ValueError, TypeError):
        exp_score = 0

    try:
        aux_score = int(candidate_info.get("auxiliary_score", 0))
    except (ValueError, TypeError):
        aux_score = 0

    # Auto-distribute sub-scores if total score is provided manually
    if score > 0 and tech_score == 0 and exp_score == 0 and aux_score == 0:
        tech_score = round(score * 0.40)
        exp_score = round(score * 0.40)
        aux_score = max(0, score - tech_score - exp_score)

    suggested_message = candidate_info.get("suggested_message")
    if not suggested_message and location_compatible:
        suggested_message = generate_default_outreach_message(name, vacancy, evaluation_summary)
    elif not suggested_message:
        suggested_message = ""
        
    about = candidate_info.get("about", "")
    experience = candidate_info.get("experience", "")
    skills = candidate_info.get("skills", "")
    timestamp = candidate_info.get("timestamp", datetime.now().isoformat())
    notes = candidate_info.get("notes", "")

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # If vacancy_id not provided, try to find matching vacancy in DB
        if not vacancy_id and vacancy:
            clean_vac = vacancy.replace(".txt", "").strip()
            cursor.execute("SELECT id FROM vacancies WHERE title = ? OR title LIKE ? LIMIT 1", (clean_vac, f"%{clean_vac}%"))
            v_row = cursor.fetchone()
            if v_row:
                vacancy_id = v_row["id"]
        
        # Check if candidate already exists
        cursor.execute("SELECT id, status, notes, suggested_message, vacancy_id FROM candidates WHERE linkedin_url = ?", (url,))
        existing = cursor.fetchone()
        
        if existing:
            candidate_id = existing["id"]
            existing_status = existing["status"]
            existing_notes = existing["notes"]
            existing_msg = existing["suggested_message"]
            existing_vid = existing["vacancy_id"]
            
            final_status = existing_status if existing_status != 'new' else status
            final_notes = existing_notes if existing_notes else notes
            final_msg = suggested_message if suggested_message else existing_msg
            final_vid = vacancy_id if vacancy_id else existing_vid
            
            cursor.execute("""
                UPDATE candidates SET
                    vacancy_id = ?,
                    vacancy = ?,
                    name = ?,
                    headline = ?,
                    location = ?,
                    open_to_work = ?,
                    location_compatible = ?,
                    score = ?,
                    technical_score = ?,
                    experience_score = ?,
                    auxiliary_score = ?,
                    evaluation_summary = ?,
                    suggested_message = ?,
                    status = ?,
                    notes = ?,
                    about = ?,
                    experience = ?,
                    skills = ?,
                    timestamp = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                final_vid, vacancy, name, headline, location, open_to_work, location_compatible, score,
                tech_score, exp_score, aux_score, evaluation_summary,
                final_msg, final_status, final_notes, about, experience,
                skills, timestamp, candidate_id
            ))
            conn.commit()
            return candidate_id
        else:
            cursor.execute("""
                INSERT INTO candidates (
                    vacancy_id, vacancy, name, headline, linkedin_url, location,
                    open_to_work, location_compatible, score, technical_score, experience_score,
                    auxiliary_score, evaluation_summary, suggested_message,
                    status, notes, about, experience, skills, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                vacancy_id, vacancy, name, headline, url, location,
                open_to_work, location_compatible, score, tech_score, exp_score,
                aux_score, evaluation_summary, suggested_message,
                status, notes, about, experience, skills, timestamp
            ))
            conn.commit()
            return cursor.lastrowid

def get_candidates(
    vacancy_id: Optional[int] = None,
    vacancy: Optional[str] = None,
    min_score: Optional[int] = None,
    max_score: Optional[int] = None,
    status: Optional[str] = None,
    open_to_work: Optional[bool] = None,
    hide_location_mismatch: bool = True,
    pipeline_view: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "score",
    sort_order: str = "desc",
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    db_path: str = DB_PATH
) -> List[Dict[str, Any]]:
    """Fetches candidates with dynamic filters, strictly partitioning viable vs discarded when requested."""
    init_db(db_path)
    
    query = "SELECT * FROM candidates WHERE 1=1"
    params: List[Any] = []
    
    if vacancy_id is not None:
        query += " AND vacancy_id = ?"
        params.append(vacancy_id)
    elif vacancy and vacancy != "all":
        clean_v = vacancy.replace(".txt", "").strip()
        query += " AND (vacancy = ? OR vacancy = ? OR vacancy LIKE ?)"
        params.extend([vacancy, clean_v, f"%{clean_v}%"])
        
    if pipeline_view == "viable":
        query += " AND score >= 60 AND location_compatible = 1 AND status NOT IN ('discarded', 'location_mismatch') AND evaluation_summary NOT LIKE '%location mismatch%'"
    elif pipeline_view == "discarded":
        query += " AND (score < 60 OR location_compatible = 0 OR status IN ('discarded', 'location_mismatch') OR evaluation_summary LIKE '%location mismatch%')"
    else:
        if hide_location_mismatch:
            query += " AND location_compatible = 1 AND evaluation_summary NOT LIKE '%location mismatch%' AND evaluation_summary NOT LIKE '%location incompatible%'"
        
    if min_score is not None:
        query += " AND score >= ?"
        params.append(min_score)
        
    if max_score is not None:
        query += " AND score <= ?"
        params.append(max_score)
        
    if status and status != "all":
        query += " AND status = ?"
        params.append(status)
        
    if open_to_work is not None:
        query += " AND open_to_work = ?"
        params.append(1 if open_to_work else 0)
        
    if search and search.strip():
        search_pattern = f"%{search.strip()}%"
        query += " AND (name LIKE ? OR headline LIKE ? OR location LIKE ? OR evaluation_summary LIKE ? OR skills LIKE ? OR notes LIKE ?)"
        params.extend([search_pattern] * 6)
        
    allowed_sort_fields = {"score", "name", "created_at", "updated_at", "technical_score", "experience_score", "status"}
    field = sort_by if sort_by in allowed_sort_fields else "score"
    order = "ASC" if sort_order.lower() == "asc" else "DESC"
    query += f" ORDER BY {field} {order}"
    
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
        if offset is not None:
            query += " OFFSET ?"
            params.append(offset)
            
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_candidate_by_id(candidate_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Retrieves single candidate by primary key ID."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_candidate_status(candidate_id: int, status: str, db_path: str = DB_PATH) -> bool:
    """Updates candidate pipeline status."""
    init_db(db_path)
    valid_statuses = {'new', 'contacted', 'interviewing', 'discarded', 'hired', 'location_mismatch'}
    if status not in valid_statuses:
        return False
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE candidates SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, candidate_id))
        conn.commit()
        return cursor.rowcount > 0

def restore_candidate_to_pipeline(candidate_id: int, db_path: str = DB_PATH) -> bool:
    """Restores a discarded candidate to the active pipeline (status='new', location_compatible=1, score at least 60)."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT score FROM candidates WHERE id = ?", (candidate_id,))
        row = cursor.fetchone()
        if not row:
            return False
        current_score = row["score"] or 0
        new_score = max(current_score, 60)
        cursor.execute("""
            UPDATE candidates 
            SET status = 'new', 
                location_compatible = 1, 
                score = ?, 
                updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (new_score, candidate_id))
        conn.commit()
        return cursor.rowcount > 0


def update_candidate_notes(candidate_id: int, notes: str, db_path: str = DB_PATH) -> bool:
    """Updates recruiter notes for a candidate."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE candidates SET notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (notes, candidate_id))
        conn.commit()
        return cursor.rowcount > 0

def update_candidate_message(candidate_id: int, message: str, db_path: str = DB_PATH) -> bool:
    """Updates suggested outreach message for a candidate."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE candidates SET suggested_message = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (message, candidate_id))
        conn.commit()
        return cursor.rowcount > 0

def delete_candidate(candidate_id: int, db_path: str = DB_PATH) -> bool:
    """Deletes a candidate record."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
        conn.commit()
        return cursor.rowcount > 0

def get_stats(db_path: str = DB_PATH) -> Dict[str, Any]:
    """Returns general metrics and breakdown excluding location mismatches."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as all_evaluated_records,
                COUNT(CASE WHEN location_compatible = 1 THEN 1 END) as total_candidates,
                SUM(CASE WHEN score >= 85 AND location_compatible = 1 THEN 1 ELSE 0 END) as desirable_candidates,
                SUM(CASE WHEN open_to_work = 1 AND location_compatible = 1 THEN 1 ELSE 0 END) as open_to_work_count,
                SUM(CASE WHEN status = 'new' AND location_compatible = 1 THEN 1 ELSE 0 END) as new_count,
                SUM(CASE WHEN status = 'contacted' AND location_compatible = 1 THEN 1 ELSE 0 END) as contacted_count,
                SUM(CASE WHEN status = 'interviewing' AND location_compatible = 1 THEN 1 ELSE 0 END) as interviewing_count,
                SUM(CASE WHEN status = 'hired' AND location_compatible = 1 THEN 1 ELSE 0 END) as hired_count,
                SUM(CASE WHEN status = 'discarded' AND location_compatible = 1 THEN 1 ELSE 0 END) as discarded_count,
                SUM(CASE WHEN location_compatible = 0 THEN 1 ELSE 0 END) as location_mismatch_count,
                AVG(CASE WHEN location_compatible = 1 THEN score END) as avg_score
            FROM candidates
        """)
        row = cursor.fetchone()
        stats = dict(row) if row else {}
        stats["avg_score"] = round(stats.get("avg_score") or 0, 1)
        
        # Add vacancies counts
        cursor.execute("SELECT COUNT(CASE WHEN status = 'active' THEN 1 END) as active_vacancies, COUNT(CASE WHEN status = 'archived' THEN 1 END) as archived_vacancies, COUNT(*) as total_vacancies FROM vacancies")
        v_stats = cursor.fetchone()
        if v_stats:
            stats.update(dict(v_stats))
            
        return stats

def get_processed_urls_from_db(db_path: str = DB_PATH) -> set:
    """
    Returns a set of all linkedin_urls already evaluated and stored in SQLite.
    SQLite is 100% the single source of truth.
    """
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT linkedin_url FROM candidates WHERE linkedin_url IS NOT NULL AND linkedin_url != ''")
        return {row["linkedin_url"] for row in cursor.fetchall() if row["linkedin_url"]}

def is_url_processed_in_db(url: str, db_path: str = DB_PATH) -> bool:
    """
    Checks if a LinkedIn profile URL has already been processed and saved in SQLite.
    """
    if not url:
        return False
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM candidates WHERE linkedin_url = ? LIMIT 1", (url.strip(),))
        return cursor.fetchone() is not None


