import requests
import json
import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import logging

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Get API keys from environment variables
API_KEY = os.getenv('API_KEY', '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')
SEARCH_API_KEY = os.getenv('SEARCH_API_KEY', '0fce37158be0d3b9fe4fdadb58c4327eb092cd30f68bda8a1d601172f509c524')
API_URL = "https://openrouter.ai/api/v1/chat/completions"
# For Vercel, we'll use in-memory storage instead of file storage
conversation_history = [
    {"role": "system", "content": "You are a helpful assistant that provides quick and concise responses."}
]

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://chat-bot1-umber.vercel.app/",  # Will update after deployment
    "X-Title": "Python Chatbot",
    "OpenAI-Organization": "org-123"  # Required by OpenRouter 
}

# Function to trim conversation history
def trim_conversation_history():
    global conversation_history
    # Keep system message and last 10 messages
    if len(conversation_history) > 11:
        conversation_history = [conversation_history[0]] + conversation_history[-10:]

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    app.logger.info("Received chat request")
    data = request.json
    app.logger.debug(f"Request data: {data}")
    user_message = data.get('message')
    if not user_message:
        return jsonify({"error": "No message provided"}), 400
    
    # Add the user's message to conversation history
    conversation_history.append({"role": "user", "content": user_message})
    
    try:
        # Check if it's a general knowledge question
        if any(keyword in user_message.lower() for keyword in ["who", "what", "when", "where", "how", "current", "latest", "news", "weather"]):
            real_time_info = web_search(user_message)
            # Inject real-time info as context
            conversation_history.append({"role": "system", "content": real_time_info})

        # Make the API request
        app.logger.debug(f"Sending request to API with headers: {headers}")
        app.logger.debug(f"Request body: {conversation_history}")
        
        request_body = {
            "messages": conversation_history,
            "model": "deepseek/deepseek-chat-v3.1:free",
            "temperature": 0.7,
            "max_tokens": 1000
        }
        app.logger.debug(f"Request body: {json.dumps(request_body, indent=2)}")
        
        response = requests.post(
            API_URL,
            headers=headers,
            json=request_body,
            timeout=30
        )
        
        app.logger.debug(f"API Response Status: {response.status_code}")
        app.logger.debug(f"API Response: {response.text}")
        
        if response.status_code != 200:
            error_msg = f"API Error: {response.status_code} - {response.text}"
            app.logger.error(error_msg)
            return jsonify({"error": error_msg}), 500
            
        response_data = response.json()
        if 'choices' not in response_data or not response_data['choices']:
            error_msg = "No response choices in API response"
            app.logger.error(error_msg)
            return jsonify({"error": error_msg}), 500
            
        bot_message = response_data['choices'][0]['message']['content']
        
        # Add the bot's response to conversation history
        conversation_history.append({"role": "assistant", "content": bot_message})
        trim_conversation_history()  # Trim history to maintain context window
        
        return jsonify({"response": bot_message})
    
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Request error: {str(e)}")
        return jsonify({"error": f"Failed to communicate with API: {str(e)}"}), 500
    except json.JSONDecodeError as e:
        app.logger.error(f"JSON decode error: {str(e)}")
        return jsonify({"error": "Failed to parse API response"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

def web_search(query):
    params = {
        "q": query,
        "api_key": SEARCH_API_KEY,
        "num": 3  # Top 3 results
    }
    response = requests.get("https://serpapi.com/search", params=params)

    if response.status_code == 200:
        results = response.json().get("organic_results", [])
        snippets = "\n".join([r.get("snippet") for r in results if "snippet" in r])
        return f"🌐 Real-time search results:\n{snippets}"
    else:
        return "⚠️ Could not fetch real-time data."

if __name__ == '__main__':
    app.run(debug=True)