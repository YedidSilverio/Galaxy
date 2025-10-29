from flask import Flask, render_template, request, redirect, url_for, session, flash
from database import init_db, crear_usuario, verificar_usuario, guardar_en_historial, obtener_historial_usuario  # Agregar los imports que faltan
from flask import jsonify  

app = Flask(__name__)
app.secret_key ='288b0fcd9ce892c8c69de4254d8ca7152c5c4c19d85bf878'

init_db()

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard')) 
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = verificar_usuario(username, password)
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('¡Login exitoso!', 'success')
            return redirect(url_for('dashboard'))  
        else:
            flash('Usuario o contraseña incorrectos', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Las contraseñas no coinciden', 'error')
        elif len(password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres', 'error')
        else:
            if crear_usuario(username, email, password):
                flash('¡Registro exitoso! Ahora puedes iniciar sesión', 'success')
                return redirect(url_for('login'))
            else:
                flash('El usuario o email ya existe', 'error')
    
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # CAMBIADO: Ahora usa el template del dashboard completo
    return render_template('dashboard.html', username=session['username'])

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión', 'info')
    return redirect(url_for('login'))

@app.route('/historial')
def historial():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    historial_usuario = obtener_historial_usuario(session['user_id'])
    
    return render_template('historial.html', 
                         username=session['username'],
                         historial=historial_usuario)

@app.route('/probar_historial')
def probar_historial():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    guardar_en_historial(
        user_id=session['user_id'],
        tool_name="FastQC",
        input_file="mi_archivo.fastq",
        status="completado"
    )
    
    flash('Ejemplo agregado al historial!', 'success')  
    return redirect(url_for('historial'))

@app.route('/api/guardar_analisis', methods=['POST'])
def api_guardar_analisis():
    if 'user_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    
    datos = request.json
    guardar_en_historial(
        user_id=session['user_id'],
        tool_name=datos['herramienta'],
        input_file=datos['archivo'],
        status=datos.get('estado', 'completado')
    )
    
    return jsonify({'mensaje': 'Análisis guardado en historial'})

if __name__ == '__main__':
    app.run(debug=True)