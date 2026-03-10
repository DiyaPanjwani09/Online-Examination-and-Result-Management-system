import sqlite3
from werkzeug.security import generate_password_hash

DATABASE = "database.db"


# ================= DATABASE CONNECTION =================
def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ================= INITIALIZE DATABASE =================
def init_db():
    conn = get_connection()

    # ================= USERS =================
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('student','faculty'))
        )
    """)

    # ================= STUDENT DETAILS =================
    conn.execute("""
        CREATE TABLE IF NOT EXISTS student_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            enrollment_no TEXT UNIQUE NOT NULL,
            branch TEXT,
            semester INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ================= FACULTY DETAILS =================
    conn.execute("""
        CREATE TABLE IF NOT EXISTS faculty_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            department TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ================= SUBJECTS =================
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_name TEXT NOT NULL,
            branch TEXT NOT NULL,
            semester INTEGER NOT NULL,
            faculty_id INTEGER,
            UNIQUE(subject_name, branch, semester),
            FOREIGN KEY(faculty_id) REFERENCES faculty_details(id) 
            ON DELETE SET NULL
        )
    """)

    # ================= STUDENT - SUBJECT MAPPING =================
    conn.execute("""
        CREATE TABLE IF NOT EXISTS student_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            UNIQUE(student_id, subject_id),
            FOREIGN KEY(student_id) REFERENCES student_details(id) 
            ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) 
            ON DELETE CASCADE
        )
    """)

    # ================= EXAMS =================
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            exam_name TEXT NOT NULL,
            exam_date TEXT,
            total_marks INTEGER,
            duration_minutes INTEGER,
            pass_percentage INTEGER DEFAULT 40,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) 
            ON DELETE CASCADE
        )
    """)

    # ================= EXAM ATTEMPTS =================
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exam_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            exam_id INTEGER NOT NULL,
            score INTEGER,
            completed INTEGER DEFAULT 0,
            FOREIGN KEY(student_id) REFERENCES student_details(id) 
            ON DELETE CASCADE,
            FOREIGN KEY(exam_id) REFERENCES exams(id) 
            ON DELETE CASCADE
        )
    """)

    # ================= QUESTIONS =================
    conn.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER,
            question_text TEXT NOT NULL,
            question_type TEXT NOT NULL,
            marks INTEGER DEFAULT 1,
            negative_marks REAL DEFAULT 0,
            difficulty TEXT,
            correct_integer_answer INTEGER,
            FOREIGN KEY(subject_id) REFERENCES subjects(id)
            ON DELETE CASCADE
        )
    ''')

    # ================= OPTIONS =================
    conn.execute('''
        CREATE TABLE IF NOT EXISTS options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER,
            option_text TEXT NOT NULL,
            is_correct INTEGER DEFAULT 0,
            FOREIGN KEY(question_id) REFERENCES questions(id)
            ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()


# ================= ADD USER =================
def add_user(username, password, role):
    conn = get_connection()

    hashed_password = generate_password_hash(password)

    conn.execute("""
        INSERT INTO users (username, password, role)
        VALUES (?, ?, ?)
    """, (username, hashed_password, role))

    conn.commit()
    conn.close()


# ================= GET USER =================
def get_user_by_username(username, role):
    conn = get_connection()

    user = conn.execute("""
        SELECT * FROM users
        WHERE username = ? AND role = ?
    """, (username, role)).fetchone()

    conn.close()
    return user


# ================= GET USER BY EMAIL =================
def get_user_by_email(email, role):
    conn = get_connection()
    user = conn.execute("""
        SELECT * FROM users
        WHERE email = ? AND role = ?
    """, (email.strip().lower(), role)).fetchone()
    conn.close()
    return user


def get_user_by_email_any_role(email):
    conn = get_connection()
    user = conn.execute("""
        SELECT * FROM users
        WHERE email = ?
    """, (email.strip().lower(),)).fetchone()
    conn.close()
    return user


# ================= UPDATE PASSWORD =================
def update_user_password(user_id, new_password):
    from werkzeug.security import generate_password_hash
    conn = get_connection()
    conn.execute("""
        UPDATE users SET password = ? WHERE id = ?
    """, (generate_password_hash(new_password), user_id))
    conn.commit()
    conn.close()
