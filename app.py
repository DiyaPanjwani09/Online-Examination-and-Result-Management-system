from flask import Flask, redirect, url_for
from database import init_db
from routes.auth import auth_bp
from routes.student import student_bp
from routes.faculty import faculty_bp

app = Flask(__name__)
app.secret_key = "super_secret_key_change_this"

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(student_bp)
app.register_blueprint(faculty_bp)

@app.route("/")
def home():
    # Redirect to student dashboard by default, but if you want to support both
    # maybe it's better to go to login. This keeps previous logic.
    return redirect(url_for("student_bp.student_dashboard"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
