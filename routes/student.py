from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_connection, update_user_password
from werkzeug.security import check_password_hash
from datetime import datetime

student_bp = Blueprint('student_bp', __name__)

@student_bp.route("/student/dashboard")
def student_dashboard():
    if not session.get("user_id"):
        return redirect(url_for("auth_bp.student_login"))
    if session.get("role") == "faculty":
        return redirect(url_for("faculty_bp.faculty_dashboard"))
    if session.get("role") != "student":
        return redirect(url_for("auth_bp.student_login"))

    conn = get_connection()
    _cur = conn.cursor()
    _cur.execute("""
        SELECT enrollment_no, full_name, branch, semester 
        FROM student_details 
        WHERE user_id = %s
    """, (session["user_id"],))
    student = _cur.fetchone()

    if not student:
        conn.close()
        flash("Student profile not found. Please contact administration.", "danger")
        session.clear()
        return redirect(url_for("auth_bp.student_login"))

    enrollment_no = student["enrollment_no"]

    # 2. Fetch assigned subjects
    _cur.execute("""
        SELECT s.subject_name, f.full_name AS faculty_name, f.department
        FROM student_subjects ss
        JOIN exams e ON ss.course_code = e.course_code
        JOIN subjects s ON e.subject_id = s.id
        LEFT JOIN faculty_details f ON s.faculty_id = f.id
        WHERE ss.enrollment_no = %s
    """, (enrollment_no,))
    subjects = _cur.fetchall()

    # 3. Get exam statistics
    _cur.execute("""
        SELECT 
            COUNT(e.course_code) AS total_exams,
            SUM(CASE WHEN ea.completed = 1 THEN 1 ELSE 0 END) AS completed_exams
        FROM exams e
        JOIN student_subjects ss ON e.course_code = ss.course_code
        LEFT JOIN exam_attempts ea 
            ON ea.course_code = e.course_code AND ea.enrollment_no = %s
        WHERE ss.enrollment_no = %s
    """, (enrollment_no, enrollment_no))
    exam_stats = _cur.fetchone()

    total_exams = exam_stats["total_exams"] if exam_stats and exam_stats["total_exams"] else 0
    completed_exams = exam_stats["completed_exams"] if exam_stats and exam_stats["completed_exams"] else 0
    upcoming_exams = total_exams - completed_exams

    conn.close()

    return render_template(
        "student_dashboard.html",
        student=dict(student),
        subjects=[dict(row) for row in subjects],
        total_exams=total_exams,
        completed_exams=completed_exams,
        upcoming_exams=upcoming_exams
    )

@student_bp.route("/student/exams")
def student_exams():
    if not session.get("user_id") or session.get("role") != "student":
        return redirect(url_for("auth_bp.student_login"))
    
    conn = get_connection()
    _cur = conn.cursor()
    _cur.execute("""
        SELECT 
            s.subject_name,
            f.full_name AS faculty_name,
            e.course_code,
            e.exam_date,
            e.start_time,
            e.end_time,
            e.duration_minutes,
            COALESCE(ea.completed, 0) AS is_completed,
            ea.score,
            (SELECT COUNT(*) FROM exam_blacklist eb WHERE eb.course_code = e.course_code AND eb.enrollment_no = ss.enrollment_no) as is_blacklisted
        FROM student_subjects ss
        JOIN exams e ON ss.course_code = e.course_code
        JOIN subjects s ON e.subject_id = s.id
        LEFT JOIN faculty_details f ON s.faculty_id = f.id
        LEFT JOIN exam_attempts ea ON e.course_code = ea.course_code AND ss.enrollment_no = ea.enrollment_no
        WHERE ss.enrollment_no = (SELECT enrollment_no FROM student_details WHERE user_id = %s)
    """, (session["user_id"],))
    exams_data = _cur.fetchall()
    
    # Check scheduling status
    now = datetime.now()
    exams_with_status = []
    for row in exams_data:
        d = dict(row)
        d['status'] = 'open'
        
        def parse_dt(dt_str):
            if not dt_str: return None
            try:
                s = dt_str.replace('T', ' ')
                if len(s) > 19: s = s[:19]
                return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
            except:
                try: return datetime.strptime(dt_str.replace('T', ' '), "%Y-%m-%d %H:%M")
                except: return None

        start = parse_dt(d['start_time'])
        end = parse_dt(d['end_time'])

        if start and now < start:
            d['status'] = 'upcoming'
        elif end and now > end:
            d['status'] = 'expired'
        exams_with_status.append(d)
    
    _cur.execute("SELECT enrollment_no, full_name, branch, semester FROM student_details WHERE user_id = %s", (session["user_id"],))
    student = _cur.fetchone()
    conn.close()

    return render_template("student_exams.html", exams=exams_with_status, student=dict(student) if student else {})

@student_bp.route("/exam")
def exam_page():
    if not session.get("user_id"):
        return redirect(url_for("auth_bp.student_login"))
    
    course_code = request.args.get("course_code")
    if not course_code:
        flash("Exam not specified.", "danger")
        return redirect(url_for("student_bp.student_dashboard"))

    conn = get_connection()
    _cur = conn.cursor()
    
    # Fetch student details first
    _cur.execute("SELECT enrollment_no FROM student_details WHERE user_id = %s", (session["user_id"],))
    student = _cur.fetchone()
    if not student:
        conn.close()
        flash("Student profile not found.", "danger")
        return redirect(url_for("student_bp.student_dashboard"))
        
    enrollment_no = student["enrollment_no"]

    _cur.execute("SELECT * FROM exams WHERE course_code = %s", (course_code,))
    exam = _cur.fetchone()
    if not exam:
        conn.close()
        flash("Exam not found.", "danger")
        return redirect(url_for("student_bp.student_dashboard"))
    
    # Check blacklist
    _cur.execute("SELECT id FROM exam_blacklist WHERE course_code = %s AND enrollment_no = %s", (course_code, enrollment_no))
    if _cur.fetchone():
        conn.close()
        flash("You are blacklisted from this exam. Please contact your faculty.", "danger")
        return redirect(url_for("student_bp.student_dashboard"))

    # Check enrollment
    _cur.execute("SELECT enrollment_no FROM student_subjects WHERE enrollment_no = %s AND course_code = %s", (enrollment_no, course_code))
    if not _cur.fetchone():
        conn.close()
        flash("You are not enrolled for this specific course/exam.", "danger")
        return redirect(url_for("student_bp.student_dashboard"))
        
    # Check if already completed
    _cur.execute("SELECT completed FROM exam_attempts WHERE enrollment_no = %s AND course_code = %s", (enrollment_no, course_code))
    attempt = _cur.fetchone()
    if attempt and attempt["completed"] == 1:
        conn.close()
        flash("You have already completed this exam.", "warning")
        return redirect(url_for("student_bp.student_dashboard"))

    # Strict scheduling check
    now = datetime.now()
    
    def parse_dt(dt_str):
        if not dt_str: return None
        try:
            s = dt_str.replace('T', ' ')
            if len(s) > 19: s = s[:19]
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except:
            try: return datetime.strptime(dt_str.replace('T', ' '), "%Y-%m-%d %H:%M")
            except: return None

    start = parse_dt(exam["start_time"])
    end = parse_dt(exam["end_time"])

    if start and now < start:
        conn.close()
        flash(f"This exam is scheduled to start at {exam['start_time']}.", "warning")
        return redirect(url_for("student_bp.student_dashboard"))
    if end and now > end:
        conn.close()
        flash("This exam has already expired.", "danger")
        return redirect(url_for("student_bp.student_dashboard"))

    subject_id = exam["subject_id"]
    _cur.execute("SELECT subject_name FROM subjects WHERE id = %s", (subject_id,))
    subject = _cur.fetchone()
    subject_name = subject["subject_name"] if subject else "Unknown Subject"

    try:
        # Check if specific questions are assigned to this exam
        _cur.execute("SELECT COUNT(*) as count FROM exam_questions WHERE course_code = %s", (course_code,))
        exam_q_count = _cur.fetchone()["count"]
        
        if exam_q_count > 0:
            # Fetch only assigned questions
            _cur.execute("""
                SELECT q.*, eq.section 
                FROM questions q
                JOIN exam_questions eq ON q.id = eq.question_id
                WHERE eq.course_code = %s
            """, (course_code,))
            questions_db = _cur.fetchall()
        else:
            # Fallback - show all questions for the subject
            _cur.execute("SELECT * FROM questions WHERE subject_id = %s", (subject_id,))
            questions_db = _cur.fetchall()
    except Exception:
        questions_db = []

    questions = []
    for q in questions_db:
        _cur.execute("SELECT id, option_text, is_correct FROM options WHERE question_id = %s", (q["id"],))
        options_db = _cur.fetchall()
        
        q_dict = dict(q)
        q_dict["options"] = [dict(row) for row in options_db]
        questions.append(q_dict)

    conn.close()
    return render_template("exam.html", subject_name=subject_name, exam=dict(exam), questions=questions)

@student_bp.route("/exam/submit", methods=["POST"])
def submit_exam():
    if not session.get("user_id"):
        return {"success": False, "message": "Unauthorized"}, 401

    data = request.json
    course_code = data.get("course_code")
    score = data.get("score")

    conn = get_connection()
    _cur = conn.cursor()
    _cur.execute("SELECT enrollment_no FROM student_details WHERE user_id = %s", (session["user_id"],))
    student = _cur.fetchone()
    
    if not student:
        conn.close()
        return {"success": False, "message": "Student not found"}, 404

    # Check if attempt already exists and update or create
    _cur.execute("SELECT id, completed FROM exam_attempts WHERE enrollment_no = %s AND course_code = %s", 
                 (student["enrollment_no"], course_code))
    existing_attempt = _cur.fetchone()
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if existing_attempt:
        if existing_attempt["completed"] == 1:
            conn.close()
            return {"success": False, "message": "Exam already completed"}, 400
            
        _cur.execute("UPDATE exam_attempts SET score = %s, completed = 1, attempt_time = %s WHERE id = %s", (score, now, existing_attempt["id"]))
    else:
        _cur.execute("INSERT INTO exam_attempts (enrollment_no, course_code, score, completed, attempt_time) VALUES (%s, %s, %s, 1, %s)", 
                     (student["enrollment_no"], course_code, score, now))
    
    conn.commit()
    conn.close()
    
    return {"success": True}

@student_bp.route("/exam/blacklist", methods=["POST"])
def blacklist_student():
    if not session.get("user_id"):
        return {"success": False, "message": "Unauthorized"}, 401
        
    data = request.json
    course_code = data.get("course_code")
    
    conn = get_connection()
    _cur = conn.cursor()
    _cur.execute("SELECT enrollment_no FROM student_details WHERE user_id = %s", (session["user_id"],))
    student = _cur.fetchone()
    if not student:
        conn.close()
        return {"success": False, "message": "Student not found"}, 404
        
    # Check if already blacklisted
    _cur.execute("SELECT id FROM exam_blacklist WHERE course_code = %s AND enrollment_no = %s", (course_code, student["enrollment_no"]))
    existing = _cur.fetchone()
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not existing:
        _cur.execute("INSERT INTO exam_blacklist (course_code, enrollment_no) VALUES (%s, %s)", (course_code, student["enrollment_no"]))
    
    # Also mark as completed with 0 score (or keep existing)
    _cur.execute("SELECT id FROM exam_attempts WHERE course_code = %s AND enrollment_no = %s", (course_code, student["enrollment_no"]))
    existing_attempt = _cur.fetchone()
    
    if not existing_attempt:
        _cur.execute("INSERT INTO exam_attempts (enrollment_no, course_code, score, completed, attempt_time) VALUES (%s, %s, 0, 1, %s)", 
                     (student["enrollment_no"], course_code, now))
    
    conn.commit()
    conn.close()
    
    return {"success": True}

@student_bp.route("/result")
def result_page():
    if not session.get("user_id"):
        return redirect(url_for("auth_bp.student_login"))
    return render_template("result.html")
