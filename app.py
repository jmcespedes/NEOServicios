import os
import time
import random
import re
from flask import Flask, request, jsonify, make_response, redirect
from flask_cors import CORS
from twilio.rest import Client

print("===> Flask app iniciado correctamente")
print("===> Antes de importar db")

from db import (
    get_db_connection, crear_sesion, obtener_datos_sesion, actualizar_sesion,
    get_comunas_con_region, get_servicios_por_comuna, buscar_servicios_por_comuna_y_texto, generar_codigo_verificacion
)
print("===> Después de importar db")

app = Flask(__name__)

# CORS global: para pruebas, permite todos los orígenes
#CORS(app, origins="*", supports_credentials=True, methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type"])
# Para producción, cambia a:
CORS(app, origins=[
    "https://www.neoservicios.cl",
    "https://neoservicios.cl"
], supports_credentials=True,
   methods=["GET", "POST", "OPTIONS"],
   allow_headers=["Content-Type"])

# Configuración de Twilio
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE = os.getenv("TWILIO_PHONE_NUMBER")  # Debe ser un número de Twilio SMS, no WhatsApp

twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

def enviar_codigo_sms(numero, codigo):
    try:
        mensaje = f"Tu código de verificación NEOServicios es: {codigo}"
        message = twilio_client.messages.create(
            body=mensaje,
            from_=TWILIO_PHONE,
            to=numero
        )
        print(f"✅ SMS enviado a {numero} (SID: {message.sid})")
        return True
    except Exception as e:
        print(f"❌ Error al enviar SMS a {numero}: {e}")
        return False

@app.errorhandler(Exception)
def handle_exception(e):
    response = jsonify({'error': str(e)})
    response.status_code = 500
    return response

@app.before_request
def force_https():
    if not request.is_secure and request.headers.get('X-Forwarded-Proto', 'http') != 'https':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)

iconos_servicios = {
    "Flete": "🚚",
    "Abogado": "⚖️",
    "Electricista": "⚡",
    "Gasfiter": "🔧",
    "Peluqueria": "💇"
}

@app.route('/', methods=['GET', 'POST'])
def chat():
    if request.method == 'GET':
        return jsonify({'response': 'Método GET no soportado. Usa POST.'})

    t0 = time.time()
    try:
        data = request.get_json()
        print(f"[{time.time() - t0:.4f}s] Recibido POST /")

        session_id = data.get("session_id")
        t1 = time.time()
        if session_id:
            session = obtener_datos_sesion(session_id)
            print(f"[{time.time() - t1:.4f}s] obtener_datos_sesion")
            if not session:
                session = crear_sesion()
                session_id = session['session_id']
                print(f"[{time.time() - t1:.4f}s] crear_sesion (no session)")
        else:
            session = crear_sesion()
            session_id = session['session_id']
            print(f"[{time.time() - t1:.4f}s] crear_sesion (no session_id)")

        paso_actual = session.get('paso_actual', 'espera_comuna_region')
        print(f"[{time.time() - t0:.4f}s] paso_actual: {paso_actual}")

        if paso_actual == 'espera_comuna_region':
            user_response = data.get("response", "").strip()
            t2 = time.time()
            posibles_comunas = get_comunas_con_region(user_response)
            print(f"[{time.time() - t2:.4f}s] get_comunas_con_region")

            if len(posibles_comunas) > 1:
                print(f"[{time.time() - t0:.4f}s] Varias comunas encontradas")
                comunas_con_region = [f"{c[1]} ({c[3]})" for c in posibles_comunas]
                mensaje = "⚠️ Varias comunas coinciden. Por favor indica la comuna y su región (ej: *'Puente Alto, Metropolitana'*):\n"
                mensaje += "\n".join([f"- {c}" for c in comunas_con_region])
                return jsonify({
                    'response': mensaje,
                    'action': 'desambiguar_comuna',
                    'session_id': session_id
                })

            if not posibles_comunas:
                print(f"[{time.time() - t0:.4f}s] No se encontró comuna")
                return jsonify({
                    'response': 'No reconozco esa comuna. Por favor indica una comuna válida de Chile.',
                    'session_id': session_id
                })

            comuna = posibles_comunas[0]
            comuna_id, comuna_nombre, region_id, region_nombre = comuna

            t4 = time.time()
            servicios = get_servicios_por_comuna(comuna_nombre)
            print(f"[{time.time() - t4:.4f}s] get_servicios_por_comuna")

            if not servicios:
                print(f"[{time.time() - t0:.4f}s] No hay servicios para la comuna")
                return jsonify({
                    'response': f'⚠️ No hay servicios disponibles para {comuna_nombre}. Por favor indica otra comuna.',
                    'session_id': session_id
                })

            actualizar_sesion(session_id, comuna_id=comuna_id, region_id=region_id, paso_actual='espera_servicio')
            print(f"[{time.time() - t0:.4f}s] actualizar_sesion (espera_servicio)")

            servicios_lista = [{"id": s[0], "nombre": s[1].lower()} for s in servicios]

            respuesta = (
                f"Para {comuna_nombre}, Región: {region_nombre} tenemos {len(servicios_lista)} servicios disponibles.<br><br>"
                "Por favor, selecciona un servicio del siguiente listado:"
            )
            return jsonify({
                'response': respuesta,
                'session_id': session_id,
                'servicios': servicios_lista,
                'action': 'seleccionar_servicio'
            })

        elif paso_actual == 'espera_servicio':
            comuna_id = session['comuna_id']
            if not comuna_id:
                print(f"[{time.time() - t0:.4f}s] No hay comuna_id en sesión")
                return jsonify({'response': 'Primero necesitamos tu comuna.', 'session_id': session_id})

            t5 = time.time()
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT nombre FROM comunas WHERE id = %s", (comuna_id,))
                comuna_nombre = cur.fetchone()[0]
            conn.close()
            print(f"[{time.time() - t5:.4f}s] SELECT nombre FROM comunas")

            t6 = time.time()
            servicios = get_servicios_por_comuna(comuna_nombre)
            print(f"[{time.time() - t6:.4f}s] get_servicios_por_comuna (espera_servicio)")

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
                print(f"[{time.time() - t0:.4f}s] Servicio encontrado y sesión actualizada")
                return jsonify({
                    'response': f"✅ Servicio ingresado: *{servicio_encontrado['nombre'].capitalize()}*. Favor formula la pregunta al proveedor (que sea clara)",
                    'session_id': session_id
                })
            else:
                print(f"[{time.time() - t0:.4f}s] Servicio no reconocido")
                servicios_texto = "\n".join([f"- {s['nombre'].capitalize()}" for s in servicios_lista])
                mensaje = (
                    "⚠️ No reconozco ese servicio. Por favor selecciona uno de la lista:\n\n"
                    f"{servicios_texto}"
                )
                return jsonify({
                    'response': mensaje,
                    'session_id': session_id,
                    'servicios': servicios_lista,
                    'action': 'seleccionar_servicio'
                })

        elif paso_actual == 'espera_pregunta':
            pregunta = data.get('response', '').strip()
            if len(pregunta) < 25:
                print(f"[{time.time() - t0:.4f}s] Pregunta demasiado corta")
                return jsonify({
                    'response': "📝 Por favor formula tu pregunta con más detalle (mínimo 25 caracteres).",
                    'session_id': session_id
                })

            actualizar_sesion(session_id, pregunta_cliente=pregunta, paso_actual='espera_celular')
            print(f"[{time.time() - t0:.4f}s] Pregunta guardada, paso_actual espera_celular")
            return jsonify({
                'response': "📱 Ahora, por favor indica tu número de celular con formato +569XXXXXXXX.",
                'session_id': session_id
            })

        elif paso_actual == 'espera_celular':
            celular = data.get('response')
            if not re.match(r'^\+569\d{8}$', celular):
                print(f"[{time.time() - t0:.4f}s] Celular inválido")
                return jsonify({
                    'response': "⚠️ Por favor indica un número de celular válido, con formato +569XXXXXXXX.",
                    'session_id': session_id
                })

            # Genera código de 4 dígitos
            codigo = str(random.randint(1000, 9999))
            print(f"[{time.time() - t0:.4f}s] Código generado: {codigo}")

            # Guarda el código y el celular en la sesión
            actualizar_sesion(session_id, celular=celular, codigo_verificacion=codigo, paso_actual='espera_codigo_sms')

            # Envía el SMS
            sms_enviado = enviar_codigo_sms(celular, codigo)

            if sms_enviado:
                print(f"[{time.time() - t0:.4f}s] Código SMS enviado correctamente")
                return jsonify({
                    'response': "🔒 Te enviamos un SMS con un código de 4 dígitos. Por favor ingrésalo aquí para verificar tu número.",
                    'session_id': session_id
                })
            else:
                print(f"[{time.time() - t0:.4f}s] Error al enviar SMS")
                return jsonify({
                    'response': "❌ Hubo un problema al enviar el SMS. Por favor verifica tu número o intenta más tarde.",
                    'session_id': session_id
                })

        elif paso_actual == 'espera_codigo_sms':
            codigo_usuario = data.get('response', '').strip()
            datos_sesion = obtener_datos_sesion(session_id)
            codigo_real = datos_sesion.get('codigo_verificacion')
            celular = datos_sesion.get('celular')

            print(f"[{time.time() - t0:.4f}s] Verificando código: usuario={codigo_usuario}, real={codigo_real}")

            if codigo_usuario == codigo_real:
                # Código correcto, registramos la solicitud
                actualizar_sesion(session_id, paso_actual='terminado')

                # Obtenemos los datos necesarios para registrar la solicitud
                region_id = datos_sesion['region_id']
                comuna_id = datos_sesion['comuna_id']
                servicio_id = datos_sesion['servicio_id']
                pregunta_cliente = datos_sesion['pregunta_cliente']

                try:
                    t7 = time.time()
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO envios_whatsapp (sesion_id, celular, region_id, comuna_id, servicio_id, pregunta_cliente)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (session_id, celular, region_id, comuna_id, servicio_id, pregunta_cliente))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    print(f"[{time.time() - t7:.4f}s] INSERT INTO envios_whatsapp")
                except Exception as e:
                    print("❌ Error al registrar en envios_whatsapp:", e)
                    return jsonify({
                        'response': "❌ Hubo un problema al registrar tu solicitud. Por favor intenta más tarde.",
                        'session_id': session_id
                    })

                print(f"[{time.time() - t0:.4f}s] Código verificado correctamente, solicitud registrada")
                return jsonify({
                    'response': "✅ ¡Gracias! Tu número fue verificado y tu solicitud ha sido registrada. Pronto te contactaremos.",
                    'session_id': session_id
                })
            else:
                print(f"[{time.time() - t0:.4f}s] Código incorrecto, regenerando código")
                # Genera un nuevo código
                nuevo_codigo = str(random.randint(1000, 9999))
                # Envía el nuevo código por SMS
                sms_enviado = enviar_codigo_sms(celular, nuevo_codigo)

                if sms_enviado:
                    # Guarda el nuevo código en la sesión
                    actualizar_sesion(session_id, codigo_verificacion=nuevo_codigo)
                    print(f"[{time.time() - t0:.4f}s] Nuevo código SMS enviado")
                    return jsonify({
                        'response': "❌ El código ingresado no es correcto. Te enviamos un nuevo código por SMS. Por favor revísalo e inténtalo de nuevo.",
                        'session_id': session_id
                    })
                else:
                    print(f"[{time.time() - t0:.4f}s] Error al enviar nuevo SMS")
                    return jsonify({
                        'response': "❌ El código ingresado no es correcto, pero hubo un problema al enviar un nuevo SMS. Por favor inténtalo de nuevo más tarde.",
                        'session_id': session_id
                    })

        elif paso_actual == 'finalizado':
            print(f"[{time.time() - t0:.4f}s] Sesión finalizada")
            return jsonify({
                'response': "Gracias por usar el asistente. Si necesitas algo más, inicia una nueva sesión.",
                'session_id': session_id
            })

        else:
            print(f"[{time.time() - t0:.4f}s] Paso_actual desconocido")
            return jsonify({
                'response': "No entiendo tu mensaje. Por favor, intenta de nuevo.",
                'session_id': session_id
            })

    except Exception as e:
        print(f"Error en el endpoint '/': {e}")
        return jsonify({'response': 'Error interno en el servidor.'})

@app.route('/autocompletar_comunas', methods=['GET'])
def autocompletar_comunas():
    t0 = time.time()
    texto = request.args.get('q', '').strip().lower()
    print(f'[{time.time() - t0:.4f}s] Texto recibido para autocompletar: "{texto}"')
    if not texto or len(texto) < 2:
        return jsonify([])

    try:
        t1 = time.time()
        posibles_comunas = get_comunas_con_region(texto)
        print(f'[{time.time() - t1:.4f}s] get_comunas_con_region (autocompletar)')
        resultados = [
            {
                "id": c[0],
                "nombre": c[1],
                "region_id": c[2],
                "region": c[3]
            }
            for c in posibles_comunas
        ]
        print(f'[{time.time() - t0:.4f}s] Respuesta enviada (autocompletar_comunas)')
        return jsonify(resultados)
    except Exception as e:
        print("❌ Error en /autocompletar_comunas:", e)
        return jsonify([])

@app.route('/autocompletar_servicios', methods=['GET'])
def autocompletar_servicios():
    t0 = time.time()
    comuna = request.args.get('comuna', '').strip().lower()
    texto = request.args.get('q', '').strip().lower()
    print(f'[{time.time() - t0:.4f}s] Autocompletar servicios para comuna="{comuna}", texto="{texto}"')

    if not comuna:
        return jsonify({'error': 'Parámetro comuna es obligatorio'}), 400
    if not texto or len(texto) < 2:
        return jsonify([])

    try:
        t1 = time.time()
        servicios = buscar_servicios_por_comuna_y_texto(comuna, texto)
        print(f'[{time.time() - t1:.4f}s] buscar_servicios_por_comuna_y_texto')
        resultados = [{"nombre": s} for s in servicios]
        print(f'[{time.time() - t0:.4f}s] Respuesta enviada (autocompletar_servicios)')
        return jsonify(resultados)
    except Exception as e:
        print("❌ Error en /autocompletar_servicios:", e)
        return jsonify([])

if __name__ == '__main__':
    app.run(debug=True)