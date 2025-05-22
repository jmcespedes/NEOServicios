import os
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import re

from db import (
    get_db_connection, crear_sesion, obtener_datos_sesion, actualizar_sesion,
    get_comunas_con_region, get_servicios_por_comuna, buscar_servicios_por_comuna_y_texto ,generar_codigo_verificacion
)

app = Flask(__name__)
CORS(app)

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response

iconos_servicios = {
    "Flete": "🚚",
    "Abogado": "⚖️",
    "Electricista": "⚡",
    "Gasfiter": "🔧",
    "Peluqueria": "💇"
}

@app.route('/', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        session_id = data.get("session_id")
        
        if session_id:
            session = obtener_datos_sesion(session_id)
            if not session:
                session = crear_sesion()
                session_id = session['session_id']
        else:
            session = crear_sesion()
            session_id = session['session_id']

        paso_actual = session.get('paso_actual', 'espera_comuna_region')
        
        if paso_actual == 'espera_comuna_region':
            user_response = data.get("response", "").strip()
            posibles_comunas = get_comunas_con_region(user_response)

            if len(posibles_comunas) > 1:
                comunas_con_region = [f"{c[1]} ({c[3]})" for c in posibles_comunas]
                mensaje = "⚠️ Varias comunas coinciden. Por favor indica la comuna y su región (ej: *'Puente Alto, Metropolitana'*):\n"
                mensaje += "\n".join([f"- {c}" for c in comunas_con_region])
                return jsonify({
                    'response': mensaje,
                    'action': 'desambiguar_comuna',
                    'session_id': session_id
                })

            if not posibles_comunas:
                return jsonify({
                    'response': 'No reconozco esa comuna. Por favor indica una comuna válida de Chile.',
                    'session_id': session_id
                })

            comuna = posibles_comunas[0]
            comuna_id, comuna_nombre, region_id, region_nombre = comuna

            actualizar_sesion(session_id, comuna_id=comuna_id, region_id=region_id, paso_actual='espera_servicio')

            servicios = get_servicios_por_comuna(comuna_nombre)
            if not servicios:
                return jsonify({'response': f'⚠️ No hay servicios disponibles para {comuna_nombre}.', 'session_id': session_id})

            servicios_lista = [{"id": s[0], "nombre": s[1].lower()} for s in servicios]

            comuna = posibles_comunas[0]
            comuna_id, comuna_nombre, region_id, region_nombre = comuna

            actualizar_sesion(session_id, comuna_id=comuna_id, region_id=region_id, paso_actual='espera_servicio')
            
            servicios = get_servicios_por_comuna(comuna_nombre)
            if not servicios:
                return jsonify({'response': f'⚠️ No hay servicios disponibles para {comuna_nombre}.', 'session_id': session_id})

            servicios_lista = [{"id": s[0], "nombre": s[1].lower()} for s in servicios]

            respuesta = f"{comuna_nombre}, Región: {region_nombre} ✨ Servicios disponibles ✨<br><br>"
            for i, servicio in enumerate(servicios_lista, 1):
                icono = iconos_servicios.get(servicio['nombre'].capitalize(), "🔹")
                respuesta += f"{i}. {icono} <b>{servicio['nombre'].capitalize()}</b> (ID: {servicio['id']})<br>"
            respuesta += "<br>🔽 Selecciona el número, nombre o ID del servicio."

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
                actualizar_sesion(session_id, servicio_id=servicio_encontrado['id'], paso_actual='espera_pregunta')
                return jsonify({
                    'response': f"✅ Servicio ingresado: *{servicio_encontrado['nombre'].capitalize()}*. Favor formula la pregunta al proveedor (que sea clara)",
                    'session_id': session_id
                })
            else:
                return jsonify({
                    'response': "⚠️ No reconozco ese servicio. Por favor selecciona uno de la lista.",
                    'session_id': session_id
                })


        elif paso_actual == 'espera_pregunta':
            pregunta = data.get('response', '').strip()

            # Validar largo mínimo
            if len(pregunta) < 50:
                return jsonify({
                    'response': "📝 Por favor formula tu pregunta con más detalle (mínimo 50 caracteres).",
                    'session_id': session_id
                })

            # Guardar la pregunta en la sesión y avanzar
            actualizar_sesion(session_id, pregunta_cliente=pregunta, paso_actual='espera_celular')

            return jsonify({
                'response': "📱 Ahora, por favor indica tu número de celular con formato +569XXXXXXXX.",
                'session_id': session_id
            })







        elif paso_actual == 'espera_celular':
            celular = data.get('response')

            if not re.match(r'^\+569\d{8}$', celular):
                return jsonify({
                    'response': "⚠️ Por favor indica un número de celular válido, con formato +569XXXXXXXX.",
                    'session_id': session_id
                })

            actualizar_sesion(session_id, celular=celular, paso_actual='terminado')
            datos_sesion = obtener_datos_sesion(session_id)

            region_id = datos_sesion['region_id']
            comuna_id = datos_sesion['comuna_id']
            servicio_id = datos_sesion['servicio_id']
            pregunta_cliente = datos_sesion['pregunta_cliente']

            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO envios_whatsapp (sesion_id, celular, region_id, comuna_id, servicio_id,pregunta_cliente)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (session_id, celular, region_id, comuna_id, servicio_id,pregunta_cliente))
                conn.commit()
                cursor.close()
                conn.close()
            except Exception as e:
                print("❌ Error al registrar en envios_whatsapp:", e)

            return jsonify({
                'response': "✅ ¡Gracias! Tu solicitud ha sido registrada. Pronto te contactaremos.",
                'session_id': session_id
            })

        elif paso_actual == 'finalizado':
            return jsonify({
                'response': "Gracias por usar el asistente. Si necesitas algo más, inicia una nueva sesión.",
                'session_id': session_id
            })

        else:
            return jsonify({
                'response': "No entiendo tu mensaje. Por favor, intenta de nuevo.",
                'session_id': session_id
            })

    except Exception as e:
        print(f"Error en el endpoint '/': {e}")
        return jsonify({'response': 'Error interno en el servidor.'})

# Nuevo endpoint para autocompletar comunas mientras se escribe



@app.route('/autocompletar_comunas', methods=['GET'])
def autocompletar_comunas():
    texto = request.args.get('q', '').strip().lower()
    print(f'Texto recibido para autocompletar: "{texto}"')
    if not texto or len(texto) < 2:
        return jsonify([])

    try:
        posibles_comunas = get_comunas_con_region(texto)
        resultados = [
            {
                "id": c[0],
                "nombre": c[1],
                "region_id": c[2],
                "region": c[3]
            }
            for c in posibles_comunas
        ]
        return jsonify(resultados)
    except Exception as e:
        print("❌ Error en /autocompletar_comunas:", e)
        return jsonify([])


@app.route('/autocompletar_servicios', methods=['GET'])
def autocompletar_servicios():
    comuna = request.args.get('comuna', '').strip().lower()
    texto = request.args.get('q', '').strip().lower()

    if not comuna:
        return jsonify({'error': 'Parámetro comuna es obligatorio'}), 400
    if not texto or len(texto) < 2:
        return jsonify([])

    try:
        servicios = buscar_servicios_por_comuna_y_texto(comuna, texto)
        resultados = [{"nombre": s} for s in servicios]
        return jsonify(resultados)
    except Exception as e:
        print("❌ Error en /autocompletar_servicios:", e)
        return jsonify([])


if __name__ == '__main__':
    app.run(debug=True)
