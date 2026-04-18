# 📝 Online Examination and Result Management System

A full-stack web application for conducting online exams and managing results, built with **Python Flask** and an SQL database.

---

## 🚀 Features

- **Role-Based Authentication**: Separate portals for Admin, Faculty, and Students
- **Exam Management**: Faculty can create exams, add questions (including CSV bulk upload), and set time limits
- **Randomized Question Delivery**: Each student receives a unique, randomized set of questions per exam session
- **Result Tracking**: Automated result calculation and result history per student
- **Faculty Analytics**: Performance analysis and insights dashboard for faculty
- **Admin Dashboard**: User management and full system oversight

---

## 🛠️ Tech Stack

| Layer      | Technology              |
|------------|-------------------------|
| Backend    | Python, Flask           |
| Database   | SQLite (via `database.py`) |
| Frontend   | HTML, CSS, JavaScript   |
| Deployment | Procfile (Gunicorn)     |

---

## 📁 Project Structure

```
├── app.py                  # Main Flask application entry point
├── database.py             # Database initialization and models
├── requirements.txt        # Python dependencies
├── Procfile                # Deployment configuration
├── routes/
│   ├── auth.py             # Authentication (login/logout)
│   ├── student.py          # Student exam-taking routes
│   ├── faculty.py          # Faculty exam management routes
│   ├── faculty_analysis.py # Faculty result analysis routes
│   └── admin.py            # Admin management routes
├── static/                 # CSS, JS, and image assets
└── templates/              # HTML Jinja2 templates
```

---

## ⚙️ Getting Started

### Prerequisites

- Python 3.8+
- pip

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/DiyaPanjwani09/Online-Examination-and-Result-Management-system.git
cd Online-Examination-and-Result-Management-system

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the application
python app.py
```

The app will be available at **http://localhost:5006**

---

## 👤 Default Roles

| Role    | Access                                      |
|---------|---------------------------------------------|
| Admin   | Manage users, view all exams and results    |
| Faculty | Create exams, upload questions, view analytics |
| Student | Take exams, view own results and history    |

---

## 📊 How It Works

1. **Admin** sets up the system by registering faculty and students.
2. **Faculty** creates an exam for a subject, uploads questions via CSV or manually, and publishes it.
3. **Students** log in, take the exam (with randomized questions), and instantly receive their results.
4. **Faculty** can review class-wide performance in the analytics dashboard.

---

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).

---

*Developed as an academic project for streamlining the examination process.*
