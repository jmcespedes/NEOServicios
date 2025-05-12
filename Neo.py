import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
import psycopg2
from flask_cors import CORS
import uuid
import re

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "https://neoservicios.cl"}})

# Configuración de la base de datos
db_config = {
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

def obtener_sesion(session_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT region_id, comuna_id, servicio_id, celular, paso_actual
                FROM sesiones_servicios
                WHERE session_id = %s
            """, (session_id,))
            row = cur.fetchone()
            if row:
                return {
                    'region_id': row[0],
                    'comuna_id': row[1],
                    'servicio_id': row[2],
                    'celular': row[3],
                    'paso_actual': row[4]
                }
            else:
                return None
    except Exception as e:
        print(f"Error al obtener sesión: {e}")
        return None
    finally:
        conn.close()



# Conexión a la base de datos
def get_db_connection():
    try:
        conn = psycopg2.connect(**db_config)
        conn.autocommit = True
        return conn
    except Exception as e:
        print(f"Error de conexión a la base de datos: {e}")
        return None

# Crear una nueva sesión
def crear_sesion():
    session_id = str(uuid.uuid4())
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO sesiones_servicios (session_id, paso_actual)
                VALUES (%s, %s)
                RETURNING id
            """, (session_id, 'espera_comuna_region'))
            session_db_id = cur.fetchone()[0]
            return {'session_id': session_id, 'db_id': session_db_id}
    except Exception as e:
        print(f"Error al crear sesión: {e}")
        return None
    finally:
        conn.close()

# Obtener datos de la sesión
def obtener_datos_sesion(session_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT region_id, comuna_id, servicio_id, celular, paso_actual
        FROM sesiones_servicios
        WHERE session_id = %s
    """, (session_id,))
    row = cur.fetchone()
    conn.close()

    if row:
        return {
            'region_id': row[0],
            'comuna_id': row[1],
            'servicio_id': row[2],
            'celular': row[3],
            'paso_actual': row[4]
        }
    else:
        return {
            'region_id': None,
            'comuna_id': None,
            'servicio_id': None,
            'celular': None,
            'paso_actual': 'espera_comuna_region'
        }

# Actualizar sesión
def actualizar_sesion(session_id, **kwargs):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            set_clause = ", ".join([f"{k} = %s" for k in kwargs.keys()])
            values = list(kwargs.values()) + [session_id]
            cur.execute(f"""
                UPDATE sesiones_servicios
                SET {set_clause}, fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE session_id = %s
                RETURNING id
            """, values)
            return cur.fetchone()[0]
    except Exception as e:
        print(f"Error al actualizar sesión: {e}")
        return None
    finally:
        conn.close()

# Obtener comunas con región
def get_comunas_con_region(nombre_comuna):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.id, c.nombre, r.id, r.nombre 
                FROM comunas c
                JOIN regiones r ON c.region_id = r.id
                WHERE LOWER(c.nombre) = LOWER(%s)
            """, (nombre_comuna,))
            return cur.fetchall()
    except Exception as e:
        print(f"Error en consulta de comunas: {e}")
        return []
    finally:
        conn.close()

# Obtener servicios para una comuna
def get_servicios_por_comuna(comuna_nombre):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(""" 
                SELECT id, servicios
                FROM proveedores
                WHERE comuna = %s
            """, (comuna_nombre,))
            return cur.fetchall()
    except Exception as e:
        print(f"Error en consulta de servicios: {e}")
        return []
    finally:
        conn.close()

# Iconos por tipo de servicio
iconos_servicios = {
    "Flete": "🚚",
    "Abogado": "⚖️",
    "Electricista": "⚡",
    "Gasfiter": "🔧",
    "Peluqueria": "💇"
}

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        session_id = data.get("session_id")
        
        # ✅ Importante: intenta recuperar sesión solo si `session_id` existe
        if session_id:
            session = obtener_datos_sesion(session_id)
            if not session:
                # Si no encuentra la sesión, se crea una nueva
                session = crear_sesion()
                session_id = session['session_id']
        else:
            session = crear_sesion()
            session_id = session['session_id']

        paso_actual = session.get('paso_actual', 'espera_comuna_region')
        
        if paso_actual == 'espera_comuna_region':
            user_response = data.get("response", "").strip()
            
            # Buscar la comuna en la base de datos
            posibles_comunas = get_comunas_con_region(user_response)

            if len(posibles_comunas) > 1:
                # Si hay varias posibles, se necesita desambiguar
                comunas_con_region = [f"{c[1]} ({c[3]})" for c in posibles_comunas]
                mensaje = "⚠️ Varias comunas coinciden. Por favor indica la comuna y su región (ej: *'Puente Alto, Metropolitana'*):\n"
                mensaje += "\n".join([f"- {c}" for c in comunas_con_region])
                return jsonify({
                    'response': mensaje,
                    'action': 'desambiguar_comuna',
                    'session_id': session_id
                })

            if not posibles_comunas:
                # Si no se encuentra ninguna comuna válida
                return jsonify({
                    'response': 'No reconozco esa comuna. Por favor indica una comuna válida de Chile.',
                    'session_id': session_id
                })

            comuna = posibles_comunas[0]
            comuna_id, comuna_nombre, region_id, region_nombre = comuna

            # Actualizar la sesión con la comuna encontrada
            actualizar_sesion(session_id, comuna_id=comuna_id, region_id=region_id, paso_actual='espera_servicio')

            # Buscar los servicios disponibles para la comuna
            servicios = get_servicios_por_comuna(comuna_nombre)
            if not servicios:
                return jsonify({'response': f'⚠️ No hay servicios disponibles para {comuna_nombre}.', 'session_id': session_id})

            servicios_lista = [{"id": s[0], "nombre": s[1].lower()} for s in servicios]

            # Respuesta con los servicios disponibles
            respuesta = f'{comuna_nombre}, Región: {region_nombre} ✨ *Servicios disponibles:* ✨<br><br>'
            for i, servicio in enumerate(servicios_lista, 1):
                icono = iconos_servicios.get(servicio['nombre'].capitalize(), "🔹")
                respuesta += f"{i}. {icono} *{servicio['nombre'].capitalize()}* (ID: {servicio['id']})<br>"
            respuesta += "<br>🔽 *Selecciona el número, nombre o ID del servicio.*"

            return jsonify({
                'response': respuesta,
                'session_id': session_id,
                'servicios': servicios_lista,
                'action': 'seleccionar_servicio'
            })

        elif paso_actual == 'espera_servicio':
            comuna_id = session['comuna_id']
            if not comuna_id:
                return jsonify({'response': 'Primero necesitamos tu comuna.', 'session_id': session_id})

            # Buscar nuevamente los servicios disponibles para la comuna seleccionada
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT nombre FROM comunas WHERE id = %s", (comuna_id,))
                comuna_nombre = cur.fetchone()[0]
            conn.close()

            servicios = get_servicios_por_comuna(comuna_nombre)
            servicios_lista = [{"id": s[0], "nombre": s[1].lower()} for s in servicios]

            respuesta_normalizada = data.get('response', '').lower()
            servicio_encontrado = None
            for servicio in servicios_lista:
                if respuesta_normalizada == servicio['nombre']:
                    servicio_encontrado = servicio
                    break

            if not servicio_encontrado:
                try:
                    num = int(respuesta_normalizada)
                    for servicio in servicios_lista:
                        if servicio['id'] == num:
                            servicio_encontrado = servicio
                            break
                except:
                    pass

            if servicio_encontrado:
                # Actualizamos la sesión con el servicio seleccionado
                actualizar_sesion(session_id, servicio_id=servicio_encontrado['id'], paso_actual='espera_celular')
                return jsonify({
                    'response': f"✅ Servicio ingresado: *{servicio_encontrado['nombre'].capitalize()}*. Ahora dime tu número de celular (+56942674761).",
                    'session_id': session_id
                })
            else:
                return jsonify({
                    'response': "⚠️ No reconozco ese servicio. Por favor selecciona uno de la lista.",
                    'session_id': session_id
                })

        elif paso_actual == 'espera_celular':
            celular = data.get('response')

            # Validar formato +569XXXXXXX
            if not re.match(r'^\+569\d{8}$', celular):
                return jsonify({
                    'response': "⚠️ Por favor indica un número de celular válido, con formato +569XXXXXXXX.",
                    'session_id': session_id
                })

            # Actualizar sesión como 'terminado'
            actualizar_sesion(session_id, celular=celular, paso_actual='terminado')
            # Obtener datos necesarios de la sesión actual para registrar envío
            datos_sesion = obtener_sesion(session_id)  # Asegúrate de que esta función te devuelve todo lo necesario

            region_id = datos_sesion['region_id']
            comuna_id = datos_sesion['comuna_id']
            servicio_id = datos_sesion['servicio_id']

                # Registrar en tabla de envíos (psycopg2)
            try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO envios_whatsapp (sesion_id, celular, region_id, comuna_id, servicio_id)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (session_id, celular, region_id, comuna_id, servicio_id))
                    conn.commit()
                    cursor.close()
                    conn.close()
            except Exception as e:
                    print("❌ Error al registrar en envios_whatsapp:", e)

            return jsonify({
                    'response': "✅ ¡Gracias! Tu solicitud ha sido registrada. Pronto te contactaremos.",
                    'session_id': session_id
            })

        
            # Si pasa la validación, continúa con la lógica de actualización de sesión
            actualizar_sesion(session_id, celular=celular, paso_actual='terminado')

            actualizar_sesion(session_id, celular=celular, paso_actual='finalizado')
            return jsonify({
                'response': f"📲 ¡Gracias! Tu número {celular} ha sido registrado. Pronto te contactaremos con un proveedor.",
                'session_id': session_id
            })

        elif paso_actual == 'finalizado':
            return jsonify({
                'response': "✅ Ya completaste el proceso. Si deseas comenzar de nuevo, escribe 'inicio'.",
                'session_id': session_id
            })

        return jsonify({
            'response': '❌ Paso no reconocido.',
            'session_id': session_id
        })

    except Exception as e:
        print(f"Error en el endpoint /api/chat: {e}")
        return jsonify({'error': 'Ocurrió un error procesando la solicitud.'})

if __name__ == '__main__':
    app.run(debug=True)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)



