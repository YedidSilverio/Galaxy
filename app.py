import os
from datetime import datetime
import time

from bioblend.galaxy import GalaxyInstance
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

# Impor config y modelos separados
from config import Config
from models import db, Usuario, Historia

# ---------------------------------------------------------
# Inicializa Flask y base de datos (SQLAlchemy)
# ---------------------------------------------------------
app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

# ---------------------------------------------------------
# Conexión a Galaxy usando variables del config (.env)
# ---------------------------------------------------------
gi = GalaxyInstance(
    url=Config.GALAXY_URL,
    key=Config.GALAXY_API_KEY
)

# Carpeta temporal para archivos subidos
TEMP_FOLDER = 'temp'
os.makedirs(TEMP_FOLDER, exist_ok=True)

# ---------------------------------------------------------
# Modelo extra dentro de app.py: Analisis (registro de herramientas)
# (Se define aquí para no depender de database.py)
# ---------------------------------------------------------
class Analisis(db.Model):
    __tablename__ = 'analisis'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)            # usuario local (FK opcional)
    tool_name = db.Column(db.String(200), nullable=False)      # e.g. FastQC
    input_file = db.Column(db.String(300))
    status = db.Column(db.String(50), default='pendiente')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'tool_name': self.tool_name,
            'input_file': self.input_file,
            'status': self.status,
            'created_at': self.created_at.isoformat()
        }

# ---------------------------------------------------------
# Funciones que reemplazan lo que hacía database.py
# ---------------------------------------------------------
def guardar_en_historial(user_id: int, tool_name: str, input_file: str, status: str = "completado"):
    """Guarda un registro de análisis en la tabla analisis."""
    a = Analisis(
        user_id=user_id,
        tool_name=tool_name,
        input_file=input_file,
        status=status
    )
    db.session.add(a)
    db.session.commit()
    return a

def obtener_historial_usuario(user_id: int):
    """Obtiene todos los análisis de un usuario ordenados por fecha descendente."""
    rows = Analisis.query.filter_by(user_id=user_id).order_by(Analisis.created_at.desc()).all()
    return [r.to_dict() for r in rows]

# Reemplazo simple de galaxy_connection.listar_historiales()
def listar_historiales():
    """Obtiene historiales desde Galaxy y devuelve una lista formateada o error dict."""
    try:
        raw = gi.histories.get_histories()
        formatted = []
        for h in raw:
            formatted.append({
                'name': h.get('name'),
                'id': h.get('id'),
                'update_time': h.get('update_time'),
                'url': f"https://usegalaxy.org/histories/view?id={h.get('id')}"
            })
        return formatted
    except Exception as e:
        return {'error': str(e)}

# ---------------------------------------------------------
# RUTAS DE USUARIO
# ---------------------------------------------------------
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

        # Verificar usuario en PostgreSQL
        user = Usuario.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('¡Login exitoso!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'error')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Las contraseñas no coinciden', 'error')
            return redirect(url_for('register'))

        if len(password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres', 'error')
            return redirect(url_for('register'))

        # Verificar duplicados
        if Usuario.query.filter((Usuario.username == username) | (Usuario.email == email)).first():
            flash('El usuario o email ya existe', 'error')
            return redirect(url_for('register'))

        # Crear usuario
        hashed = generate_password_hash(password)
        nuevo = Usuario(username=username, email=email, password=hashed)
        db.session.add(nuevo)
        db.session.commit()

        flash('¡Registro exitoso! Ahora puedes iniciar sesión', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión', 'info')
    return redirect(url_for('login'))

# ---------------------------------------------------------
# DASHBOARD (muestra historiales de Galaxy)
# ---------------------------------------------------------
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        historiales_galaxy = gi.histories.get_histories()
        historiales = []
        for h in historiales_galaxy:
            historiales.append({
                'name': h['name'],
                'id': h['id'],
                'update_time': h['update_time'],
                'url': f"https://usegalaxy.org/histories/view?id={h['id']}"
            })
    except Exception as e:
        flash(f"Error al obtener historiales de Galaxy: {str(e)}", 'error')
        historiales = []

    return render_template('dashboard.html',
                           username=session.get('username'),
                           historiales=historiales)

# ---------------------------------------------------------
# CREAR HISTORIA en Galaxy + guardar en BD local
# ---------------------------------------------------------
@app.route('/crear_historia', methods=['GET', 'POST'])
def crear_historia():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        nombre = request.form.get('nombre_historia')
        if not nombre:
            flash('Debe ingresar un nombre para la historia', 'error')
            return redirect(url_for('crear_historia'))

        try:
            history = gi.histories.create_history(name=nombre)
            # Guardamos la historia activa en sesión
            session['history_id'] = history['id']

            # Guardar en la BD local (tabla Historia)
            nueva_historia = Historia(
                galaxy_id=history['id'],
                nombre=history.get('name', nombre),
                fecha_creacion=datetime.utcnow(),
                usuario_id=session['user_id']
            )
            db.session.add(nueva_historia)
            db.session.commit()

            flash(f"Historia '{nombre}' creada correctamente", 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f"Error al crear historia: {str(e)}", 'error')
            return redirect(url_for('crear_historia'))

    # GET request - mostrar el template del formulario completo
    return render_template('crear_historia.html')
# ---------------------------------------------------------
# Historial local (analisis guardados)
# ---------------------------------------------------------
@app.route('/historial')
def historial():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    historial_usuario = obtener_historial_usuario(session['user_id'])
    return render_template('historial.html',
                           username=session.get('username'),
                           historial=historial_usuario)
@app.route('/historia/<history_id>', methods=['GET', 'POST'])
def datasets_historia(history_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Obtener información de la historia
    try:
        history_info = gi.histories.show_history(history_id)
        nombre_historia = history_info.get('name', f"Historia {history_id}")
        
        # Obtener datasets de la historia
        history_contents = gi.histories.show_history(history_id, contents=True)
        
        # Separar datasets por tipo (simulado - necesitarás ajustar esta lógica)
        datasets_fastq = []
        genomes = []
        
        for item in history_contents:
            if item['type'] == 'file':
                # Esto es una simplificación - necesitarás lógica más específica
                if item['name'].lower().endswith(('.fastq', '.fq')):
                    datasets_fastq.append({
                        'id': item['id'],
                        'name': item['name'],
                        'state': item.get('state', 'unknown')
                    })
                elif item['name'].lower().endswith(('.fa', '.fasta', '.fna')):
                    genomes.append({
                        'id': item['id'],
                        'name': item['name'],
                        'state': item.get('state', 'unknown')
                    })
        
        datasets = datasets_fastq + genomes
        
    except Exception as e:
        flash(f"Error al obtener información de la historia: {str(e)}", 'error')
        nombre_historia = f"Historia {history_id}"
        datasets_fastq = []
        genomes = []
        datasets = []

    # Si es POST, procesar el workflow
    if request.method == 'POST':
        id_dataset = request.form.get('id_dataset')
        id_dataset2 = request.form.get('id_dataset2')
        id_genoma = request.form.get('id_genoma')
        
        # Aquí iría la lógica para ejecutar el workflow de Galaxy
        # Por ahora solo simulamos
        flash(f"Workflow ejecutado (simulado) con dataset: {id_dataset}, genoma: {id_genoma}", 'success')
        
        # Recargar la página
        return redirect(url_for('datasets_historia', history_id=history_id))

    return render_template('datasetsHistoria.html', 
                         nombre_historia=nombre_historia,
                         datasets_fastq=datasets_fastq,
                         genomes=genomes,
                         datasets=datasets,
                         history_id=history_id)
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
        tool_name=datos.get('herramienta', 'desconocida'),
        input_file=datos.get('archivo', ''),
        status=datos.get('estado', 'completado')
    )

    return jsonify({'mensaje': 'Análisis guardado en historial'})

# ---------------------------------------------------------
# Rutas Galaxy (listado de historiales via wrapper)
# ---------------------------------------------------------
@app.route('/galaxy_historiales')
def galaxy_historiales():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    historiales = listar_historiales()
    if isinstance(historiales, dict) and historiales.get('error'):
        flash(f"Error al obtener historiales: {historiales.get('error')}", 'error')
        historiales = []

    return render_template('galaxy_historiales.html', historiales=historiales)

# ---------------------------------------------------------
# SUBIR ARCHIVO A GALAXY y ejecutar herramientas
# ---------------------------------------------------------
@app.route('/subir_archivo', methods=['GET', 'POST'])
def subir_archivo():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Obtener historiales para el dropdown (tanto GET como POST)
    try:
        historiales_galaxy = gi.histories.get_histories()
        historiales = []
        for h in historiales_galaxy:
            historiales.append({
                'name': h['name'],
                'id': h['id'],
                'update_time': h['update_time']
            })
    except Exception as e:
        flash(f"Error al obtener historiales de Galaxy: {str(e)}", 'error')
        historiales = []

    if request.method == 'POST':
        archivo = request.files.get('file')
        history_id = request.form.get('history_id')

        if not archivo:
            flash('No se seleccionó ningún archivo', 'error')
            return redirect(url_for('subir_archivo'))

        if not history_id:
            flash('Debe seleccionar una historia', 'error')
            return redirect(url_for('subir_archivo'))

        # Guardar temporalmente
        filepath = os.path.join(TEMP_FOLDER, archivo.filename)
        archivo.save(filepath)
        session['last_uploaded_filename'] = archivo.filename

        # Subir archivo con tipo correcto
        try:
            dataset = gi.tools.upload_file(filepath, history_id, file_type='fastqsanger')
            dataset_id = dataset['outputs'][0]['id']
        except Exception as e:
            flash(f'Error al subir archivo a Galaxy: {e}', 'error')
            return redirect(url_for('subir_archivo'))

        # Guardar IDs en sesión
        session['dataset_id'] = dataset_id
        session['history_id'] = history_id

        # Registrar en historial local que se subió archivo
        guardar_en_historial(
            user_id=session['user_id'],
            tool_name='upload',
            input_file=archivo.filename,
            status='subido'
        )

        # --- Ejecutar FastQC ---
        try:
            tool_fastqc = 'toolshed.g2.bx.psu.edu/repos/devteam/fastqc/fastqc/0.72+galaxy1'
            gi.tools.run_tool(history_id, tool_fastqc, {
                'input_file': {'id': dataset_id, 'src': 'hda'}
            })
            flash('FastQC ejecutado correctamente', 'success')
            guardar_en_historial(session['user_id'], 'FastQC', archivo.filename, 'completado')
        except Exception as e:
            flash(f' Error al ejecutar FastQC: {e}', 'error')
            guardar_en_historial(session['user_id'], 'FastQC', archivo.filename, 'error')

        # --- Ejecutar Bowtie2 ---
        try:
            tool_bowtie = 'toolshed.g2.bx.psu.edu/repos/devteam/bowtie2/bowtie2/2.5.0+galaxy0'
            inputs = {
                'input_1': {'id': dataset_id, 'src': 'hda'},
                'reference_genome': {'values': ['hg19']},
                'analysis_type': 'default'
            }
            gi.tools.run_tool(history_id, tool_bowtie, inputs)
            flash('✅Bowtie2 ejecutado correctamente en Galaxy', 'success')
            guardar_en_historial(session['user_id'], 'Bowtie2', archivo.filename, 'completado')
        except Exception as e:
            flash(f' Error al ejecutar Bowtie2: {e}', 'error')
            guardar_en_historial(session['user_id'], 'Bowtie2', archivo.filename, 'error')

        flash(f"Archivo '{archivo.filename}' subido y analizado correctamente en Galaxy", 'success')
        return redirect(url_for('dashboard'))

    # GET request - mostrar el template del formulario completo
    return render_template('subir_archivo.html', historiales=historiales)
# EJECUTAR FASTQC (ruta separada)
# ---------------------------------------------------------
@app.route('/ejecutar_fastqc', methods=['POST'])
def ejecutar_fastqc():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    last_filename = session.get('last_uploaded_filename')
    if not last_filename:
        flash('Debes subir un archivo primero', 'error')
        return redirect(url_for('dashboard'))

    try:
        # Crear una history nueva para este análisis
        hname = f"FastQC de {session['username']} - {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        history = gi.histories.create_history(name=hname)

        # Subir el archivo a esta history
        dataset = gi.tools.upload_file(
            filename=os.path.join(TEMP_FOLDER, last_filename),
            history_id=history['id'],
            file_type='auto'
        )

        dataset_id = dataset['outputs'][0]['id']

        # Ejecutar FastQC
        tool_inputs = {'input1': {'id': dataset_id, 'src': 'hda'}}
        gi.tools.run_tool(history_id=history['id'], tool_id='fastqc', inputs=tool_inputs)

        # Guardar history_id y dataset_id en sesión si quieres usarlo después
        session['history_id'] = history['id']
        session['dataset_id'] = dataset_id

        flash(f"FastQC ejecutado correctamente en la history '{history['name']}'", 'success')
        guardar_en_historial(session['user_id'], 'FastQC', last_filename, 'completado')
    except Exception as e:
        flash(f"Error al ejecutar FastQC: {e}", 'error')
        guardar_en_historial(session['user_id'], 'FastQC', last_filename or 'desconocido', 'error')

    return redirect(url_for('dashboard'))

# ---------------------------------------------------------
# EJECUTAR BOWTIE2 (ruta separada)
# ---------------------------------------------------------
@app.route('/ejecutar_bowtie', methods=['POST'])
def ejecutar_bowtie():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    dataset_id = session.get('dataset_id')
    history_id = session.get('history_id')

    if not dataset_id or not history_id:
        flash('No hay archivo cargado para ejecutar Bowtie2', 'error')
        return redirect(url_for('dashboard'))

    try:
        tool_bowtie = 'toolshed.g2.bx.psu.edu/repos/devteam/bowtie2/bowtie2/2.5.0+galaxy0'
        inputs = {
            'input_1': {'id': dataset_id, 'src': 'hda'},
            'reference_genome': 'hg19',
            'analysis_type': 'default'
        }
        gi.tools.run_tool(history_id, tool_bowtie, inputs)
        flash('✅ Bowtie2 ejecutado correctamente en Galaxy', 'success')
        guardar_en_historial(session['user_id'], 'Bowtie2', dataset_id, 'completado')
    except Exception as e:
        flash(f'⚠️ Error al ejecutar Bowtie2: {e}', 'error')
        guardar_en_historial(session['user_id'], 'Bowtie2', dataset_id or 'desconocido', 'error')

    return redirect(url_for('dashboard'))

# ---------------------------------------------------------
# Ejecutar servidor
# ---------------------------------------------------------
if __name__ == '__main__':
    # Crea las tablas si no existen
    with app.app_context():
        db.create_all()
    app.run(debug=True)
