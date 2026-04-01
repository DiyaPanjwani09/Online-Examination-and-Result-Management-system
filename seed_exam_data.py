import sqlite3
from werkzeug.security import generate_password_hash
import datetime

DB_PATH = "database.db"

def seed_exam_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Clear existing data
    print("Cleaning database for fresh sample data...")
    cursor.execute("PRAGMA foreign_keys = OFF;")
    tables = ["exam_blacklist", "exam_questions", "options", "questions", "exam_attempts", "exams", "student_subjects", "subjects", "faculty_details", "student_details", "users"]
    for t in tables:
        cursor.execute(f"DELETE FROM {t};")
        cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{t}';")
    cursor.execute("PRAGMA foreign_keys = ON;")

    hpw = generate_password_hash("Password@123")

    # 2. Setup Faculty
    faculty_list = [
        {"username": "alice", "name": "Prof. Alice", "dept": "Computer Science", "email": "alice@test.com"},
        {"username": "bob", "name": "Prof. Bob", "dept": "Information Technology", "email": "bob@test.com"}
    ]
    
    faculty_ids = []
    for f in faculty_list:
        cursor.execute("INSERT INTO users (username, password, role, email) VALUES (?, ?, 'faculty', ?)", (f["username"], hpw, f["email"]))
        uid = cursor.lastrowid
        cursor.execute("INSERT INTO faculty_details (user_id, full_name, department) VALUES (?, ?, ?)", (uid, f["name"], f["dept"]))
        faculty_ids.append(cursor.lastrowid)

    # 3. Setup Subjects & Exams (with unique times)
    # (name, code, faculty_id, branch, semester, start_time)
    subjects = [
        ("DBMS", "CS401", faculty_ids[0], "CS", 4, "10:00"),
        ("CN", "CS501", faculty_ids[0], "CS", 5, "11:00"),
        ("DSA", "CS301", faculty_ids[1], "IT", 3, "12:00"),
        ("AI", "CS601", faculty_ids[1], "IT", 6, "13:00")
    ]
    
    for name, code, fid, branch, sem, stime in subjects:
        cursor.execute("INSERT INTO subjects (subject_code, subject_name, branch, semester, faculty_id) VALUES (?, ?, ?, ?, ?)", (code, name, branch, sem, fid))
        sid = cursor.lastrowid
        
        # Create an exam for each subject
        exam_name = f"{name} Mid-Term 2026"
        cursor.execute("""
            INSERT INTO exams (course_code, subject_id, exam_name, exam_date, start_time, end_time, total_marks, duration_minutes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (code, sid, exam_name, "2026-04-15", stime, "15:00", 20, 60))

    # 4. Setup Students & Enrollment
    students = [
        ("Student One", "EN001", "CS", 4),
        ("Student Two", "EN002", "CS", 4),
        ("Student Three", "EN003", "IT", 3),
        ("Student Four", "EN004", "IT", 6)
    ]
    
    for name, enroll, br, sem in students:
        cursor.execute("INSERT INTO users (username, password, role, email) VALUES (?, ?, 'student', ?)", (enroll, hpw, f"{enroll}@test.com"))
        uid = cursor.lastrowid
        cursor.execute("INSERT INTO student_details (user_id, full_name, enrollment_no, branch, semester) VALUES (?, ?, ?, ?, ?)", (uid, name, enroll, br, sem))
        
        if enroll in ["EN001", "EN002"]:
            cursor.execute("INSERT INTO student_subjects (enrollment_no, course_code) VALUES (?, ?)", (enroll, "CS401"))
            cursor.execute("INSERT INTO student_subjects (enrollment_no, course_code) VALUES (?, ?)", (enroll, "CS501"))
        else:
            cursor.execute("INSERT INTO student_subjects (enrollment_no, course_code) VALUES (?, ?)", (enroll, "CS301"))
            cursor.execute("INSERT INTO student_subjects (enrollment_no, course_code) VALUES (?, ?)", (enroll, "CS601"))

    # 5. Add Sample Questions for DBMS (CS401)
    dbms_questions = [
        ("What does SQL stand for?", "Structured Query Language", "Structured Question Language", "Strong Query Language", "Simple Query Language", 1),
        ("Which of the following is a NoSQL database?", "MongoDB", "MySQL", "PostgreSQL", "Oracle", 1),
        ("What is a primary key?", "Unique identifier for a record", "A key used for encryption", "A foreign key", "None of these", 1)
    ]
    
    cursor.execute("SELECT id FROM subjects WHERE subject_code = 'CS401'")
    dbms_sid = cursor.fetchone()[0]
    
    for q_text, o1, o2, o3, o4, correct in dbms_questions:
        cursor.execute("INSERT INTO questions (subject_id, question_text, marks, difficulty) VALUES (?, ?, ?, ?)", (dbms_sid, q_text, 5, "medium"))
        qid = cursor.lastrowid
        cursor.execute("INSERT INTO exam_questions (course_code, question_id, section) VALUES (?, ?, ?)", ("CS401", qid, "A"))
        opts = [o1, o2, o3, o4]
        for i, opt in enumerate(opts):
            cursor.execute("INSERT INTO options (question_id, option_text, is_correct) VALUES (?, ?, ?)", (qid, opt, 1 if i+1 == correct else 0))

    conn.commit()
    conn.close()
    print("Exam Test Sample Data Seeded Successfully!")

if __name__ == "__main__":
    seed_exam_data()
