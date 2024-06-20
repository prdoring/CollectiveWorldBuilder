from flask import Flask, redirect, url_for, session, render_template, request, current_app
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from authlib.integrations.flask_client import OAuth
from flask_socketio import SocketIO, emit, join_room, leave_room
from tinydb import Query
from dotenv import load_dotenv
import os
from util.summary_creator import *
from apis.gpt import *
from util.config import DevelopmentConfig, ProductionConfig  # Import configuration classes
from functools import wraps
from werkzeug.middleware.proxy_fix import ProxyFix
from apis.sqldb import (vector_query, get_facts_by_user, get_user_fact_count, check_for_taxonomy_update, 
                        get_all_proper_nouns, sql_get_or_create_conversation, sql_update_conversation_history, 
                        get_user_conversations, get_overview_data, delete_user_fact, get_nouns_by_user, delete_user_noun,
                        delete_conversation)
from util.decorators import timing_decorator
from transport.emitters import *

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.config.from_object(DevelopmentConfig if os.getenv('FLASK_ENV') == 'development' else ProductionConfig)

# Flask-Login setup
login_manager = LoginManager(app)
login_manager.login_view = "google_login"

# Authlib OAuth setup
oauth = OAuth(app)
database_agent_name = app.config["DATABASE_AGENT_NAME"]
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


@app.route('/')
@local_login_required
def home():
    print(f"User {current_user.id} accessed the home page.")
    print("Entries For ",current_user.id, ": ", get_user_fact_count(current_user.id))

    all_proper_nouns = get_all_proper_nouns()

    return render_template('index.html', nouns=all_proper_nouns)

@app.route('/overview')
@local_login_required
def overview():   
    all_proper_nouns = get_all_proper_nouns()
    return render_template('overview.html', sections=get_overview_data(), nouns=all_proper_nouns)

@app.route('/userfacts')
@local_login_required
def user_facts():
    return render_template('userfacts.html', categorized_facts=get_facts_by_user(current_user.id), nouns=get_nouns_by_user(current_user.id))

@socketio.on('connect')
def on_connect():
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    on_connect_emitters(current_user.id)

@socketio.on('create_conversation')
def handle_create_conversation(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    name = data['name']
    existing_conversations = get_user_conversations(current_user.id)
    has_convo = any(conversation['chat_name'] == name for conversation in existing_conversations)
    if(not has_convo):
        welcome_message = f"Hello {name}! Please introduce yourself, let me know who you are, what you do, etc., or just say hello! Remember, anything you come up with in this conversation will become canon (unless it conflicts with information I already have). If you don't want to say something wrong, you can always ask me what I know about a specific thing before responding to my question."
        sql_get_or_create_conversation(name, current_user.id, welcome_message)
        emit_conversation_created(name)

@socketio.on('send_message')
def handle_send_message(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    message = {'text': data['message'], 'sender': 'user'}
    conversation_id = data['conversation_id']
    conversation = sql_get_or_create_conversation(conversation_id, current_user.id)
    if conversation:
        conversation = conversation
        emit_broadcast_message(conversation_id, message)
        res = {'text': message_gpt(message['text'], conversation_id, user_id=current_user.id, disable_canon=(conversation_id == database_agent_name)), 'sender': 'system'}
        emit_broadcast_message(conversation_id, res)
        emit_user_fact_count(current_user.id)

@socketio.on('join_conversation')
def handle_join_conversation(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    conversation_id = data['conversation_id']
    join_room(conversation_id)
    emit_conversation_history(conversation_id, current_user.id)

@socketio.on('leave_conversation')
def handle_leave_conversation(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    leave_room(data['conversation_id'])

@socketio.on('delete_conversation')
def handle_delete_conversation(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    leave_room(data['conversation_id'])
    delete_conversation(data['conversation_id'], current_user.id)

@socketio.on('request_welcome_message')
def request_welcome_message(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    emit_welcome_message()

@socketio.on('request_nouns')
def request_nouns(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    emit_proper_nouns()

@socketio.on('delete_fact')
def delete_fact(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    delete_user_fact(current_user.id,data["id"])

@socketio.on('delete_noun')
def delete_noun(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    delete_user_noun(current_user.id,data["id"])

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=6969)
    

