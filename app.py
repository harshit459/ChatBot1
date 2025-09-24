import requests
import json
import os
import logging
import uuid
import hashlib
import traceback
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
from functools import wraps
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24))
CORS(app, supports_credentials=True)

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Initialize Supabase client
try:
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env file")
    
    app.logger.info("Initializing Supabase client...")
    app.logger.debug(f"Supabase URL: {supabase_url}")
    app.logger.debug(f"Supabase key (first 10 chars): {supabase_key[:10]}...")
    
    supabase = create_client(supabase_url, supabase_key)
    
    # Test the connection
    app.logger.info("Testing Supabase connection...")
    test_query = supabase.table('users').select("count").execute()
    app.logger.info("Supabase connection successful!")
except Exception as e:
    app.logger.error(f"Failed to initialize Supabase: {str(e)}")
    app.logger.error(traceback.format_exc())
    raise

def hash_password(password):
    """Create a secure hash of the password."""
    return hashlib.sha256(password.encode()).hexdigest()

def login_required(f):
    """Decorator to check if user is logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Please log in to continue"}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        app.logger.info(f"Registration attempt for username: {username}")
        
        if not username or not password or not confirm_password:
            return render_template('register.html', error="Please fill in all fields")
        
        if password != confirm_password:
            return render_template('register.html', error="Passwords do not match")
        
        try:
            # Check if username exists
            result = supabase.table('users').select('id').eq('username', username).execute()
            if result.data:
                return render_template('register.html', error="Username already exists")
            
            # Create new user with a valid UUID
            user_id = uuid.uuid4()
            
            # Log the attempt to create user
            app.logger.info("Attempting to create new user in Supabase...")
            
            # Hash the password
            hashed_password = hash_password(password)
            
            # Prepare user data
            user_data = {
                'id': str(user_id),
                'username': username,
                'password_hash': hashed_password
            }
            
            # Insert new user with RLS bypass
            app.logger.info("Inserting new user into database...")
            try:
                result = supabase.table('users').insert(user_data).execute()
                
                if not result.data:
                    app.logger.error("User creation failed: No data returned")
                    return render_template('register.html', error="Registration failed: No data returned")
            except Exception as db_error:
                error_str = str(db_error)
                app.logger.error(f"Database error: {error_str}")
                if "new row violates row-level security policy" in error_str:
                    # If this error occurs, we need to use the auth API instead
                    try:
                        auth_response = supabase.auth.sign_up({
                            "email": f"{username}@temp.com",
                            "password": password,
                            "data": {
                                "username": username,
                                "custom_id": str(user_id)
                            }
                        })
                        if auth_response.user and auth_response.user.id:
                            result = supabase.table('users').insert({
                                'id': auth_response.user.id,
                                'username': username,
                                'password_hash': hashed_password
                            }).execute()
                        else:
                            return render_template('register.html', error="Registration failed: Auth error")
                    except Exception as auth_error:
                        app.logger.error(f"Auth error: {str(auth_error)}")
                        return render_template('register.html', error="Registration failed: Authentication error")
            
            # Set session data
            session['user_id'] = str(user_id)
            session['username'] = username
            
            # Initialize user_info
            app.logger.info("Initializing user_info...")
            supabase.table('user_info').insert({
                'user_id': str(user_id),
                'info': json.dumps({})
            }).execute()
            
            app.logger.info("User registration complete. Redirecting to home...")
            return redirect(url_for('home'))
            
        except Exception as e:
            app.logger.error(f"Registration error: {str(e)}")
            app.logger.error(f"Error type: {type(e)}")
            app.logger.error(traceback.format_exc())
            return render_template('register.html', error=f"Registration failed: {str(e)}")
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            return render_template('login.html', error="Please fill in all fields")
        
        try:
            result = supabase.table('users').select('id, password_hash').eq('username', username).execute()
            
            if result.data and result.data[0]['password_hash'] == hash_password(password):
                session.clear()
                session['user_id'] = result.data[0]['id']
                session['username'] = username
                session.permanent = True
                return redirect(url_for('home'))
            
            return render_template('login.html', error="Invalid username or password")
        except Exception as e:
            app.logger.error(f"Login error: {str(e)}")
            return render_template('login.html', error="An error occurred. Please try again.")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session.get('username', ''))

def extract_user_info(message):
    """Extract potential user information from the message."""
    info = {}
    import re
    name_patterns = [
        r"(?i)my name is (\w+)",
        r"(?i)i am (\w+)",
        r"(?i)i'm (\w+)",
        r"(?i)call me (\w+)"
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, message)
        if match:
            info['name'] = match.group(1)
            break
    
    return info

def save_user_info(user_id, new_info):
    """Save or update user information in Supabase."""
    try:
        result = supabase.table('user_info').select('info').eq('user_id', user_id).execute()
        
        if result.data:
            current_info = json.loads(result.data[0]['info'])
            current_info.update(new_info)
            supabase.table('user_info').update({'info': json.dumps(current_info)}).eq('user_id', user_id).execute()
        else:
            supabase.table('user_info').insert({
                'user_id': user_id,
                'info': json.dumps(new_info)
            }).execute()
    except Exception as e:
        app.logger.error(f"Error saving user info: {str(e)}")
        raise

def get_user_info(user_id):
    """Get user information from Supabase."""
    try:
        result = supabase.table('user_info').select('info').eq('user_id', user_id).execute()
        return json.loads(result.data[0]['info']) if result.data else {}
    except Exception as e:
        app.logger.error(f"Error getting user info: {str(e)}")
        return {}

def get_conversation_history(user_id, limit=20):
    """Get recent conversation history for a user."""
    try:
        result = supabase.table('conversations').select('role', 'content').eq('user_id', user_id).order('timestamp', desc=True).limit(limit).execute()
        messages = result.data
        
        system_message = {
            "role": "system",
            "content": """You are a helpful, friendly assistant that remembers information about the user throughout the conversation.

            Important instructions for formatting responses:
            1. Always structure your responses in a clean, easy-to-read format
            2. Use bullet points (•) or numbered lists when listing multiple items
            3. Use appropriate spacing and line breaks for readability
            4. For data or statistics, present them in a clear, structured way
            5. Use appropriate emphasis with bold or italics markers when needed
            6. When sharing weather or time-sensitive information, highlight the key details
            7. Break down complex information into digestible sections
            
            Important instructions for personalization:
            1. Remember and use the user's name if they share it
            2. Remember personal preferences and context from previous conversations
            3. If providing real-time data (weather, news, etc.), highlight the most relevant information first
            4. If you need to correct or clarify something, do so politely
            5. Keep your tone friendly and conversational while maintaining professionalism

            When formatting responses:
            • For weather: Start with current conditions, then forecast
            • For lists: Use bullet points and clear categories
            • For explanations: Use short paragraphs with clear headings
            • For data: Present in a structured, easy-to-read format
            • For instructions: Use numbered steps

            Keep your responses concise but informative, and always prioritize clarity."""
        }
        
        conversation = [system_message] + list(reversed(messages))
        return conversation
    except Exception as e:
        app.logger.error(f"Error getting conversation history: {str(e)}")
        return [system_message]

def save_message(user_id, role, content):
    """Save a message to the conversation history."""
    try:
        supabase.table('conversations').insert({
            'user_id': user_id,
            'role': role,
            'content': content
        }).execute()
    except Exception as e:
        app.logger.error(f"Error saving message: {str(e)}")
        raise

def web_search(query):
    """Perform a web search using SerpAPI."""
    try:
        params = {
            "q": query,
            "api_key": os.getenv('SEARCH_API_KEY'),
            "num": 3
        }
        response = requests.get("https://serpapi.com/search", params=params, timeout=10)
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

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    """Handle chat requests with persistent conversation memory."""
    try:
        user_id = session['user_id']
        data = request.get_json()
        
        if not data or 'message' not in data:
            return jsonify({"error": "No message provided"}), 400
            
        user_message = data['message']
        app.logger.info(f"Processing message for user {user_id[:8]}: {user_message[:50]}...")
        
        # Handle web search for knowledge questions
        enhanced_message = user_message
        if any(kw in user_message.lower() for kw in ["who", "what", "when", "where", "how", "why", "current", "latest"]):
            search_result = web_search(user_message)
            if search_result:
                enhanced_message = f"{user_message}\n\nContext: {search_result}"
        
        # Extract and save user information
        user_info = extract_user_info(user_message)
        if user_info:
            save_user_info(user_id, user_info)
            
        # Add context from stored user info
        stored_info = get_user_info(user_id)
        if stored_info:
            context = "Previous context: "
            if 'name' in stored_info:
                context += f"The user's name is {stored_info['name']}. "
            enhanced_message = f"{context}\n\nCurrent message: {enhanced_message}"
            
        # Save user message and get conversation history
        save_message(user_id, "user", enhanced_message)
        conversation = get_conversation_history(user_id)
        
        # Prepare API request
        headers = {
            "Authorization": f"Bearer {os.getenv('API_KEY')}",
            "HTTP-Referer": request.headers.get('Origin', 'https://python-chatbot.com'),
            "X-Title": "ChatBot1",
            "Content-Type": "application/json"
        }
        
        request_body = {
            "messages": conversation[-5:],
            "model": "x-ai/grok-4-fast:free",
            "temperature": 0.5,  # Lower temperature for more consistent formatting
            "max_tokens": 500,   # Increased token limit for better formatting
            "stream": False,
            "top_p": 0.9,       # More focused responses
            "frequency_penalty": 0.3,  # Reduce repetition
            "presence_penalty": 0.3    # Encourage more diverse responses
        }
        
        # Enhance the system message based on the type of query
        if "weather" in user_message.lower():
            request_body["messages"].insert(0, {
                "role": "system",
                "content": """Format weather information in a clean, structured way:
                • Start with current conditions
                • Show temperature with both °C and °F
                • Highlight important weather alerts or changes
                • Use bullet points for hourly breakdowns
                • Put severe weather warnings in a separate section"""
            })
        elif any(word in user_message.lower() for word in ["list", "steps", "how to", "guide"]):
            request_body["messages"].insert(0, {
                "role": "system",
                "content": """You are a concise and clear assistant. Format your responses following these rules:

1. Keep responses brief and focused
   • Limit lists to 5 items maximum
   • One key point per item
   • No lengthy explanations

2. Use Simple Formatting
   • Numbered steps for instructions
   • Short, clear sentences
   • No special characters or markers
   • No repetition

For bullet point lists:
• Start each item with a bullet point (•)
• Include a space after the bullet point
• Keep items aligned and properly indented
• Use sub-bullets for nested items

For headings and sections:
- Use clear, descriptive headings
- Add a blank line before and after headings
- Group related information under each heading
- Use consistent formatting throughout

Formatting rules:
- Never use asterisks (*) for formatting
- Use proper spacing and line breaks
- Keep paragraphs short and focused
- Use clear, simple language"""
            })

        # Get response from API
        app.logger.debug(f"Making API request to OpenRouter...")
        app.logger.debug(f"Headers: {headers}")
        app.logger.debug(f"Request body: {json.dumps(request_body, indent=2)}")
        
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            data=json.dumps(request_body),
            timeout=30
        )
        
        app.logger.debug(f"Response status code: {response.status_code}")
        app.logger.debug(f"Response headers: {dict(response.headers)}")
        app.logger.debug(f"Response text: {response.text}")
        
        response.raise_for_status()
        response_data = response.json()
        
        if 'choices' not in response_data or not response_data['choices']:
            raise ValueError("Invalid response from API")
            
        bot_message = response_data['choices'][0]['message']['content']
        
        # Clean up and format the response
        def format_response(message):
            def clean_text(text):
                # Remove multiple spaces and clean up markers
                text = ' '.join(text.split())
                text = text.replace('###', '')
                text = text.replace('**', '')
                text = text.replace('*.', '•')
                text = text.replace('•*', '•')
                text = text.replace('*', '')
                return text.strip()

            def format_list_item(line, is_numbered=False):
                # Format a single list item
                line = clean_text(line)
                if is_numbered and '. ' in line:
                    num, content = line.split('. ', 1)
                    if num.isdigit():
                        return f"{num}. {content}"
                return line

            # Split response into sections
            sections = message.split('\n\n')
            formatted_sections = []

            for section in sections:
                lines = section.split('\n')
                formatted_lines = []

                # Process greeting or introduction separately
                if not any(line.strip()[0].isdigit() for line in lines) and \
                   not any('•' in line for line in lines) and \
                   len(lines[0].split()) < 15:
                    formatted_sections.append(clean_text(lines[0]))
                    lines = lines[1:]
                
                # Format remaining lines
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Handle numbered items
                    if line[0].isdigit() and '. ' in line[:4]:
                        formatted_lines.append(format_list_item(line, is_numbered=True))
                    # Handle bullet points
                    elif '•' in line or line.lstrip().startswith('-'):
                        line = line.replace('-', '•')
                        formatted_lines.append(f"  • {clean_text(line.split('•', 1)[1])}")
                    # Handle regular text
                    else:
                        formatted_lines.append(clean_text(line))

                if formatted_lines:
                    formatted_sections.append('\n'.join(formatted_lines))

            # Join sections with proper spacing
            return '\n\n'.join(formatted_sections)

        def truncate_response(message, max_items=5):
            # Split into sections
            sections = message.split('\n\n')
            
            # Always keep the first section (greeting/intro)
            result = [sections[0]]
            
            # Find and limit list items
            list_items = []
            for section in sections[1:]:
                lines = section.split('\n')
                for line in lines:
                    if (line.strip().startswith(('1.', '2.', '3.', '4.', '5.', '•'))):
                        list_items.append(line)
                        if len(list_items) >= max_items:
                            break
                if len(list_items) >= max_items:
                    break
            
            if list_items:
                result.append('\n'.join(list_items))
            
            # Add a closing note if there were more items
            if len(list_items) < sum(1 for section in sections[1:] for line in section.split('\n') 
                                   if line.strip().startswith(('1.', '2.', '3.', '4.', '5.', '•'))):
                result.append("Let me know if you'd like more suggestions.")
            
            return '\n\n'.join(result)
        
        # Clean and format the response
        bot_message = format_response(bot_message)
        
        # Truncate if it's a list-type response
        if any(line.strip().startswith(('1.', '•')) for line in bot_message.split('\n')):
            bot_message = truncate_response(bot_message, max_items=5)
        
        save_message(user_id, "assistant", bot_message)
        
        return jsonify({
            "response": bot_message,
            "status": "success",
            "debug_info": {
                "remembered_info": stored_info,
                "conversation_length": len(conversation)
            }
        })
        
    except requests.exceptions.HTTPError as e:
        app.logger.error(f"HTTP Error: {str(e)}")
        app.logger.error(f"Response status code: {e.response.status_code}")
        app.logger.error(f"Response text: {e.response.text}")
        return jsonify({"error": f"API Error: {e.response.status_code} - {e.response.text}"}), 500
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Request error: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({"error": f"Request failed: {str(e)}"}), 500
    except Exception as e:
        app.logger.error(f"Chat error: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)