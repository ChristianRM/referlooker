import os
import sys
import json
import time
import webbrowser
import threading
from typing import Optional
from flask import Flask, render_template, request, jsonify, send_file, Response

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import (
    init_db,
    get_candidates,
    get_candidate_by_id,
    update_candidate_status,
    restore_candidate_to_pipeline,
    update_candidate_notes,
    update_candidate_message,
    delete_candidate,
    get_vacancies,
    get_vacancy_by_id,
    create_vacancy,
    update_vacancy,
    toggle_vacancy_starred,
    delete_vacancy,
    touch_vacancy,
    get_stats,
    upsert_candidate,
    get_processed_urls_from_db,
    DB_PATH
)
from evaluator import generate_outreach_message_llm, evaluate_candidate
from query_generator import generate_search_query, chat_refine_search_query, diagnose_sourcing_issues

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static")
)

def load_config():
    config_path = "config.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

@app.route("/")
def index():
    """Serves the main SPA Dashboard."""
    return render_template("index.html")

@app.route("/api/candidates", methods=["GET"])
def api_get_candidates():
    """Returns candidates matching active query filters (hiding location mismatches by default)."""
    vacancy_id_str = request.args.get("vacancy_id")
    vacancy = request.args.get("vacancy")
    min_score_str = request.args.get("min_score")
    max_score_str = request.args.get("max_score")
    status = request.args.get("status")
    otw_str = request.args.get("open_to_work")
    hide_loc_str = request.args.get("hide_location_mismatch", "true")
    search = request.args.get("search")
    sort_by = request.args.get("sort_by", "score")
    sort_order = request.args.get("sort_order", "desc")
    pipeline_view = request.args.get("pipeline_view")
    
    vacancy_id = int(vacancy_id_str) if vacancy_id_str and vacancy_id_str.isdigit() else None
    min_score = int(min_score_str) if min_score_str and min_score_str.isdigit() else None
    max_score = int(max_score_str) if max_score_str and max_score_str.isdigit() else None
    open_to_work = (otw_str.lower() == "true") if otw_str in ("true", "false", "1", "0") else None
    hide_location_mismatch = (hide_loc_str.lower() != "false")
    
    if vacancy_id:
        touch_vacancy(vacancy_id)
    
    candidates = get_candidates(
        vacancy_id=vacancy_id,
        vacancy=vacancy,
        min_score=min_score,
        max_score=max_score,
        status=status,
        open_to_work=open_to_work,
        hide_location_mismatch=hide_location_mismatch,
        pipeline_view=pipeline_view,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order
    )
    return jsonify({"success": True, "count": len(candidates), "candidates": candidates})

# --- VACANCIES REST API (100% DB-DRIVEN) ---

@app.route("/api/vacancies", methods=["GET"])
def api_get_vacancies():
    """Returns vacancies from SQLite with candidate metrics."""
    status = request.args.get("status")
    vacancies = get_vacancies(status=status)
    return jsonify({"success": True, "vacancies": vacancies})

@app.route("/api/vacancies", methods=["POST"])
def api_create_vacancy():
    """Creates a new vacancy directly in SQLite."""
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    target_country = data.get("target_country", "Any").strip() or "Any"
    is_starred = bool(data.get("is_starred", False))
    
    if not title:
        return jsonify({"success": False, "error": "Title is required"}), 400
    if not description:
        return jsonify({"success": False, "error": "Description is required"}), 400
        
    new_id = create_vacancy(title, description, target_country=target_country, status="active", is_starred=is_starred)
    vac = get_vacancy_by_id(new_id)
    return jsonify({"success": True, "vacancy": vac, "message": "Vacancy created successfully"}), 201

@app.route("/api/vacancies/<int:vacancy_id>", methods=["GET"])
def api_get_vacancy(vacancy_id: int):
    """Retrieves full vacancy details from SQLite."""
    vac = get_vacancy_by_id(vacancy_id)
    if not vac:
        return jsonify({"success": False, "error": "Vacancy not found"}), 404
    return jsonify({"success": True, "vacancy": vac})

@app.route("/api/vacancies/<int:vacancy_id>", methods=["PATCH"])
def api_update_vacancy(vacancy_id: int):
    """Updates vacancy title, description, target country, is_starred, or status."""
    data = request.get_json() or {}
    title = data.get("title")
    description = data.get("description")
    target_country = data.get("target_country")
    status = data.get("status")
    is_starred = data.get("is_starred")
    
    if update_vacancy(vacancy_id, title=title, description=description, target_country=target_country, status=status, is_starred=is_starred):
        vac = get_vacancy_by_id(vacancy_id)
        return jsonify({"success": True, "vacancy": vac, "message": "Vacancy updated successfully"})
    return jsonify({"success": False, "error": "Failed to update vacancy or no changes specified"}), 400

@app.route("/api/vacancies/<int:vacancy_id>/toggle-star", methods=["POST"])
def api_toggle_vacancy_starred(vacancy_id: int):
    """Toggles starred status of a vacancy."""
    new_status = toggle_vacancy_starred(vacancy_id)
    if new_status is None:
        return jsonify({"success": False, "error": "Vacancy not found"}), 404
    vac = get_vacancy_by_id(vacancy_id)
    return jsonify({
        "success": True, 
        "is_starred": new_status, 
        "vacancy": vac,
        "message": f"Vacancy {'marked as Starred' if new_status else 'removed from Starred'}"
    })

@app.route("/api/vacancies/<int:vacancy_id>", methods=["DELETE"])
def api_delete_vacancy(vacancy_id: int):
    """Deletes a vacancy from SQLite."""
    if delete_vacancy(vacancy_id):
        return jsonify({"success": True, "message": "Vacancy deleted successfully"})
    return jsonify({"success": False, "error": "Vacancy not found"}), 404

@app.route("/api/vacancies/<int:vacancy_id>/touch", methods=["POST"])
def api_touch_vacancy(vacancy_id: int):
    """Updates last_opened_at timestamp when vacancy is accessed/opened."""
    touch_vacancy(vacancy_id)
    return jsonify({"success": True, "message": "Vacancy touched"})

@app.route("/api/vacancies/<int:vacancy_id>/archive", methods=["POST"])
def api_archive_vacancy(vacancy_id: int):
    """Sets vacancy status to 'archived'."""
    if update_vacancy(vacancy_id, status="archived"):
        vac = get_vacancy_by_id(vacancy_id)
        return jsonify({"success": True, "vacancy": vac, "message": "Vacancy archived"})
    return jsonify({"success": False, "error": "Vacancy not found"}), 404

@app.route("/api/vacancies/<int:vacancy_id>/reopen", methods=["POST"])
def api_reopen_vacancy(vacancy_id: int):
    """Sets vacancy status to 'active'."""
    if update_vacancy(vacancy_id, status="active"):
        vac = get_vacancy_by_id(vacancy_id)
        return jsonify({"success": True, "vacancy": vac, "message": "Vacancy reopened"})
    return jsonify({"success": False, "error": "Vacancy not found"}), 404

# --- SAFE SEQUENTIAL SOURCING QUEUE MANAGER ---
# To protect the user's LinkedIn account from rate limits and anti-bot bans,
# searches are executed strictly sequentially (1 at a time) with humanized safety pacing.

sourcing_jobs = {}

class SourcingQueueManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.queue = []          # List of dicts: [{"vacancy_id": 1, "target_count": 5, "title": "...", "added_at": ...}]
        self.active_job = None   # Dict or None
        self.worker_thread = None

    def enqueue(self, vacancy_id: int, target_count: int, title: str, custom_query: Optional[str] = None):
        with self.lock:
            # Check if currently running
            if self.active_job and self.active_job.get("vacancy_id") == vacancy_id and self.active_job.get("running"):
                return {"status": "already_running", "position": 0}
            # Check if already in queue
            for idx, item in enumerate(self.queue):
                if item["vacancy_id"] == vacancy_id:
                    return {"status": "already_queued", "position": idx + 1}
            
            job_item = {
                "vacancy_id": vacancy_id,
                "target_count": target_count,
                "title": title,
                "custom_query": custom_query,
                "added_at": time.time()
            }
            self.queue.append(job_item)
            position = len(self.queue)
            
            # Set initial queued status in sourcing_jobs
            sourcing_jobs[vacancy_id] = {
                "vacancy_id": vacancy_id,
                "title": title,
                "running": False,
                "queued": True,
                "queue_position": position,
                "cancelled": False,
                "progress": 0,
                "target": target_count,
                "custom_query": custom_query,
                "message": f"Queued at position #{position}. Waiting for active search to complete...",
                "logs": [f"🕒 Job added to safe sourcing queue (Position #{position}). Sourcing will begin automatically..."],
                "error": None
            }
            
            # Start background queue worker if not active
            if not self.worker_thread or not self.worker_thread.is_alive():
                self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
                self.worker_thread.start()
                
            return {"status": "queued", "position": position}

    def cancel_job(self, vacancy_id: int):
        with self.lock:
            # Check if in queue
            for i, item in enumerate(self.queue):
                if item["vacancy_id"] == vacancy_id:
                    self.queue.pop(i)
                    if vacancy_id in sourcing_jobs:
                        sourcing_jobs[vacancy_id]["queued"] = False
                        sourcing_jobs[vacancy_id]["cancelled"] = True
                        sourcing_jobs[vacancy_id]["message"] = "Removed from sourcing queue."
                        sourcing_jobs[vacancy_id]["logs"].append("🛑 [Action] Job removed from queue by user.")
                    return {"success": True, "type": "dequeued"}
            
            # Check if currently active
            if self.active_job and self.active_job.get("vacancy_id") == vacancy_id:
                self.active_job["cancelled"] = True
                self.active_job["running"] = False
                self.active_job["message"] = "AI Sourcing cancelled by user."
                if "logs" in self.active_job:
                    self.active_job["logs"].append("🛑 [Action] Process cancellation requested by user. Aborting...")
                return {"success": True, "type": "cancelled_active"}
                
            return {"success": False, "message": "No active or queued job found"}

    def cancel_all(self):
        with self.lock:
            for item in self.queue:
                vid = item["vacancy_id"]
                if vid in sourcing_jobs:
                    sourcing_jobs[vid]["queued"] = False
                    sourcing_jobs[vid]["cancelled"] = True
                    sourcing_jobs[vid]["message"] = "Queue cancelled."
            self.queue.clear()
            
            if self.active_job and self.active_job.get("running"):
                self.active_job["cancelled"] = True
                self.active_job["running"] = False
                self.active_job["message"] = "AI Sourcing cancelled by user."
                if "logs" in self.active_job:
                    self.active_job["logs"].append("🛑 [Action] All sourcing tasks cancelled and queue cleared.")
            return {"success": True}

    def get_status(self):
        with self.lock:
            queued_items = []
            for idx, item in enumerate(self.queue):
                vid = item["vacancy_id"]
                queued_items.append({
                    "position": idx + 1,
                    "vacancy_id": vid,
                    "title": item["title"],
                    "target_count": item["target_count"]
                })
                # Update queue position in job record
                if vid in sourcing_jobs:
                    sourcing_jobs[vid]["queue_position"] = idx + 1
                    sourcing_jobs[vid]["message"] = f"Queued at position #{idx + 1}. Waiting for active search to complete..."
                
            active = None
            if self.active_job and self.active_job.get("running"):
                active = {
                    "vacancy_id": self.active_job.get("vacancy_id"),
                    "title": self.active_job.get("title", ""),
                    "progress": self.active_job.get("progress", 0),
                    "target": self.active_job.get("target", 5),
                    "message": self.active_job.get("message", "Processing..."),
                    "running": True
                }
                
            return {
                "active_job": active,
                "queued_jobs": queued_items,
                "total_in_progress": (1 if active else 0) + len(queued_items)
            }

    def _worker_loop(self):
        while True:
            job_info = None
            with self.lock:
                if not self.queue:
                    self.active_job = None
                    break
                job_info = self.queue.pop(0)
                
            vid = job_info["vacancy_id"]
            target = job_info["target_count"]
            c_query = job_info.get("custom_query")
            _run_sourcing_worker(vid, target, custom_query=c_query)
            
            # Anti-ban Safety Human delay between sequential searches (3 seconds)
            time.sleep(3)

queue_manager = SourcingQueueManager()

def _run_sourcing_worker(vacancy_id: int, min_target: int, custom_query: Optional[str] = None):
    from main import process_vacancy, load_config
    
    vacancy = get_vacancy_by_id(vacancy_id)
    if not vacancy:
        sourcing_jobs[vacancy_id] = {
            "vacancy_id": vacancy_id,
            "title": f"Vacancy #{vacancy_id}",
            "running": False,
            "paused": False,
            "queued": False,
            "cancelled": False,
            "error": "Vacancy not found",
            "progress": 0,
            "target": min_target,
            "message": "Vacancy not found",
            "matched_candidates": [],
            "discarded_candidates": [],
            "discard_stats": {"location_mismatch": 0, "error": 0, "low_score": 0, "total_discarded": 0}
        }
        return
        
    config = load_config()
    processed_history = get_processed_urls_from_db()
    
    pause_evt = threading.Event()
    pause_evt.set()  # Initial state: running (unpaused)
    
    current_job = {
        "vacancy_id": vacancy_id,
        "title": vacancy["title"],
        "running": True,
        "paused": False,
        "queued": False,
        "cancelled": False,
        "progress": 0,
        "target": min_target,
        "custom_query": custom_query,
        "matched_candidates": [],
        "discarded_candidates": [],
        "discard_stats": {
            "location_mismatch": 0,
            "error": 0,
            "low_score": 0,
            "total_discarded": 0
        },
        "pause_event": pause_evt,
        "message": f"Starting AI sourcing for '{vacancy['title']}'...",
        "logs": [f"🚀 Sourcing started for '{vacancy['title']}' (Target: {min_target} evaluated candidates)..."],
        "error": None
    }
    sourcing_jobs[vacancy_id] = current_job
    queue_manager.active_job = current_job
    
    def is_cancelled():
        return sourcing_jobs.get(vacancy_id, {}).get("cancelled", False)
        
    def is_paused():
        return sourcing_jobs.get(vacancy_id, {}).get("paused", False)
        
    def get_current_query():
        return sourcing_jobs.get(vacancy_id, {}).get("custom_query")
        
    def on_eval(cand_record):
        if vacancy_id not in sourcing_jobs:
            return
        score = cand_record.get("score", 0)
        status = cand_record.get("status", "new")
        loc_comp = cand_record.get("location_compatible", 1)
        eval_summary = cand_record.get("evaluation_summary", "")
        
        is_viable = (score >= 60) and (loc_comp == 1 or loc_comp is True) and (status not in ('discarded', 'location_mismatch'))
        
        if is_viable:
            c_summary = {
                "id": cand_record.get("id"),
                "name": cand_record.get("name", "Unknown"),
                "headline": cand_record.get("headline", ""),
                "score": score,
                "location": cand_record.get("location", ""),
                "open_to_work": cand_record.get("open_to_work", False),
                "linkedin_url": cand_record.get("linkedin_url", ""),
                "evaluation_summary": eval_summary
            }
            if "matched_candidates" not in sourcing_jobs[vacancy_id]:
                sourcing_jobs[vacancy_id]["matched_candidates"] = []
            sourcing_jobs[vacancy_id]["matched_candidates"].append(c_summary)
        else:
            discard_info = {
                "name": cand_record.get("name", "LinkedIn Member"),
                "headline": cand_record.get("headline", "Profile evaluated"),
                "location": cand_record.get("location", "Not specified"),
                "score": score,
                "linkedin_url": cand_record.get("linkedin_url", ""),
                "type": "low_score" if (loc_comp == 1 and "location mismatch" not in eval_summary.lower()) else "location_mismatch",
                "reason": f"Low match score ({score}%): {eval_summary[:110]}..." if (loc_comp == 1 and "location mismatch" not in eval_summary.lower()) else f"Location mismatch / Discarded ({score}%)."
            }
            if "discarded_candidates" not in sourcing_jobs[vacancy_id]:
                sourcing_jobs[vacancy_id]["discarded_candidates"] = []
            sourcing_jobs[vacancy_id]["discarded_candidates"].append(discard_info)
            
            stats = sourcing_jobs[vacancy_id].setdefault("discard_stats", {"location_mismatch": 0, "error": 0, "low_score": 0, "total_discarded": 0})
            stats["total_discarded"] = stats.get("total_discarded", 0) + 1
            dtype = discard_info["type"]
            stats[dtype] = stats.get(dtype, 0) + 1
        
    def on_discard(discard_info):
        if vacancy_id not in sourcing_jobs:
            return
        if "discarded_candidates" not in sourcing_jobs[vacancy_id]:
            sourcing_jobs[vacancy_id]["discarded_candidates"] = []
        sourcing_jobs[vacancy_id]["discarded_candidates"].append(discard_info)
        
        dtype = discard_info.get("type", "error")
        stats = sourcing_jobs[vacancy_id].setdefault("discard_stats", {"location_mismatch": 0, "error": 0, "low_score": 0, "total_discarded": 0})
        stats["total_discarded"] = stats.get("total_discarded", 0) + 1
        if dtype in stats:
            stats[dtype] = stats.get(dtype, 0) + 1
        else:
            stats[dtype] = 1
    
    def on_progress(msg, current_evals, target, is_done=False):
        if vacancy_id not in sourcing_jobs:
            sourcing_jobs[vacancy_id] = {}
        sourcing_jobs[vacancy_id]["progress"] = current_evals
        sourcing_jobs[vacancy_id]["target"] = target
        sourcing_jobs[vacancy_id]["message"] = msg
        if is_done or is_cancelled():
            sourcing_jobs[vacancy_id]["running"] = False
        if "logs" not in sourcing_jobs[vacancy_id]:
            sourcing_jobs[vacancy_id]["logs"] = []
        sourcing_jobs[vacancy_id]["logs"].append(msg)
        if len(sourcing_jobs[vacancy_id]["logs"]) > 50:
            sourcing_jobs[vacancy_id]["logs"] = sourcing_jobs[vacancy_id]["logs"][-50:]
            
    try:
        res = process_vacancy(
            vacancy_input=vacancy,
            config=config,
            processed_history=processed_history,
            min_target=min_target,
            interactive=False,
            progress_callback=on_progress,
            cancel_check=is_cancelled,
            custom_query=custom_query,
            pause_check=is_paused,
            get_active_query=get_current_query,
            on_candidate_evaluated=on_eval,
            on_candidate_discarded=on_discard
        )
        sourcing_jobs[vacancy_id]["running"] = False
        if is_cancelled() or (isinstance(res, dict) and res.get("cancelled")):
            sourcing_jobs[vacancy_id]["cancelled"] = True
            sourcing_jobs[vacancy_id]["message"] = f"AI Sourcing stopped by user ({sourcing_jobs[vacancy_id].get('progress', 0)} candidates processed)."
        else:
            sourcing_jobs[vacancy_id]["message"] = f"AI Sourcing finished ({sourcing_jobs[vacancy_id].get('progress', 0)} candidates evaluated)."
    except Exception as e:
        sourcing_jobs[vacancy_id]["running"] = False
        sourcing_jobs[vacancy_id]["error"] = str(e)
        sourcing_jobs[vacancy_id]["message"] = f"Error during sourcing: {str(e)}"
    finally:
        with queue_manager.lock:
            if queue_manager.active_job and queue_manager.active_job.get("vacancy_id") == vacancy_id:
                queue_manager.active_job["running"] = False

# --- COPILOT CONVERSATIONAL REFINEMENT APIS ---

@app.route("/api/copilot/initial", methods=["POST"])
def api_copilot_initial():
    """Generates initial query and welcoming analysis message from the AI Sourcing Copilot."""
    data = request.get_json() or {}
    vacancy_id = data.get("vacancy_id")
    if not vacancy_id:
        return jsonify({"success": False, "error": "vacancy_id is required"}), 400
        
    vac = get_vacancy_by_id(vacancy_id)
    if not vac:
        return jsonify({"success": False, "error": "Vacancy not found"}), 404
        
    config = load_config()
    vac_text = vac.get("description", "").strip()
    if not vac_text:
        return jsonify({"success": False, "error": "Vacancy description is empty"}), 400
        
    analysis = generate_search_query(vac_text, config)
    role = analysis.get("role", vac["title"])
    country = vac.get("target_country") or analysis.get("target_country", "Any")
    query = analysis.get("search_query", "")
    
    greeting = (
        f"Hello! I have analyzed the Job Description for **{vac['title']}** (Region: **{country}**). "
        f"I've crafted an initial Google X-Ray search query optimized to discover active Open to Work candidates.\n\n"
        f"Would you like to fine-tune any specifics (e.g., seniority level, alternate tech stacks, or target location) "
        f"or launch the sourcing search directly?"
    )
    
    return jsonify({
        "success": True,
        "role": role,
        "target_country": country,
        "search_query": query,
        "reply": greeting,
        "tips": [
            "Ask me to adjust or relax seniority titles",
            "Specify if you want to prioritize specific technologies from the stack",
            "Let me know if this requisition accepts candidates from other regions or remote"
        ]
    })

@app.route("/api/copilot/chat", methods=["POST"])
def api_copilot_chat():
    """Handles conversational chat messages to refine the search query with AI."""
    data = request.get_json() or {}
    vacancy_id = data.get("vacancy_id")
    message = data.get("message", "").strip()
    history = data.get("history", [])
    current_query = data.get("current_query", "").strip()
    
    if not vacancy_id:
        return jsonify({"success": False, "error": "vacancy_id is required"}), 400
    if not message:
        return jsonify({"success": False, "error": "Message cannot be empty"}), 400
        
    vac = get_vacancy_by_id(vacancy_id)
    if not vac:
        return jsonify({"success": False, "error": "Vacancy not found"}), 404
        
    config = load_config()
    vac_text = vac.get("description", "").strip()
    target_country = vac.get("target_country", "Any")
    
    messages_payload = list(history)
    messages_payload.append({"role": "user", "content": message})
    
    res = chat_refine_search_query(
        history=messages_payload,
        vacancy_text=vac_text,
        current_query=current_query,
        target_country=target_country,
        config=config
    )
    
    return jsonify({
        "success": True,
        "reply": res.get("reply", ""),
        "search_query": res.get("search_query", current_query),
        "target_country": res.get("target_country", target_country),
        "tips": res.get("tips", [])
    })

@app.route("/api/vacancies/<int:vacancy_id>/run-search", methods=["POST"])
def api_run_search_vacancy(vacancy_id: int):
    """Triggers or safely enqueues AI sourcing search for a specific vacancy."""
    vac = get_vacancy_by_id(vacancy_id)
    if not vac:
        return jsonify({"success": False, "error": "Vacancy not found"}), 404
        
    data = request.get_json() or {}
    target_count = data.get("target_count", 5)
    custom_query = data.get("custom_query")
    try:
        target_count = int(target_count)
    except ValueError:
        target_count = 5
        
    enqueue_res = queue_manager.enqueue(vacancy_id, target_count, vac["title"], custom_query=custom_query)
    
    return jsonify({
        "success": True,
        "status": enqueue_res["status"],
        "position": enqueue_res["position"],
        "message": f"AI Sourcing for '{vac['title']}' {'started' if enqueue_res['status'] == 'queued' and enqueue_res['position'] == 1 and not queue_manager.active_job else 'added to queue (Position #' + str(enqueue_res['position']) + ')'}",
        "target_count": target_count
    })

@app.route("/api/vacancies/<int:vacancy_id>/cancel-search", methods=["POST"])
def api_cancel_search_vacancy(vacancy_id: int):
    """Cancels or dequeues a sourcing job."""
    res = queue_manager.cancel_job(vacancy_id)
    if res.get("success"):
        return jsonify({"success": True, "message": "Sourcing job cancelled / removed from queue"})
    return jsonify({"success": True, "message": "No active or queued search to cancel"})

@app.route("/api/sourcing/cancel-all", methods=["POST"])
def api_cancel_all_sourcing():
    """Cancels all active searches and empties the queue."""
    queue_manager.cancel_all()
    return jsonify({"success": True, "message": "All sourcing tasks cancelled and queue cleared"})

@app.route("/api/vacancies/<int:vacancy_id>/search-status", methods=["GET"])
def api_get_search_status(vacancy_id: int):
    """Returns current search progress, matched candidates stream, discarded profiles, and logs."""
    job = sourcing_jobs.get(vacancy_id, {
        "running": False,
        "paused": False,
        "queued": False,
        "cancelled": False,
        "progress": 0,
        "target": 5,
        "message": "Idle",
        "logs": [],
        "matched_candidates": [],
        "discarded_candidates": [],
        "discard_stats": {"location_mismatch": 0, "error": 0, "low_score": 0, "total_discarded": 0},
        "custom_query": ""
    })
    
    running = job.get("running", False)
    paused = job.get("paused", False)
    queued = job.get("queued", False)
    cancelled = job.get("cancelled", False)
    error = job.get("error")
    progress = job.get("progress", 0)
    target = max(1, job.get("target", 5))
    
    if running and paused:
        status = "paused"
    elif running:
        status = "running"
    elif queued:
        status = "queued"
    elif cancelled:
        status = "cancelled"
    elif error:
        status = "error"
    elif progress > 0 or job.get("logs"):
        status = "completed"
    else:
        status = "idle"
        
    pct = int((progress / target) * 100) if target else 0
    
    matched_cands = job.get("matched_candidates", [])
    discarded_cands = job.get("discarded_candidates", [])
    discard_stats = job.get("discard_stats", {"location_mismatch": 0, "error": 0, "low_score": 0, "total_discarded": len(discarded_cands)})
    
    enriched_job = {
        "vacancy_id": vacancy_id,
        "title": job.get("title", ""),
        "status": status,
        "running": running,
        "is_paused": paused,
        "queued": queued,
        "cancelled": cancelled,
        "progress_pct": min(100, max(6 if running else 0, pct)),
        "evaluated_count": progress,
        "target_count": target,
        "current_step": job.get("message", "Processing..."),
        "logs": job.get("logs", []),
        "error": job.get("error"),
        "custom_query": job.get("custom_query", ""),
        "matched_candidates": matched_cands,
        "discarded_candidates": discarded_cands,
        "discard_stats": discard_stats
    }
    return jsonify({"success": True, "job": enriched_job})

@app.route("/api/vacancies/<int:vacancy_id>/pause-search", methods=["POST"])
def api_pause_search_vacancy(vacancy_id: int):
    """Pauses the active sourcing search in-flight without losing progress or terminating."""
    job = sourcing_jobs.get(vacancy_id)
    if not job or not job.get("running"):
        return jsonify({"success": False, "error": "No active running sourcing task for this requisition"}), 400
        
    job["paused"] = True
    if "pause_event" in job and job["pause_event"]:
        job["pause_event"].clear()
        
    job["message"] = f"AI Sourcing paused by recruiter ({job.get('progress', 0)}/{job.get('target', 5)} evaluated). Ready for query refinement."
    if "logs" in job:
        job["logs"].append("⏸️ [Action] Sourcing paused by recruiter for refinement.")
        
    return jsonify({
        "success": True,
        "message": "AI Sourcing paused",
        "current_query": job.get("custom_query", ""),
        "progress": job.get("progress", 0),
        "target": job.get("target", 5),
        "discard_stats": job.get("discard_stats", {}),
        "discarded_samples": job.get("discarded_candidates", [])[-10:]
    })

@app.route("/api/vacancies/<int:vacancy_id>/resume-search", methods=["POST"])
def api_resume_search_vacancy(vacancy_id: int):
    """Resumes a paused sourcing task, optionally applying an updated boolean query in-flight."""
    job = sourcing_jobs.get(vacancy_id)
    if not job or not job.get("running"):
        return jsonify({"success": False, "error": "No active sourcing task to resume"}), 400
        
    data = request.get_json() or {}
    new_query = data.get("custom_query")
    if new_query and new_query.strip():
        job["custom_query"] = new_query.strip()
        if "logs" in job:
            job["logs"].append(f"🔄 [Copilot] Query updated in-flight: {new_query.strip()}")
            
    job["paused"] = False
    if "pause_event" in job and job["pause_event"]:
        job["pause_event"].set()
        
    job["message"] = f"Resuming AI sourcing with updated parameters ({job.get('progress', 0)}/{job.get('target', 5)} evaluated)..."
    if "logs" in job:
        job["logs"].append("▶️ [Action] Sourcing resumed.")
        
    return jsonify({
        "success": True,
        "message": "AI Sourcing resumed",
        "current_query": job.get("custom_query", ""),
        "progress": job.get("progress", 0),
        "target": job.get("target", 5)
    })

@app.route("/api/copilot/diagnose-search", methods=["POST"])
def api_copilot_diagnose_search():
    """Diagnoses search issues from discarded candidate profiles in the active or recent run."""
    data = request.get_json() or {}
    vacancy_id = data.get("vacancy_id")
    if not vacancy_id:
        return jsonify({"success": False, "error": "vacancy_id is required"}), 400
        
    vac = get_vacancy_by_id(vacancy_id)
    if not vac:
        return jsonify({"success": False, "error": "Vacancy not found"}), 404
        
    job = sourcing_jobs.get(vacancy_id, {})
    current_query = data.get("current_query") or job.get("custom_query") or ""
    discarded_samples = job.get("discarded_candidates", [])
    target_country = vac.get("target_country", "Any")
    
    config = load_config()
    vac_text = vac.get("description", "").strip()
    
    if not current_query:
        analysis = generate_search_query(vac_text, config)
        current_query = analysis.get("search_query", "")
        
    diag_res = diagnose_sourcing_issues(
        vacancy_text=vac_text,
        current_query=current_query,
        target_country=target_country,
        discarded_samples=discarded_samples,
        config=config
    )
    
    return jsonify({
        "success": True,
        "reply": diag_res.get("reply", ""),
        "search_query": diag_res.get("search_query", current_query),
        "target_country": diag_res.get("target_country", target_country),
        "tips": diag_res.get("tips", []),
        "discard_count": len(discarded_samples)
    })

@app.route("/api/sourcing/active-jobs", methods=["GET"])
def api_get_active_sourcing_jobs():
    """Returns all currently active and queued sourcing tasks."""
    queue_status = queue_manager.get_status()
    # Backward compatibility dictionary
    active_dict = {}
    if queue_status.get("active_job"):
        aj = queue_status["active_job"]
        active_dict[aj["vacancy_id"]] = aj
        
    return jsonify({
        "success": True,
        "active_jobs": active_dict,
        "active_job": queue_status.get("active_job"),
        "queued_jobs": queue_status.get("queued_jobs", []),
        "total_in_progress": queue_status.get("total_in_progress", 0)
    })


@app.route("/api/candidates", methods=["POST"])
def api_create_candidate():
    """Manually creates or adds a candidate profile to a specific vacancy."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    linkedin_url = data.get("linkedin_url", "").strip()
    vacancy_id = data.get("vacancy_id")
    
    if not name:
        return jsonify({"success": False, "error": "Candidate name is required"}), 400
    if not linkedin_url:
        return jsonify({"success": False, "error": "LinkedIn URL is required"}), 400
        
    # Format LinkedIn URL if user entered profile handle or partial URL
    if not linkedin_url.startswith("http://") and not linkedin_url.startswith("https://"):
        if "linkedin.com" in linkedin_url:
            linkedin_url = f"https://{linkedin_url}"
        else:
            clean_handle = linkedin_url.strip("/@")
            linkedin_url = f"https://www.linkedin.com/in/{clean_handle}/"
            
    vacancy_title = "General"
    target_country = "Any"
    if vacancy_id:
        vac = get_vacancy_by_id(vacancy_id)
        if vac:
            vacancy_title = vac["title"]
            target_country = vac.get("target_country", "Any")
            
    # Default score logic for manual creation
    try:
        score = int(data.get("score", 85))
    except (ValueError, TypeError):
        score = 85
        
    score = max(0, min(100, score))
    
    # Location compatibility default
    location = data.get("location", "").strip()
    loc_compatible = bool(data.get("location_compatible", True))
    if "location_compatible" not in data and target_country and target_country not in ("Any", "Remote", "") and location:
        loc_compatible = target_country.lower() in location.lower()
        
    candidate_dict = {
        "vacancy_id": vacancy_id,
        "vacancy": vacancy_title,
        "name": name,
        "linkedin_url": linkedin_url,
        "headline": data.get("headline", "").strip() or f"Candidate for {vacancy_title}",
        "location": location or target_country or "Remote",
        "open_to_work": bool(data.get("open_to_work", True)),
        "location_compatible": loc_compatible,
        "score": score,
        "status": data.get("status", "new"),
        "notes": data.get("notes", "").strip(),
        "evaluation_summary": data.get("evaluation_summary", "").strip() or data.get("notes", "").strip() or f"Manually added candidate for {vacancy_title}.",
        "suggested_message": data.get("suggested_message", "").strip(),
        "about": data.get("about", "").strip(),
        "experience": data.get("experience", "").strip(),
        "skills": data.get("skills", "").strip()
    }
    
    cand_id = upsert_candidate(candidate_dict)
    if cand_id > 0:
        saved_cand = get_candidate_by_id(cand_id)
        return jsonify({
            "success": True,
            "message": f"Candidate '{name}' successfully added to {vacancy_title}",
            "candidate": saved_cand,
            "candidate_id": cand_id
        }), 201
    else:
        return jsonify({"success": False, "error": "Failed to save candidate to database"}), 500

@app.route("/api/candidates/<int:candidate_id>", methods=["GET"])
def api_get_candidate(candidate_id: int):
    """Retrieves single candidate full details."""
    cand = get_candidate_by_id(candidate_id)
    if not cand:
        return jsonify({"success": False, "error": "Candidate not found"}), 404
    return jsonify({"success": True, "candidate": cand})

@app.route("/api/candidates/<int:candidate_id>", methods=["PATCH"])
def api_update_candidate(candidate_id: int):
    """Updates status, notes, or outreach message for a candidate."""
    data = request.get_json() or {}
    updated = False
    
    if "status" in data:
        if update_candidate_status(candidate_id, data["status"]):
            updated = True
            
    if "notes" in data:
        if update_candidate_notes(candidate_id, data["notes"]):
            updated = True
            
    if "suggested_message" in data:
        if update_candidate_message(candidate_id, data["suggested_message"]):
            updated = True
            
    if updated:
        cand = get_candidate_by_id(candidate_id)
        return jsonify({"success": True, "candidate": cand})
    return jsonify({"success": False, "error": "No updates applied or invalid parameters"}), 400

@app.route("/api/candidates/<int:candidate_id>/restore", methods=["POST"])
def api_restore_candidate(candidate_id: int):
    """Restores a discarded candidate to active pipeline (score >= 60, location_compatible = 1, status = 'new')."""
    if restore_candidate_to_pipeline(candidate_id):
        cand = get_candidate_by_id(candidate_id)
        return jsonify({"success": True, "candidate": cand, "message": "Candidate restored to active pipeline"})
    return jsonify({"success": False, "error": "Candidate not found"}), 404

@app.route("/api/candidates/<int:candidate_id>", methods=["DELETE"])
def api_delete_candidate(candidate_id: int):
    """Deletes a candidate record."""
    if delete_candidate(candidate_id):
        return jsonify({"success": True, "message": "Candidate deleted"})
    return jsonify({"success": False, "error": "Candidate not found"}), 404

@app.route("/api/candidates/<int:candidate_id>/generate-message", methods=["POST"])
def api_generate_message(candidate_id: int):
    """Generates or regenerates an outreach message using Ollama/LLM."""
    cand = get_candidate_by_id(candidate_id)
    if not cand:
        return jsonify({"success": False, "error": "Candidate not found"}), 404
        
    config = load_config()
    
    # Retrieve vacancy description from SQLite database
    vac_text = ""
    vac_id = cand.get("vacancy_id")
    if vac_id:
        vac = get_vacancy_by_id(vac_id)
        if vac:
            vac_text = vac.get("description", "")
            
    if not vac_text and cand.get("vacancy"):
        # Fallback to query by vacancy title
        all_vacs = get_vacancies()
        clean_name = cand.get("vacancy", "").replace(".txt", "").strip()
        for v in all_vacs:
            if v.get("title") == clean_name or clean_name in v.get("title", ""):
                vac_text = v.get("description", "")
                break
                
    generated_msg = generate_outreach_message_llm(cand, vacancy_text=vac_text, config=config)
    update_candidate_message(candidate_id, generated_msg)
    
    return jsonify({"success": True, "suggested_message": generated_msg})

@app.route("/api/candidates/<int:candidate_id>/reevaluate", methods=["POST"])
def api_reevaluate_candidate(candidate_id: int):
    """Re-evaluates a candidate's profile against their vacancy description using Ollama."""
    cand = get_candidate_by_id(candidate_id)
    if not cand:
        return jsonify({"success": False, "error": "Candidate not found"}), 404
        
    config = load_config()
    vac_text = ""
    target_country = "Any"
    vac_id = cand.get("vacancy_id")
    if vac_id:
        vac = get_vacancy_by_id(vac_id)
        if vac:
            vac_text = vac.get("description", "")
            target_country = vac.get("target_country", "Any")
            
    if not vac_text and cand.get("vacancy"):
        all_vacs = get_vacancies()
        clean_name = cand.get("vacancy", "").replace(".txt", "").strip()
        for v in all_vacs:
            if v.get("title") == clean_name or clean_name in v.get("title", ""):
                vac_text = v.get("description", "")
                target_country = v.get("target_country", "Any")
                break
                
    if not vac_text:
        return jsonify({"success": False, "error": "Vacancy description not found for this candidate"}), 400
        
    profile_data = {
        "url": cand.get("linkedin_url", ""),
        "name": cand.get("name", "Candidate"),
        "headline": cand.get("headline", ""),
        "location": cand.get("location", ""),
        "about": cand.get("about", ""),
        "experience": cand.get("experience", ""),
        "skills": cand.get("skills", ""),
        "raw_text": f"{cand.get('headline', '')} {cand.get('about', '')} {cand.get('experience', '')} {cand.get('skills', '')}".strip(),
        "open_to_work_detected": bool(cand.get("open_to_work", False)),
        "open_to_work_source": "Database record" if cand.get("open_to_work") else "",
        "status": "success"
    }
    
    eval_res = evaluate_candidate(profile_data, vac_text, config)
    
    cand["score"] = eval_res["match_score"]
    cand["technical_score"] = eval_res["technical_score"]
    cand["experience_score"] = eval_res["experience_score"]
    cand["auxiliary_score"] = eval_res["auxiliary_score"]
    cand["open_to_work"] = eval_res["open_to_work"]
    cand["evaluation_summary"] = eval_res["evaluation_summary"]
    if eval_res.get("suggested_message"):
        cand["suggested_message"] = eval_res["suggested_message"]
        
    cand_loc = cand.get("location", "")
    if target_country and target_country not in ("Any", "Remote", "") and cand_loc:
        cand["location_compatible"] = target_country.lower() in cand_loc.lower()
    else:
        cand["location_compatible"] = True
        
    if cand.get("status") in ("discarded", "location_mismatch") and cand["score"] > 0:
        cand["status"] = "new"
        
    upsert_candidate(cand)
    updated_cand = get_candidate_by_id(candidate_id)
    return jsonify({"success": True, "candidate": updated_cand, "message": "Candidate re-evaluated successfully"})

@app.route("/api/vacancies/<int:vacancy_id>/reevaluate-candidates", methods=["POST"])
def api_reevaluate_vacancy_candidates(vacancy_id: int):
    """Re-evaluates discarded or unviable candidates for a specific vacancy using Ollama."""
    vac = get_vacancy_by_id(vacancy_id)
    if not vac:
        return jsonify({"success": False, "error": "Vacancy not found"}), 404
        
    vac_text = vac.get("description", "")
    if not vac_text:
        return jsonify({"success": False, "error": "Vacancy has no description"}), 400
        
    target_country = vac.get("target_country", "Any")
    config = load_config()
    
    data = request.get_json() or {}
    only_discarded = data.get("only_discarded", True)
    only_zero_scores = data.get("only_zero_scores", False)
    
    candidates = get_candidates(vacancy_id=vacancy_id, hide_location_mismatch=False)
    reevaluated_count = 0
    upgraded_count = 0
    unchanged_count = 0
    
    for cand in candidates:
        old_score = cand.get("score", 0)
        is_discarded = (old_score < 60) or (cand.get("status") in ("discarded", "location_mismatch")) or (not cand.get("location_compatible", True))
        
        if only_zero_scores and old_score > 0 and not is_discarded:
            continue
        elif only_discarded and not is_discarded:
            continue
            
        profile_data = {
            "url": cand.get("linkedin_url", ""),
            "name": cand.get("name", "Candidate"),
            "headline": cand.get("headline", ""),
            "location": cand.get("location", ""),
            "about": cand.get("about", ""),
            "experience": cand.get("experience", ""),
            "skills": cand.get("skills", ""),
            "raw_text": f"{cand.get('headline', '')} {cand.get('about', '')} {cand.get('experience', '')} {cand.get('skills', '')}".strip(),
            "open_to_work_detected": bool(cand.get("open_to_work", False)),
            "open_to_work_source": "Database record" if cand.get("open_to_work") else "",
            "status": "success"
        }
        
        eval_res = evaluate_candidate(profile_data, vac_text, config)
        new_score = eval_res.get("match_score", 0)
        
        cand["score"] = new_score
        cand["technical_score"] = eval_res.get("technical_score", 0)
        cand["experience_score"] = eval_res.get("experience_score", 0)
        cand["auxiliary_score"] = eval_res.get("auxiliary_score", 0)
        cand["open_to_work"] = eval_res.get("open_to_work", False)
        cand["evaluation_summary"] = eval_res.get("evaluation_summary", "")
        if eval_res.get("suggested_message"):
            cand["suggested_message"] = eval_res["suggested_message"]
            
        cand_loc = cand.get("location", "")
        if target_country and target_country not in ("Any", "Remote", "") and cand_loc:
            cand["location_compatible"] = target_country.lower() in cand_loc.lower()
        else:
            cand["location_compatible"] = True
            
        if new_score >= 60 and cand.get("location_compatible", True):
            if cand.get("status") in ("discarded", "location_mismatch"):
                cand["status"] = "new"
            if old_score < 60:
                upgraded_count += 1
            else:
                unchanged_count += 1
        else:
            unchanged_count += 1
            
        upsert_candidate(cand)
        reevaluated_count += 1
        
    msg = f"AI re-evaluated {reevaluated_count} candidate(s): {upgraded_count} upgraded to viable pipeline (≥60%), {unchanged_count} confirmed unsuitable." if reevaluated_count > 0 else "No discarded candidate profiles found to re-evaluate."
    return jsonify({
        "success": True,
        "count": reevaluated_count,
        "upgraded_count": upgraded_count,
        "unchanged_count": unchanged_count,
        "message": msg
    })

@app.route("/api/vacancies/<int:vacancy_id>/discard-insights", methods=["GET"])
def api_get_discard_insights(vacancy_id: int):
    """Analyzes discarded profiles to extract common disqualification trends and actionable suggestions."""
    vac = get_vacancy_by_id(vacancy_id)
    if not vac:
        return jsonify({"success": False, "error": "Vacancy not found"}), 404
        
    target_country = vac.get("target_country", "Any")
    candidates = get_candidates(vacancy_id=vacancy_id, hide_location_mismatch=False)
    
    discarded = [c for c in candidates if (c.get("score", 0) < 60) or not c.get("location_compatible", True) or c.get("status") in ("discarded", "location_mismatch")]
    total = len(discarded)
    
    if total < 2:
        return jsonify({"success": True, "has_insight": False, "total_discarded": total})
        
    # Analyze location mismatch
    loc_mismatches = [c for c in discarded if not c.get("location_compatible", True)]
    loc_pct = round((len(loc_mismatches) / total) * 100) if total > 0 else 0
    
    # Analyze common patterns in evaluation summary / headlines
    non_tech_count = sum(1 for c in discarded if any(kw in (c.get("headline", "") + " " + c.get("evaluation_summary", "")).lower() for kw in ["recruiter", "talent", "hr", "sales", "account executive", "marketing"]))
    non_tech_pct = round((non_tech_count / total) * 100) if total > 0 else 0
    
    low_tech_count = sum(1 for c in discarded if c.get("technical_score", 0) <= 20)
    low_tech_pct = round((low_tech_count / total) * 100) if total > 0 else 0
    
    if target_country and target_country not in ("Any", "Remote", "") and loc_pct >= 35:
        insight_title = "Geographic Trend Alert"
        insight_text = f"{loc_pct}% of discarded profiles ({len(loc_mismatches)}/{total}) were outside target region ({target_country})."
        recommendation = f"Add '\"{target_country}\"' or specific cities in Copilot query to narrow location targeting."
    elif non_tech_pct >= 25:
        insight_title = "Non-Engineering Profiles Detected"
        insight_text = f"{non_tech_pct}% of discarded profiles were in non-technical or recruiting fields."
        recommendation = "Add negative boolean terms (e.g. -recruiter -talent -sales) in Sourcing Copilot."
    elif low_tech_pct >= 40:
        insight_title = "Core Tech Stack Mismatch"
        insight_text = f"{low_tech_pct}% of discarded profiles lacked primary technical skills from the job description."
        recommendation = "Refine search query with exact-match quotes around critical required technologies."
    else:
        insight_title = "Sourcing Pattern"
        insight_text = f"{total} candidates were reviewed and scored below the 60% match threshold."
        recommendation = "Use Copilot AI to generate alternative title synonyms or adjust seniority filters."
        
    return jsonify({
        "success": True,
        "has_insight": True,
        "total_discarded": total,
        "insight_title": insight_title,
        "insight_text": insight_text,
        "recommendation": recommendation
    })

@app.route("/api/stats", methods=["GET"])
def api_get_stats():
    """Returns general metrics."""
    stats = get_stats()
    return jsonify({"success": True, "stats": stats})

def start_dashboard(host: str = "127.0.0.1", port: int = 5000, open_browser: bool = True, debug: bool = False):
    """Starts the Flask web dashboard and opens the browser."""
    init_db()

    url = f"http://{host}:{port}"
    print("\n" + "=" * 65)
    print(f"       REFERLOOKER - WEB ATS & KANBAN DASHBOARD")
    print(f"       Access URL: {url}")
    print("=" * 65 + "\n")

    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    app.run(host=host, port=port, debug=debug, use_reloader=False)

if __name__ == "__main__":
    start_dashboard(open_browser=True, debug=True)
