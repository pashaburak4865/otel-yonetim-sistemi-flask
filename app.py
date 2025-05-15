# app.py
from flask import Flask, render_template, request, redirect, url_for, session, send_file
import sqlite3, os, hashlib
import pandas as pd
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'gizli_anahtar'
app.config['UPLOAD_FOLDER'] = 'uploads'

ROOM_PRICES = {'SINGLE': 100, 'DOUBLE': 150, 'TRIPLE': 200}

def init_db():
    conn = sqlite3.connect('db.sqlite3')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            check_in TEXT,
            check_out TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS guests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            group_id INTEGER,
            room_no TEXT,
            room_type TEXT,
            price INTEGER,
            FOREIGN KEY(group_id) REFERENCES groups(id)
        )
    ''')
    conn.commit()
    conn.close()

def init_users():
    conn = sqlite3.connect('db.sqlite3')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    ''')
    conn.commit()
    hashed_pw = hashlib.sha256("admin123".encode()).hexdigest()
    try:
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                  ("admin", hashed_pw, "admin"))
        conn.commit()
    except:
        pass
    conn.close()

init_db()
init_users()

def require_role(role):
    return session.get('role') == role

@app.before_request
def require_login():
    public_routes = ['login', 'static']
    if request.endpoint not in public_routes and 'user_id' not in session:
        return redirect(url_for('login'))

@app.route('/')
def index():
    conn = sqlite3.connect('db.sqlite3')
    c = conn.cursor()
    c.execute("SELECT * FROM groups")
    groups = c.fetchall()
    guests_by_group = {}
    for g in groups:
        c.execute("SELECT id, full_name FROM guests WHERE group_id=?", (g[0],))
        guests = [(row[1], row[0]) for row in c.fetchall()]
        guests_by_group[g[0]] = guests
    conn.close()
    return render_template("index.html", groups=groups, guests=guests_by_group)

@app.route('/create_group', methods=['POST'])
def create_group():
    name = request.form['group_name']
    check_in = request.form['check_in']
    check_out = request.form['check_out']
    conn = sqlite3.connect('db.sqlite3')
    c = conn.cursor()
    c.execute("INSERT INTO groups (name, check_in, check_out) VALUES (?, ?, ?)", 
              (name, check_in, check_out))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/upload_guests', methods=['POST'])
def upload_guests():
    file = request.files['file']
    group_id = request.form['group_id']
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    df = pd.read_excel(filepath)
    conn = sqlite3.connect('db.sqlite3')
    c = conn.cursor()
    for _, row in df.iterrows():
        name = row['Ad Soyad']
        c.execute("INSERT INTO guests (full_name, group_id) VALUES (?, ?)", (name, group_id))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/assign_room', methods=['POST'])
def assign_room():
    guest_id = request.form['guest_id']
    room_no = request.form['room_no']
    room_type = request.form['room_type']
    price = ROOM_PRICES.get(room_type.upper(), 0)
    conn = sqlite3.connect('db.sqlite3')
    c = conn.cursor()
    c.execute("UPDATE guests SET room_no=?, room_type=?, price=? WHERE id=?", 
              (room_no, room_type, price, guest_id))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/financial_report')
def financial_report():
    if not require_role('admin'):
        return "❌ Erişim reddedildi", 403
    conn = sqlite3.connect('db.sqlite3')
    c = conn.cursor()
    c.execute("SELECT id, name FROM groups")
    groups = c.fetchall()
    report = []
    total = 0
    for gid, gname in groups:
        c.execute("SELECT SUM(price) FROM guests WHERE group_id=?", (gid,))
        group_total = c.fetchone()[0] or 0
        total += group_total
        report.append((gname, group_total))
    conn.close()
    return render_template("report.html", report=report, total=total)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        conn = sqlite3.connect('db.sqlite3')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[3]
            return redirect(url_for('index'))
        else:
            error = "Hatalı giriş"
    return render_template("login.html", error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/manage_users')
def manage_users():
    if not require_role('admin'):
        return "⛔ Yetkisiz", 403
    return render_template("manage_users.html")

@app.route('/add_user', methods=['POST'])
def add_user():
    if not require_role('admin'):
        return "⛔ Yetkisiz", 403
    username = request.form['username']
    password = hashlib.sha256(request.form['password'].encode()).hexdigest()
    role = request.form['role']
    conn = sqlite3.connect('db.sqlite3')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                  (username, password, role))
        conn.commit()
    except sqlite3.IntegrityError:
        return "Kullanıcı adı zaten var"
    conn.close()
    return redirect(url_for('manage_users'))

@app.route('/export_excel')
def export_excel():
    conn = sqlite3.connect('db.sqlite3')
    c = conn.cursor()
    c.execute('''
        SELECT g.name, gr.check_in, gr.check_out, g.full_name 
        FROM guests g
        JOIN groups gr ON g.group_id = gr.id
    ''')
    rows = c.fetchall()
    conn.close()
    df = pd.DataFrame(rows, columns=['Grup Adı', 'Giriş Tarihi', 'Çıkış Tarihi', 'Ad Soyad'])
    output_path = os.path.join('exports', 'misafir_raporu.xlsx')
    df.to_excel(output_path, index=False)
    return send_file(output_path, as_attachment=True)

if __name__ == '__main__':
    if not os.path.exists('uploads'): os.makedirs('uploads')
    if not os.path.exists('exports'): os.makedirs('exports')
    app.run(debug=True)
