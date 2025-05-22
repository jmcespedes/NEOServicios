from flask import Flask
import psycopg2
import time
import threading
from twilio.rest import Client

# Configura tu conexión PostgreSQL
DB_CONFIG = {
    'host': 'tu_host',
    'dbname': 'tu_db',
    'user': 'tu_usuario',
    'password': 'tu_clave',
    'port': '5432'
}

# Configura Twilio
TWILIO_SID = 'tu_sid'
TWILIO_AUTH_TOKEN = 'tu_token'
TWILIO_NUMBER = 'tu_numero'  # Ej: +1415xxxxxxx

app = Flask(__name__)

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def enviar_mensajes():
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 1. Obtener solicitudes pendientes
            cursor.execute("""
                SELECT sesion_id, celular, comuna_id, servicio_id, pregunta_cliente
                FROM envios_whatsapp
                WHERE pregunta_cliente IS NOT NULL
                AND enviado_proveedores = false
                LIMIT 5
            """)
            solicitudes = cursor.fetchall()

            for sesion_id, celular, comuna_id, servicio_id, pregunta in solicitudes:
                # 2. Obtener nombre de la comuna
                cursor.execute("SELECT nombre FROM comunas WHERE id = %s", (comuna_id,))
                comuna_nombre = cursor.fetchone()[0]

                # 3. Buscar proveedores según comuna y servicio
                cursor.execute("""
                    SELECT nombre, telefono
                    FROM proveedores
                    WHERE LOWER(comuna) = LOWER(%s)
                    AND servicio_id = %s
                """, (comuna_nombre, servicio_id))
                proveedores = cursor.fetchall()

                # 4. Enviar WhatsApp a cada proveedor
                client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
                for nombre, telefono in proveedores:
                    mensaje = f"👋 Hola {nombre},\nNueva solicitud: {pregunta}\nCliente: {celular}"
                    try:
                        client.messages.create(
                            body=mensaje,
                            from_=TWILIO_NUMBER,
                            to=telefono
                        )
                    except Exception as e:
                        print(f"❌ Error al enviar mensaje a {telefono}: {e}")

                # 5. Marcar como enviado
                cursor.execute("""
                    UPDATE envios_whatsapp
                    SET enviado_proveedores = true
                    WHERE sesion_id = %s
                """, (sesion_id,))

                conn.commit()

            cursor.close()
            conn.close()

        except Exception as e:
            print(f"❌ Error en el proceso: {e}")

        # Esperar 60 segundos antes de volver a verificar
        time.sleep(60)

# Iniciar verificación automática en un hilo al iniciar la app
@app.before_first_request
def iniciar_verificador():
    hilo = threading.Thread(target=enviar_mensajes)
    hilo.daemon = True
    hilo.start()

@app.route('/')
def index():
    return "🟢 Bot de envío automático de WhatsApps a proveedores activo."

if __name__ == '__main__':
    app.run(debug=True)