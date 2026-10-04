# integraciones/whatsapp.py
# Base para recibir consultas de huéspedes por WhatsApp (API oficial de Meta)
#
# Lo que haría:
#  1. Registrar un webhook en Meta Business que recibe mensajes de WhatsApp.
#  2. Al llegar un mensaje: identificar la propiedad por número de teléfono
#     (cada propiedad tendría un número asociado) o por el contexto.
#  3. Llamar a ia.responder_huesped(propiedad_id, mensaje, info_huespedes).
#  4. Enviar la respuesta de vuelta al huésped por la API de WhatsApp.
#  5. Guardar en consultas_huespedes con fuente='whatsapp'.

def verificar_webhook(token, hub_challenge):
    """Verificación inicial del webhook de Meta."""
    VERIFY_TOKEN = "rentaia_whatsapp_token"  # Cambiar en producción
    if token == VERIFY_TOKEN:
        return hub_challenge
    return None


def procesar_mensaje_entrante(payload):
    """Procesa un mensaje entrante de WhatsApp y devuelve la respuesta."""
    # TODO: parsear payload de Meta, llamar a ia.responder_huesped(), enviar respuesta
    raise NotImplementedError("Implementar con credenciales de WhatsApp Business API")
