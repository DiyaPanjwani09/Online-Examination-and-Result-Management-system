import sqlite3


DATABASE = "database.db"


# ---------- DATABASE CONNECTION ----------
def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# ---------- CREATE QUESTION TABLES ----------
def create_question_tables():
    conn = get_connection()

    # SUBJECTS
    conn.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_name TEXT NOT NULL
        )
    ''')

    # QUESTIONS
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
        )
    ''')

    # OPTIONS (For MCQ Types)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER,
            option_text TEXT NOT NULL,
            is_correct INTEGER DEFAULT 0,
            FOREIGN KEY(question_id) REFERENCES questions(id)
        )
    ''')

    conn.commit()
    conn.close()


# ---------- ADD SUBJECT ----------
def add_subject(subject_name):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("INSERT INTO subjects (subject_name) VALUES (?)", (subject_name,))
    conn.commit()
    conn.close()


# ---------- ADD QUESTION ----------
def add_question(subject_id, question_text, question_type,
                 marks=1, negative_marks=0, difficulty="Easy",
                 correct_integer_answer=None):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO questions 
        (subject_id, question_text, question_type, marks, negative_marks, difficulty, correct_integer_answer)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (subject_id, question_text, question_type,
          marks, negative_marks, difficulty, correct_integer_answer))

    question_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return question_id


# ---------- ADD OPTIONS ----------
def add_option(question_id, option_text, is_correct=0):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO options (question_id, option_text, is_correct)
        VALUES (?, ?, ?)
    """, (question_id, option_text, is_correct))

    conn.commit()
    conn.close()


# ---------- GET QUESTIONS BY SUBJECT ----------
def get_questions_by_subject(subject_id):
    conn = get_connection()

    questions = conn.execute("""
        SELECT * FROM questions WHERE subject_id = ?
    """, (subject_id,)).fetchall()

    exam_data = []

    for q in questions:
        options = conn.execute("""
            SELECT * FROM options WHERE question_id = ?
        """, (q['id'],)).fetchall()

        exam_data.append({
            "question": q,
            "options": options
        })

    conn.close()
    return exam_data
