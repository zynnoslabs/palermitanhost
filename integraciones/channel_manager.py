# integraciones/channel_manager.py
# Base para integrar un channel manager (Hostaway, Guesty, Hospitable, etc.)
#
# Lo que haría:
#  1. Autenticarse con la API del channel manager usando OAuth o API key.
#  2. Obtener reservas nuevas vía webhook (el CM llama a una URL nuestra) o polling.
#  3. Transformar el formato del CM al formato interno de RentaIA y llamar a
#     database.execute() para insertar la reserva.
#  4. Para el asistente: el CM envía el mensaje del huésped → llamamos a
#     ia.responder_huesped() → devolvemos la respuesta al CM para que la envíe.
#
# Ejemplo de endpoint webhook (agregar a app.py):
#
# @app.route("/webhook/reserva", methods=["POST"])
# def webhook_reserva():
#     datos = request.json
#     # transformar datos del CM al formato interno...
#     # database.execute(INSERT INTO reservas ...)
#     return jsonify({"ok": True})

def recibir_reserva_webhook(datos_cm):
    """Transforma datos del channel manager al formato interno."""
    # TODO: implementar según el CM elegido
    raise NotImplementedError("Implementar según el channel manager")


def enviar_respuesta_huesped(mensaje_id, respuesta):
    """Envía una respuesta al huésped a través del CM."""
    # TODO: implementar según el CM elegido
    raise NotImplementedError("Implementar según el channel manager")
