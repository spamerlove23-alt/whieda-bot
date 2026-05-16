import os
import threading
import asyncio
from flask import Flask, request, jsonify
from flask_cors import CORS
from anthropic import Anthropic

app = Flask(__name__)
CORS(app)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")
client = Anthropic(api_key=ANTHROPIC_KEY)

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        messages = data.get('messages', [])
        system = data.get('system', '')
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=system,
            messages=messages
        )
        return jsonify({'content': response.content[0].text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

def run_bot():
    import olga_bot as bot
    bot.main()

if __name__ == '__main__':
    # Запускаем Telegram бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    port = int(os.environ.get('PORT', 5000))
    print(f"Flask прокси запущен на порту {port}")
    app.run(host='0.0.0.0', port=port)
