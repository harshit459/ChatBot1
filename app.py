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
API_KEY = os.environ.get('API_KEY')
SEARCH_API_KEY = os.environ.get('SEARCH_API_KEY')
API_URL = "https://openrouter.ai/api/v1/chat/completions"
SERPAPI_BASE_URL = "https://serpapi.com/search"

# Check for required API keys
if not API_KEY:
    raise ValueError("API_KEY environment variable is not set")
if not SEARCH_API_KEY:
    raise ValueError("SEARCH_API_KEY environment variable is not set")

# Initialize system message
SYSTEM_MESSAGE = {"role": "system", "content": "You are a helpful assistant that provides quick and concise responses."}

def get_conversation_history():
    # Start with system message for each new conversation
    return [SYSTEM_MESSAGE]

def get_headers():
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "$http://localhost:3000",  # Fixed value for Vercel
        "X-Title": "Python Chatbot",
        "Accept": "application/json"
    }

# Function to trim conversation history
def trim_conversation_history(conversation_history):
    # Keep system message and last 10 messages
    if len(conversation_history) > 11:
        return [conversation_history[0]] + conversation_history[-10:]
    return conversation_history

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
        app.logger.info("Received chat request")
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        user_message = data.get('message')
        if not user_message:
            return jsonify({"error": "No message provided"}), 400
        
        # Initialize conversation history for this request
        conversation_history = get_conversation_history()
        
        # Add the user's message to conversation history
        conversation_history.append({"role": "user", "content": user_message})
        
        # Check if it's a question that might benefit from web search
        search_keywords = ["who", "what", "when", "where", "how", "why", "which", 
                         "current", "latest", "news", "weather", "price", "cost"]
        
        if any(keyword in user_message.lower() for keyword in search_keywords):
            app.logger.info("Question might benefit from web search")
            search_result = web_search(user_message)
            
            if search_result:
                app.logger.debug("Web search found relevant information")
                # Add search results as system context
                conversation_history.append({
                    "role": "system",
                    "content": search_result
                })

        # Make the API request
        request_headers = get_headers()
        
        request_body = {
            "messages": conversation_history,
            "model": "deepseek/deepseek-chat-v3.1",  # Changed to a more reliable model
            "temperature": 0.7,
            "max_tokens": 500  # Reduced max tokens
        }
        
        app.logger.debug("Sending request to OpenRouter API")
        response = requests.post(
            API_URL,
            headers=request_headers,
            json=request_body,
            timeout=10  # Reduced timeout
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
        # Trim history and get the updated version
        conversation_history = trim_conversation_history(conversation_history)
        
        return jsonify({
            "response": bot_message,
            "status": "success"
        })
    
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
    if not SEARCH_API_KEY:
        app.logger.warning("Search API key not configured, skipping web search")
        return None

    try:
        params = {
            "q": query,
            "api_key": SEARCH_API_KEY,
            "num": 3,  # Top 3 results
            "engine": "google"  # Explicitly specify the search engine
        }
        
        app.logger.debug(f"Making search request for query: {query}")
        response = requests.get(
            SERPAPI_BASE_URL,
            params=params,
            timeout=5,  # Shorter timeout for search
            headers={"Accept": "application/json"}
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
                organic_results = data.get("organic_results", [])
                
                if organic_results:
                    # Extract and combine snippets
                    snippets = []
                    for result in organic_results[:3]:  # Limit to top 3
                        snippet = result.get("snippet", "").strip()
                        if snippet:
                            snippets.append(snippet)
                    
                    if snippets:
                        return f"Context from web search:\n{' '.join(snippets)}"
                
            except json.JSONDecodeError as e:
                app.logger.error(f"Failed to parse search results: {str(e)}")
                
        elif response.status_code == 429:  # Rate limit
            app.logger.warning("Search API rate limit reached")
        else:
            app.logger.error(f"Search failed with status {response.status_code}")
            
    except requests.exceptions.Timeout:
        app.logger.warning("Search request timed out")
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Search request failed: {str(e)}")
    except Exception as e:
        app.logger.error(f"Unexpected error in web search: {str(e)}")
    
    return None  # Return None for any failure case

if __name__ == '__main__':
    app.run(debug=True)