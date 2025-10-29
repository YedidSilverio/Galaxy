import sqlite3 
from werkzeug.security import generate_password_hash, check_password_hash

def init_db():
    conn = sqlite3.connect('galaxy_usuarios.db')
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users ( 
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            correo TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tool_name TEXT,
            input_file TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    conn.commit()
    conn.close()

def guardar_en_historial(user_id, tool_name, input_file, status="completado"):
    conn = sqlite3.connect('galaxy_usuarios.db')
    c = conn.cursor()
    
    try:
        c.execute(
            'INSERT INTO historial (user_id, tool_name, input_file, status) VALUES (?, ?, ?, ?)',
            (user_id, tool_name, input_file, status)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error guardando en historial: {e}")
        return False
    finally:
        conn.close()

def obtener_historial_usuario(user_id):
    conn = sqlite3.connect('galaxy_usuarios.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT * FROM historial 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    ''', (user_id,))
    
    historial = c.fetchall()
    conn.close()
    return historial

def crear_usuario(username, email, password): 
    conn = sqlite3.connect('galaxy_usuarios.db')
    c = conn.cursor()

    try:
        password_hash = generate_password_hash(password)
        c.execute(
            'INSERT INTO users (username, correo, password_hash) VALUES (?, ?, ?)',
            (username, email, password_hash)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError: 
        return False  
    finally:
        conn.close()

def verificar_usuario(username, password):
    conn = sqlite3.connect('galaxy_usuarios.db')
    c = conn.cursor()
    
    c.execute('SELECT id, username, password_hash FROM users WHERE username = ?', (username,))
    user = c.fetchone()
    conn.close()

    if user and check_password_hash(user[2], password):
        return {'id': user[0], 'username': user[1]}
    return None