# ==============================
# IMPORTS CORRECTOS
# ==============================
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
import psycopg2
from datetime import datetime, date, timedelta
import json
import hashlib
from functools import wraps
import os
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clave_secreta_pos_2024_sistema_login')

# ==============================
# CONEXIÓN A BASE DE DATOS PARA RENDER
# ==============================
def get_db_connection():
    # Para Render: usar DATABASE_URL
    # Para desarrollo local: usar variables locales
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Conexión para Render (PostgreSQL en la nube)
        result = urlparse(database_url)
        return psycopg2.connect(
            host=result.hostname,
            database=result.path[1:],  # Elimina el '/' inicial
            user=result.username,
            password=result.password,
            port=result.port,
            sslmode='require'
        )
    else:
        # Conexión para desarrollo local
        return psycopg2.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            port=os.environ.get('DB_PORT', '5432'),
            database=os.environ.get('DB_NAME', 'roka'),
            user=os.environ.get('DB_USER', 'postgres'),
            password=os.environ.get('DB_PASSWORD', 'pm')
        )

# ==============================
# CREACIÓN DE TABLAS (SI NO EXISTEN)
# ==============================
def create_tables():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        print("📝 Creando/verificando tablas...")
        
        # Tabla usuarios
        cur.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                nombre VARCHAR(100) NOT NULL,
                email VARCHAR(100),
                rol VARCHAR(20) DEFAULT 'cajero',
                activo BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla categorias
        cur.execute('''
            CREATE TABLE IF NOT EXISTS categorias (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla proveedores
        cur.execute('''
            CREATE TABLE IF NOT EXISTS proveedores (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(200) NOT NULL,
                contacto VARCHAR(100),
                telefono VARCHAR(20),
                email VARCHAR(100),
                direccion TEXT,
                activo BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla mesas
        cur.execute('''
            CREATE TABLE IF NOT EXISTS mesas (
                id SERIAL PRIMARY KEY,
                numero INTEGER UNIQUE NOT NULL,
                capacidad INTEGER DEFAULT 4,
                estado VARCHAR(20) DEFAULT 'disponible',
                ubicacion VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla productos
        cur.execute('''
            CREATE TABLE IF NOT EXISTS productos (
                id SERIAL PRIMARY KEY,
                codigo_barra VARCHAR(50) UNIQUE,
                nombre VARCHAR(200) NOT NULL,
                precio DECIMAL(10,2) NOT NULL,
                stock INTEGER DEFAULT 0,
                categoria_id INTEGER,
                proveedor_id INTEGER,
                tipo VARCHAR(20) DEFAULT 'producto',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (categoria_id) REFERENCES categorias(id) ON DELETE SET NULL,
                FOREIGN KEY (proveedor_id) REFERENCES proveedores(id) ON DELETE SET NULL
            )
        ''')
        
        # Tabla ordenes
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ordenes (
                id SERIAL PRIMARY KEY,
                mesa_id INTEGER NOT NULL,
                mozo_nombre VARCHAR(100) NOT NULL,
                estado VARCHAR(20) DEFAULT 'abierta',
                observaciones TEXT,
                total DECIMAL(10,2) DEFAULT 0,
                fecha_apertura TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_cierre TIMESTAMP,
                dispositivo_origen VARCHAR(100),
                FOREIGN KEY (mesa_id) REFERENCES mesas(id) ON DELETE CASCADE
            )
        ''')
        
        # Tabla orden_items
        cur.execute('''
            CREATE TABLE IF NOT EXISTS orden_items (
                id SERIAL PRIMARY KEY,
                orden_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                producto_nombre VARCHAR(200) NOT NULL,
                cantidad INTEGER NOT NULL,
                precio_unitario DECIMAL(10,2) NOT NULL,
                observaciones TEXT,
                estado_item VARCHAR(20) DEFAULT 'pendiente',
                tiempo_inicio TIMESTAMP,
                tiempo_fin TIMESTAMP,
                tiempo_estimado INTEGER DEFAULT 15,
                FOREIGN KEY (orden_id) REFERENCES ordenes(id) ON DELETE CASCADE,
                FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE SET NULL
            )
        ''')
        
        # Tabla caja_turnos
        cur.execute('''
            CREATE TABLE IF NOT EXISTS caja_turnos (
                id SERIAL PRIMARY KEY,
                fecha_apertura TIMESTAMP NOT NULL,
                fecha_cierre TIMESTAMP,
                monto_inicial DECIMAL(10,2) NOT NULL DEFAULT 0,
                monto_final_real DECIMAL(10,2),
                total_ventas DECIMAL(10,2) DEFAULT 0,
                monto_esperado DECIMAL(10,2),
                diferencia DECIMAL(10,2),
                observaciones TEXT,
                estado VARCHAR(20) DEFAULT 'abierta',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla cierres_caja
        cur.execute('''
            CREATE TABLE IF NOT EXISTS cierres_caja (
                id SERIAL PRIMARY KEY,
                turno_id INTEGER,
                fecha_cierre TIMESTAMP NOT NULL,
                monto_total DECIMAL(10,2) NOT NULL,
                monto_efectivo DECIMAL(10,2),
                monto_tarjeta DECIMAL(10,2),
                monto_transferencia DECIMAL(10,2),
                observaciones TEXT,
                usuario_cierre VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (turno_id) REFERENCES caja_turnos(id) ON DELETE SET NULL
            )
        ''')
        
        # Insertar datos iniciales si no existen
        cur.execute("SELECT COUNT(*) FROM usuarios WHERE username = 'admin'")
        if cur.fetchone()[0] == 0:
            print("👤 Creando usuarios por defecto...")
            password_hash = hashlib.sha256('admin123'.encode()).hexdigest()
            
            usuarios_default = [
                ('admin', password_hash, 'Administrador', 'admin@sistema.com', 'admin'),
                ('mozo', hashlib.sha256('mozo123'.encode()).hexdigest(), 'Mozo Principal', 'mozo@sistema.com', 'mozo'),
                ('chef', hashlib.sha256('chef123'.encode()).hexdigest(), 'Chef Principal', 'chef@sistema.com', 'chef'),
                ('cajero', hashlib.sha256('cajero123'.encode()).hexdigest(), 'Cajero Principal', 'cajero@sistema.com', 'cajero')
            ]
            
            for user in usuarios_default:
                cur.execute('''
                    INSERT INTO usuarios (username, password_hash, nombre, email, rol) 
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (username) DO NOTHING
                ''', user)
        
        # Insertar mesas por defecto
        for i in range(1, 11):
            cur.execute('''
                INSERT INTO mesas (numero, capacidad) 
                VALUES (%s, %s) 
                ON CONFLICT (numero) DO NOTHING
            ''', (i, 4))
        
        # Insertar categorías por defecto
        categorias_default = ['ENTRADAS', 'PICADAS', 'EMPANADAS', 'MINUTAS', 'GUARNICIONES', 
                             'PASTAS', 'SALSAS', 'PIZZAS', 'PLATOS ESPECIALES', 'POSTRES', 'HELADOS', 'BEBIDAS']
        for categoria in categorias_default:
            cur.execute('''
                INSERT INTO categorias (nombre) 
                VALUES (%s) 
                ON CONFLICT (nombre) DO NOTHING
            ''', (categoria,))
        
        # Insertar productos de ejemplo
        cur.execute("SELECT COUNT(*) FROM productos")
        if cur.fetchone()[0] == 0:
            print("📦 Creando productos de ejemplo...")
            productos_ejemplo = [
                ('Pizza Margarita', 2500.00, 'comida'),
                ('Hamburguesa Clásica', 1800.00, 'comida'),
                ('Ensalada César', 1200.00, 'comida'),
                ('Coca Cola 500ml', 800.00, 'bebida'),
                ('Agua Mineral 500ml', 500.00, 'bebida'),
                ('Jugo de Naranja', 700.00, 'bebida'),
                ('Papas Fritas', 900.00, 'comida'),
                ('Cerveza Artesanal', 1200.00, 'bebida'),
                ('Flan Casero', 600.00, 'comida'),
                ('Café Americano', 400.00, 'bebida')
            ]
            for nombre, precio, tipo in productos_ejemplo:
                cur.execute('''
                    INSERT INTO productos (nombre, precio, tipo) 
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                ''', (nombre, precio, tipo))
        
        conn.commit()
        print("✅ Tablas creadas/verificadas exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error al crear tablas: {e}")
        return False
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

# Crear tablas al inicio (importante para Render)
create_tables()

# ==============================
# FUNCIONES DE AUTENTICACIÓN
# ==============================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, password_hash):
    return hash_password(password) == password_hash

def login_user(username, password):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT id, username, password_hash, nombre, rol FROM usuarios WHERE username = %s AND activo = true', (username,))
        usuario = cur.fetchone()
        if usuario and verify_password(password, usuario[2]):
            return {'id': usuario[0], 'username': usuario[1], 'nombre': usuario[3], 'rol': usuario[4]}
        return None
    except Exception as e:
        print(f"❌ Error en login: {e}")
        return None
    finally:
        cur.close()
        conn.close()

def get_usuario_actual():
    if 'user_id' in session:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute('SELECT id, username, nombre, rol FROM usuarios WHERE id = %s', (session['user_id'],))
            usuario = cur.fetchone()
            if usuario:
                return {'id': usuario[0], 'username': usuario[1], 'nombre': usuario[2], 'rol': usuario[3]}
        except Exception as e:
            print(f"❌ Error obteniendo usuario: {e}")
        finally:
            cur.close()
            conn.close()
    return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==============================
# FUNCIÓN PARA ABRIR CAJA AUTOMÁTICAMENTE
# ==============================
def abrir_caja_automaticamente():
    """Abre caja automáticamente si no hay una abierta"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar si ya hay caja abierta
        cur.execute("SELECT id FROM caja_turnos WHERE estado = 'abierta'")
        if cur.fetchone():
            return True
        
        # Abrir nueva caja automáticamente
        cur.execute('''
            INSERT INTO caja_turnos (fecha_apertura, monto_inicial, observaciones, estado)
            VALUES (NOW(), 0, 'Caja abierta automáticamente al iniciar sesión', 'abierta')
        ''')
        conn.commit()
        return True
        
    except Exception as e:
        print(f"❌ Error al abrir caja automáticamente: {e}")
        return False
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

# ==============================
# RUTAS PRINCIPALES
# ==============================
@app.route("/")
def index():
    """Página principal"""
    return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    """Login para sistema"""
    if 'user_id' in session:
        usuario_actual = get_usuario_actual()
        if usuario_actual:
            flash(f'Ya estás logueado como {usuario_actual["nombre"]}', 'info')
            
            # Redirigir según rol
            if usuario_actual['rol'] == 'chef':
                return redirect(url_for('chef'))
            elif usuario_actual['rol'] == 'mozo':
                return redirect(url_for('ordenes'))
            else:
                # Para admin y cajero: abrir caja automáticamente
                abrir_caja_automaticamente()
                return redirect(url_for('caja'))
    
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        usuario = login_user(username, password)
        
        if usuario:
            session['user_id'] = usuario['id']
            session['username'] = usuario['username']
            session['nombre'] = usuario['nombre']
            session['rol'] = usuario['rol']
            flash(f'Bienvenido {usuario["nombre"]}!', 'success')
            
            # Redirigir según rol
            if usuario['rol'] == 'chef':
                return redirect(url_for('chef'))
            elif usuario['rol'] == 'mozo':
                return redirect(url_for('ordenes'))
            else:
                # Para admin y cajero: abrir caja automáticamente
                if abrir_caja_automaticamente():
                    flash('Turno de caja abierto automáticamente', 'info')
                return redirect(url_for('caja'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    
    return render_template("login.html", ahora=datetime.now())

# ==============================
# RUTA PARA VERIFICAR/REPARAR TABLAS
# ==============================
@app.route("/verificar-tablas")
def verificar_tablas():
    """Ruta para verificar y reparar tablas si es necesario"""
    try:
        success = create_tables()
        if success:
            return '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Tablas Verificadas</title>
                <style>
                    body { font-family: Arial, sans-serif; padding: 20px; text-align: center; }
                    .success { color: green; font-size: 24px; margin: 20px 0; }
                    .info { margin: 20px 0; }
                </style>
            </head>
            <body>
                <div class="success">✅ Tablas verificadas y creadas exitosamente</div>
                <div class="info">
                    <a href="/login">Ir al Login</a><br><br>
                    Usuarios disponibles:<br>
                    • admin / admin123 (Administrador)<br>
                    • chef / chef123 (Chef)<br>
                    • mozo / mozo123 (Mozo)<br>
                    • cajero / cajero123 (Cajero)
                </div>
            </body>
            </html>
            '''
        else:
            return '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Error</title>
                <style>
                    body { font-family: Arial, sans-serif; padding: 20px; text-align: center; }
                    .error { color: red; font-size: 24px; margin: 20px 0; }
                </style>
            </head>
            <body>
                <div class="error">❌ Error al verificar tablas</div>
            </body>
            </html>
            '''
    except Exception as e:
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Error</title>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; text-align: center; }}
                .error {{ color: red; font-size: 24px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="error">❌ Error: {str(e)}</div>
        </body>
        </html>
        '''

# ==============================
# PANEL DE CAJA (MEJORADO PARA RENDER)
# ==============================
@app.route("/caja")
@login_required
def caja():
    """Panel de caja"""
    usuario_actual = get_usuario_actual()
    
    # Solo cajeros y admins pueden acceder
    if usuario_actual['rol'] not in ['cajero', 'admin']:
        flash('Acceso restringido a caja', 'warning')
        return redirect(url_for('ordenes'))
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar si hay caja abierta
        cur.execute("SELECT id, fecha_apertura, monto_inicial FROM caja_turnos WHERE estado = 'abierta'")
        caja_abierta = cur.fetchone()
        
        if not caja_abierta:
            # Si no hay caja abierta, crear una automáticamente
            cur.execute('''
                INSERT INTO caja_turnos (fecha_apertura, monto_inicial, observaciones, estado)
                VALUES (NOW(), 0, 'Caja abierta automáticamente', 'abierta')
                RETURNING id, fecha_apertura, monto_inicial
            ''')
            caja_abierta = cur.fetchone()
            conn.commit()
            flash('Caja abierta automáticamente con monto inicial $0', 'info')
        
        caja_info = {
            'id': caja_abierta[0],
            'fecha_apertura': caja_abierta[1],
            'monto_inicial': float(caja_abierta[2]) if caja_abierta[2] else 0
        }
        
        # Obtener órdenes abiertas
        cur.execute('''
            SELECT o.id, m.numero as mesa_numero, o.mozo_nombre, o.total 
            FROM ordenes o 
            JOIN mesas m ON o.mesa_id = m.id 
            WHERE o.estado = 'abierta' 
            ORDER BY o.fecha_apertura DESC
        ''')
        ordenes_abiertas_db = cur.fetchall()
        
        ordenes_abiertas = []
        for o in ordenes_abiertas_db:
            ordenes_abiertas.append({
                'id': o[0],
                'mesa_numero': o[1],
                'mozo_nombre': o[2],
                'total': float(o[3]) if o[3] else 0
            })
        
        cur.close()
        conn.close()
        
        return render_template("caja.html", 
                             usuario=usuario_actual, 
                             ahora=datetime.now(),
                             turno_abierto=caja_info,
                             ordenes_abiertas=ordenes_abiertas)
        
    except Exception as e:
        print(f"Error en panel de caja: {e}")
        flash('Error al cargar panel de caja', 'danger')
        return redirect(url_for('index'))

# ==============================
# RUTAS PARA CHEF (SIN RESTRICCIÓN DE ROL PARA FACILITAR)
# ==============================
@app.route("/chef")
def chef():
    """Panel del chef"""
    usuario_dummy = {'nombre': 'Chef', 'rol': 'chef'}
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Obtener pedidos pendientes
    cur.execute('''
        SELECT o.id, m.numero as mesa_numero, o.mozo_nombre, 
               o.fecha_apertura, COUNT(oi.id) as items_pendientes
        FROM ordenes o 
        JOIN mesas m ON o.mesa_id = m.id 
        LEFT JOIN orden_items oi ON o.id = oi.orden_id AND oi.estado_item = 'pendiente'
        WHERE o.estado = 'abierta'
        GROUP BY o.id, m.numero, o.mozo_nombre, o.fecha_apertura
        ORDER BY o.fecha_apertura ASC
    ''')
    pedidos_db = cur.fetchall()
    
    pedidos = []
    for p in pedidos_db:
        pedidos.append({
            'id': p[0],
            'mesa_numero': p[1],
            'mozo_nombre': p[2],
            'fecha_apertura': p[3],
            'items_pendientes': p[4]
        })
    
    cur.close()
    conn.close()
    
    return render_template("chef.html",
                         usuario=usuario_dummy,
                         pedidos=pedidos,
                         ahora=datetime.now())

# ==============================
# RUTAS PARA MOZO
# ==============================
@app.route("/ordenes")
@login_required
def ordenes():
    """Panel principal del mozo"""
    usuario_actual = get_usuario_actual()
    
    # Solo mozos y admins pueden acceder
    if usuario_actual['rol'] not in ['mozo', 'admin']:
        flash('Acceso restringido a ordenes', 'warning')
        return redirect(url_for('caja'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM mesas ORDER BY numero')
    mesas = cur.fetchall()
    
    cur.execute('''
        SELECT o.*, m.numero as mesa_numero 
        FROM ordenes o 
        JOIN mesas m ON o.mesa_id = m.id 
        WHERE o.estado = 'abierta' 
        ORDER BY o.fecha_apertura DESC
    ''')
    ordenes_activas = cur.fetchall()
    
    mesas_list = []
    for mesa in mesas:
        mesas_list.append({
            'id': mesa[0],
            'numero': mesa[1],
            'capacidad': mesa[2],
            'estado': mesa[3]
        })
    
    ordenes_list = []
    for orden in ordenes_activas:
        ordenes_list.append({
            'id': orden[0],
            'mesa_id': orden[1],
            'mesa_numero': orden[9],
            'mozo_nombre': orden[2],
            'estado': orden[3],
            'total': float(orden[5]) if orden[5] else 0,
            'fecha_apertura': orden[6]
        })
    
    cur.close()
    conn.close()
    
    return render_template("ordenes.html", 
                         usuario=usuario_actual,
                         mesas=mesas_list,
                         ordenes=ordenes_list,
                         ahora=datetime.now())

# ==============================
# RUTAS PARA PRODUCTOS
# ==============================
@app.route("/productos")
@login_required
def productos():
    """Lista de productos"""
    usuario_actual = get_usuario_actual()
    search = request.args.get('search', '')
    conn = get_db_connection()
    cur = conn.cursor()
    
    if search:
        cur.execute('''
            SELECT p.id, p.nombre, p.precio, p.stock, p.tipo, p.codigo_barra,
                   c.nombre as categoria_nombre
            FROM productos p 
            LEFT JOIN categorias c ON p.categoria_id = c.id
            WHERE p.nombre ILIKE %s
            ORDER BY p.nombre
        ''', (f'%{search}%',))
    else:
        cur.execute('''
            SELECT p.id, p.nombre, p.precio, p.stock, p.tipo, p.codigo_barra,
                   c.nombre as categoria_nombre
            FROM productos p 
            LEFT JOIN categorias c ON p.categoria_id = c.id
            ORDER BY p.nombre
        ''')
    
    productos_db = cur.fetchall()
    
    cur.execute('SELECT id, nombre FROM categorias ORDER BY nombre')
    categorias_db = cur.fetchall()
    
    productos_list = []
    for p in productos_db:
        productos_list.append({
            'id': p[0],
            'nombre': p[1],
            'precio': float(p[2]) if p[2] else 0.0,
            'stock': p[3] if p[3] is not None else 0,
            'tipo': p[4] if p[4] else 'producto',
            'codigo_barra': p[5] if p[5] else '',
            'categoria_nombre': p[6] if p[6] else 'Sin categoría'
        })
    
    cur.close()
    conn.close()
    
    return render_template("productos.html", 
                         usuario=usuario_actual,
                         productos=productos_list,
                         categorias=[{'id': c[0], 'nombre': c[1]} for c in categorias_db],
                         search=search,
                         ahora=datetime.now())

# ==============================
# RUTAS RESTANTES (MANTENIDAS)
# ==============================
# ... (mantén todas las demás rutas como están en tu app2.py original)
# Solo asegúrate de que todas usen get_db_connection() correctamente

@app.route("/mesas")
@login_required
def mesas():
    """Lista de mesas"""
    # ... (código existente)
    pass

@app.route("/crear_orden/<int:mesa_id>")
@login_required
def crear_orden(mesa_id):
    """Crear nueva orden para una mesa"""
    # ... (código existente)
    pass

@app.route("/api/crear_orden", methods=["POST"])
@login_required
def api_crear_orden():
    """API para crear orden"""
    # ... (código existente)
    pass

@app.route("/ver_orden/<int:orden_id>")
@login_required
def ver_orden(orden_id):
    """Ver detalle de orden"""
    # ... (código existente)
    pass

@app.route("/cobrar_orden/<int:orden_id>", methods=["GET", "POST"])
@login_required
def cobrar_orden(orden_id):
    """Cobrar una orden"""
    # ... (código existente)
    pass

# ==============================
# RUTAS DE API (IMPORTANTES PARA RENDER)
# ==============================
@app.route("/api/productos")
def api_productos():
    """API para obtener productos"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('SELECT id, nombre, precio, tipo FROM productos ORDER BY nombre')
        productos_db = cur.fetchall()
        
        productos = []
        for p in productos_db:
            productos.append({
                'id': p[0],
                'nombre': p[1],
                'precio': float(p[2]) if p[2] else 0,
                'tipo': p[3] if p[3] else 'producto'
            })
        
        return jsonify(productos)
    except Exception as e:
        print(f"Error en api_productos: {e}")
        return jsonify([])
    finally:
        cur.close()
        conn.close()

@app.route("/api/ordenes_activas")
def api_ordenes_activas():
    """API para obtener órdenes activas"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('''
            SELECT o.id, m.numero as mesa_numero, o.mozo_nombre, o.total, o.estado
            FROM ordenes o 
            JOIN mesas m ON o.mesa_id = m.id 
            WHERE o.estado = 'abierta'
            ORDER BY o.fecha_apertura DESC
        ''')
        ordenes_db = cur.fetchall()
        
        ordenes = []
        for o in ordenes_db:
            ordenes.append({
                'id': o[0],
                'mesa_numero': o[1],
                'mozo_nombre': o[2],
                'total': float(o[3]) if o[3] else 0,
                'estado': o[4]
            })
        
        return jsonify(ordenes)
    except Exception as e:
        print(f"Error en api_ordenes_activas: {e}")
        return jsonify([])
    finally:
        cur.close()
        conn.close()

# ==============================
# LOGOUT
# ==============================
@app.route("/logout")
def logout():
    """Cerrar sesión"""
    session.clear()
    flash('Sesión cerrada correctamente', 'info')
    return redirect(url_for('login'))

# ==============================
# MANEJO DE ERRORES
# ==============================
@app.errorhandler(404)
def pagina_no_encontrada(e):
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Página no encontrada</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            h1 { color: #666; }
            a { color: #3498db; text-decoration: none; }
        </style>
    </head>
    <body>
        <h1>404 - Página no encontrada</h1>
        <p>La página que buscas no existe.</p>
        <p><a href="/">Volver al inicio</a></p>
    </body>
    </html>
    ''', 404

@app.errorhandler(500)
def error_servidor(e):
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Error del servidor</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            h1 { color: #e74c3c; }
            a { color: #3498db; text-decoration: none; }
        </style>
    </head>
    <body>
        <h1>500 - Error del servidor</h1>
        <p>Algo salió mal. Por favor, intenta nuevamente más tarde.</p>
        <p><a href="/">Volver al inicio</a></p>
    </body>
    </html>
    ''', 500

# ==============================
# EJECUCIÓN PRINCIPAL (ADAPTADA PARA RENDER)
# ==============================
if __name__ == "__main__":
    # Obtener el puerto de Render o usar 5000 por defecto
    port = int(os.environ.get("PORT", 5000))
    
    # En Render, necesitamos ejecutar en el host 0.0.0.0
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False  # En producción, debug debe ser False
    )
