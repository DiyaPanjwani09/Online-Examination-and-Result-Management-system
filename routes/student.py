from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_connection

student_bp = Blueprint('student_bp', __name__)

@student_bp.route("/student/dashboard")
def student_dashboard():
    if not session.get("user_id") or session.get("role") != "student":
        flash("Please login first.", "danger")
        return redirect(url_for("auth_bp.student_login"))

    conn = get_connection()
    dashboard_data = conn.execute("""
        SELECT 
            sd.id AS student_id,
            sd.full_name,
            sd.enrollment_no,
            sd.branch,
            sd.semester,
            s.subject_name,
            f.full_name AS faculty_name,
            f.department
        FROM student_details sd
        JOIN student_subjects ss ON sd.id = ss.student_id
        JOIN subjects s ON ss.subject_id = s.id
        LEFT JOIN faculty_details f ON s.faculty_id = f.id
        WHERE sd.user_id = ?
    """, (session["user_id"],)).fetchall()

    if not dashboard_data:
        conn.close()
        flash("Student data not found.", "danger")
        return redirect(url_for("auth_bp.student_login"))

    student_id = dashboard_data[0]["student_id"]

    exam_stats = conn.execute("""
        SELECT 
            COUNT(e.id) AS total_exams,
            SUM(CASE WHEN ea.completed = 1 THEN 1 ELSE 0 END) AS completed_exams
        FROM exams e
        JOIN student_subjects ss ON e.subject_id = ss.subject_id
        LEFT JOIN exam_attempts ea 
            ON ea.exam_id = e.id AND ea.student_id = ?
        WHERE ss.student_id = ?
    """, (student_id, student_id)).fetchone()

    total_exams = exam_stats["total_exams"] if exam_stats["total_exams"] else 0
    completed_exams = exam_stats["completed_exams"] if exam_stats["completed_exams"] else 0
    upcoming_exams = total_exams - completed_exams

    conn.close()

    return render_template(
        "student_dashboard.html",
        student=dashboard_data[0],
        subjects=dashboard_data,
        total_exams=total_exams,
        completed_exams=completed_exams,
        upcoming_exams=upcoming_exams
    )

@student_bp.route("/student/exams")
def student_exams():
    if not session.get("user_id") or session.get("role") != "student":
        return redirect(url_for("auth_bp.student_login"))
    
    conn = get_connection()
    exams_data = conn.execute("""
        SELECT 
            s.subject_name,
            f.full_name AS faculty_name,
            e.id AS exam_id,
            e.exam_date,
            e.duration_minutes
        FROM student_subjects ss
        JOIN subjects s ON ss.subject_id = s.id
        LEFT JOIN faculty_details f ON s.faculty_id = f.id
        LEFT JOIN exams e ON s.id = e.subject_id
        WHERE ss.student_id = (SELECT id FROM student_details WHERE user_id = ?)
    """, (session["user_id"],)).fetchall()
    
    student = conn.execute("SELECT * FROM student_details WHERE user_id = ?", (session["user_id"],)).fetchone()
    conn.close()

    return render_template("student_exams.html", exams=exams_data, student=student)

@student_bp.route("/exam")
def exam_page():
    if not session.get("user_id"):
        return redirect(url_for("auth_bp.student_login"))
    
    subject_name = request.args.get("subject")
    if not subject_name:
        flash("Subject not specified.", "danger")
        return redirect(url_for("student_bp.student_dashboard"))

    conn = get_connection()
    subject = conn.execute("SELECT id FROM subjects WHERE subject_name = ?", (subject_name,)).fetchone()
    if not subject:
        conn.close()
        flash("Subject not found.", "danger")
        return redirect(url_for("student_bp.student_dashboard"))
    
    subject_id = subject["id"]

    try:
        questions_db = conn.execute("SELECT * FROM questions WHERE subject_id = ?", (subject_id,)).fetchall()
    except Exception:
        questions_db = []

    questions = []
    for q in questions_db:
        options_db = conn.execute("SELECT * FROM options WHERE question_id = ?", (q["id"],)).fetchall()
        options = [dict(row) for row in options_db]
        
        q_dict = dict(q)
        q_dict["options"] = options
        questions.append(q_dict)

    conn.close()
    return render_template("exam.html", subject_name=subject_name, questions=questions)

@student_bp.route("/result")
def result_page():
    if not session.get("user_id"):
        return redirect(url_for("auth_bp.student_login"))
    return render_template("result.html")
