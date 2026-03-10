from flask import Blueprint, render_template, request, redirect, url_for, session, flash, Response
from database import get_connection
from datetime import datetime

faculty_bp = Blueprint('faculty_bp', __name__)

@faculty_bp.route("/faculty/dashboard")
def faculty_dashboard():
    if not session.get("user_id") or session.get("role") != "faculty":
        flash("Please login first.", "danger")
        return redirect(url_for("auth_bp.faculty_login"))

    conn = get_connection()
    faculty = conn.execute("SELECT * FROM faculty_details WHERE user_id = ?", (session["user_id"],)).fetchone()

    if not faculty:
        conn.close()
        flash("Faculty profile not found.", "danger")
        return redirect(url_for("auth_bp.faculty_login"))

    total_students = conn.execute("SELECT COUNT(*) FROM student_details").fetchone()[0]
    subjects = conn.execute("SELECT id, subject_name, branch, semester FROM subjects WHERE faculty_id = ?", (faculty["id"],)).fetchall()
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
        placeholders = ','.join('?' for _ in subject_ids)
        active_exams_count = conn.execute(
            f"SELECT COUNT(*) FROM exams WHERE subject_id IN ({placeholders})", tuple(subject_ids)
        ).fetchone()[0]

        recent_exams = conn.execute(f"""
            SELECT e.id, e.exam_name, e.exam_date, e.total_marks, e.duration_minutes,
                   s.id AS subject_id, s.subject_name, s.branch, s.semester,
                   e.pass_percentage,
                   (SELECT COUNT(*) FROM exam_attempts ea2 WHERE ea2.exam_id = e.id AND ea2.completed = 1) AS attempt_count,
                   (SELECT COUNT(*) FROM questions WHERE subject_id = s.id) AS question_count
            FROM exams e
            JOIN subjects s ON e.subject_id = s.id
            WHERE e.subject_id IN ({placeholders})
            ORDER BY e.exam_date DESC LIMIT 5
        """, tuple(subject_ids)).fetchall()

        total_results = conn.execute(f"""
            SELECT COUNT(*) FROM exam_attempts ea
            JOIN exams e ON ea.exam_id = e.id
            WHERE e.subject_id IN ({placeholders}) AND ea.completed = 1
        """, tuple(subject_ids)).fetchone()[0]

        exams_with_attempts = conn.execute(f"""
            SELECT COUNT(DISTINCT e.id) FROM exams e
            JOIN exam_attempts ea ON e.id = ea.exam_id
            WHERE e.subject_id IN ({placeholders}) AND ea.completed = 1
        """, tuple(subject_ids)).fetchone()[0]
        pending_results = max(0, active_exams_count - exams_with_attempts)

        recent_activity = conn.execute(f"""
            SELECT sd.full_name, e.exam_name, ea.score, e.total_marks, ea.completed, s.subject_name
            FROM exam_attempts ea
            JOIN student_details sd ON ea.student_id = sd.id
            JOIN exams e ON ea.exam_id = e.id
            JOIN subjects s ON e.subject_id = s.id
            WHERE e.subject_id IN ({placeholders})
            ORDER BY ea.id DESC LIMIT 8
        """, tuple(subject_ids)).fetchall()

        # Score distribution for charts
        all_scores = conn.execute(f"""
            SELECT ea.score, e.total_marks
            FROM exam_attempts ea
            JOIN exams e ON ea.exam_id = e.id
            WHERE e.subject_id IN ({placeholders}) AND ea.completed = 1 AND e.total_marks > 0
        """, tuple(subject_ids)).fetchall()

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
        at_risk_raw = conn.execute(f"""
            SELECT sd.full_name, sd.enrollment_no, ea.score, e.total_marks, e.exam_name, s.subject_name,
                   ROUND(CAST(ea.score AS FLOAT)/e.total_marks*100, 1) AS pct
            FROM exam_attempts ea
            JOIN student_details sd ON ea.student_id = sd.id
            JOIN exams e ON ea.exam_id = e.id
            JOIN subjects s ON e.subject_id = s.id
            WHERE e.subject_id IN ({placeholders}) AND ea.completed = 1 AND e.total_marks > 0
              AND CAST(ea.score AS FLOAT)/e.total_marks*100 < 40
            ORDER BY pct ASC LIMIT 5
        """, tuple(subject_ids)).fetchall()
        at_risk_students = [dict(r) for r in at_risk_raw]

    conn.close()
    return render_template("faculty_dashboard.html",
        faculty=faculty,
        total_students=total_students,
        active_exams=active_exams_count,
        recent_exams=recent_exams,
        subjects=subjects,
        pending_results=pending_results,
        total_results=total_results,
        recent_activity=recent_activity,
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
    faculty = conn.execute("SELECT * FROM faculty_details WHERE user_id = ?", (session["user_id"],)).fetchone()
    subjects = conn.execute("SELECT id, subject_name, branch, semester FROM subjects WHERE faculty_id = ?", (faculty["id"],)).fetchall()
    subject_ids = [s["id"] for s in subjects]

    all_exams = []
    if subject_ids:
        placeholders = ','.join('?' for _ in subject_ids)
        all_exams = conn.execute(f"""
            SELECT e.id, e.exam_name, e.exam_date, e.total_marks, e.duration_minutes,
                   e.pass_percentage,
                   s.id AS subject_id, s.subject_name, s.branch, s.semester,
                   (SELECT COUNT(*) FROM exam_attempts ea WHERE ea.exam_id = e.id AND ea.completed = 1) AS attempt_count,
                   (SELECT COUNT(*) FROM questions q WHERE q.subject_id = s.id) AS question_count
            FROM exams e
            JOIN subjects s ON e.subject_id = s.id
            WHERE e.subject_id IN ({placeholders})
            ORDER BY e.exam_date DESC
        """, tuple(subject_ids)).fetchall()

    conn.close()
    return render_template("faculty_exams.html", faculty=faculty, subjects=subjects, all_exams=all_exams)

@faculty_bp.route("/faculty/create_exam", methods=["POST"])
def create_exam():
    if not session.get("user_id") or session.get("role") != "faculty":
        flash("Please login first.", "danger")
        return redirect(url_for("auth_bp.faculty_login"))
        
    subject_id = request.form.get("subject_id")
    exam_name = request.form.get("exam_name", "").strip()
    total_marks = request.form.get("total_marks", 100, type=int)
    duration = request.form.get("duration", 60, type=int)
    pass_percentage = request.form.get("pass_percentage", 40, type=int)
    
    exam_date_input = request.form.get("exam_date", "").strip()
    exam_date = exam_date_input if exam_date_input else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not subject_id or not exam_name:
        flash("Subject and Exam Name are required.", "danger")
        return redirect(url_for("faculty_bp.faculty_exams"))
        
    try:
        conn = get_connection()
        conn.execute("""
            INSERT INTO exams (subject_id, exam_name, exam_date, total_marks, duration_minutes, pass_percentage)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (subject_id, exam_name, exam_date, total_marks, duration, pass_percentage))
        conn.commit()
        conn.close()
        flash("Exam created successfully!", "success")
    except Exception as e:
        flash(f"Error creating exam: {str(e)}", "danger")

    return redirect(url_for("faculty_bp.faculty_exams"))

@faculty_bp.route("/faculty/subject/<int:subject_id>/questions")
def manage_questions(subject_id):
    if not session.get("user_id") or session.get("role") != "faculty":
        flash("Please login first.", "danger")
        return redirect(url_for("auth_bp.faculty_login"))

    conn = get_connection()
    subject = conn.execute("SELECT * FROM subjects WHERE id = ? AND faculty_id = (SELECT id FROM faculty_details WHERE user_id = ?)", (subject_id, session["user_id"])).fetchone()
    
    if not subject:
        conn.close()
        flash("Subject not found or you don't have access.", "danger")
        return redirect(url_for("faculty_bp.faculty_exams"))

    questions_db = conn.execute("SELECT * FROM questions WHERE subject_id = ? ORDER BY id DESC", (subject_id,)).fetchall()
    
    questions = []
    for q in questions_db:
        options = conn.execute("SELECT * FROM options WHERE question_id = ?", (q["id"],)).fetchall()
        q_dict = dict(q)
        q_dict["options"] = [dict(o) for o in options]
        questions.append(q_dict)

    conn.close()
    return render_template("faculty_questions.html", subject=subject, questions=questions)

@faculty_bp.route("/faculty/subject/<int:subject_id>/add_question", methods=["POST"])
def add_question(subject_id):
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))

    question_text = request.form.get("question_text", "").strip()
    marks = request.form.get("marks", 1, type=int)
    question_type = "MCQ"
    
    if not question_text:
        flash("Question text is required.", "danger")
        return redirect(url_for("faculty_bp.manage_questions", subject_id=subject_id))
        
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO questions (subject_id, question_text, question_type, marks)
            VALUES (?, ?, ?, ?)
        """, (subject_id, question_text, question_type, marks))
        question_id = cursor.lastrowid
        
        for i in range(1, 5):
            opt_text = request.form.get(f"option_{i}", "").strip()
            is_correct = 1 if request.form.get("correct_option") == str(i) else 0
            if opt_text:
                cursor.execute("""
                    INSERT INTO options (question_id, option_text, is_correct)
                    VALUES (?, ?, ?)
                """, (question_id, opt_text, is_correct))
                
        conn.commit()
        flash("Question added successfully!", "success")
    except Exception as e:
        flash(f"Error adding question: {str(e)}", "danger")
    finally:
        conn.close()
        
    return redirect(url_for("faculty_bp.manage_questions", subject_id=subject_id))

@faculty_bp.route("/faculty/students")
def faculty_students():
    if not session.get("user_id") or session.get("role") != "faculty":
        flash("Please login first.", "danger")
        return redirect(url_for("auth_bp.faculty_login"))

    conn = get_connection()
    faculty = conn.execute("SELECT * FROM faculty_details WHERE user_id = ?", (session["user_id"],)).fetchone()
    
    # Get all students in the system, and left join with the faculty's subjects
    raw_students = conn.execute("""
        SELECT sd.id, sd.full_name, sd.enrollment_no, sd.branch as student_branch, sd.semester as student_semester,
               s.subject_name, s.branch as subject_branch, s.id as subject_code
        FROM student_details sd
        LEFT JOIN student_subjects ss ON sd.id = ss.student_id
        LEFT JOIN subjects s ON ss.subject_id = s.id AND s.faculty_id = ?
        ORDER BY sd.semester ASC, sd.full_name ASC, s.subject_name ASC
    """, (faculty["id"],)).fetchall()
    
    # Consolidate duplicate rows for students taking multiple subjects
    student_dict = {}
    for row in raw_students:
        s_id = row['id']
        if s_id not in student_dict:
            student_dict[s_id] = {
                'id': s_id,
                'full_name': row['full_name'],
                'enrollment_no': row['enrollment_no'],
                'student_branch': row['student_branch'],
                'student_semester': row['student_semester'],
                'subjects': []
            }
        
        # We handle displaying multiple subjects by appending them to a list
        if row['subject_name']:
            student_dict[s_id]['subjects'].append({
                'name': row['subject_name'],
                'code': row['subject_code']
            })
            
    # For compatibility with existing template logic that expects single 'subject_name' attributes,
    # we'll format the subjects list into strings. If empty, it'll fall back to template's 'Not Assigned'
    students = []
    for s in student_dict.values():
        s['subject_name'] = ', '.join([sub['name'] for sub in s['subjects']]) if s['subjects'] else None
        s['subject_code'] = s['subjects'][0]['code'] if s['subjects'] else None
        students.append(s)
    
    # Get subjects taught by this faculty for the dropdowns
    subjects = conn.execute("SELECT id, subject_name, branch, semester FROM subjects WHERE faculty_id = ?", (faculty["id"],)).fetchall()
    
    conn.close()
    return render_template("faculty_students.html", faculty=faculty, students=students, subjects=subjects)

@faculty_bp.route("/faculty/results")
def faculty_results():
    if not session.get("user_id") or session.get("role") != "faculty":
        flash("Please login first.", "danger")
        return redirect(url_for("auth_bp.faculty_login"))

    conn = get_connection()
    faculty = conn.execute("SELECT * FROM faculty_details WHERE user_id = ?", (session["user_id"],)).fetchone()

    results = conn.execute("""
        SELECT ea.id, sd.full_name, sd.enrollment_no,
               e.exam_name, e.total_marks, ea.score,
               s.subject_name, s.branch, s.semester,
               CASE WHEN e.total_marks > 0
                    THEN ROUND(CAST(ea.score AS FLOAT)/e.total_marks*100, 1)
                    ELSE 0 END AS pct
        FROM exam_attempts ea
        JOIN student_details sd ON ea.student_id = sd.id
        JOIN exams e ON ea.exam_id = e.id
        JOIN subjects s ON e.subject_id = s.id
        WHERE s.faculty_id = ? AND ea.completed = 1
        ORDER BY e.exam_name, ea.score DESC
    """, (faculty["id"],)).fetchall()

    # Aggregate analytics
    class_avg = 0.0
    pass_rate = 0.0
    highest_score = 0.0
    lowest_score = 100.0
    score_dist = {"excellent": 0, "passed": 0, "failed": 0}

    if results:
        pcts = []
        for r in results:
            p = r["pct"] or 0.0
            pcts.append(p)
            if p >= 75: score_dist["excellent"] += 1
            elif p >= 40: score_dist["passed"] += 1
            else: score_dist["failed"] += 1

        class_avg = round(sum(pcts) / len(pcts), 1)
        passed = score_dist["excellent"] + score_dist["passed"]
        pass_rate = round(passed / len(results) * 100, 1)
        highest_score = round(max(pcts), 1)
        lowest_score = round(min(pcts), 1)

    conn.close()
    return render_template("faculty_results.html",
        faculty=faculty, results=results,
        class_avg=class_avg, pass_rate=pass_rate,
        highest_score=highest_score, lowest_score=lowest_score,
        score_dist=score_dist,
    )

@faculty_bp.route("/faculty/results/export")
def export_results_csv():
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))

    import csv as csv_module
    from io import StringIO

    conn = get_connection()
    faculty = conn.execute("SELECT * FROM faculty_details WHERE user_id = ?", (session["user_id"],)).fetchone()
    results = conn.execute("""
        SELECT sd.full_name, sd.enrollment_no,
               e.exam_name, s.subject_name, s.branch, s.semester,
               e.total_marks, ea.score,
               CASE WHEN e.total_marks > 0
                    THEN ROUND(CAST(ea.score AS FLOAT) / e.total_marks * 100, 1)
                    ELSE 0 END AS percentage
        FROM exam_attempts ea
        JOIN student_details sd ON ea.student_id = sd.id
        JOIN exams e ON ea.exam_id = e.id
        JOIN subjects s ON e.subject_id = s.id
        WHERE s.faculty_id = ? AND ea.completed = 1
        ORDER BY e.exam_name, ea.score DESC
    """, (faculty["id"],)).fetchall()
    conn.close()

    si = StringIO()
    writer = csv_module.writer(si)
    writer.writerow(["Student Name", "Enrollment No", "Exam", "Subject", "Branch", "Semester", "Total Marks", "Score", "Percentage (%)"])
    for r in results:
        writer.writerow([r["full_name"], r["enrollment_no"], r["exam_name"],
                         r["subject_name"], r["branch"], r["semester"],
                         r["total_marks"], r["score"], r["percentage"]])

    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=exam_results.csv"}
    )


# ── EDIT EXAM ──────────────────────────────────────────────────────────────
@faculty_bp.route("/faculty/exam/edit/<int:exam_id>", methods=["POST"])
def edit_exam(exam_id):
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))
    conn = get_connection()
    faculty = conn.execute("SELECT id FROM faculty_details WHERE user_id = ?", (session["user_id"],)).fetchone()
    exam = conn.execute("""
        SELECT e.id FROM exams e JOIN subjects s ON e.subject_id = s.id
        WHERE e.id = ? AND s.faculty_id = ?
    """, (exam_id, faculty["id"])).fetchone()
    if exam:
        exam_name = request.form.get("exam_name", "").strip()
        total_marks = request.form.get("total_marks", 100, type=int)
        duration = request.form.get("duration_minutes", 60, type=int)
        pass_pct = request.form.get("pass_percentage", 40, type=int)
        exam_date = request.form.get("exam_date", "").strip()
        conn.execute("""
            UPDATE exams SET exam_name=?, total_marks=?, duration_minutes=?, pass_percentage=?, exam_date=?
            WHERE id=?
        """, (exam_name, total_marks, duration, pass_pct, exam_date or None, exam_id))
        conn.commit()
        flash("Exam updated successfully.", "success")
    else:
        flash("Exam not found or access denied.", "danger")
    conn.close()
    return redirect(url_for("faculty_bp.faculty_exams"))

# ── DUPLICATE EXAM ─────────────────────────────────────────────────────────
@faculty_bp.route("/faculty/exam/duplicate/<int:exam_id>", methods=["POST"])
def duplicate_exam(exam_id):
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))
    conn = get_connection()
    faculty = conn.execute("SELECT id FROM faculty_details WHERE user_id = ?", (session["user_id"],)).fetchone()
    exam = conn.execute("""
        SELECT e.* FROM exams e JOIN subjects s ON e.subject_id = s.id
        WHERE e.id = ? AND s.faculty_id = ?
    """, (exam_id, faculty["id"])).fetchone()
    if exam:
        conn.execute("""
            INSERT INTO exams (subject_id, exam_name, exam_date, total_marks, duration_minutes, pass_percentage)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (exam["subject_id"], exam["exam_name"] + " (Copy)",
              exam["exam_date"], exam["total_marks"],
              exam["duration_minutes"], exam["pass_percentage"]))
        conn.commit()
        flash(f"Exam duplicated as '{exam['exam_name']} (Copy)'.", "success")
    else:
        flash("Exam not found or access denied.", "danger")
    conn.close()
    return redirect(url_for("faculty_bp.faculty_exams"))

# ── PER-EXAM STATS (JSON) ─────────────────────────────────────────────────
@faculty_bp.route("/faculty/exam/<int:exam_id>/stats")
def exam_stats(exam_id):
    from flask import jsonify
    if not session.get("user_id") or session.get("role") != "faculty":
        return jsonify({"error": "unauthorized"}), 401
    conn = get_connection()
    faculty = conn.execute("SELECT id FROM faculty_details WHERE user_id = ?", (session["user_id"],)).fetchone()
    exam = conn.execute("""
        SELECT e.*, s.subject_name FROM exams e JOIN subjects s ON e.subject_id = s.id
        WHERE e.id = ? AND s.faculty_id = ?
    """, (exam_id, faculty["id"])).fetchone()
    if not exam:
        conn.close()
        return jsonify({"error": "not found"}), 404

    attempts = conn.execute("""
        SELECT ea.score, sd.full_name, sd.enrollment_no,
               ROUND(CAST(ea.score AS FLOAT)/? * 100, 1) AS pct
        FROM exam_attempts ea
        JOIN student_details sd ON ea.student_id = sd.id
        WHERE ea.exam_id = ? AND ea.completed = 1
        ORDER BY ea.score DESC
    """, (exam["total_marks"] or 1, exam_id)).fetchall()

    conn.close()
    if not attempts:
        return jsonify({"count": 0, "avg": 0, "high": 0, "low": 0,
                        "pass_count": 0, "fail_count": 0, "students": []})

    pcts = [a["pct"] for a in attempts]
    pass_mark = exam["pass_percentage"] or 40
    passed = sum(1 for p in pcts if p >= pass_mark)
    return jsonify({
        "count": len(pcts),
        "avg": round(sum(pcts)/len(pcts), 1),
        "high": max(pcts),
        "low": min(pcts),
        "pass_count": passed,
        "fail_count": len(pcts) - passed,
        "students": [dict(a) for a in attempts[:8]]
    })

@faculty_bp.route("/faculty/exam/delete/<int:exam_id>", methods=["POST"])
def delete_exam(exam_id):
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))

    conn = get_connection()
    try:
        # Verify this exam belongs to a subject owned by this faculty
        faculty = conn.execute("SELECT id FROM faculty_details WHERE user_id = ?", (session["user_id"],)).fetchone()
        exam = conn.execute("""
            SELECT e.id FROM exams e
            JOIN subjects s ON e.subject_id = s.id
            WHERE e.id = ? AND s.faculty_id = ?
        """, (exam_id, faculty["id"])).fetchone()

        if not exam:
            flash("Exam not found or access denied.", "danger")
        else:
            conn.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
            conn.commit()
            flash("Exam deleted successfully.", "success")
    except Exception as e:
        flash(f"Error deleting exam: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for("faculty_bp.faculty_exams"))




import csv
from io import StringIO
from werkzeug.security import generate_password_hash


@faculty_bp.route("/faculty/question/delete/<int:question_id>", methods=["POST"])
def delete_question(question_id):
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))

    conn = get_connection()
    faculty = conn.execute("SELECT id FROM faculty_details WHERE user_id = ?", (session["user_id"],)).fetchone()
    # Verify ownership before delete
    q = conn.execute("""
        SELECT q.id, q.subject_id FROM questions q
        JOIN subjects s ON q.subject_id = s.id
        WHERE q.id = ? AND s.faculty_id = ?
    """, (question_id, faculty["id"])).fetchone()

    if q:
        subject_id = q["subject_id"]
        conn.execute("DELETE FROM options WHERE question_id = ?", (question_id,))
        conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        conn.commit()
        flash("Question deleted.", "success")
        conn.close()
        return redirect(url_for("faculty_bp.manage_questions", subject_id=subject_id))
    else:
        flash("Question not found or access denied.", "danger")
        conn.close()
        return redirect(url_for("faculty_bp.faculty_exams"))

@faculty_bp.route("/faculty/students/add", methods=["POST"])
def add_student_manual():
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))

    full_name = request.form.get("full_name", "").strip()
    enrollment_no = request.form.get("enrollment_no", "").strip()
    branch = request.form.get("branch", "").strip()
    semester = request.form.get("semester", type=int)
    subject_id = request.form.get("subject_id", type=int)

    if not all([full_name, enrollment_no, branch, semester, subject_id]):
        flash("All fields are required.", "danger")
        return redirect(url_for("faculty_bp.faculty_students"))

    conn = get_connection()
    try:
        # Check if user already exists
        cursor = conn.cursor()
        user = cursor.execute("SELECT id FROM users WHERE username = ?", (enrollment_no,)).fetchone()
        
        if not user:
            # Create user
            hashed_pw = generate_password_hash("student123")
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, 'student')", (enrollment_no, hashed_pw))
            user_id = cursor.lastrowid
            
            # Create student details
            cursor.execute("""
                INSERT INTO student_details (user_id, full_name, enrollment_no, branch, semester)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, full_name, enrollment_no, branch, semester))
            student_id = cursor.lastrowid
        else:
            student = cursor.execute("SELECT id FROM student_details WHERE user_id = ?", (user["id"],)).fetchone()
            student_id = student["id"]

        # Enroll in subject (ignore if already enrolled)
        cursor.execute("INSERT OR IGNORE INTO student_subjects (student_id, subject_id) VALUES (?, ?)", (student_id, subject_id))
        conn.commit()
        flash("Student added successfully!", "success")
    except Exception as e:
        flash(f"Error adding student: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for("faculty_bp.faculty_students"))

@faculty_bp.route("/faculty/students/upload_csv", methods=["POST"])
def upload_students_csv():
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))

    if 'csv_file' not in request.files:
        flash("No file uploaded.", "danger")
        return redirect(url_for("faculty_bp.faculty_students"))

    file = request.files['csv_file']
    subject_id = request.form.get("subject_id", type=int)

    if file.filename == '':
        flash("No file selected.", "danger")
        return redirect(url_for("faculty_bp.faculty_students"))
        
    if not subject_id:
        flash("Subject selection is required.", "danger")
        return redirect(url_for("faculty_bp.faculty_students"))

    if not file.filename.endswith('.csv'):
        flash("Invalid file format. Please upload a CSV file.", "danger")
        return redirect(url_for("faculty_bp.faculty_students"))

    try:
        stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream)
        
        conn = get_connection()
        cursor = conn.cursor()
        added_count = 0
        
        for row in csv_input:
            # Expected columns: full_name, enrollment_no, branch, semester
            full_name = row.get('full_name', '').strip()
            enrollment_no = row.get('enrollment_no', '').strip()
            branch = row.get('branch', '').strip()
            semester = row.get('semester', '').strip()
            
            if not all([full_name, enrollment_no, branch, semester]):
                continue # Skip invalid rows
                
            # Check user
            user = cursor.execute("SELECT id FROM users WHERE username = ?", (enrollment_no,)).fetchone()
            if not user:
                hashed_pw = generate_password_hash("student123")
                cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, 'student')", (enrollment_no, hashed_pw))
                user_id = cursor.lastrowid
                
                cursor.execute("""
                    INSERT INTO student_details (user_id, full_name, enrollment_no, branch, semester)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, full_name, enrollment_no, branch, int(semester)))
                student_id = cursor.lastrowid
            else:
                student = cursor.execute("SELECT id FROM student_details WHERE user_id = ?", (user["id"],)).fetchone()
                student_id = student["id"]
                
            cursor.execute("INSERT OR IGNORE INTO student_subjects (student_id, subject_id) VALUES (?, ?)", (student_id, subject_id))
            added_count += 1
            
        conn.commit()
        flash(f"Successfully processed {added_count} students via CSV.", "success")
    except Exception as e:
        flash(f"Error processing CSV: {str(e)}", "danger")
    finally:
        if 'conn' in locals():
            conn.close()

    return redirect(url_for("faculty_bp.faculty_students"))

@faculty_bp.route("/faculty/students/edit/<int:student_id>", methods=["POST"])
def edit_student(student_id):
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))

    full_name = request.form.get("full_name", "").strip()
    branch = request.form.get("branch", "").strip()
    semester = request.form.get("semester", type=int)

    if not all([full_name, branch, semester]):
        flash("All fields are required.", "danger")
        return redirect(url_for("faculty_bp.faculty_students"))

    conn = get_connection()
    try:
        conn.execute("""
            UPDATE student_details 
            SET full_name = ?, branch = ?, semester = ?
            WHERE id = ?
        """, (full_name, branch, semester, student_id))
        conn.commit()
        flash("Student details updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating student: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for("faculty_bp.faculty_students"))

@faculty_bp.route("/faculty/students/delete/<int:student_id>", methods=["POST"])
def delete_student(student_id):
    if not session.get("user_id") or session.get("role") != "faculty":
        return redirect(url_for("auth_bp.faculty_login"))

    conn = get_connection()
    try:
        # First check if the student is assigned to any subjects controlled by this faculty
        faculty_subjects = conn.execute("SELECT id FROM subjects WHERE faculty_id = (SELECT id FROM faculty_details WHERE user_id = ?)", (session["user_id"],)).fetchall()
        subject_ids = [s["id"] for s in faculty_subjects]
        
        if subject_ids:
            placeholders = ','.join('?' for _ in subject_ids)
            # Remove from faculty's subjects
            conn.execute(f"DELETE FROM student_subjects WHERE student_id = ? AND subject_id IN ({placeholders})", [student_id] + subject_ids)
            
            # Check if student is still enrolled in ANY other subjects
            remaining = conn.execute("SELECT COUNT(*) FROM student_subjects WHERE student_id = ?", (student_id,)).fetchone()[0]
            if remaining == 0:
                # Fully delete the student and user record if they have no other subjects
                user_id = conn.execute("SELECT user_id FROM student_details WHERE id = ?", (student_id,)).fetchone()["user_id"]
                conn.execute("DELETE FROM student_details WHERE id = ?", (student_id,))
                conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
                
            conn.commit()
            flash("Student successfully removed from your cohort.", "success")
    except Exception as e:
        flash(f"Error removing student: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for("faculty_bp.faculty_students"))
