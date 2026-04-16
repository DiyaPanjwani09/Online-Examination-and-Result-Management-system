from flask import Blueprint, render_template, request, redirect, url_for, session, flash, Response, jsonify
from database import get_connection
from datetime import datetime
import os
from dotenv import load_dotenv
import random

faculty_bp = Blueprint('faculty_bp', __name__)

# Load environment variables from .env file
load_dotenv()

# LLM Configuration — FEATURE ON HOLD
# Stub fallbacks while Gemini feature is on hold
def estimate_difficulty_llm(text):
    """Stub: returns 'medium' while Gemini feature is on hold."""
    return "medium"

def select_questions_llm(exam_name, candidates, count, difficulty):
    """Stub: returns random selection while Gemini feature is on hold."""
    return random.sample([c["id"] for c in candidates], min(len(candidates), count))

def _process_questions_csv(subject_id, file, forced_difficulty=None):
    """Helper to process question CSV and return list of (question_id, section) tuples."""
    from io import StringIO
    import csv
    
    # Read the file content
    content = file.stream.read().decode("UTF8")
    stream = StringIO(content, newline=None)
    csv_input = csv.DictReader(stream)
    
    conn = get_connection()
    cursor = conn.cursor()
    processed_data = [] # List of tuples: (q_id, section)
    
    for row in csv_input:
        # Flexible column mapping
        q_text = (row.get('questions') or row.get('question_text') or row.get('question') or '').strip()
        marks = int(row.get('marks', 1))
        section = row.get('section', 'A').strip().upper()
        if section not in ['A', 'B', 'C']: section = 'A'
        
        # Priority order: forced_difficulty > 'difficulty' column > 'level of difficulty' column > default 'medium'
        difficulty = forced_difficulty
        if not difficulty:
            difficulty = (row.get('difficulty') or row.get('level of difficulty') or '').strip().lower()
            
        if difficulty not in ['easy', 'medium', 'hard']:
            difficulty = 'medium'
        
        if not q_text: continue
        
        cursor.execute("INSERT INTO questions (subject_id, question_text, question_type, marks, difficulty) VALUES (%s, %s, 'MCQ', %s, %s) RETURNING id", 
                       (subject_id, q_text, marks, difficulty))
        q_id = cursor.fetchone()["id"]
        processed_data.append((q_id, section))
        
        # Option mapping
        correct = row.get('correct answer') or row.get('correct_option') or row.get('answer') or '1'
        
        for i in range(1, 5):
            opt_text = (row.get(f'option{i}') or row.get(f'option_{i}') or '').strip()
            if opt_text:
                is_correct = 1 if str(correct) == str(i) or str(correct).strip() == opt_text else 0
                cursor.execute("INSERT INTO options (question_id, option_text, is_correct) VALUES (%s, %s, %s)", (q_id, opt_text, is_correct))
    
    conn.commit()
    conn.close()
    return processed_data


@faculty_bp.route("/faculty/dashboard")
def faculty_dashboard():
    if not session.get("user_id"):
        return redirect(url_for("auth_bp.faculty_login"))
    if session.get("role") == "student":
        return redirect(url_for("student_bp.student_dashboard"))
    if session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))
    
    session.pop('_flashes', None) # Clear any leftover login error flashes

    conn = get_connection()
    _cur = conn.cursor()
    _cur.execute("SELECT * FROM faculty_details WHERE user_id = %s", (session["user_id"],))
    faculty = _cur.fetchone()

    if not faculty:
        conn.close()
        flash("Faculty profile not found. Please contact administration.", "danger")
        session.clear()
        return redirect(url_for("auth_bp.faculty_login"))

    _cur.execute("SELECT COUNT(*) as count FROM student_details")
    total_students = _cur.fetchone()["count"]
    
    _cur.execute("SELECT id, subject_name, branch, semester FROM subjects WHERE faculty_id = %s", (faculty["id"],))
    subjects = _cur.fetchall()
    subject_ids = [s["id"] for s in subjects]

    active_exams_count = 0
    recent_exams = []
    pending_results = 0
    total_results = 0
    recent_activity = []
    score_dist = {"excellent": 0, "passed": 0, "failed": 0}
    at_risk_students = []
    class_avg = 0.0

    if subject_ids:
        placeholders = ','.join('%s' for _ in subject_ids)
        _cur.execute(f"SELECT COUNT(*) as count FROM exams WHERE subject_id IN ({placeholders})", tuple(subject_ids))
        active_exams_count = _cur.fetchone()["count"]

        _cur.execute(f"""
            SELECT e.course_code, e.exam_name, e.exam_date, e.total_marks, e.duration_minutes,
                   s.id AS subject_id, s.subject_name, s.branch, s.semester,
                   e.pass_percentage,
                   (SELECT COUNT(*) FROM exam_attempts ea2 WHERE ea2.course_code = e.course_code AND ea2.completed = 1) AS attempt_count,
                   (SELECT COUNT(*) FROM questions WHERE subject_id = s.id) AS question_count
            FROM exams e
            JOIN subjects s ON e.subject_id = s.id
            WHERE e.subject_id IN ({placeholders})
            ORDER BY e.exam_date DESC LIMIT 5
        """, tuple(subject_ids))
        recent_exams = _cur.fetchall()

        _cur.execute(f"""
            SELECT COUNT(*) as count FROM exam_attempts ea
            JOIN exams e ON ea.course_code = e.course_code
            WHERE e.subject_id IN ({placeholders}) AND ea.completed = 1
        """, tuple(subject_ids))
        total_results = _cur.fetchone()["count"]

        _cur.execute(f"""
            SELECT COUNT(DISTINCT e.course_code) as count FROM exams e
            JOIN exam_attempts ea ON e.course_code = ea.course_code
            WHERE e.subject_id IN ({placeholders}) AND ea.completed = 1
        """, tuple(subject_ids))
        exams_with_attempts = _cur.fetchone()["count"]
        pending_results = max(0, active_exams_count - exams_with_attempts)

        _cur.execute(f"""
            SELECT sd.full_name, e.exam_name, ea.score, e.total_marks, ea.completed, s.subject_name
            FROM exam_attempts ea
            JOIN student_details sd ON ea.enrollment_no = sd.enrollment_no
            JOIN exams e ON ea.course_code = e.course_code
            JOIN subjects s ON e.subject_id = s.id
            WHERE e.subject_id IN ({placeholders})
            ORDER BY ea.id DESC LIMIT 8
        """, tuple(subject_ids))
        recent_activity = _cur.fetchall()

        # Score distribution for charts
        _cur.execute(f"""
            SELECT ea.score, e.total_marks
            FROM exam_attempts ea
            JOIN exams e ON ea.course_code = e.course_code
            WHERE e.subject_id IN ({placeholders}) AND ea.completed = 1 AND e.total_marks > 0
        """, tuple(subject_ids))
        all_scores = _cur.fetchall()

        total_pct_sum = 0.0
        for row in all_scores:
            pct = (row["score"] / row["total_marks"]) * 100
            total_pct_sum += pct
            if pct >= 75:
                score_dist["excellent"] += 1
            elif pct >= 40:
                score_dist["passed"] += 1
            else:
                score_dist["failed"] += 1

        if all_scores:
            class_avg = round(total_pct_sum / len(all_scores), 1)

        # At-risk students (last attempt score < 40%)
        _cur.execute(f"""
            SELECT sd.full_name, sd.enrollment_no, ea.score, e.total_marks, e.exam_name, s.subject_name,
                   ROUND(CAST(ea.score AS FLOAT)/e.total_marks*100, 1) AS pct
            FROM exam_attempts ea
            JOIN student_details sd ON ea.enrollment_no = sd.enrollment_no
            JOIN exams e ON ea.course_code = e.course_code
            JOIN subjects s ON e.subject_id = s.id
            WHERE e.subject_id IN ({placeholders}) AND ea.completed = 1 AND e.total_marks > 0
              AND CAST(ea.score AS FLOAT)/e.total_marks*100 < 40
            ORDER BY pct ASC LIMIT 5
        """, tuple(subject_ids))
        at_risk_raw = _cur.fetchall()
        at_risk_students = [dict(r) for r in at_risk_raw]

    conn.close()
    return render_template("faculty_dashboard.html",
        faculty=dict(faculty),
        total_students=total_students,
        active_exams=active_exams_count,
        recent_exams=[dict(r) for r in recent_exams],
        subjects=[dict(r) for r in subjects],
        pending_results=pending_results,
        total_results=total_results,
        recent_activity=[dict(r) for r in recent_activity],
        score_dist=score_dist,
        at_risk_students=at_risk_students,
        class_avg=class_avg,
    )

@faculty_bp.route("/faculty/exams")
def faculty_exams():
    if not session.get("user_id") or session.get("role") != "faculty":
        flash("Please login first.", "danger")
        return redirect(url_for("auth_bp.faculty_login"))

    conn = get_connection()
    _cur = conn.cursor()
    _cur.execute("SELECT * FROM faculty_details WHERE user_id = %s", (session["user_id"],))
    faculty = _cur.fetchone()
    if not faculty:
        conn.close()
        return redirect(url_for("auth_bp.faculty_login"))
        
    _cur.execute("SELECT id, subject_name, branch, semester FROM subjects WHERE faculty_id = %s", (faculty["id"],))
    subjects = _cur.fetchall()
    subject_ids = [s["id"] for s in subjects]

    all_exams = []
    if subject_ids:
        placeholders = ','.join('%s' for _ in subject_ids)
        _cur.execute(f"""
            SELECT e.course_code, e.exam_name, e.exam_date, e.start_time, e.end_time, e.total_marks, e.duration_minutes,
                   e.pass_percentage,
                   s.id AS subject_id, s.subject_name, s.branch, s.semester, s.subject_code,
                   (SELECT COUNT(*) FROM exam_attempts ea WHERE ea.course_code = e.course_code AND ea.completed = 1) AS attempt_count,
                   (SELECT COUNT(*) FROM exam_questions eq WHERE eq.course_code = e.course_code) AS question_count
            FROM exams e
            JOIN subjects s ON e.subject_id = s.id
            WHERE e.subject_id IN ({placeholders})
            ORDER BY e.exam_date DESC
        """, tuple(subject_ids))
        all_exams_raw = _cur.fetchall()
        
        for e in all_exams_raw:
            ed = dict(e)
            # Fetch difficulty breakdown for this specific exam
            _cur.execute("""
                SELECT 
                    SUM(CASE WHEN q.difficulty = 'easy' THEN 1 ELSE 0 END) as easy_q,
                    SUM(CASE WHEN q.difficulty = 'medium' THEN 1 ELSE 0 END) as medium_q,
                    SUM(CASE WHEN q.difficulty = 'hard' THEN 1 ELSE 0 END) as hard_q,
                    SUM(CASE WHEN q.difficulty IS NULL OR q.difficulty = '' OR q.difficulty = 'error_api' OR q.difficulty = 'error_no_key' THEN 1 ELSE 0 END) as unknown_q
                FROM exam_questions eq
                JOIN questions q ON eq.question_id = q.id
                WHERE eq.course_code = %s
            """, (e["course_code"],))
            diff_stats = _cur.fetchone()
            
            ed["difficulty_dist"] = {
                "easy": diff_stats["easy_q"] or 0,
                "medium": diff_stats["medium_q"] or 0,
                "hard": diff_stats["hard_q"] or 0,
                "unknown": diff_stats["unknown_q"] or 0
            }
            all_exams.append(ed)

    conn.close()
    return render_template("faculty_exams.html", faculty=faculty, subjects=subjects, all_exams=all_exams)

@faculty_bp.route("/faculty/create_exam", methods=["POST"])
def create_exam():
    if not session.get("user_id") or session.get("role") != "faculty":
        flash("Please login first.", "danger")
        return redirect(url_for("auth_bp.faculty_login"))
        
    subject_id = request.form.get("subject_id")
    course_code = request.form.get("course_code")
    exam_name = request.form.get("exam_name", "").strip()
    total_marks = request.form.get("total_marks", 100, type=int)
    duration = request.form.get("duration", 60, type=int)
    pass_percentage = request.form.get("pass_percentage", 40, type=int)
    
    if not course_code:
        flash("Course Code is required.", "danger")
        return redirect(url_for("faculty_bp.faculty_exams"))
    
    exam_date_input = request.form.get("exam_date", "").strip()
    start_time = request.form.get("start_time", "").strip()
    end_time = request.form.get("end_time", "").strip()
    
    auto_easy = request.form.get("auto_easy", 0, type=int)
    auto_medium = request.form.get("auto_medium", 0, type=int)
    auto_hard = request.form.get("auto_hard", 0, type=int)
    
    exam_date = exam_date_input if exam_date_input else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not subject_id or not exam_name:
        flash("Subject and Exam Name are required.", "danger")
        return redirect(url_for("faculty_bp.faculty_exams"))
        
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO exams (course_code, subject_id, exam_name, exam_date, start_time, end_time, total_marks, duration_minutes, pass_percentage)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (course_code, subject_id, exam_name, exam_date, start_time or None, end_time or None, total_marks, duration, pass_percentage))
        
        # Handle Bulk CSV Upload if present
        uploaded_info = [] # Store (q_id, section)
        if 'csv_file' in request.files:
            file = request.files['csv_file']
            if file and file.filename.endswith('.csv'):
                new_info = _process_questions_csv(subject_id, file)
                uploaded_info.extend(new_info)
                # Link uploaded questions to this exam
                for qid, section in new_info:
                    cursor.execute("INSERT INTO exam_questions (course_code, question_id, section) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (course_code, qid, section))
        
        uploaded_q_ids = [info[0] for info in uploaded_info]

        if auto_easy > 0 or auto_medium > 0 or auto_hard > 0:
            def fetch_random_q(diff, count):
                if count <= 0: return []
                exclude_ids = uploaded_q_ids if uploaded_q_ids else [-1]
                placeholders = ','.join('%s' for _ in exclude_ids)
                cursor.execute(f"SELECT id FROM questions WHERE subject_id = %s AND difficulty = %s AND id NOT IN ({placeholders})", (subject_id, diff, *exclude_ids))
                qs = cursor.fetchall()
                q_ids = [q["id"] for q in qs]
                if not q_ids: return []
                return random.sample(q_ids, min(len(q_ids), count))
                
            selected_ids = []
            selected_ids.extend(fetch_random_q("easy", auto_easy))
            selected_ids.extend(fetch_random_q("medium", auto_medium))
            selected_ids.extend(fetch_random_q("hard", auto_hard))
            
            for qid in selected_ids:
                cursor.execute("INSERT INTO exam_questions (course_code, question_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (course_code, qid))

        conn.commit()
        conn.close()
        flash("Exam created successfully!", "success")

    except Exception as e:
        flash(f"Error creating exam: {str(e)}", "danger")

    return redirect(url_for("faculty_bp.faculty_exams"))

@faculty_bp.route("/faculty/exam/delete/<string:course_code>", methods=["POST"])
def delete_exam(course_code):
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))

    conn = get_connection()
    try:
        _cur = conn.cursor()
        # Verify ownership
        _cur.execute("""
            SELECT e.course_code FROM exams e
            JOIN subjects s ON e.subject_id = s.id
            WHERE e.course_code = %s AND s.faculty_id = (SELECT id FROM faculty_details WHERE user_id = %s)
        """, (course_code, session["user_id"]))
        exam = _cur.fetchone()

        if exam:
            _cur.execute("DELETE FROM exams WHERE course_code = %s", (course_code,))
            conn.commit()
            flash("Exam deleted successfully.", "success")
        else:
            flash("Exam not found or access denied.", "danger")
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for("faculty_bp.faculty_exams"))

@faculty_bp.route("/faculty/exam/edit/<string:course_code>", methods=["POST"])
def edit_exam(course_code):
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))

    exam_name = request.form.get("exam_name", "").strip()
    total_marks = request.form.get("total_marks", 0, type=int)
    pass_percentage = request.form.get("pass_percentage", 0, type=int)
    duration_minutes = request.form.get("duration_minutes", 0, type=int)
    start_time_str = request.form.get("start_time", "").strip()
    end_time_str = request.form.get("end_time", "").strip()

    if not all([exam_name, total_marks, pass_percentage, duration_minutes, start_time_str, end_time_str]):
        flash("All fields are required.", "danger")
        return redirect(url_for("faculty_bp.faculty_exams"))

    try:
        start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M")
        end_time = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M")
    except:
         flash("Invalid date format. Use YYYY-MM-DD HH:MM", "danger")
         return redirect(url_for("faculty_bp.faculty_exams"))

    conn = get_connection()
    try:
        _cur = conn.cursor()
        # Verify ownership
        _cur.execute("""
            SELECT e.course_code FROM exams e
            JOIN subjects s ON e.subject_id = s.id
            WHERE e.course_code = %s AND s.faculty_id = (SELECT id FROM faculty_details WHERE user_id = %s)
        """, (course_code, session["user_id"]))
        exam = _cur.fetchone()

        if exam:
            _cur.execute("""
                UPDATE exams SET exam_name = %s, total_marks = %s, pass_percentage = %s, 
                                 duration_minutes = %s, start_time = %s, end_time = %s
                WHERE course_code = %s
            """, (exam_name, total_marks, pass_percentage, duration_minutes, start_time, end_time, course_code))
            conn.commit()
            flash("Exam updated successfully.", "success")
        else:
            flash("Exam not found or access denied.", "danger")
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for("faculty_bp.faculty_exams"))

@faculty_bp.route("/faculty/exam/duplicate/<string:course_code>", methods=["POST"])
def duplicate_exam(course_code):
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))
    
    conn = get_connection()
    try:
        _cur = conn.cursor()
        # Get faculty ID
        _cur.execute("SELECT id FROM faculty_details WHERE user_id = %s", (session["user_id"],))
        faculty = _cur.fetchone()
        
        # Get original exam
        _cur.execute("""
            SELECT e.* FROM exams e 
            JOIN subjects s ON e.subject_id = s.id
            WHERE e.course_code = %s AND s.faculty_id = %s
        """, (course_code, faculty["id"]))
        exam = _cur.fetchone()
        
        if not exam:
            flash("Exam not found or access denied.", "danger")
            return redirect(url_for("faculty_bp.faculty_exams"))
            
        # Create new course code
        new_code = f"{exam['course_code']}-COPY-{random.randint(100, 999)}"
        new_name = f"{exam['exam_name']} (Copy)"
        
        _cur.execute("""
            INSERT INTO exams (course_code, subject_id, exam_name, exam_date, start_time, end_time, total_marks, duration_minutes, pass_percentage)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (new_code, exam["subject_id"], new_name, exam["exam_date"], exam["start_time"], exam["end_time"], 
              exam["total_marks"], exam["duration_minutes"], exam["pass_percentage"]))
        
        # Duplicate questions
        _cur.execute("SELECT question_id, section FROM exam_questions WHERE course_code = %s", (course_code,))
        questions = _cur.fetchall()
        for q in questions:
            _cur.execute("INSERT INTO exam_questions (course_code, question_id, section) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (new_code, q["question_id"], q["section"]))
            
        conn.commit()
        flash(f"Exam duplicated as '{new_name}' with code '{new_code}'", "success")
    except Exception as e:
        flash(f"Error duplicating exam: {str(e)}", "danger")
    finally:
        conn.close()
    
    return redirect(url_for("faculty_bp.faculty_exams"))

@faculty_bp.route("/faculty/exam/<string:course_code>/blacklist_data")
def get_blacklist_data(course_code):
    if not session.get("user_id") or session.get("role") != "faculty":
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_connection()
    try:
        _cur = conn.cursor()
        # Get exam
        _cur.execute("SELECT subject_id FROM exams WHERE course_code = %s", (course_code,))
        exam = _cur.fetchone()
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        
        # Get all students enrolled in this course and their blacklist status
        _cur.execute("""
            SELECT sd.full_name, sd.enrollment_no,
                   (SELECT 1 FROM exam_blacklist eb WHERE eb.course_code = %s AND eb.enrollment_no = sd.enrollment_no) AS is_blacklisted
            FROM student_details sd
            JOIN student_subjects ss ON sd.enrollment_no = ss.enrollment_no
            WHERE ss.course_code = %s
        """, (course_code, course_code))
        students = _cur.fetchall()
        
        return jsonify([dict(s) for s in students])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@faculty_bp.route("/faculty/exam/<string:course_code>/blacklist/toggle/<string:enrollment_no>", methods=["POST"])
def toggle_blacklist(course_code, enrollment_no):
    if not session.get("user_id") or session.get("role") != "faculty":
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_connection()
    try:
        _cur = conn.cursor()
        _cur.execute("SELECT id FROM exam_blacklist WHERE course_code = %s AND enrollment_no = %s", (course_code, enrollment_no))
        eb = _cur.fetchone()
        if eb:
            _cur.execute("DELETE FROM exam_blacklist WHERE course_code = %s AND enrollment_no = %s", (course_code, enrollment_no))
            status = "removed"
        else:
            _cur.execute("INSERT INTO exam_blacklist (course_code, enrollment_no) VALUES (%s, %s)", (course_code, enrollment_no))
            status = "added"
        conn.commit()
        return jsonify({"status": "success", "new_status": status})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@faculty_bp.route("/faculty/exam/<string:course_code>/stats")
def get_exam_stats(course_code):
    if not session.get("user_id") or session.get("role") != "faculty":
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_connection()
    try:
        _cur = conn.cursor()
        _cur.execute("SELECT total_marks FROM exams WHERE course_code = %s", (course_code,))
        exam = _cur.fetchone()
        if not exam:
            return jsonify({"error": "Exam not found"}), 404
        
        tm = exam["total_marks"]
        _cur.execute("""
            SELECT ea.score, sd.full_name, sd.enrollment_no
            FROM exam_attempts ea
            JOIN student_details sd ON ea.enrollment_no = sd.enrollment_no
            WHERE ea.course_code = %s AND ea.completed = 1
        """, (course_code,))
        attempts_db = _cur.fetchall()
        
        attempts = [dict(a) for a in attempts_db]
        count = len(attempts)
        if count == 0:
            return jsonify({
                "count": 0, "avg": 0, "high": 0, "low": 0, "pass_count": 0, "fail_count": 0, "students": []
            })

        scores = [a["score"] for a in attempts]
        pcts = [round((s/tm*100), 1) if tm > 0 else 0 for s in scores]
        passed = [p for p in pcts if p >= 40]
        
        for i in range(len(attempts)):
             attempts[i]["pct"] = pcts[i]

        return jsonify({
            "count": count,
            "avg": round(sum(pcts)/count, 1),
            "high": max(pcts),
            "low": min(pcts),
            "pass_count": len(passed),
            "fail_count": count - len(passed),
            "students": attempts[:10]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@faculty_bp.route("/faculty/subject/<int:subject_id>/questions")
def manage_questions(subject_id):
    if not session.get("user_id") or session.get("role") != "faculty":
        flash("Please login first.", "danger")
        return redirect(url_for("auth_bp.faculty_login"))

    conn = get_connection()
    _cur = conn.cursor()
    _cur.execute("SELECT * FROM subjects WHERE id = %s AND faculty_id = (SELECT id FROM faculty_details WHERE user_id = %s)", (subject_id, session["user_id"]))
    subject = _cur.fetchone()
    
    if not subject:
        conn.close()
        flash("Subject not found or you don't have access.", "danger")
        return redirect(url_for("faculty_bp.faculty_exams"))

    _cur.execute("SELECT * FROM questions WHERE subject_id = %s ORDER BY id DESC", (subject_id,))
    questions_db = _cur.fetchall()
    
    questions = []
    for q in questions_db:
        _cur.execute("SELECT * FROM options WHERE question_id = %s", (q["id"],))
        options_db = _cur.fetchall()
        q_dict = dict(q)
        q_dict["options"] = [dict(o) for o in options_db]
        questions.append(q_dict)

    conn.close()
    return render_template("faculty_questions.html", subject=dict(subject), questions=questions)

@faculty_bp.route("/faculty/subject/<int:subject_id>/add_question", methods=["POST"])
def add_question(subject_id):
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))

    question_text = request.form.get("question_text", "").strip()
    marks = request.form.get("marks", 1, type=int)
    question_type = "MCQ"
    difficulty = request.form.get("difficulty", "medium").strip()
    
    if not question_text:
        flash("Question text is required.", "danger")
        return redirect(url_for("faculty_bp.manage_questions", subject_id=subject_id))
        
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO questions (subject_id, question_text, question_type, marks, difficulty)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        """, (subject_id, question_text, question_type, marks, difficulty))
        question_id = cursor.fetchone()["id"]
        
        for i in range(1, 5):
            opt_text = request.form.get(f"option_{i}", "").strip()
            is_correct = 1 if request.form.get("correct_option") == str(i) else 0
            if opt_text:
                cursor.execute("""
                    INSERT INTO options (question_id, option_text, is_correct)
                    VALUES (%s, %s, %s)
                """, (question_id, opt_text, is_correct))
                
        conn.commit()
        flash("Question added successfully!", "success")
    except Exception as e:
        flash(f"Error adding question: {str(e)}", "danger")
    finally:
        conn.close()
        
    return redirect(url_for("faculty_bp.manage_questions", subject_id=subject_id))

@faculty_bp.route("/faculty/subject/<int:subject_id>/upload_csv", methods=["POST"])
def upload_questions_subject_csv(subject_id):
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))

    conn = get_connection()
    _cur = conn.cursor()
    _cur.execute("SELECT id FROM faculty_details WHERE user_id = %s", (session["user_id"],))
    faculty = _cur.fetchone()
    
    if not faculty:
        conn.close()
        return redirect(url_for("auth_bp.faculty_login"))

    _cur.execute("SELECT * FROM subjects WHERE id = %s AND faculty_id = %s", (subject_id, faculty["id"]))
    subject = _cur.fetchone()
    
    if not subject:
        conn.close()
        flash("Subject not found or access denied.", "danger")
        return redirect(url_for("faculty_bp.faculty_exams"))

    if 'csv_file' not in request.files:
        conn.close()
        flash("No file uploaded.", "danger")
        return redirect(url_for("faculty_bp.manage_questions", subject_id=subject_id))

    file = request.files['csv_file']
    if file.filename == '':
        conn.close()
        flash("No file selected.", "danger")
        return redirect(url_for("faculty_bp.manage_questions", subject_id=subject_id))

    try:
        new_info = _process_questions_csv(subject_id, file)
        flash(f"Successfully added {len(new_info)} questions via CSV.", "success")
    except Exception as e:
        flash(f"Error processing CSV: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for("faculty_bp.manage_questions", subject_id=subject_id))

@faculty_bp.route("/faculty/students")
def faculty_students():
    if not session.get("user_id") or session.get("role") != "faculty":
        flash("Please login first.", "danger")
        return redirect(url_for("auth_bp.faculty_login"))

    conn = get_connection()
    _cur = conn.cursor()
    _cur.execute("SELECT id FROM faculty_details WHERE user_id = %s", (session["user_id"],))
    faculty = _cur.fetchone()
    if not faculty:
        conn.close()
        return redirect(url_for("auth_bp.faculty_login"))

    _cur.execute("""
        SELECT sd.full_name, sd.enrollment_no, sd.branch as student_branch, sd.semester as student_semester,
               s.subject_name, s.branch as subject_branch, e.course_code as subject_code
        FROM student_details sd
        LEFT JOIN student_subjects ss ON sd.enrollment_no = ss.enrollment_no
        LEFT JOIN exams e ON ss.course_code = e.course_code
        LEFT JOIN subjects s ON e.subject_id = s.id AND s.faculty_id = %s
        ORDER BY sd.semester ASC, sd.full_name ASC, s.subject_name ASC
    """, (faculty["id"],))
    raw_students = _cur.fetchall()
    
    student_dict = {}
    for row in raw_students:
        s_id = row['enrollment_no']
        if s_id not in student_dict:
            student_dict[s_id] = {
                'enrollment_no': s_id,
                'full_name': row['full_name'],
                'student_branch': row['student_branch'],
                'student_semester': row['student_semester'],
                'subjects': []
            }
        if row['subject_name']:
            student_dict[s_id]['subjects'].append({'name': row['subject_name'], 'code': row['subject_code']})
            
    students = []
    for s in student_dict.values():
        s['subject_name'] = ', '.join([sub['name'] for sub in s['subjects']]) if s['subjects'] else None
        s['subject_code'] = s['subjects'][0]['code'] if s['subjects'] else None
        students.append(s)
    
    _cur.execute("""
        SELECT e.course_code, s.subject_name, s.branch, s.semester 
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        WHERE s.faculty_id = %s
    """, (faculty["id"],))
    subjects = _cur.fetchall()
    
    conn.close()
    return render_template("faculty_students.html", faculty=faculty, students=students, subjects=subjects)

@faculty_bp.route("/faculty/results")
def faculty_results():
    if not session.get("user_id") or session.get("role") != "faculty":
        flash("Please login first.", "danger")
        return redirect(url_for("auth_bp.faculty_login"))

    conn = get_connection()
    _cur = conn.cursor()
    _cur.execute("SELECT * FROM faculty_details WHERE user_id = %s", (session["user_id"],))
    faculty = _cur.fetchone()
    if not faculty:
        conn.close()
        return redirect(url_for("auth_bp.faculty_login"))

    _cur.execute("""
        SELECT ea.id, e.course_code, sd.full_name, sd.enrollment_no,
               e.exam_name, e.total_marks, ea.score,
               s.subject_name, s.branch, s.semester,
               CASE WHEN e.total_marks > 0
                    THEN ROUND(CAST(ea.score AS FLOAT)/e.total_marks*100, 1)
                    ELSE 0 END AS pct
        FROM exam_attempts ea
        JOIN student_details sd ON ea.enrollment_no = sd.enrollment_no
        JOIN exams e ON ea.course_code = e.course_code
        JOIN subjects s ON e.subject_id = s.id
        WHERE s.faculty_id = %s AND ea.completed = 1
        ORDER BY e.exam_name, ea.score DESC
    """, (faculty["id"],))
    results = _cur.fetchall()

    class_avg = 0.0
    pass_rate = 0.0
    highest_score = 0.0
    lowest_score = 100.0
    score_dist = {"excellent": 0, "passed": 0, "failed": 0}

    if results:
        pcts = [r["pct"] or 0.0 for r in results]
        for p in pcts:
            if p >= 75: score_dist["excellent"] += 1
            elif p >= 40: score_dist["passed"] += 1
            else: score_dist["failed"] += 1
        class_avg = round(sum(pcts) / len(pcts), 1)
        pass_rate = round((score_dist["excellent"] + score_dist["passed"]) / len(results) * 100, 1)
        highest_score = round(max(pcts), 1)
        lowest_score = round(min(pcts), 1)

    results_dicts = [dict(r) for r in results]
    conn.close()
    return render_template("faculty_results.html",
        faculty=dict(faculty), results=results_dicts,
        class_avg=class_avg, pass_rate=pass_rate,
        highest_score=highest_score, lowest_score=lowest_score,
        score_dist=score_dist,
    )

@faculty_bp.route("/faculty/exam/report/<string:course_code>")
def exam_report(course_code):
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))

    conn = get_connection()
    try:
        _cur = conn.cursor()
        _cur.execute("""
            SELECT e.*, s.subject_name, s.branch, s.semester 
            FROM exams e
            JOIN subjects s ON e.subject_id = s.id
            WHERE e.course_code = %s AND s.faculty_id = (SELECT id FROM faculty_details WHERE user_id = %s)
        """, (course_code, session["user_id"]))
        exam = _cur.fetchone()

        if not exam:
            flash("Exam not found.", "danger")
            return redirect(url_for("faculty_bp.faculty_exams"))

        _cur.execute("""
            SELECT ea.*, sd.full_name, sd.enrollment_no
            FROM exam_attempts ea
            JOIN student_details sd ON ea.enrollment_no = sd.enrollment_no
            WHERE ea.course_code = %s AND ea.completed = 1
            ORDER BY ea.score DESC
        """, (course_code,))
        results = _cur.fetchall()
        results_dicts = [dict(r) for r in results]
        
        tm = exam["total_marks"]
        for r in results_dicts:
            r["pct"] = round((r["score"]/tm*100), 1) if tm > 0 else 0

        return render_template("faculty_exam_report.html", exam=dict(exam), results=results_dicts)
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for("faculty_bp.faculty_exams"))
    finally:
        conn.close()

@faculty_bp.route("/faculty/results/export")
def export_results_csv():
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))

    import csv as csv_module
    from io import StringIO

    conn = get_connection()
    _cur = conn.cursor()
    _cur.execute("SELECT id FROM faculty_details WHERE user_id = %s", (session["user_id"],))
    faculty = _cur.fetchone()
    if not faculty:
        conn.close()
        return redirect(url_for("auth_bp.faculty_login"))

    _cur.execute("""
        SELECT sd.full_name, sd.enrollment_no,
               e.exam_name, s.subject_name, s.branch, s.semester,
               e.total_marks, ea.score,
               CASE WHEN e.total_marks > 0
                    THEN ROUND(CAST(ea.score AS FLOAT) / e.total_marks * 100, 1)
                    ELSE 0 END AS percentage
        FROM exam_attempts ea
        JOIN student_details sd ON ea.enrollment_no = sd.enrollment_no
        JOIN exams e ON ea.course_code = e.course_code
        JOIN subjects s ON e.subject_id = s.id
        WHERE s.faculty_id = %s AND ea.completed = 1
        ORDER BY e.exam_name, ea.score DESC
    """, (faculty["id"],))
    results = _cur.fetchall()
    conn.close()

    si = StringIO()
    writer = csv_module.writer(si)
    writer.writerow(["Student Name", "Enrollment No", "Exam", "Subject", "Branch", "Semester", "Total Marks", "Score", "Percentage (%)"])
    for r in results:
        writer.writerow([r["full_name"], r["enrollment_no"], r["exam_name"],
                         r["subject_name"], r["branch"], r["semester"],
                         r["total_marks"], r["score"], r["percentage"]])

    return Response(si.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=exam_results.csv"})

@faculty_bp.route("/faculty/question/delete/<int:question_id>", methods=["POST"])
def delete_question(question_id):
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))

    conn = get_connection()
    _cur = conn.cursor()
    _cur.execute("SELECT id FROM faculty_details WHERE user_id = %s", (session["user_id"],))
    faculty = _cur.fetchone()
    
    _cur.execute("""
        SELECT q.id, q.subject_id FROM questions q
        JOIN subjects s ON q.subject_id = s.id
        WHERE q.id = %s AND s.faculty_id = %s
    """, (question_id, faculty["id"]))
    q = _cur.fetchone()

    if q:
        subject_id = q["subject_id"]
        _cur.execute("DELETE FROM questions WHERE id = %s", (question_id,))
        conn.commit()
        conn.close()
        flash("Question deleted successfully.", "success")
        return redirect(url_for("faculty_bp.manage_questions", subject_id=subject_id))
    
    conn.close()
    flash("Question not found or access denied.", "danger")
    return redirect(url_for("faculty_bp.faculty_exams"))

@faculty_bp.route("/faculty/exam/<string:course_code>/questions/manage")
def manage_exam_questions_link(course_code):
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))
        
    conn = get_connection()
    _cur = conn.cursor()
    _cur.execute("""
        SELECT e.*, s.subject_name 
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        WHERE e.course_code = %s AND s.faculty_id = (SELECT id FROM faculty_details WHERE user_id = %s)
    """, (course_code, session["user_id"]))
    exam = _cur.fetchone()
    
    if not exam:
        conn.close()
        flash("Exam not found or access denied.", "danger")
        return redirect(url_for("faculty_bp.faculty_exams"))
        
    # Get currently assigned questions
    _cur.execute("""
        SELECT q.*, eq.section 
        FROM questions q
        JOIN exam_questions eq ON q.id = eq.question_id
        WHERE eq.course_code = %s
    """, (course_code,))
    assigned_questions = _cur.fetchall()
    
    # Get available questions (same subject, not assigned)
    assigned_ids = [q["id"] for q in assigned_questions]
    if assigned_ids:
        placeholders = ','.join('%s' for _ in assigned_ids)
        _cur.execute(f"SELECT * FROM questions WHERE subject_id = %s AND id NOT IN ({placeholders})", (exam["subject_id"], *assigned_ids))
    else:
        _cur.execute("SELECT * FROM questions WHERE subject_id = %s", (exam["subject_id"],))
    available_questions = _cur.fetchall()
    
    conn.close()
    return render_template("faculty_exam_questions.html", exam=dict(exam), assigned=assigned_questions, available=available_questions)

@faculty_bp.route("/faculty/exam/<string:course_code>/questions/add", methods=["POST"])
def add_questions_to_exam(course_code):
    if not session.get("user_id") or session.get("role") != "faculty":
        return jsonify({"success": False}), 401
    
    data = request.json
    question_ids = data.get("question_ids", [])
    section = data.get("section", "A")
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        for qid in question_ids:
            cursor.execute("INSERT INTO exam_questions (course_code, question_id, section) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (course_code, qid, section))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

@faculty_bp.route("/faculty/exam/<string:course_code>/questions/remove", methods=["POST"])
def remove_questions_from_exam(course_code):
    if not session.get("user_id") or session.get("role") != "faculty":
        return jsonify({"success": False}), 401
    
    data = request.json
    question_ids = data.get("question_ids", [])
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if question_ids:
            placeholders = ','.join('%s' for _ in question_ids)
            cursor.execute(f"DELETE FROM exam_questions WHERE course_code = %s AND question_id IN ({placeholders})", (course_code, *question_ids))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()
