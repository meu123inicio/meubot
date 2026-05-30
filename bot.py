from flask import Flask, request

app = Flask(__name__)

VERIFY_TOKEN = "123456"

@app.route('/')
def home():
    return "Bot rodando com sucesso 🚀"

# 🔹 Verificação do Webhook
@app.route('/webhook', methods=['GET'])
def verify():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if token == VERIFY_TOKEN:
        return challenge
    return "Erro de verificação"

# 🔹 Receber mensagens
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    print("Mensagem recebida:", data)
    return "ok", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
