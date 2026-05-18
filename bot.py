from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot rodando com sucesso 🚀"

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    
    print("SINAL RECEBIDO:", data)

    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
