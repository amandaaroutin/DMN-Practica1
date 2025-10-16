import os
from flask import Flask, request, render_template, redirect, url_for, session, jsonify
import psycopg2
import hashlib
from datetime import datetime
from functools import wraps

# Configuración de la base de datos
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'bd'),
    'database': os.environ.get('DB_NAME', 'DMN-pec1'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', 'postgres'),
    'port': int(os.environ.get('DB_PORT', 5432))
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')

app = Flask(
    __name__,
    template_folder=os.path.join(FRONTEND_DIR, 'templates'),
    static_folder=os.path.join(FRONTEND_DIR, 'static')
)
app.secret_key = 'postgres'

def get_db_connection():
    """Establece conexión con la base de datos"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.set_session(autocommit=True, isolation_level='READ COMMITTED')  # Fuerza autocommit y aislamiento seguro
        return conn
    except psycopg2.Error as e:
        print(f"Error conectando a la base de datos: {e}")
        return str(e)

def init_db():
    """Inicializa la tabla pacientes si no existe y la tabla citas"""
    conn = get_db_connection()
    if not isinstance(conn, psycopg2.extensions.connection):
        print(f"Error inicializando la base de datos: {conn}")
        return
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pacientes (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(255) NOT NULL,
                edad INTEGER NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS citas (
                id SERIAL PRIMARY KEY,
                paciente_id INT REFERENCES pacientes(id),
                fecha DATE NOT NULL,
                hora TIME NOT NULL,
                motivo TEXT
            );
        ''')
        conn.commit()
        cursor.close()
        conn.close()
    except psycopg2.Error as e:
        print(f"Error inicializando la base de datos: {e}")

def hash_password(password):
    """Genera hash de la contraseña"""
    return hashlib.sha256(password.encode()).hexdigest()

def get_next_patient_id():
    """Obtiene el siguiente ID disponible para pacientes"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM pacientes")
            next_id = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return next_id
        except psycopg2.Error as e:
            print(f"Error obteniendo siguiente ID: {e}")
            return 1
    return 1

def login_required(f):
    """Decorador que requiere que el usuario esté autenticado"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('index'))
        
        # Verificar que el user_id existe en la base de datos
        conn = get_db_connection()
        if isinstance(conn, psycopg2.extensions.connection):
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT id, nombre FROM pacientes WHERE id = %s", (session['user_id'],))
                user = cursor.fetchone()
                cursor.close()
                conn.close()
                
                if not user:
                    # Usuario no existe en BD, limpiar sesión
                    session.clear()
                    return redirect(url_for('index'))
                
                # Actualizar nombre en sesión si existe
                session['user_name'] = user[1]
                
            except Exception as e:
                # Error en BD, redirigir a login
                session.clear()
                return redirect(url_for('index'))
        else:
            # Error de conexión, redirigir a login
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """Página principal con formularios de login y registro"""
    # Asegúrate de pasar las variables necesarias para evitar errores en el template
    return render_template('index.html', show_register=request.args.get('show_register') == '1', message=None, success=None)

@app.route('/login', methods=['POST'])
def login():
    """Maneja el inicio de sesión"""
    email = request.form['email']
    password = request.form['password']
    
    if not email or not password:
        return render_template('index.html', message='Por favor completa todos los campos', success=False, show_register=False)
    
    # Verificar credenciales en la base de datos
    conn = get_db_connection()
    if not isinstance(conn, psycopg2.extensions.connection):
        # Mostrar el error real
        return render_template('index.html', message=f'Error de conexión a la base de datos: {conn}', success=False, show_register=False)
    
    try:
        cursor = conn.cursor()
        password_hash = hash_password(password)
        cursor.execute(
            "SELECT id, nombre, email FROM pacientes WHERE email = %s AND password_hash = %s",
            (email, password_hash)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user:
            # Login exitoso
            session['user_id'] = user[0]
            session['user_name'] = user[1]
            session['user_email'] = user[2]
            return redirect(url_for('dashboard'))
        else:
            return render_template('index.html', message='Credenciales incorrectas', success=False, show_register=False)
    except psycopg2.Error as e:
        return render_template('index.html', message=f'Error en la base de datos: {e}', success=False, show_register=False)

@app.route('/register', methods=['POST'])
def register():
    """Maneja el registro de nuevos usuarios"""
    nombre = request.form['nombre']
    edad = request.form['edad']
    email = request.form['email']
    password = request.form['password']
    
    # Validaciones básicas
    if not all([nombre, edad, email, password]):
        return render_template('index.html', message='Por favor completa todos los campos', success=False, show_register=True)
    
    try:
        edad = int(edad)
        if edad < 1 or edad > 120:
            return render_template('index.html', message='La edad debe estar entre 1 y 120 años', success=False, show_register=True)
    except ValueError:
        return render_template('index.html', message='La edad debe ser un número válido', success=False, show_register=True)
    
    # Conectar a la base de datos
    conn = get_db_connection()
    if not isinstance(conn, psycopg2.extensions.connection):
        # Mostrar el error real
        return render_template('index.html', message=f'Error de conexión a la base de datos: {conn}', success=False, show_register=True)
    
    try:
        cursor = conn.cursor()
        
        # Verificar si el email ya existe
        cursor.execute("SELECT id FROM pacientes WHERE email = %s", (email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return render_template('index.html', message='El correo electrónico ya está registrado', success=False, show_register=True)
        
        # Insertar nuevo paciente
        password_hash = hash_password(password)
        cursor.execute(
            "INSERT INTO pacientes (nombre, edad, email, password_hash) VALUES (%s, %s, %s, %s) RETURNING id",
            (nombre, edad, email, password_hash)
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        return render_template('index.html', message=f'Registro exitoso. Tu ID es: {new_id}', success=True, show_register=False)
        
    except psycopg2.Error as e:
        return render_template('index.html', message=f'Error registrando usuario: {e}', success=False, show_register=True)


@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    # Valores por defecto
    citas = []
    message = None
    success = None
    error_citas = "NO DEFINIDO"
    total_citas = "NO DEFINIDO"
    tablas_info = "NO DEFINIDO"
    error_dashboard = None
    mostrar_formulario_nueva_cita = False

    try:
        user_id = session.get('user_id')
        user_name = session.get('user_name')

        # Leer mensajes de la URL (GET)
        if request.method == 'GET':
            message = request.args.get('mensaje')
            success = request.args.get('exito')
            if success is not None:
                success = success == 'True'

        # Mostrar el formulario si se recibe nueva_cita=1 por GET
        if request.method == 'GET' and request.args.get('nueva_cita') == '1':
            mostrar_formulario_nueva_cita = True

        # Si es POST, registrar nueva cita
        if request.method == 'POST':
            fecha = request.form.get('fecha')
            hora = request.form.get('hora')
            motivo = request.form.get('motivo')
            if not (fecha and hora and motivo):
                return redirect(url_for('dashboard', mensaje="Por favor, completa todos los campos.", exito=False))
            conn = get_db_connection()
            if not isinstance(conn, psycopg2.extensions.connection):
                return redirect(url_for('dashboard', mensaje=f"Error de conexión a la base de datos: {conn}", exito=False))
            try:
                cursor = conn.cursor()
                # Verificar si ya existe una cita igual para este usuario
                cursor.execute(
                    "SELECT id FROM citas WHERE paciente_id = %s AND fecha = %s AND hora = %s AND motivo = %s",
                    (user_id, fecha, hora, motivo)
                )
                existe = cursor.fetchone()
                if existe:
                    cursor.close()
                    conn.close()
                    return redirect(url_for('dashboard', mensaje="Ya existe una cita registrada con esos datos.", exito=False))
                # Si no existe, insertar la cita
                cursor.execute(
                    "INSERT INTO citas (paciente_id, fecha, hora, motivo) VALUES (%s, %s, %s, %s)",
                    (user_id, fecha, hora, motivo)
                )
                cursor.close()
                conn.close()
                return redirect(url_for('dashboard', exito=True))
            except Exception as e:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()
                return redirect(url_for('dashboard', mensaje=f"Error al registrar la cita: {e}", exito=False))

        try:
            result = obtener_citas_paciente(user_id)
            if result is None or (isinstance(result, tuple) and result[0] is None):
                citas, error_citas = [], "obtener_citas_paciente devolvió None"
            else:
                citas, error_citas = result
        except Exception as e:
            citas = []
            error_citas = f"Error en obtener_citas_paciente: {e}"

    except Exception as e:
        error_dashboard = f"Error global en dashboard: {e}"

    return render_template(
        'dashboard.html',
        user_name=user_name,
        citas=citas,
        message=message,
        success=success,
        error_citas=error_citas,
        total_citas=total_citas,
        tablas_info=tablas_info,
        error_dashboard=error_dashboard,
        mostrar_formulario_nueva_cita=mostrar_formulario_nueva_cita
    )


def obtener_citas_paciente(user_id):
    conn = get_db_connection()
    if not isinstance(conn, psycopg2.extensions.connection):
        return [], f"Error conexión obtener_citas_paciente: {conn}"
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT fecha, hora, motivo, id FROM citas WHERE paciente_id = %s ORDER BY fecha, hora", (user_id,))
        citas = cursor.fetchall()
        cursor.close()
        conn.close()
        return citas, None
    except Exception as e:
        return [], f"Error en obtener_citas_paciente: {e}"



@app.route('/api/citas')
@login_required
def api_citas():
    """Devuelve las citas del usuario autenticado en formato JSON"""
    user_id = session['user_id']
    citas, error = obtener_citas_paciente(user_id)

    if error:
        return jsonify({"error": error}), 500

    citas_json = [
        {
            "fecha": str(cita[0]),
            "hora": str(cita[1]),
            "motivo": cita[2],
            "id": cita[3]
        }
        for cita in citas
    ]
    return jsonify(citas_json)


@app.route('/eliminar_cita/<int:cita_id>', methods=['POST'])
@login_required
def eliminar_cita(cita_id):
     """Elimina una cita del usuario autenticado"""
     user_id = session['user_id']
     conn = get_db_connection()
     if not isinstance(conn, psycopg2.extensions.connection):
         # Manejar error de conexión
         return redirect(url_for('dashboard'))
     try:
         cursor = conn.cursor()
         # Solo permite eliminar citas del usuario autenticado
         cursor.execute("DELETE FROM citas WHERE id = %s AND paciente_id = %s", (cita_id, user_id))
         cursor.close()
         conn.close()
     except Exception as e:
         # Puedes agregar manejo de errores si lo deseas
         pass
     return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    """Cerrar sesión"""
    session.clear()
    return redirect(url_for('index'))


if __name__ == '__main__':
    # Ejecutar una sola vez, sin reloader para evitar dobles cargas y pérdida de estado
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)




