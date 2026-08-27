import os
import logging
import requests

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify


# ============================================================
# CONFIGURAÇÃO
# ============================================================

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# Token usado na verificação do Webhook.
# Pode ser qualquer senha que você definir no Render.
VERIFY_TOKEN = os.getenv(
    "VERIFY_TOKEN",
    "123456"
)


# Token permanente/temporário fornecido pela Meta.
WHATSAPP_ACCESS_TOKEN = os.getenv(
    "WHATSAPP_ACCESS_TOKEN",
    ""
)


# ID do número de telefone dentro do WhatsApp Business.
WHATSAPP_PHONE_NUMBER_ID = os.getenv(
    "WHATSAPP_PHONE_NUMBER_ID",
    ""
)


# Versão da Graph API.
GRAPH_API_VERSION = os.getenv(
    "GRAPH_API_VERSION",
    "v23.0"
)



# ============================================================
# GOVERNANÇA DA MESA — MASTER / VINCULADOS / RISCO
# ============================================================

# Número WhatsApp do administrador MASTER.
# Nunca coloque senha ou token diretamente no código.
MASTER_PHONE_NUMBER = os.getenv("MASTER_PHONE_NUMBER", "").strip()

# Lista de números vinculados, separados por vírgula.
# Ex.: "5511999999999,5549999999999"
LINKED_USERS = {
    item.strip()
    for item in os.getenv("LINKED_USERS", "").split(",")
    if item.strip()
}

# Política de gerenciamento de capital definida para a Mesa:
# 100% do capital = base de referência
# 80% = protegido em spot/reserva
# 20% = capital operacional
# 30% dos 20% = utilização operacional inicial (6% do total)
TOTAL_CAPITAL_PCT = 100.0
PROTECTED_CAPITAL_PCT = 80.0
OPERATIONAL_CAPITAL_PCT = 20.0
INITIAL_OPERATIONAL_USE_PCT = 30.0

INITIAL_USE_OF_TOTAL_PCT = (
    OPERATIONAL_CAPITAL_PCT * INITIAL_OPERATIONAL_USE_PCT / 100.0
)

if PROTECTED_CAPITAL_PCT + OPERATIONAL_CAPITAL_PCT != TOTAL_CAPITAL_PCT:
    raise ValueError("A divisão de capital da Mesa deve totalizar 100%.")

def is_master(sender):
    """Somente o número MASTER possui acesso administrativo."""
    return bool(MASTER_PHONE_NUMBER) and sender == MASTER_PHONE_NUMBER

def is_linked_user(sender):
    """Usuário vinculado recebe somente a camada de resultado autorizada."""
    return sender in LINKED_USERS

def user_role(sender):
    if is_master(sender):
        return "MASTER"
    if is_linked_user(sender):
        return "VINCULADO"
    return "NAO_AUTORIZADO"

def risk_summary():
    return (
        f"Capital: {TOTAL_CAPITAL_PCT:.0f}% | "
        f"Protegido: {PROTECTED_CAPITAL_PCT:.0f}% | "
        f"Operacional: {OPERATIONAL_CAPITAL_PCT:.0f}% | "
        f"Uso operacional inicial: {INITIAL_OPERATIONAL_USE_PCT:.0f}% "
        f"do operacional ({INITIAL_USE_OF_TOTAL_PCT:.1f}% do total)."
    )

def master_response(text):
    """Camada administrativa. A lógica operacional completa ficará aqui."""
    text_lower = text.lower().strip()

    if text_lower in ["status", "/status"]:
        return (
            "👑 MESA — STATUS ADMINISTRATIVO\n\n"
            "MASTER autorizado.\n"
            f"{risk_summary()}\n\n"
            "A camada de execução de operações ainda não foi habilitada."
        )

    if text_lower in ["risco", "/risco"]:
        return (
            "🛡️ GERENCIAMENTO DE RISCO DA MESA\n\n"
            f"{risk_summary()}\n\n"
            "Regra-base registrada no sistema. "
            "Nenhuma ordem real será enviada por esta camada até "
            "a integração da corretora/exchange ser validada."
        )

    return generate_response(text)

def linked_user_response(text):
    """Camada externa: somente resultado autorizado, sem detalhes internos."""
    return (
        "📊 RESULTADO DA MESA\n\n"
        "Sua conta está vinculada à Mesa.\n"
        "As informações operacionais internas, estratégias, "
        "credenciais e parâmetros de execução são restritas à administração.\n\n"
        "Quando houver resultado autorizado para divulgação, "
        "ele será informado por este canal."
    )

def unauthorized_response():
    return (
        "Acesso não autorizado. Este número não está vinculado à Mesa."
    )

# URL da API de envio de mensagens.
WHATSAPP_MESSAGES_URL = (
    f"https://graph.facebook.com/"
    f"{GRAPH_API_VERSION}/"
    f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
)


# ============================================================
# ROTA PRINCIPAL
# ============================================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "status": "online",
        "service": "WhatsApp Bot",
        "message": "Bot rodando com sucesso 🚀"
    }), 200


# ============================================================
# VERIFICAÇÃO DO WEBHOOK
# ============================================================

@app.route("/webhook", methods=["GET"])
def verify_webhook():

    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    logger.info("Solicitação de verificação do Webhook recebida.")

    logger.info(
        "mode=%s | token_recebido=%s",
        mode,
        "SIM" if token else "NAO"
    )

    if mode == "subscribe" and token == VERIFY_TOKEN:

        logger.info("Webhook verificado com sucesso.")

        return challenge, 200

    logger.error("Falha na verificação do Webhook.")

    return "Token inválido", 403


# ============================================================
# RECEBIMENTO DAS MENSAGENS
# ============================================================

@app.route("/webhook", methods=["POST"])
def receive_webhook():

    try:

        data = request.get_json(
            silent=True
        )

        logger.info(
            "=================================================="
        )

        logger.info(
            "NOVO WEBHOOK RECEBIDO"
        )

        logger.info(
            "Payload recebido: %s",
            data
        )

        if not data:

            logger.warning(
                "Webhook recebido sem JSON."
            )

            return "OK", 200


        # ----------------------------------------------------
        # Estrutura padrão da WhatsApp Cloud API
        # ----------------------------------------------------

        entries = data.get(
            "entry",
            []
        )

        if not entries:

            logger.info(
                "Webhook sem campo entry."
            )

            return "OK", 200


        for entry in entries:

            changes = entry.get(
                "changes",
                []
            )

            for change in changes:

                value = change.get(
                    "value",
                    {}
                )


                # ------------------------------------------------
                # Verifica se existe uma mensagem
                # ------------------------------------------------

                messages = value.get(
                    "messages",
                    []
                )

                if not messages:

                    logger.info(
                        "Evento recebido sem mensagem."
                    )

                    continue


                for message in messages:

                    process_message(
                        message
                    )


        return "OK", 200


    except Exception as error:

        logger.exception(
            "ERRO AO PROCESSAR WEBHOOK: %s",
            error
        )

        # A Meta espera uma resposta rápida do webhook.
        return "OK", 200


# ============================================================
# PROCESSAMENTO DA MENSAGEM
# ============================================================

def process_message(message):

    try:

        logger.info(
            "Mensagem individual recebida: %s",
            message
        )


        # ----------------------------------------------------
        # ID do usuário que enviou a mensagem
        # ----------------------------------------------------

        sender = message.get(
            "from"
        )


        if not sender:

            logger.warning(
                "Não foi possível identificar o remetente."
            )

            return


        # ----------------------------------------------------
        # Tipo da mensagem
        # ----------------------------------------------------

        message_type = message.get(
            "type"
        )


        logger.info(
            "Remetente: %s | Tipo: %s | Papel: %s",
            sender,
            message_type,
            user_role(sender)
        )


        # ----------------------------------------------------
        # Somente mensagens de texto neste primeiro teste
        # ----------------------------------------------------

        if message_type != "text":

            logger.info(
                "Mensagem não textual recebida."
            )

            send_whatsapp_message(
                sender,
                "Recebi sua mensagem, mas neste momento estou preparado para responder apenas textos."
            )

            return


        # ----------------------------------------------------
        # Extrai o texto
        # ----------------------------------------------------

        text_data = message.get(
            "text",
            {}
        )

        incoming_text = text_data.get(
            "body",
            ""
        )


        incoming_text = incoming_text.strip()


        logger.info(
            "Texto recebido: %s",
            incoming_text
        )


        if not incoming_text:

            logger.warning(
                "Mensagem de texto vazia."
            )

            return


        # ----------------------------------------------------
        # PROCESSAMENTO
        # ----------------------------------------------------

        # Controle de acesso por função.
        # MASTER recebe a camada administrativa; vinculados recebem
        # somente a camada de resultado autorizada.
        role = user_role(sender)

        if role == "MASTER":
            response_text = master_response(incoming_text)
        elif role == "VINCULADO":
            response_text = linked_user_response(incoming_text)
        else:
            response_text = unauthorized_response()


        # ----------------------------------------------------
        # ENVIA A RESPOSTA
        # ----------------------------------------------------

        send_whatsapp_message(
            sender,
            response_text
        )


    except Exception as error:

        logger.exception(
            "Erro no processamento da mensagem: %s",
            error
        )


# ============================================================
# INTELIGÊNCIA / RESPOSTA
# ============================================================

def generate_response(text):

    text_lower = text.lower().strip()


    logger.info(
        "Processando texto recebido."
    )


    # --------------------------------------------------------
    # TESTE PRINCIPAL
    # --------------------------------------------------------

    if text_lower in [
        "oi",
        "olá",
        "ola",
        "teste",
        "test",
        "hello"
    ]:

        return (
            "Olá! 👋\n\n"
            "Mensagem recebida com sucesso pelo servidor! "
            "O caminho WhatsApp → Render → Python → WhatsApp "
            "está funcionando. 🚀"
        )


    # --------------------------------------------------------
    # RESPOSTA PADRÃO
    # --------------------------------------------------------

    return (
        "Recebi sua mensagem! ✅\n\n"
        f"Você escreveu:\n{text}\n\n"
        "O servidor Python recebeu e processou sua mensagem."
    )


# ============================================================
# ENVIO PARA O WHATSAPP
# ============================================================

def send_whatsapp_message(
    recipient,
    text
):

    if not WHATSAPP_ACCESS_TOKEN:

        logger.error(
            "WHATSAPP_ACCESS_TOKEN não configurado."
        )

        return False


    if not WHATSAPP_PHONE_NUMBER_ID:

        logger.error(
            "WHATSAPP_PHONE_NUMBER_ID não configurado."
        )

        return False


    headers = {
        "Authorization": (
            f"Bearer {WHATSAPP_ACCESS_TOKEN}"
        ),
        "Content-Type": "application/json"
    }


    payload = {

        "messaging_product": "whatsapp",

        "recipient_type": "individual",

        "to": recipient,

        "type": "text",

        "text": {

            "preview_url": False,

            "body": text
        }
    }


    logger.info(
        "Enviando resposta para WhatsApp: %s",
        recipient
    )


    try:

        response = requests.post(
            WHATSAPP_MESSAGES_URL,
            headers=headers,
            json=payload,
            timeout=20
        )


        logger.info(
            "Status da API WhatsApp: %s",
            response.status_code
        )


        logger.info(
            "Resposta da API WhatsApp: %s",
            response.text
        )


        if response.ok:

            logger.info(
                "MENSAGEM ENVIADA COM SUCESSO! ✅"
            )

            return True


        logger.error(
            "Falha no envio da mensagem."
        )

        return False


    except requests.RequestException as error:

        logger.exception(
            "Erro de conexão com a API do WhatsApp: %s",
            error
        )

        return False


# ============================================================
# INICIALIZAÇÃO
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )


    logger.info(
        "=================================================="
    )

    logger.info(
        "INICIANDO BOT DO WHATSAPP"
    )

    logger.info(
        "Porta: %s",
        port
    )

    logger.info(
        "Phone Number ID configurado: %s",
        "SIM" if WHATSAPP_PHONE_NUMBER_ID else "NAO"
    )

    logger.info(
        "Access Token configurado: %s",
        "SIM" if WHATSAPP_ACCESS_TOKEN else "NAO"
    )

    logger.info(
        "=================================================="
    )




    app.run(
        host="0.0.0.0",
        port=port
    )