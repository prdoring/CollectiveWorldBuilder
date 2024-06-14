from flask import Flask, redirect, url_for, session, render_template, request, current_app
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from authlib.integrations.flask_client import OAuth
from flask_socketio import SocketIO, emit, join_room, leave_room
from tinydb import Query
from dotenv import load_dotenv
import os
import threading
from summary_creator import *
from database import *
from gpt import *
from config import DevelopmentConfig, ProductionConfig  # Import configuration classes
from functools import wraps
from werkzeug.middleware.proxy_fix import ProxyFix
from sqldb import vector_query, get_facts_by_user, get_user_fact_count, check_for_taxonomy_update, get_all_proper_nouns, sql_get_or_create_conversation, sql_update_conversation_history, get_user_conversations
from decorators import timing_decorator

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.config.from_object(DevelopmentConfig if os.getenv('FLASK_ENV') == 'development' else ProductionConfig)

# Flask-Login setup
login_manager = LoginManager(app)
login_manager.login_view = "google_login"

# Authlib OAuth setup
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    access_token_url='https://oauth2.googleapis.com/token',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# User session management setup
class User(UserMixin):
    pass

@login_manager.user_loader
def load_user(user_id):
    user = User()
    user.id = user_id
    return user

def local_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_app.config['ENV'] == 'development':
            mock_login()
        if not current_user.is_authenticated:
            return redirect(url_for('google_login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def mock_login():
    if not current_user.is_authenticated:
        user = User()
        user.id = 'mockuser@example.com'  # Mock user ID or email
        login_user(user)


# Google OAuth login route
@app.route('/login')
def google_login():
    redirect_uri = url_for('authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = google.authorize_access_token()
    resp = google.get('userinfo')
    user_info = resp.json()
    user = User()
    user.id = user_info['email']
    login_user(user)
    return redirect(url_for('home'))

@app.route('/logout')
@local_login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

socketio = SocketIO(app)

check_for_taxonomy_update()

# Function to count the number of entries for a specific user
def count_user_entries(user_name):
    return get_user_fact_count(user_name)

@timing_decorator
def message_gpt(message, conversation_id, initial_system_message=initial_system_message_text, fact_message=fact_message_text, user_id = "system", disable_canon = True):
    """Process and respond to a message in a conversation using GPT, including system and fact messages."""
    conversation = sql_get_or_create_conversation(conversation_id, current_user.id)
    context = fetch_context()

    # request relevant history summary

    messages_history = conversation['messages']
    last_message = messages_history[-1]['text'] if messages_history else None

    relevant_history = json.dumps(vector_query(message, 25))
    messages_for_gpt = prepare_messages_for_gpt(messages_history, message, relevant_history, initial_system_message)
    messages_for_fact = prepare_messages_for_fact(context, message, last_message, fact_message)

    response_text = get_gpt_response(messages_for_gpt)

    # Call get_fact_response on a separate thread unless it is disabled
    if(not disable_canon):
        fact_response_thread = threading.Thread(target=call_get_fact_response, args=(messages_for_fact,user_id,))
        fact_response_thread.start()
    sql_update_conversation_history(conversation_id, current_user.id, message, response_text, messages_history)
    return response_text

@app.route('/')
@local_login_required
def home():
    print(f"User {current_user.id} accessed the home page.")
    print("Entries For ",current_user.id, ": ", count_user_entries(current_user.id))
    return render_template('index.html')

@app.route('/overview')
@local_login_required
def overview():
    dat = []
    for category in categories_list:
        dbs = init_dbs()
        overviewQuery = Query()
        snc = dbs["overview_table"].search(overviewQuery.category == category)
        if(snc):
            print(snc[0]['time'])
            dat.append({'data':snc[0]['data']['wikiSection'],'time':snc[0]['time']})
    
    all_proper_nouns = get_all_proper_nouns()
    unique_sorted_proper_nouns = []
    seen_words = set()
    for noun in sorted(all_proper_nouns, key=lambda x: x['word']):
        if noun['word'] not in seen_words:
            unique_sorted_proper_nouns.append(noun)
            seen_words.add(noun['word'])
            
    return render_template('overview.html', sections=dat, nouns=unique_sorted_proper_nouns)

@app.route('/userfacts')
@local_login_required
def user_facts():
    s_user_facts = get_facts_by_user(current_user.id)
    categorized_facts = {}
    for fact in s_user_facts:
        category = fact['category']
        if category not in categorized_facts:
            categorized_facts[category] = []
        categorized_facts[category].append(fact['textv'])
    
    return render_template('userfacts.html', categorized_facts=categorized_facts)

database_agent_name = "DATABASE"
@socketio.on('connect')
def on_connect():
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    
    existing_conversations = get_user_conversations(current_user.id)
    # Check if any conversation has the name "DATABASE" - This is used for the non content creation talking to the DB
    has_database_conversation = any(conversation['chat_name'] == database_agent_name for conversation in existing_conversations)
    if(not has_database_conversation):
        print("creating db agent")
        welcome_message = {"sender": "assistant", "text": f"I am an agent for you to communicate with the database without generating canon, please use me to ask anything about this world."}
        sql_get_or_create_conversation(database_agent_name, current_user.id)
        sql_update_conversation_history(database_agent_name, current_user, [],[],[welcome_message])
        existing_conversations = get_user_conversations(current_user.id)
    print(existing_conversations)
    emit('existing_conversations', existing_conversations)
    emit('user_fact_count', {'count': count_user_entries(current_user.id)})

@socketio.on('create_conversation')
def handle_create_conversation(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    name = data['name']
    existing_conversations = get_user_conversations(current_user.id)
    has_convo = any(conversation['chat_name'] == name for conversation in existing_conversations)
    if(not has_convo):
        welcome_message = {"sender": "assistant", "text": f"Hello {name}! Please introduce yourself, let me know who you are, what you do, etc., or just say hello! Remember, anything you come up with in this conversation will become canon (unless it conflicts with information I already have). If you don't want to say something wrong, you can always ask me what I know about a specific thing before responding to my question."}
        sql_get_or_create_conversation(name, current_user.id)
        sql_update_conversation_history(name, current_user, [],[],[welcome_message])
        emit('conversation_created_all', {'name': name}, broadcast=True)
        emit('conversation_created', {'name': name})

@socketio.on('send_message')
def handle_send_message(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    message = {'text': data['message'], 'sender': 'user'}
    conversation_id = data['conversation_id']
    conversation = sql_get_or_create_conversation(conversation_id, current_user.id)
    if conversation:
        conversation = conversation
        emit('broadcast_message', {'conversation_id': conversation_id, 'message': message}, room=conversation_id)
        res = {'text': message_gpt(message['text'], conversation_id, user_id=current_user.id, disable_canon=(conversation_id == database_agent_name)), 'sender': 'system'}
        emit('broadcast_message', {'conversation_id': conversation_id, 'message': res}, room=conversation_id)
        emit('user_fact_count', {'count': count_user_entries(current_user.id)})

@socketio.on('join_conversation')
def handle_join_conversation(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    conversation_id = data['conversation_id']
    join_room(conversation_id)

    conversation = sql_get_or_create_conversation(conversation_id, current_user.id)
    if conversation:
        emit('conversation_history', {'conversation_id': conversation_id, 'history': conversation['messages'], 'user': current_user.id})

@socketio.on('leave_conversation')
def handle_leave_conversation(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    leave_room(data['conversation_id'])

@socketio.on('request_welcome_message')
def request_welcome_message(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    context = fetch_context()
    messages_for_welcome = prepare_messages_for_welcome_message(context)
    response_text = get_gpt_response(messages_for_welcome)
    emit('welcome_message', {'message': response_text})

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=6969)
    

