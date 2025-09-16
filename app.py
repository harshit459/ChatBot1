import requests
import json
import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import logging
import sys

app = Flask(__name__)
CORS(app)

# Set up logging to stdout for Vercel
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# Get API key from environment variable
API_KEY = os.environ.get('API_KEY')
API_URL = "https://openrouter.ai/api/v1/chat/completions"

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    if not API_KEY:
        logging.error("API key not configured")
        return jsonify({"error": "API key not configured"}), 500

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        user_message = data.get('message')
        if not user_message:
            return jsonify({"error": "No message provided"}), 400

        logging.info(f"Processing chat request with message: {user_message[:50]}...")
        
        # Create a new conversation for each request
        messages = [
            {"role": "system", "content": "You are a helpful assistant that provides quick and concise responses."},
            {"role": "user", "content": user_message}
        ]

        # Prepare headers
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://chatbot1-harshit459.vercel.app",
            "X-Title": "Harshit's Chatbot",
            "Accept": "application/json"
        }

        # Prepare request body
        request_body = {
            "messages": messages,
            "model": "deepseek/deepseek-chat-v3.1",
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        logging.info("Sending request to API")
        response = requests.post(
            API_URL,
            headers=headers,
            json=request_body,
            timeout=10
        )
        
        if response.status_code != 200:
            error_msg = f"API Error: {response.status_code}"
            logging.error(error_msg)
            return jsonify({"error": error_msg}), 500
            
        response_data = response.json()
        if 'choices' not in response_data or not response_data['choices']:
            error_msg = "No response choices in API response"
            logging.error(error_msg)
            return jsonify({"error": error_msg}), 500
            
        bot_message = response_data['choices'][0]['message']['content']
        logging.info("Successfully generated response")
        
        return jsonify({
            "response": bot_message,
            "status": "success"
        })
    
    except requests.exceptions.Timeout:
        logging.error("Request timed out")
        return jsonify({"error": "Request timed out"}), 504
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error: {str(e)}")
        return jsonify({"error": "Failed to communicate with API"}), 500
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error: {str(e)}")
        return jsonify({"error": "Failed to parse API response"}), 500
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(debug=True)