import os
from datetime import datetime
import time

from bioblend.galaxy import GalaxyInstance
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash

# Import config y modelos separados
from config import Config
from models import db, Usuario, Historia

# Importar funciones de utilidad de Galaxy
from galaxy_tools import ejecutar_fastqc, obtener_datasets_de_historia

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
# Modelos de Base de Datos (SQLAlchemy)
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

class Resultado(db.Model):
    __tablename__ = 'resultados'
    id = db.Column(db.Integer, primary_key=True)
    analisis_id = db.Column(db.Integer, db.ForeignKey('analisis.id'), nullable=False)
    galaxy_output_id = db.Column(db.String(255), nullable=False)
    output_type = db.Column(db.String(50), nullable=False) # e.g., 'html', 'txt'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'analisis_id': self.analisis_id,
            'galaxy_output_id': self.galaxy_output_id,
            'output_type': self.output_type,
            'created_at': self.created_at.isoformat()
        }

# ---------------------------------------------------------
# Funciones de Utilidad de Base de Datos
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

def guardar_resultado(analisis_id: int, galaxy_output_id: str, output_type: str):
    """Guarda un registro de resultado en la tabla resultados."""
    r = Resultado(
        analisis_id=analisis_id,
        galaxy_output_id=galaxy_output_id,
        output_type=output_type
    )
    db.session.add(r)
    db.session.commit()
    return r

def obtener_analisis_con_resultados(user_id: int):
    """Obtiene todos los análisis de un usuario que tienen resultados."""
    try:
        # Obtener análisis del usuario
        analisis_list = Analisis.query.filter_by(user_id=user_id).order_by(Analisis.created_at.desc()).all()
        
        output = []
        for a in analisis_list:
            # Obtener resultados asociados
            resultados = Resultado.query.filter_by(analisis_id=a.id).all()
            
            # Solo incluir análisis que tienen resultados
            if resultados:
                a_dict = a.to_dict()
                a_dict['resultados'] = [r.to_dict() for r in resultados]
                output.append(a_dict)
        return output
    except Exception as e:
        # Manejar el error si la tabla no existe (ej. al iniciar por primera vez)
        if "relation" in str(e) and "does not exist" in str(e):
            flash("Advertencia: Las tablas de la base de datos no existen. Por favor, asegúrese de que la aplicación se haya iniciado correctamente para crear las tablas.", "warning")
            return []
        raise e

def obtener_resultado_por_id(resultado_id: int):
    """Obtiene un resultado por su ID local."""
    return Resultado.query.get(resultado_id)

def obtener_historial_usuario(user_id: int):
    """Obtiene todos los análisis de un usuario ordenados por fecha descendente."""
    try:
        rows = Analisis.query.filter_by(user_id=user_id).order_by(Analisis.created_at.desc()).all()
        return [r.to_dict() for r in rows]
    except Exception as e:
        # Manejar el error si la tabla no existe (ej. al iniciar por primera vez)
        if "relation" in str(e) and "does not exist" in str(e):
            flash("Advertencia: Las tablas de la base de datos no existen. Por favor, asegúrese de que la aplicación se haya iniciado correctamente para crear las tablas.", "warning")
            return []
        raise e

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
        # Usar la función listar_historiales que ya existe en app.py
        historiales_galaxy = listar_historiales() 
        
        # Si listar_historiales devuelve un error, lo manejamos
        if isinstance(historiales_galaxy, dict) and historiales_galaxy.get('error'):
            flash(f"Error al obtener historiales de Galaxy: {historiales_galaxy.get('error')}", 'error')
            historiales = []
        else:
            historiales = historiales_galaxy
            
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
# SUBIR ARCHIVO A GALAXY
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

        flash(f"Archivo '{archivo.filename}' subido correctamente a Galaxy", 'success')
        return redirect(url_for('dashboard'))

    # GET request - mostrar el template del formulario completo
    return render_template('subir_archivo.html', historiales=historiales)

# ---------------------------------------------------------
# API para cargar datasets (Necesario para el JavaScript del dashboard)
# ---------------------------------------------------------
@app.route('/api/datasets/<history_id>', methods=['GET'])
def api_datasets(history_id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
        
    try:
        # Usar la instancia gi ya definida en app.py
        datasets = obtener_datasets_de_historia(gi, history_id)
        # Solo retornar los campos necesarios para el frontend
        datasets_info = [{'id': d['id'], 'name': d['name'], 'file_ext': d.get('file_ext', 'desconocido')} for d in datasets]
        return jsonify(datasets_info)
    except Exception as e:
        print(f"Error al obtener datasets: {e}")
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------
# API para Iniciar Análisis (Usada por el botón "Iniciar Análisis")
# ---------------------------------------------------------
@app.route('/api/iniciar_analisis', methods=['POST'])
def api_iniciar_analisis():
    if 'user_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
        
    data = request.get_json()
    tool = data.get('tool')
    history_id = data.get('history_id')
    datasetID_R1 = data.get('datasetID_R1')
    datasetID_R2 = data.get('datasetID_R2')
    
    if not history_id or not datasetID_R1:
        return jsonify({'error': 'Debe seleccionar una historia y el Dataset R1.'}), 400
        
    input_files = f"R1:{datasetID_R1}" + (f", R2:{datasetID_R2}" if datasetID_R2 else "")
    
    try:
        if tool == 'fastqc':
            # 1. Ejecutar FastQC
            # datasetID_R2 puede ser None o "" si el usuario no selecciona nada (single-end)
            results = ejecutar_fastqc(gi, history_id, datasetID_R1, datasetID_R2 if datasetID_R2 and datasetID_R2 != "" else None)
            
            # 2. Registrar en historial local
            analisis = guardar_en_historial(
                user_id=session['user_id'], 
                tool_name='FastQC', 
                input_file=input_files, 
                status='completado'
            )
            
            # 3. Recolectar IDs de jobs y outputs
            job_ids = [r['job_id'] for r in results]
            resultado_ids = []
            
            # 4. Guardar los IDs de los resultados en la nueva tabla Resultado
            for r in results:
                html_found = False
                # 4a. Priorizar el informe HTML
                for output in r['outputs']:
                    output_name = output.get('name')
                    output_ext = output.get('file_ext')
                    
                    # Filtro más flexible para el informe HTML
                    is_html_report = (output_ext == 'html' or output_ext == 'html_file') or \
                                     (output_name and ('webpage' in output_name.lower() or 'fastqc' in output_name.lower()))
                    
                    if is_html_report:
                        resultado = guardar_resultado(
                            analisis_id=analisis.id,
                            galaxy_output_id=output['id'],
                            output_type='html'
                        )
                        resultado_ids.append(resultado.id) # Devolvemos el ID LOCAL del resultado
                        html_found = True
                        break # Solo necesitamos un resultado HTML por job
                
                # 4b. Fallback: Si no se encontró HTML, tomar el primer output
                if not html_found and r['outputs']:
                    first_output = r['outputs'][0]
                    resultado = guardar_resultado(
                        analisis_id=analisis.id,
                        galaxy_output_id=first_output['id'],
                        output_type='unknown' # Marcar como desconocido
                    )
                    resultado_ids.append(resultado.id)
                    
            # Si no se encontró ningún output, marcamos el análisis como advertencia
            if not resultado_ids:
                analisis.status = 'advertencia'
                db.session.commit()
                
            return jsonify({
                'mensaje': 'FastQC iniciado con éxito.',
                'job_ids': job_ids,
                'resultado_ids': resultado_ids # Devolvemos los IDs LOCALES de los resultados
            })
        else:
            return jsonify({'error': f'Herramienta {tool} no implementada aún.'}), 400
            
    except Exception as e:
        # Registrar error en historial local
        guardar_en_historial(
            user_id=session['user_id'], 
            tool_name=tool, 
            input_file=input_files, 
            status='error'
        )
        print(f"Error al ejecutar {tool}: {e}")
        return jsonify({'error': f'Error al ejecutar {tool}: {str(e)}'}), 500

# ---------------------------------------------------------
# RUTA PARA VISUALIZAR EL RESULTADO DE FASTQC
# ---------------------------------------------------------
@app.route('/ver_resultado/<resultado_id>')
def ver_resultado(resultado_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    try:
        # 1. Obtener el registro de resultado local
        resultado = obtener_resultado_por_id(resultado_id)
        if not resultado:
            flash("Error: Resultado no encontrado en la base de datos local.", "error")
            return redirect(url_for('dashboard'))
            
        # 2. Descargar el contenido del dataset (el informe HTML)
        galaxy_output_id = resultado.galaxy_output_id
        dataset_content = gi.datasets.download_dataset(galaxy_output_id, stream=False)
        
        # 3. Servir el contenido como HTML
        return Response(dataset_content, mimetype='text/html')
        
    except Exception as e:
        flash(f"Error al obtener el resultado de Galaxy: {e}", "error")
        return redirect(url_for('dashboard'))

# ---------------------------------------------------------
# RUTA PARA MOSTRAR TODOS LOS RESULTADOS GUARDADOS
# ---------------------------------------------------------
@app.route('/resultados')
def resultados():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    # Obtener análisis que tienen resultados asociados
    analisis_con_resultados = obtener_analisis_con_resultados(session['user_id'])
    
    return render_template('resultados.html',
                           username=session.get('username'),
                           analisis=analisis_con_resultados)

# ---------------------------------------------------------
# EJECUTAR BOWTIE2 (ruta separada) - MANTENIDA POR AHORA
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
#<<<<<<< HEAD
    app.run(host="0.0.0.0", port=5000, debug=True)

#=======
    # Crea las tablas si no existen
    with app.app_context():
        db.create_all()
    app.run(debug=True)
#>>>>>>> erick/main
