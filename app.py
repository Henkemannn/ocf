def get_dagvecka_dates(start_date):
    """Returnerar lista med datum för dagvecka: fredag efter startdatum till fredag veckan därpå (8 dagar)."""
    # Hitta första fredag efter startdatum
    first_friday = start_date + timedelta(days=(4 - start_date.weekday()) % 7)
    if first_friday <= start_date:
        first_friday += timedelta(days=7)
    # Dagvecka: fredag till fredag (8 dagar)
    return [first_friday + timedelta(days=i) for i in range(8)]
def get_current_meny(dt, anchor_week_iso, anchor_menu_1to4, start_friday_date):
    """
    Returnerar (meal_mode, active_ukesmeny) för ett givet datum och schema.
    meal_mode: NONE, MIDDAG_ONLY, LUNCH_OG_MIDDAG, LUNCH_ONLY
    active_ukesmeny: 1-4
    """
    from datetime import timedelta
    # Hjälp: ISO-vecka
    def iso_week(d):
        return d.isocalendar()[1]
    # Hjälp: roll meny
    def roll_ukesmeny(anchor_week, anchor_menu, target_week):
        diff = (target_week - anchor_week) % 4
        return ((anchor_menu - 1 + diff) % 4) + 1
    # Hjälp: rotation phase
    def rotation_phase(d, start_friday):
        days = (d - start_friday).days
        if days < 0:
            return 'OFF'
        offset = days % 42
        if offset <= 6:
            return 'ON_NATT'
        if offset == 7:
            return 'ON_DAG_FREDAG_MIDDAG'
        if 8 <= offset <= 13:
            return 'ON_DAG_LUNCH_MIDDAG'
        if offset == 14:
            return 'ON_DAG_FREDAG_LUNCH'
        return 'OFF'
    # Beräkna
    week = iso_week(dt)
    phase = rotation_phase(dt, start_friday_date)
    # Robust rotation: alltid roll_ukesmeny för dagvecka, ingen duplicering
    dagvecka_menu = roll_ukesmeny(anchor_week_iso, anchor_menu_1to4, week)
    # Meal mode
    if phase == 'ON_NATT':
        meal_mode = 'NONE'
    elif phase == 'ON_DAG_FREDAG_MIDDAG':
        meal_mode = 'MIDDAG_ONLY'
    elif phase == 'ON_DAG_LUNCH_MIDDAG':
        meal_mode = 'LUNCH_OG_MIDDAG'
    elif phase == 'ON_DAG_FREDAG_LUNCH':
        meal_mode = 'LUNCH_ONLY'
    else:
        meal_mode = 'NONE'
    return meal_mode, dagvecka_menu
# Hjälpfunktion för att initiera databasen (skapa tabeller om de saknas)
def init_db():
    db = get_db()
    with open('schema.sql', 'r', encoding='utf-8') as f:
        db.executescript(f.read())
    db.commit()



# 1. Alla imports
import os
import sys
import io
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
try:
    from docx import Document
except ImportError:
    Document = None
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

# --- TURNUS ENDPOINTS (Steg 6) ---
from flask import request, jsonify
import rotation
from datetime import datetime

# --- /TURNUS ENDPOINTS (Steg 6) ---

# 2. App-init och variabler
app = Flask(__name__)
app.secret_key = 'byt-ut-denna-till-nagot-unikt-och-hemligt-2025!'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'henrikjonsson031@gmail.com'
app.config['MAIL_DEFAULT_SENDER'] = 'henrikjonsson031@gmail.com'
app.config['MAIL_PASSWORD'] = 'dwsi pmkt ises bxdi'
mail = Mail(app)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- TURNUS ENDPOINTS (Steg 6) ---
from flask import request, jsonify
import rotation
from datetime import datetime

def _bad_request(msg: str, code: int = 400):
    return jsonify({"ok": False, "error": msg}), code

def _parse_ts_or_date(s: str, *, end=False) -> str:
    """
    Tillåt "YYYY-MM-DD" (konvertera till start/end på dagen) eller "YYYY-MM-DDTHH:MM".
    Returnerar ISO-sträng "YYYY-MM-DDTHH:MM".
    """
    if not s:
        raise ValueError("Tom sträng")
    try:
        # Full timestamp
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M")
        return dt.strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        pass
    try:
        # Datum → börja/sluta på dygnet
        d = datetime.strptime(s, "%Y-%m-%d")
        if end:
            d = d.replace(hour=23, minute=59)
        else:
            d = d.replace(hour=0, minute=0)
        return d.strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        raise ValueError("Fel format, använd YYYY-MM-DD eller YYYY-MM-DDTHH:MM")

@app.get("/turnus/preview")
def turnus_preview():
    """
    Returnerar slots (alla status) för rigg inom intervall.
    Query: rig_id (int), start (YYYY-MM-DD eller YYYY-MM-DDTHH:MM),
           end (samma format).
    """
    rig_id = request.args.get("rig_id", type=int)
    start = request.args.get("start")
    end = request.args.get("end")
    if rig_id is None:
        return _bad_request("Saknar rig_id (int).")
    if not start or not end:
        return _bad_request("Saknar start och/eller end.")
    try:
        start_ts = _parse_ts_or_date(start, end=False)
        end_ts = _parse_ts_or_date(end, end=True)
    except ValueError as e:
        return _bad_request(str(e))

    try:
        rows = rotation.preview(rig_id=rig_id, start_ts=start_ts, end_ts=end_ts)
        return jsonify({"ok": True, "count": len(rows), "items": rows})
    except Exception as e:
        # Logga gärna e med logger om ni har
        return _bad_request(f"Misslyckades att hämta preview: {e}", 500)

@app.get("/turnus/view")
def turnus_view():
    """
    Returnerar endast publicerade slots för rigg inom intervall.
    Query: rig_id (int), start (YYYY-MM-DD eller YYYY-MM-DDTHH:MM),
           end (samma format).
    """
    rig_id = request.args.get("rig_id", type=int)
    start = request.args.get("start")
    end = request.args.get("end")
    if rig_id is None:
        return _bad_request("Saknar rig_id (int).")
    if not start or not end:
        return _bad_request("Saknar start och/eller end.")
    try:
        start_ts = _parse_ts_or_date(start, end=False)
        end_ts = _parse_ts_or_date(end, end=True)
    except ValueError as e:
        return _bad_request(str(e))

    try:
        rows = rotation.view(rig_id=rig_id, start_ts=start_ts, end_ts=end_ts)
        return jsonify({"ok": True, "count": len(rows), "items": rows})
    except Exception as e:
        return _bad_request(f"Misslyckades att hämta view: {e}", 500)
# --- /TURNUS ENDPOINTS (Steg 6) ---

# 3. Hjälpfunktioner
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect('app.db')
        g.db.row_factory = sqlite3.Row
    return g.db

def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        session.pop('user_id', None)
        session.pop('role', None)
        session.pop('force_pw_change', None)
        return None
    return user


def superuser_required(view_func):
    from functools import wraps
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get('superuser'):
            return redirect(url_for('superuser_login'))
        return view_func(*args, **kwargs)
    return wrapper


def login_required(view_func):
    from functools import wraps
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for('login', next=request.path))
        return view_func(*args, **kwargs)
    return wrapper


# 4. Alla @app.route-funktioner (inklusive admin_menu sist)
# ...existing code for all routes...

# Admin: Menyhantering (admin_menu)
@app.route('/admin/menu', methods=['GET', 'POST'])
def admin_menu():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    s = db.execute("SELECT * FROM settings WHERE tenant_id=?", (u['tenant_id'],)).fetchone()
    startvecka_info = None
    aktuell_uke = None
    import os
    menu_sheets = []
    if request.method == 'POST':
        if 'menuFile' in request.files and request.files['menuFile'].filename:
            file = request.files['menuFile']
            filename = file.filename or 'uploaded_menu_file'
            filepath = os.path.join(UPLOAD_FOLDER, str(filename))
            file.save(filepath)
            import pandas as pd
            import os
            ext = os.path.splitext(filename)[1].lower()
            if ext == '.csv':
                df = pd.read_csv(filepath)
                # Bygg struktur: {uke: {lunsj: [...], middag: [...]}}
                uke_map = {}
                for _, row in df.iterrows():
                    uke = str(row.get('Uke', '')).strip()
                    dag = str(row.get('Dag', '')).strip()
                    maltid = str(row.get('Måltid', '')).strip().lower()
                    kategori = str(row.get('Kategori', '')).strip()
                    rett = str(row.get('Rett', '')).strip()
                    if not uke:
                        continue
                    if uke not in uke_map:
                        uke_map[uke] = {'uke': uke, 'lunsj': [], 'middag': []}
                    # Hantera både "lunsj" och "lunch" som lunch
                    if maltid in ('lunsj', 'lunch'):
                        uke_map[uke]['lunsj'].append({'dag': dag, 'kategori': kategori, 'rett': rett})
                    elif maltid == 'middag':
                        uke_map[uke]['middag'].append({'dag': dag, 'kategori': kategori, 'rett': rett})
                menu_sheets = list(uke_map.values())
            elif ext in ('.xlsx', '.xls'):
                xls = pd.ExcelFile(filepath)
                for sheet_name in xls.sheet_names:
                    df = xls.parse(sheet_name)
                    uke = sheet_name
                    lunsj = []
                    middag = []
                    for _, row in df.iterrows():
                        dag = str(row.get('Dag', '')).strip()
                        kategori = str(row.get('Kategori', '')).strip()
                        lunsj_rett = str(row.get('Lunsj', '')).strip()
                        middag_rett = str(row.get('Middag', '')).strip()
                        if lunsj_rett:
                            lunsj.append({'dag': dag, 'kategori': kategori, 'rett': lunsj_rett})
                        if middag_rett:
                            middag.append({'dag': dag, 'kategori': kategori, 'rett': middag_rett})
                    menu_sheets.append({'uke': uke, 'lunsj': lunsj, 'middag': middag})
            else:
                flash('Filformatet stöds ej. Ladda upp .csv eller .xlsx.', 'danger')
                menu_sheets = []
            flash('Menyfil opplastet og lest inn!', 'success')
        elif 'startMenu' in request.form and 'startWeek' in request.form:
            start_index = int(request.form['startMenu'])
            start_week = int(request.form['startWeek'])
            db.execute("UPDATE settings SET menu_start_index=?, menu_start_week=? WHERE tenant_id=?", (start_index, start_week, u['tenant_id']))
            db.commit()
            flash('Startmeny og uke lagret.', 'success')
        s = db.execute("SELECT * FROM settings WHERE tenant_id=?", (u['tenant_id'],)).fetchone()
    # Om GET, visa senaste uppladdade meny om den finns (csv eller excel)
    if not menu_sheets:
        import glob
        import pandas as pd
        import os
        files = sorted(glob.glob(os.path.join(UPLOAD_FOLDER, '*.xlsx')) + glob.glob(os.path.join(UPLOAD_FOLDER, '*.csv')), reverse=True)
        if files:
            latest = files[0]
            ext = os.path.splitext(latest)[1].lower()
            if ext == '.csv':
                df = pd.read_csv(latest)
                uke = 'CSV-meny'
                lunsj = []
                middag = []
                for _, row in df.iterrows():
                    dag = str(row.get('Dag', '')).strip()
                    kategori = str(row.get('Kategori', '')).strip()
                    lunsj_rett = str(row.get('Lunsj', '')).strip()
                    middag_rett = str(row.get('Middag', '')).strip()
                    if lunsj_rett:
                        lunsj.append({'dag': dag, 'kategori': kategori, 'rett': lunsj_rett})
                    if middag_rett:
                        middag.append({'dag': dag, 'kategori': kategori, 'rett': middag_rett})
                menu_sheets.append({'uke': uke, 'lunsj': lunsj, 'middag': middag})
            elif ext in ('.xlsx', '.xls'):
                xls = pd.ExcelFile(latest)
                for sheet_name in xls.sheet_names:
                    df = xls.parse(sheet_name)
                    uke = sheet_name
                    lunsj = []
                    middag = []
                    for _, row in df.iterrows():
                        dag = str(row.get('Dag', '')).strip()
                        kategori = str(row.get('Kategori', '')).strip()
                        lunsj_rett = str(row.get('Lunsj', '')).strip()
                        middag_rett = str(row.get('Middag', '')).strip()
                        if lunsj_rett:
                            lunsj.append({'dag': dag, 'kategori': kategori, 'rett': lunsj_rett})
                        if middag_rett:
                            middag.append({'dag': dag, 'kategori': kategori, 'rett': middag_rett})
                    menu_sheets.append({'uke': uke, 'lunsj': lunsj, 'middag': middag})
    if s and s['menu_start_index'] and s['menu_start_week']:
        startvecka_info = {
            'start_index': s['menu_start_index'],
            'start_date': s['menu_start_date'] or '',
        }
        aktuell_uke = date.today().isocalendar()[1]
    return render_template('admin_menu.html', startvecka_info=startvecka_info, aktuell_uke=aktuell_uke, menu_sheets=menu_sheets)


# =======================

###########################################################
# SUPERUSER ADMIN PANEL
###########################################################
from functools import wraps
SUPERUSER_CODE = "rigplan2025"  # Byt till din egen hemliga kod!


@app.route('/superuser', methods=['GET', 'POST'])
def superuser_login():
    if request.method == 'POST':
        code = request.form.get('code', '')
        if code == SUPERUSER_CODE:
            session['superuser'] = True
            return redirect(url_for('superuser_panel'))
        else:
            flash('Feil kode. Prøv igjen.', 'danger')
    return render_template('superuser_login.html')

@app.route('/superuser/panel', methods=['GET', 'POST'])
@superuser_required
def superuser_panel():
    # ...funktionens logik...
    db = get_db()
    admins = db.execute("SELECT id, name, email, rig_id FROM users WHERE role='admin'").fetchall()
    error = None
    # Hantera borttagning av rigg
    if request.method == 'POST' and 'delete_rig_id' in request.form:
        rig_id = int(request.form['delete_rig_id'])
        try:
            db.execute("DELETE FROM rigs WHERE id=?", (rig_id,))
            db.commit()
            flash("Rigg er slettet!", "success")
            return redirect(url_for('superuser_panel'))
        except Exception as e:
            error = f"Kunne ikke slette rigg: {e}"
    # Hantera borttagning av admin
    elif request.method == 'POST' and 'delete_admin_id' in request.form:
        admin_id = int(request.form['delete_admin_id'])
        try:
            db.execute("DELETE FROM users WHERE id=? AND role='admin'", (admin_id,))
            db.commit()
            flash("Admin er slettet!", "success")
            return redirect(url_for('superuser_panel'))
        except Exception as e:
            error = f"Kunne ikke slette admin: {e}"
    # Hantera skapande av rigg
    elif request.method == 'POST' and 'new_rig_name' in request.form:
        rig_name = request.form['new_rig_name'].strip()
        rig_desc = request.form.get('new_rig_desc', '').strip()
        if not rig_name:
            error = "Du må fylle ut rignavn."
        else:
            try:
                db.execute("INSERT INTO rigs (name, description) VALUES (?, ?)", (rig_name, rig_desc))
                db.commit()
                flash("Rigg er opprettet!", "success")
                return redirect(url_for('superuser_panel'))
            except Exception as e:
                error = f"Kunne ikke opprette rigg: {e}"
    # Hantera skapande av admin
    elif request.method == 'POST':
        email = request.form['email'].strip().lower()
        name = request.form['name'].strip()
        password = request.form['password']
        rig_id = int(request.form.get('rig_id', 0))
        if not email or not name or not password or not rig_id:
            error = "Du må fylle ut alle felt og velge rigg."
        else:
            try:
                db.execute("INSERT INTO users (email, name, password_hash, tenant_id, rig_id, role) VALUES (?, ?, ?, 0, ?, 'admin')",
                           (email, name, generate_password_hash(password), rig_id))
                db.commit()
                flash("Admin er opprettet!", "success")
                return redirect(url_for('superuser_panel'))
            except Exception as e:
                error = f"Kunne ikke opprette admin: {e}"
    db.execute('''
        CREATE TABLE IF NOT EXISTS prep_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_instance_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            done INTEGER DEFAULT 0,
            type TEXT CHECK(type IN ('prep','frysplock')) NOT NULL
        )
    ''')
    # Skapa rigs-tabellen om den inte finns
    db.execute('''
        CREATE TABLE IF NOT EXISTS rigs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT
        )
    ''')
    # Skapa users-tabellen om den inte finns
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            password_hash TEXT,
            tenant_id INTEGER,
            role TEXT,
            rig_id INTEGER
        )
    ''')
    db.commit()
    return render_template('superuser_panel.html', admins=admins, error=error)
    db = get_db()
    admins = db.execute("SELECT id, name, email, rig_id FROM users WHERE role='admin'").fetchall()
    error = None
    # Hantera borttagning av rigg
    if request.method == 'POST' and 'delete_rig_id' in request.form:
        rig_id = int(request.form['delete_rig_id'])
        try:
            db.execute("DELETE FROM rigs WHERE id=?", (rig_id,))
            db.commit()
            flash("Rigg er slettet!", "success")
            return redirect(url_for('superuser_panel'))
        except Exception as e:
            error = f"Kunne ikke slette rigg: {e}"
    # Hantera borttagning av admin
    elif request.method == 'POST' and 'delete_admin_id' in request.form:
        admin_id = int(request.form['delete_admin_id'])
        try:
            db.execute("DELETE FROM users WHERE id=? AND role='admin'", (admin_id,))
            db.commit()
            flash("Admin er slettet!", "success")
            return redirect(url_for('superuser_panel'))
        except Exception as e:
            error = f"Kunne ikke slette admin: {e}"
    # Hantera skapande av rigg
    elif request.method == 'POST' and 'new_rig_name' in request.form:
        rig_name = request.form['new_rig_name'].strip()
        rig_desc = request.form.get('new_rig_desc', '').strip()
        if not rig_name:
            error = "Du må fylle ut rignavn."
        else:
            try:
                db.execute("INSERT INTO rigs (name, description) VALUES (?, ?)", (rig_name, rig_desc))
                db.commit()
                flash("Rigg er opprettet!", "success")
                return redirect(url_for('superuser_panel'))
            except Exception as e:
                error = f"Kunne ikke opprette rigg: {e}"
    # Hantera skapande av admin
    elif request.method == 'POST':
        email = request.form['email'].strip().lower()
        name = request.form['name'].strip()
        password = request.form['password']
        rig_id = int(request.form.get('rig_id', 0))
        if not email or not name or not password or not rig_id:
            error = "Du må fylle ut alle felt og velge rigg."
        else:
            try:
                db.execute("INSERT INTO users (email, name, password_hash, tenant_id, rig_id, role) VALUES (?, ?, ?, 0, ?, 'admin')",
                           (email, name, generate_password_hash(password), rig_id))
                db.commit()
                flash("Admin er opprettet!", "success")
                return redirect(url_for('superuser_panel'))
            except Exception as e:
                error = f"Kunne ikke opprette admin: {e}"
    db.execute('''
        CREATE TABLE IF NOT EXISTS prep_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_instance_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            done INTEGER DEFAULT 0,
            type TEXT CHECK(type IN ('prep','frysplock')) NOT NULL
        )
    ''')
    # Skapa rigs-tabellen om den inte finns
    db.execute('''
        CREATE TABLE IF NOT EXISTS rigs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT
        )
    ''')
    # Skapa users-tabellen om den inte finns
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            password_hash TEXT,
            tenant_id INTEGER,
            role TEXT,
            temp_password TEXT,
            rig_id INTEGER
        )
    ''')
    # Lägg till kolumner om de saknas (för gamla databaser)
    try:
        db.execute("ALTER TABLE users ADD COLUMN role TEXT")
    except Exception:
        pass
    try:
        db.execute("ALTER TABLE users ADD COLUMN temp_password TEXT")
    except Exception:
        pass
    try:
        db.execute("ALTER TABLE users ADD COLUMN rig_id INTEGER")
    except Exception:
        pass

    # Skapa settings-tabellen om den inte finns
    db.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            menu_start_date TEXT,
            menu_start_index INTEGER,
            menu_start_week INTEGER,
            rotation_mode TEXT,
            shift_base_friday INTEGER,
            timezone TEXT,
            arbeidsperiod_start TEXT,
            arbeidsperiod_slut TEXT
        )
    ''')

    # Skapa övriga tabeller om de inte finns
    db.execute('''
        CREATE TABLE IF NOT EXISTS menus(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            menu_index INTEGER NOT NULL CHECK(menu_index BETWEEN 1 AND 4)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS menu_days(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_id INTEGER NOT NULL,
            dow INTEGER NOT NULL CHECK(dow BETWEEN 0 AND 6),
            meal_type TEXT NOT NULL CHECK(meal_type IN ('lunch','middag')),
            dish_name TEXT NOT NULL,
            notes_template TEXT,
            tenant_id INTEGER,
            menu_index INTEGER,
            date TEXT,
            category TEXT
        )
    ''')
    # Add category column to menu_days if missing
    try:
        db.execute("ALTER TABLE menu_days ADD COLUMN category TEXT")
    except Exception:
        pass
    db.execute('''
        CREATE TABLE IF NOT EXISTS day_instances(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            work_cycle_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            menu_index INTEGER NOT NULL,
            meal_type TEXT NOT NULL CHECK(meal_type IN ('lunch','middag')),
            notes TEXT
        )
    ''')
    # Add tenant_id column to day_instances if missing
    try:
        db.execute("ALTER TABLE day_instances ADD COLUMN tenant_id INTEGER")
    except Exception:
        pass
    # Add category column to day_instances if missing
    try:
        db.execute("ALTER TABLE day_instances ADD COLUMN category TEXT")
    except Exception:
        pass
        # Add dish_name column to day_instances if missing
        try:
            db.execute("ALTER TABLE day_instances ADD COLUMN dish_name TEXT")
        except Exception:
            pass
    db.execute('''
        CREATE TABLE IF NOT EXISTS menu_overrides(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            meal_type TEXT NOT NULL CHECK(meal_type IN ('lunch','middag')),
            dish_name TEXT,
            notes TEXT
        )
    ''')

# Skapa admin – endast om ingen admin finns
@app.route('/create_admin', methods=['GET', 'POST'])
def create_admin():
    db = get_db()
    admin_exists = db.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone() is not None
    if admin_exists:
        flash("Admin finnes allerede.", "warning")
        return redirect(url_for('start'))
    error = None
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        name = request.form['name'].strip()
        password = request.form['password']
        if not email or not name or not password:
            error = "Alle felt må fylles ut."
        else:
            from werkzeug.security import generate_password_hash
            try:
                db.execute("INSERT INTO users (email, name, password_hash, tenant_id, role) VALUES (?, ?, ?, 0, 'admin')",
                           (email, name, generate_password_hash(password)))
                db.commit()
                flash("Admin er opprettet. Du kan nå logge inn.", "success")
                return redirect(url_for('admin_login'))
            except Exception as e:
                error = f"Kunne ikke opprette admin: {e}"
    return render_template('create_admin.html', error=error)

@app.route('/adminlogin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email=? AND role='admin'", (email,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['role'] = 'admin'
            flash(f"Velkommen, admin {user['name']}!", "success")
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Feil e-post eller passord.", "danger")
    return render_template('adminlogin.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
    db = get_db()
    admin = db.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    rig_id = admin['rig_id']
    rigs = db.execute("SELECT * FROM rigs").fetchall()
    users = db.execute("SELECT * FROM users WHERE rig_id=?", (rig_id,)).fetchall()
    error = None
    new_user_info = None
    import random, string
    if request.method == 'POST':
        if 'delete_user_id' in request.form:
            user_id = int(request.form['delete_user_id'])
            try:
                db.execute("DELETE FROM users WHERE id=? AND rig_id=?", (user_id, rig_id))
                db.commit()
                flash("Bruker er slettet!", "success")
                return redirect(url_for('admin_dashboard'))
            except Exception as e:
                error = f"Kunne ikke slette bruker: {e}"
        elif 'reset_pw_user_id' in request.form:
            user_id = int(request.form['reset_pw_user_id'])
            temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            try:
                db.execute("UPDATE users SET password_hash=?, temp_password=? WHERE id=? AND rig_id=?",
                           (generate_password_hash(temp_password), temp_password, user_id, rig_id))
                db.commit()
                user = db.execute("SELECT email, role FROM users WHERE id=?", (user_id,)).fetchone()
                if user:
                    new_user_info = {'email': user['email'], 'temp_password': temp_password, 'role': user['role']}
                    # Skicka mail med nytt lösenord
                    try:
                        msg = Message('Ditt lösenord har nollställts', recipients=[user['email']])
                        msg.body = f"Hej!\n\nDitt lösenord har nollställts.\n\nE-post: {user['email']}\nRoll: {user['role']}\nEngångslösenord: {temp_password}\n\nLogga in och byt lösenord vid första inloggning."
                        mail.send(msg)
                    except Exception as e:
                        flash(f"Kunde inte skicka mail: {e}", "warning")
                flash("Lösenord nollställt!", "success")
            except Exception as e:
                error = f"Klarte ikke å nollstille lösenord: {e}"
        else:
            # Skapa ny användare (admin eller kock) för denna rigg med engångslösenord
            email = request.form['email'].strip().lower()
            name = request.form['name'].strip()
            role = request.form.get('role', 'kock')
            temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            if not email or not name or not role:
                error = "Alle felt må fylles ut."
            else:
                try:
                    db.execute("INSERT INTO users (email, name, password_hash, tenant_id, rig_id, role, temp_password) VALUES (?, ?, ?, 0, ?, ?, ?)",
                               (email, name, generate_password_hash(temp_password), rig_id, role, temp_password))
                    db.commit()
                    new_user_info = {'email': email, 'temp_password': temp_password, 'role': role}
                    # Skicka mail med inloggningsinfo
                    try:
                        msg = Message('Ditt konto är skapat', recipients=[email])
                        msg.body = f"Hej!\n\nDu har fått ett konto i Rigplanering.\n\nE-post: {email}\nRoll: {role}\nEngångslösenord: {temp_password}\n\nLogga in och byt lösenord vid första inloggning."
                        mail.send(msg)
                    except Exception as e:
                        flash(f"Kunde inte skicka mail: {e}", "warning")
                except Exception as e:
                    error = f"Klarte ikke å opprette bruker: {e}"
    return render_template('admin_dashboard.html', rigs=rigs, users=users, error=error, new_user_info=new_user_info)

    # Menus and menu days (templates)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS menus(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        menu_index INTEGER NOT NULL CHECK(menu_index BETWEEN 1 AND 4)
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS menu_days(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        menu_id INTEGER NOT NULL,
        dow INTEGER NOT NULL CHECK(dow BETWEEN 0 AND 6), -- 0=Mon ... 6=Sun
        meal_type TEXT NOT NULL CHECK(meal_type IN ('lunch','middag')),
        dish_name TEXT NOT NULL,
        notes_template TEXT
    )""")

    # Work cycles & day instances
    cur.execute("""
    CREATE TABLE IF NOT EXISTS work_cycles(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        start_friday TEXT NOT NULL -- YYYY-MM-DD
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS day_instances(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        work_cycle_id INTEGER NOT NULL,
        date TEXT NOT NULL, -- YYYY-MM-DD
        meal_type TEXT NOT NULL CHECK(meal_type IN ('lunch','middag')),
        menu_index INTEGER NOT NULL CHECK(menu_index BETWEEN 1 AND 4),
        dish_name TEXT,
        done INTEGER NOT NULL DEFAULT 0
    )""")

    # Överstyrningar via Excel (vecka -> meny)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS menu_overrides(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        iso_year INTEGER NOT NULL,
        iso_week INTEGER NOT NULL,
        menu_index INTEGER NOT NULL CHECK(menu_index BETWEEN 1 AND 4),
        UNIQUE(tenant_id, iso_year, iso_week)
    )""")

    db.commit()

# =======================
# Auth helpers (enkel sessionsbaserad)
# =======================




# =======================
# Rotation & meny
# =======================
CYCLE_DAYS = 42  # 2 veckor på + 4 veckor av

def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def iso_year_week(d: date):
    # versionssäkert: tuple (year, week, weekday)
    y, w, _ = d.isocalendar()
    return y, w

def menu_index_for_date_with_overrides(db, tenant_id: int, d: date,
                                       start_week: int,
                                       rotation_mode: str) -> int:
    """Returnerar menyindex 1..4 för datumet d, först via Excel-överstyrning sedan rotation."""
    y, w = iso_year_week(d)
    row = db.execute("""
        SELECT menu_index FROM menu_overrides
        WHERE tenant_id=? AND iso_year=? AND iso_week=?
    """, (tenant_id, y, w)).fetchone()
    if row:
        return row['menu_index']
    # Ny logik: meny gäller måndag-söndag, byts varje måndag
    s = db.execute("SELECT menu_start_date, menu_start_index FROM settings WHERE tenant_id=?", (tenant_id,)).fetchone()
    if s and s['menu_start_date'] and s['menu_start_index']:
        start_date = parse_date(s['menu_start_date'])
        start_index = int(s['menu_start_index'])
        # Hitta måndagen för startdatumet
        start_monday = start_date - timedelta(days=start_date.weekday())
        d_monday = d - timedelta(days=d.weekday())
        weeks_since_start = (d_monday - start_monday).days // 7
        menu_index = ((weeks_since_start + (start_index - 1)) % 4) + 1
        return menu_index
    return 1  # fallback

def is_on_duty(d: date, base_friday: date) -> bool:
    days = (d - base_friday).days
    return (days % CYCLE_DAYS) < 14

def duty_phase(d: date, base_friday: date) -> str:
    """
    Returns: 'off', 'week1_night', 'week1_fri_dinner', 'week2_day'
    Du börjar alltid på en fredag.
    Vecka 1 = natt (fre..tors)
    Fredag efter en vecka (offset==7): middag 15–23
    Vecka 2 (lör..fre): dag 07–19 (lunch + middag)
    """
    if not is_on_duty(d, base_friday):
        return 'off'
    offset = (d - base_friday).days % CYCLE_DAYS
    if offset <= 6:
        return 'week1_night'
    if offset == 7:
        return 'week1_fri_dinner'
    return 'week2_day'

def next_tour_start(today: date, base_friday: date) -> date:
    # Nästa datum som är kongruent med base_friday modulo 42
    days = (today - base_friday).days
    add = (-days) % CYCLE_DAYS
    return today + timedelta(days=add)

# =======================
# Seed menus if missing (Meny 1..4)
# =======================
def ensure_menus_for_tenant(tenant_id: int):
    db = get_db()
    rows = db.execute("SELECT COUNT(*) AS c FROM menus WHERE tenant_id=?", (tenant_id,)).fetchone()
    if rows['c'] >= 4:
        return
    # Skapa Meny 1..4 om saknas
    have = set(r['menu_index'] for r in db.execute("SELECT menu_index FROM menus WHERE tenant_id=?", (tenant_id,)))
    for i in range(1,5):
        if i not in have:
            db.execute("INSERT INTO menus(tenant_id,name,menu_index) VALUES(?,?,?)",
                       (tenant_id, f"Meny {i}", i))
    db.commit()

# =======================
# Routes: auth
# =======================
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        name = request.form.get('name','').strip()
        password = request.form['password']

        db = get_db()
        # tenant_id = user_id efter insert (enkel isolering)
        try:
            cur = db.execute("INSERT INTO users(email,name,password_hash,tenant_id) VALUES(?,?,?,0)",
                             (email, name, generate_password_hash(password)))
            uid = cur.lastrowid
            db.execute("UPDATE users SET tenant_id=? WHERE id=?", (uid, uid))
            db.execute("INSERT INTO settings(tenant_id, menu_start_date, menu_start_index, timezone) VALUES (?, ?, ?, ?)",
                       (uid, '', 1, 'Europe/Stockholm'))
            db.commit()
        except sqlite3.IntegrityError:
            flash("E-postadressen finnes allerede.", "danger")
            return render_template('register.html')

        if uid is not None:
            session['user_id'] = int(uid)
            ensure_menus_for_tenant(int(uid))
            flash("Konto er opprettet. Sett innstillinger.", "success")
            return redirect(url_for('settings'))
        else:
            flash("Feil ved opprettelse av bruker.", "danger")
            return render_template('register.html')

    return render_template('register.html')


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user:
            flash("Feil e-post eller passord.", "danger")
            return render_template('login.html')
        # Om temp_password är satt och matchar, tvinga byte
        if user['temp_password'] and password == user['temp_password']:
            session['user_id'] = user['id']
            session['force_pw_change'] = True
            return redirect(url_for('change_password'))
        # Vanlig inloggning
        if not check_password_hash(user['password_hash'], password):
            flash("Fel e-post eller lösenord.", "danger")
            return render_template('login.html')
        session['user_id'] = user['id']
        session.pop('force_pw_change', None)
        return redirect(request.args.get('next') or url_for('dashboard'))
    return render_template('login.html')

# Lösenordsbyte vid första inloggning
@app.route('/change_password', methods=['GET','POST'])
def change_password():
    if not session.get('user_id') or not session.get('force_pw_change'):
        return redirect(url_for('login'))
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    error = None
    if request.method == 'POST':
        pw1 = request.form['password1']
        pw2 = request.form['password2']
        if not pw1 or not pw2 or pw1 != pw2:
            error = "Lösenorden måste matcha."
        elif len(pw1) < 6:
            error = "Lösenordet måste vara minst 6 tecken."
        else:
            db.execute("UPDATE users SET password_hash=?, temp_password=NULL WHERE id=?", (generate_password_hash(pw1), user['id']))
            db.commit()
            session.pop('force_pw_change', None)
            flash("Lösenordet är bytt. Du är nu inloggad.", "success")
            return redirect(url_for('dashboard'))
    return render_template('change_password.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# =======================
# Routes: settings & menus
# =======================
@app.route('/settings', methods=['GET','POST'])
@login_required
def settings():
    db = get_db()
    u = current_user()
    if u is None:
        return redirect(url_for('login', next=request.path))
    s = db.execute("SELECT * FROM settings WHERE tenant_id=?", (u['tenant_id'],)).fetchone()
    if s is None:
        db.execute("INSERT INTO settings (tenant_id, menu_start_week, rotation_mode, shift_base_friday, timezone) VALUES (?, ?, ?, ?, ?)",
                   (u['tenant_id'], 1, 'rotation', '', 'Europe/Stockholm'))
        db.commit()
        s = db.execute("SELECT * FROM settings WHERE tenant_id=?", (u['tenant_id'],)).fetchone()

    error = None
    if request.method == 'POST':
        menu_start_date = request.form.get('menu_start_date', '').strip()
        menu_start_index = int(request.form.get('menu_start_index') or s.get('menu_start_index') or 1)
        tz = request.form.get('timezone') or s['timezone'] or 'Europe/Stockholm'
        language = request.form.get('language') or s.get('language', 'sv')
        if not menu_start_date:
            error = "Du må angi en startdato for turen."
        else:
            db.execute("""
                UPDATE settings
                SET menu_start_date=?, menu_start_index=?, timezone=?, language=?
                WHERE tenant_id=?
            """, (menu_start_date, menu_start_index, tz, language, u['tenant_id']))
            db.commit()
            flash("Innstillinger lagret.", "success")
            return redirect(url_for('dashboard'))
    return render_template('settings.html', s=s, error=error)

@app.route('/menus')
@login_required
def menus():
    db = get_db()
    u = current_user()
    if u is None:
        return redirect(url_for('login', next=request.path))
    ensure_menus_for_tenant(u['tenant_id'])
    menus = db.execute("SELECT * FROM menus WHERE tenant_id=? ORDER BY menu_index", (u['tenant_id'],)).fetchall()
    return render_template('menus.html', menus=menus)

# Enkel menyimport (dummy) – laddar upp fil men gör inget med den än
@app.route('/import_menu_file', methods=['POST'])
@login_required
def import_menu_file():
    file = request.files.get('file')
    if file and file.filename:
        # Här kan du lägga till logik för att läsa in och spara menyfilen
        flash('Menyfil är uppladdad (ingen faktisk import ännu).', 'success')
    else:
        flash('Ingen fil vald.', 'danger')
    return redirect(url_for('menus'))

@app.route('/menus/<int:menu_id>')
@login_required
def menu_detail(menu_id):
    db = get_db()
    u = current_user()
    if u is None:
        return redirect(url_for('login', next=request.path))
    mdays = db.execute("""
        SELECT md.*, m.name as menu_name FROM menu_days md
        JOIN menus m ON m.id = md.menu_id
        WHERE menu_id=? ORDER BY dow, meal_type
    """, (menu_id,)).fetchall()
    menu = db.execute("SELECT * FROM menus WHERE id=?", (menu_id,)).fetchone()
    return render_template('menu_detail.html', menu=menu, mdays=mdays)

@app.route('/menus/<int:menu_id>/add', methods=['GET','POST'])
@login_required
def menu_day_add(menu_id):
    if request.method == 'POST':
        dow = int(request.form['dow'])
        meal_type = request.form['meal_type']
        dish_name = request.form['dish_name'].strip()
        prepp = request.form.get('prepp', '').strip()
        recept = request.form.get('recept', '').strip()
        frysplock = request.form.get('frysplock', '').strip()
        extra_notes = request.form.get('extra_notes', '').strip()
        db = get_db()
    # Hämta menu_index från menus-tabellen
    menu = db.execute("SELECT menu_index FROM menus WHERE id=?", (menu_id,)).fetchone()
    menu_index = menu['menu_index'] if menu and 'menu_index' in menu.keys() else 1
    db.execute("INSERT INTO menu_days(menu_id,dow,meal_type,dish_name,prepp,recept,frysplock,extra_notes,menu_index) VALUES(?,?,?,?,?,?,?,?,?)",
           (menu_id, dow, meal_type, dish_name, prepp, recept, frysplock, extra_notes, menu_index))
    db.commit()
    return redirect(url_for('menu_detail', menu_id=menu_id))
    return render_template('menu_day_form.html', menu_id=menu_id)

@app.route('/menus/day/<int:md_id>/delete', methods=['POST'])
@login_required
def menu_day_delete(md_id):
    db = get_db()
    row = db.execute("SELECT menu_id FROM menu_days WHERE id=?", (md_id,)).fetchone()
    if row:
        db.execute("DELETE FROM menu_days WHERE id=?", (md_id,))
        db.commit()
        return redirect(url_for('menu_detail', menu_id=row['menu_id']))
    return redirect(url_for('menus'))

# =======================
# Routes: dashboard, generation & views
# =======================
@app.route('/')
def index():
    # Om inte inloggad, redirecta till login
    if not current_user():
        return redirect(url_for('login', next=request.path))
    # Om inloggad, visa dashboard
    return redirect(url_for('dashboard'))

# Dashboard kräver inloggning
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    db = get_db()
    u = current_user()
    if u is None:
        return redirect(url_for('login', next=request.path))
    s = db.execute("SELECT * FROM settings WHERE tenant_id=?", (u['tenant_id'],)).fetchone()
    if s is None:
        db.execute("INSERT INTO settings (tenant_id, menu_start_date, menu_start_index, timezone) VALUES (?, ?, ?, ?)",
                   (u['tenant_id'], '', 1, 'Europe/Stockholm'))
        db.commit()
        s = db.execute("SELECT * FROM settings WHERE tenant_id=?", (u['tenant_id'],)).fetchone()
    arbetsperiod_start = s['arbetsperiod_start'] if s and 'arbetsperiod_start' in s.keys() and s['arbetsperiod_start'] else None
    arbetsperiod_slut = s['arbetsperiod_slut'] if s and 'arbetsperiod_slut' in s.keys() and s['arbetsperiod_slut'] else None

    # --- TURNUS från nya motorn ---
    from datetime import datetime, timedelta
    import rotation
    def _monday_of_week(d: datetime) -> datetime:
        return d - timedelta(days=d.weekday())
    def _iso_day_start(d: datetime) -> str:
        return d.strftime("%Y-%m-%dT00:00")
    def _iso_day_end(d: datetime) -> str:
        return d.strftime("%Y-%m-%dT23:59")

    rig_id = u['rig_id'] if u and 'rig_id' in u else 1
    week = request.args.get("week")
    start = request.args.get("start")
    end = request.args.get("end")
    if start and end:
        try:
            d0 = datetime.strptime(start, "%Y-%m-%d")
            d1 = datetime.strptime(end, "%Y-%m-%d")
        except ValueError:
            return _bad_request("Fel datumformat, använd YYYY-MM-DD för start/end.")
    elif week:
        try:
            d = datetime.strptime(week + "-1", "%G-W%V-%u")
            d0 = d
            d1 = d0 + timedelta(days=6)
        except ValueError:
            return _bad_request("Fel week-format, använd t.ex. 2025-W37.")
    else:
        today = datetime.now()
        d0 = _monday_of_week(today)
        d1 = d0 + timedelta(days=6)
    start_ts = _iso_day_start(d0)
    end_ts = _iso_day_end(d1)
    slots = rotation.view(rig_id=rig_id, start_ts=start_ts, end_ts=end_ts)
    by_day = {}
    for s in slots:
        start_day = s["start_ts"][:10]
        by_day.setdefault(start_day, []).append(s)
    # --- /TURNUS ---

    rig_name = None
    if u and u['rig_id']:
        rig = db.execute("SELECT name FROM rigs WHERE id=?", (u['rig_id'],)).fetchone()
        if rig:
            rig_name = rig['name']
    # Menyhämtning som tidigare
    return render_template('dashboard.html', s=s, rig_name=rig_name,
                           arbetsperiod_start=arbetsperiod_start,
                           arbetsperiod_slut=arbetsperiod_slut,
                           user=u,
                           week_start=d0.date().isoformat(),
                           week_end=d1.date().isoformat(),
                           slots_by_day=by_day)

## Legacy reset_cycle and day_instances logic removed

# =======================
# Route: Import av Excel-fliken "Menyrotasjon"
# =======================
# --- Placera denna kod efter superuser_panel ---

@app.route('/superuser/rig/<int:rig_id>', methods=['GET', 'POST'])
@superuser_required
def superuser_rig_detail(rig_id):
    db = get_db()
    error = None
    rig = db.execute("SELECT * FROM rigs WHERE id=?", (rig_id,)).fetchone()
    if not rig:
        flash("Rigg finns inte.", "danger")
        return redirect(url_for('superuser_panel'))

    # Hantera borttagning av admin
    if request.method == 'POST' and 'delete_admin_id' in request.form:
        admin_id = int(request.form['delete_admin_id'])
        try:
            db.execute("DELETE FROM users WHERE id=? AND role='admin'", (admin_id,))
            db.commit()
            flash("Admin er slettet!", "success")
            return redirect(url_for('superuser_rig_detail', rig_id=rig_id))
        except Exception as e:
            error = f"Kunne ikke slette admin: {e}"

    # Hantera skapande av admin
    elif request.method == 'POST' and 'name' in request.form and 'email' in request.form and 'password' in request.form:
        email = request.form['email'].strip().lower()
        db = get_db()
        admins = db.execute("SELECT id, name, email, rig_id FROM users WHERE role='admin'").fetchall()
        error = None
        # Hantera borttagning av rigg
        if request.method == 'POST' and 'delete_rig_id' in request.form:
            rig_id = int(request.form['delete_rig_id'])
            try:
                db.execute("DELETE FROM rigs WHERE id=?", (rig_id,))
                db.commit()
                flash("Rigg er slettet!", "success")
                return redirect(url_for('superuser_panel'))
            except Exception as e:
                error = f"Kunne ikke slette rigg: {e}"
        # Hantera borttagning av admin
        elif request.method == 'POST' and 'delete_admin_id' in request.form:
            admin_id = int(request.form['delete_admin_id'])
            try:
                db.execute("DELETE FROM users WHERE id=? AND role='admin'", (admin_id,))
                db.commit()
                flash("Admin er slettet!", "success")
                return redirect(url_for('superuser_panel'))
            except Exception as e:
                error = f"Kunne ikke slette admin: {e}"
        # Hantera skapande av rigg
        elif request.method == 'POST' and 'new_rig_name' in request.form:
            rig_name = request.form['new_rig_name'].strip()
            rig_desc = request.form.get('new_rig_desc', '').strip()
            if not rig_name:
                error = "Du må fylle ut rignavn."
            else:
                try:
                    db.execute("INSERT INTO rigs (name, description) VALUES (?, ?)", (rig_name, rig_desc))
                    db.commit()
                    flash("Rigg er opprettet!", "success")
                    return redirect(url_for('superuser_panel'))
                except Exception as e:
                    error = f"Kunne ikke opprette rigg: {e}"
        # Hantera skapande av admin
        elif request.method == 'POST':
            email = request.form['email'].strip().lower()
            name = request.form['name'].strip()
            password = request.form['password']
            rig_id = int(request.form.get('rig_id', 0))
            if not email or not name or not password or not rig_id:
                error = "Du må fylle ut alle felt og velge rigg."
            else:
                try:
                    db.execute("INSERT INTO users (email, name, password_hash, tenant_id, rig_id, role) VALUES (?, ?, ?, 0, ?, 'admin')",
                               (email, name, generate_password_hash(password), rig_id))
                    db.commit()
                    flash("Admin er opprettet!", "success")
                    return redirect(url_for('superuser_panel'))
                except Exception as e:
                    error = f"Kunne ikke opprette admin: {e}"
        db.execute('''
            CREATE TABLE IF NOT EXISTS prep_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day_instance_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                done INTEGER DEFAULT 0,
                type TEXT CHECK(type IN ('prep','frysplock')) NOT NULL
            )
        ''')
        # Skapa rigs-tabellen om den inte finns
        db.execute('''
            CREATE TABLE IF NOT EXISTS rigs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT
            )
        ''')
        # Skapa users-tabellen om den inte finns
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                password_hash TEXT,
                tenant_id INTEGER,
                role TEXT,
                rig_id INTEGER
            )
        ''')
        db.commit()
    return render_template('superuser_panel.html', admins=admins, error=error)
# --- TURNUS ADMIN (Steg 8) ---
from flask import request, jsonify, render_template, redirect, url_for, flash
import rotation
import json

@app.get("/turnus/admin")
def turnus_admin_home():
    rig_id = request.args.get("rig_id", type=int)
    templates = rotation.list_templates(rig_id=rig_id) if rig_id else rotation.list_templates()
    slots = rotation.list_slots(rig_id=rig_id) if rig_id else rotation.list_slots()
    if len(slots) > 200:
        slots = slots[-200:]
    return render_template("turnus_admin.html", templates=templates, slots=slots, rig_id=rig_id)

@app.post("/turnus/admin/template/create")
def turnus_template_create():
    name = request.form.get("name")
    rig_id = request.form.get("rig_id", type=int)
    pattern_json = request.form.get("pattern_json")
    if not name or not pattern_json:
        flash("Name och pattern_json krävs", "error")
        return redirect(url_for("turnus_admin_home"))
    try:
        tmpl_id = rotation.create_template(name=name, pattern=json.loads(pattern_json), rig_id=rig_id, is_active=True)
        flash(f"Template skapad (id={tmpl_id})", "success")
    except Exception as e:
        flash(f"Misslyckades att skapa template: {e}", "error")
    return redirect(url_for("turnus_admin_home", rig_id=rig_id))

@app.post("/turnus/admin/template/update/<int:template_id>")
def turnus_template_update(template_id: int):
    name = request.form.get("name")
    rig_id = request.form.get("rig_id", type=int)
    pattern_json = request.form.get("pattern_json")
    is_active = request.form.get("is_active")
    try:
        rotation.update_template(
            template_id,
            name=name if name else None,
            rig_id=rig_id if rig_id is not None else None,
            pattern=json.loads(pattern_json) if pattern_json else None,
            is_active=(is_active == "1") if is_active is not None else None
        )
        flash("Template uppdaterad", "success")
    except Exception as e:
        flash(f"Misslyckades att uppdatera: {e}", "error")
    return redirect(url_for("turnus_admin_home", rig_id=rig_id))

@app.post("/turnus/admin/template/active/<int:template_id>")
def turnus_template_active(template_id: int):
    active = request.form.get("active") == "1"
    rig_id = request.form.get("rig_id", type=int)
    try:
        rotation.set_template_active(template_id, active)
        flash("Template status uppdaterad", "success")
    except Exception as e:
        flash(f"Fel: {e}", "error")
    return redirect(url_for("turnus_admin_home", rig_id=rig_id))

@app.post("/turnus/admin/slots/generate")
def turnus_slots_generate():
    template_id = request.form.get("template_id", type=int)
    rig_id = request.form.get("rig_id", type=int)
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    if not all([template_id, rig_id, start_date, end_date]):
        flash("template_id, rig_id, start_date, end_date krävs", "error")
        return redirect(url_for("turnus_admin_home", rig_id=rig_id))
    try:
        n = rotation.generate_slots_from_template(template_id, start_date, end_date, rig_id_override=rig_id)
        flash(f"Genererade {n} slots", "success")
    except Exception as e:
        flash(f"Misslyckades att generera: {e}", "error")
    return redirect(url_for("turnus_admin_home", rig_id=rig_id))

@app.post("/turnus/admin/slots/publish")
def turnus_slots_publish():
    rig_id = request.form.get("rig_id", type=int)
    ids_raw = request.form.get("slot_ids", "")
    try:
        slot_ids = [int(x) for x in ids_raw.split(",") if x.strip().isdigit()]
        n = rotation.publish_slots(slot_ids)
        flash(f"Publicerade {n} slots", "success")
    except Exception as e:
        flash(f"Fel vid publish: {e}", "error")
    return redirect(url_for("turnus_admin_home", rig_id=rig_id))

@app.post("/turnus/admin/slots/delete")
def turnus_slots_delete():
    rig_id = request.form.get("rig_id", type=int)
    ids_raw = request.form.get("slot_ids", "")
    try:
        slot_ids = [int(x) for x in ids_raw.split(",") if x.strip().isdigit()]
        n = rotation.delete_slots(slot_ids)
        flash(f"Raderade {n} slots", "success")
    except Exception as e:
        flash(f"Fel vid delete: {e}", "error")
    return redirect(url_for("turnus_admin_home", rig_id=rig_id))

@app.post("/turnus/admin/bind")
def turnus_bind():
    slot_id = request.form.get("slot_id", type=int)
    user_id = request.form.get("user_id", type=int)
    rig_id = request.form.get("rig_id", type=int)
    notes = request.form.get("notes")
    if not slot_id or not user_id:
        flash("slot_id och user_id krävs", "error")
        return redirect(url_for("turnus_admin_home", rig_id=rig_id))
    try:
        rotation.bind_user_to_slot(slot_id, user_id, notes=notes)
        flash("User bunden till slot", "success")
    except Exception as e:
        flash(f"Fel vid bind: {e}", "error")
    return redirect(url_for("turnus_admin_home", rig_id=rig_id))

@app.post("/turnus/admin/unbind")
def turnus_unbind():
    slot_id = request.form.get("slot_id", type=int)
    rig_id = request.form.get("rig_id", type=int)
    try:
        n = rotation.unbind_user_from_slot(slot_id)
        flash(f"Lösgjorde {n} binding(ar)", "success")
    except Exception as e:
        flash(f"Fel vid unbind: {e}", "error")
    return redirect(url_for("turnus_admin_home", rig_id=rig_id))
# --- /TURNUS ADMIN (Steg 8) ---
if __name__ == "__main__":
    app.run(debug=True)

