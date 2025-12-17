from bioblend.galaxy import GalaxyInstance
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from database import init_db, crear_usuario, verificar_usuario, guardar_en_historial, obtener_historial_usuario
from galaxy_connection import listar_historiales
import os
import time 

app = Flask(__name__)
app.secret_key = '288b0fcd9ce892c8c69de4254d8ca7152c5c4c19d85bf878'

# Inicializa la base de datos
init_db()

# Conexión global con Galaxy
gi = GalaxyInstance(
    url='https://usegalaxy.org/',
    key='78eea92c4f450db6101665d6521f37ed'
)

# Carpeta temporal para archivos subidos
TEMP_FOLDER = 'temp'
os.makedirs(TEMP_FOLDER, exist_ok=True)

# ---------------- Rutas de Usuario ---------------- #

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

#dashboard
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        # Obtener todas las historias de Galaxy
        historiales_galaxy = gi.histories.get_histories()

        historiales = []
        for h in historiales_galaxy:
            historiales.append({
                'name': h['name'],
                'id': h['id'],
                'update_time': h['update_time'],
                # URL directa para abrir la historia en Galaxy
                'url': f"https://usegalaxy.org/histories/view?id={h['id']}"
            })

    except Exception as e:
        flash(f"Error al obtener historiales de Galaxy: {str(e)}", 'error')
        historiales = []

    return render_template('dashboard.html', 
                           username=session['username'], 
                           historiales=historiales)

#crear historia
@app.route('/crear_historia', methods=['POST'])
def crear_historia():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    nombre = request.form.get('nombre_historia')
    if not nombre:
        flash('Debe ingresar un nombre para la historia', 'error')
        return redirect(url_for('dashboard'))

    try:
        history = gi.histories.create_history(name=nombre)
        # Guardamos la historia activa en sesión
        session['history_id'] = history['id']
        flash(f"Historia '{nombre}' creada correctamente", 'success')
    except Exception as e:
        flash(f"Error al crear historia: {str(e)}", 'error')

    return redirect(url_for('dashboard'))


app.route('/logout')
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

# ---------------- Rutas Galaxy ---------------- #

@app.route('/galaxy_historiales')
def galaxy_historiales():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    historiales = listar_historiales()
    if isinstance(historiales, dict) and historiales.get('error'):
        flash(f"Error al obtener historiales: {historiales.get('error')}", 'error')
        historiales = []

    return render_template('galaxy_historiales.html', historiales=historiales)


#subir archivo
@app.route('/subir_archivo', methods=['POST'])
def subir_archivo():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    archivo = request.files.get('file')
    if not archivo:
        flash('No se seleccionó ningún archivo', 'error')
        return redirect(url_for('dashboard'))

    # Guardar temporalmente
    filepath = os.path.join(TEMP_FOLDER, archivo.filename)
    archivo.save(filepath)

    # Obtener la última historia creada o crear una nueva
    histories = gi.histories.get_histories()
    if histories:
        last_history = histories[0]  # usualmente la más reciente
        history_id = last_history['id']
    else:
        new_history = gi.histories.create_history(name=f"Historia de {session['username']}")
        history_id = new_history['id']

    # Subir archivo con tipo correcto
    dataset = gi.tools.upload_file(filepath, history_id, file_type='fastqsanger')
    dataset_id = dataset['outputs'][0]['id']

    # Guardar IDs en sesión
    session['dataset_id'] = dataset_id
    session['history_id'] = history_id

    # --- Ejecutar FastQC ---
    try:
        tool_fastqc = 'toolshed.g2.bx.psu.edu/repos/devteam/fastqc/fastqc/0.72+galaxy1'
        job_fastqc = gi.tools.run_tool(history_id, tool_fastqc, {
            'input_file': {'id': dataset_id, 'src': 'hda'}
        })
        flash('✅ FastQC ejecutado correctamente', 'success')
    except Exception as e:
        flash(f'⚠️ Error al ejecutar FastQC: {e}', 'error')

    # --- Ejecutar Bowtie2 ---
    try:
        tool_bowtie = 'toolshed.g2.bx.psu.edu/repos/devteam/bowtie2/bowtie2/2.5.0+galaxy0'
        inputs = {
            'input_1': {'id': dataset_id, 'src': 'hda'},
            'reference_genome': {'values': ['hg19']},
            'analysis_type': 'default'
        }
        job_bowtie = gi.tools.run_tool(history_id, tool_bowtie, inputs)
        flash('✅ Bowtie2 ejecutado correctamente en Galaxy', 'success')
    except Exception as e:
        flash(f'⚠️ Error al ejecutar Bowtie2: {e}', 'error')

    # --- Obtener resultados finales ---
    history_contents = gi.histories.show_history(history_id, contents=True)
    resultados = []
    for item in history_contents:
        if item['name'].lower().startswith(('fastqc', 'bowtie2')):
            resultados.append({
                'name': item['name'],
                'id': item['id'],
                'state': item['state'],
                'url': f"https://usegalaxy.org/datasets/{item['id']}/display"
            })

    flash(f"Archivo '{archivo.filename}' subido y analizado correctamente en Galaxy", 'success')
    return render_template('dashboard.html',
                           username=session['username'],
                           historiales=history_contents,
                           resultados=resultados)

#FastQC
@app.route('/ejecutar_fastqc', methods=['POST'])
def ejecutar_fastqc():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    archivo = session.get('dataset_id')
    if not archivo:
        flash('Debes subir un archivo primero', 'error')
        return redirect(url_for('dashboard'))

    try:
        # Crear una history nueva para este análisis
        history = gi.histories.create_history(name=f"FastQC de {session['username']} - {datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        # Subir el archivo a esta history
        dataset = gi.tools.upload_file(
            filename=os.path.join(TEMP_FOLDER, session['last_uploaded_filename']),
            history_id=history['id'],
            file_type='auto'
        )
        
        # Ejecutar FastQC
        tool_inputs = {'input1': {'id': dataset['outputs'][0]['id'], 'src': 'hda'}}
        job = gi.tools.run_tool(history_id=history['id'], tool_id='fastqc', inputs=tool_inputs)

        # Guardar history_id y dataset_id en sesión si quieres usarlo después
        session['history_id'] = history['id']
        session['dataset_id'] = dataset['outputs'][0]['id']

        flash(f"FastQC ejecutado correctamente en la history '{history['name']}'", 'success')

    except Exception as e:
        flash(f"Error al ejecutar FastQC: {e}", 'error')

    return redirect(url_for('dashboard'))

 # Bowtie 2   
@app.route('/ejecutar_bowtie', methods=['POST'])
def ejecutar_bowtie():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    dataset_id = session.get('dataset_id')
    history_id = session.get('history_id')

    if not dataset_id or not history_id:
        flash('No hay archivo cargado para ejecutar Bowtie2', 'error')
        return redirect(url_for('dashboard'))

    # --- Ejecutar Bowtie2 ---
    try:
        tool_bowtie = 'toolshed.g2.bx.psu.edu/repos/devteam/bowtie2/bowtie2/2.5.0+galaxy0'
        
        inputs = {
            'input_1': {'id': dataset_id, 'src': 'hda'},
            'reference_genome': 'hg19',   # ESTE SÍ EXISTE EN GALAXY TEST
            'analysis_type': 'default'
        }

        job_bowtie = gi.tools.run_tool(history_id, tool_bowtie, inputs)
        flash('✅ Bowtie2 ejecutado correctamente en Galaxy', 'success')

    except Exception as e:
        flash(f'⚠️ Error al ejecutar Bowtie2: {e}', 'error')

    return redirect(url_for('dashboard'))


# ---------------- Ejecutar servidor ---------------- #
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)

