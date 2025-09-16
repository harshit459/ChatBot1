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

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Constants
API_KEY = os.getenv('API_KEY', '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')
SEARCH_API_KEY = os.getenv('SEARCH_API_KEY', '0fce37158be0d3b9fe4fdadb58c4327eb092cd30f68bda8a1d601172f509c524')
API_URL = "https://openrouter.ai/api/v1/chat/completions"
SERPAPI_URL = "https://serpapi.com/search"

def web_search(query):
    """Perform a web search using SerpAPI."""
    try:
        params = {
            "q": query,
            "api_key": SEARCH_API_KEY,
            "num": 3  # Top 3 results
        }
        response = requests.get(SERPAPI_URL, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        results = data.get("organic_results", [])
        if not results:
            return None

        snippets = [r.get("snippet", "") for r in results if "snippet" in r]
        if snippets:
            return "🌐 Real-time search results:\n" + " ".join(snippets)
        return None
    except Exception as e:
        app.logger.error(f"Web search error: {str(e)}")
        return None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat requests."""
    try:
        # Validate request data
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        user_message = data.get('message')
        if not user_message:
            return jsonify({"error": "No message provided"}), 400

        app.logger.info(f"Processing message: {user_message[:50]}...")

        # Check for knowledge questions
        search_keywords = ["who", "what", "when", "where", "how", "why", 
                         "current", "latest", "news", "weather"]
        
        enhanced_message = user_message
        if any(keyword in user_message.lower() for keyword in search_keywords):
            search_result = web_search(user_message)
            if search_result:
                enhanced_message = f"{user_message}\n\nContext: {search_result}"

        # Prepare headers with all required fields
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://python-chatbot.com",
            "X-Title": "Python Chatbot"
        }

        # Log API key for debugging (first 10 chars)
        app.logger.debug(f"Using API key starting with: {API_KEY[:10]}...")

        # Prepare request with a simpler model
        request_body = {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that provides quick and concise responses."},
                {"role": "user", "content": enhanced_message}
            ],
            "model": "mistralai/mistral-small-3.2-24b-instruct:free",
            "temperature": 0.7,
            "max_tokens": 150,
            "headers": {
                "HTTP-Referer": "https://python-chatbot.com"
            }
        }

        # Make API request
        app.logger.info("Sending request to API")
        response = requests.post(
            API_URL,
            headers=headers,
            json=request_body,
            timeout=30
        )
        
        # Handle API response
        response.raise_for_status()
        response_data = response.json()
        
        if 'choices' not in response_data or not response_data['choices']:
            app.logger.error("No choices in API response")
            return jsonify({"error": "Invalid response from API"}), 500
            
        bot_message = response_data['choices'][0]['message']['content']
        return jsonify({
            "response": bot_message,
            "status": "success"
        })
        
    except requests.Timeout:
        app.logger.error("Request to API timed out")
        return jsonify({"error": "Request timed out"}), 504
        
    except requests.RequestException as e:
        error_msg = str(e)
        app.logger.error(f"API request failed: {error_msg}")
        
        if hasattr(e.response, 'text'):
            try:
                error_data = e.response.json()
                error_msg = error_data.get('error', {}).get('message', error_msg)
            except:
                error_msg = e.response.text
            app.logger.error(f"API response: {error_msg}")
            
        # Check for specific error types
        if e.response and e.response.status_code == 401:
            return jsonify({"error": "Invalid API key. Please check your OpenRouter API key and try again."}), 401
        elif e.response and e.response.status_code == 429:
            return jsonify({"error": "Too many requests. Please try again later."}), 429
            
        return jsonify({"error": f"Failed to communicate with API: {error_msg}"}), 500
        
    except json.JSONDecodeError as e:
        app.logger.error(f"Failed to parse API response: {str(e)}")
        return jsonify({"error": "Invalid response from API"}), 500
        
    except Exception as e:
        app.logger.error(f"Unexpected error in chat: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    # Use production config when deployed
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)