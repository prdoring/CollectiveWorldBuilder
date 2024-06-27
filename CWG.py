from flask import Flask, redirect, url_for, session, render_template, request, current_app, flash
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
from apis.sqldb import (get_facts_by_user, get_user_fact_count, get_all_proper_nouns, sql_get_or_create_conversation, 
                        get_user_conversations, get_overview_data, delete_user_fact, get_nouns_by_user, delete_user_noun,
                        delete_conversation, get_users_worlds)
from util.decorators import timing_decorator
from transport.emitters import *
import requests

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.config.from_object(DevelopmentConfig if os.getenv('FLASK_ENV') == 'development' else ProductionConfig)

socketio = SocketIO(app)
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
    user.profile_photo = session.get('profile_photo')
    if not session.get('user_worlds'):
        session['user_worlds'] = get_users_worlds(user.id)
    return user

def local_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if app.config['ENV'] == 'development':
            mock_login()
        elif not current_user.is_authenticated:
            return redirect(url_for('google_login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def mock_login():
    if not current_user.is_authenticated:
        user = User()
        user.id = 'mockuser@example.com'  # Mock user ID or email
        session['profile_photo'] = "https://avatars.githubusercontent.com/u/17078488?v=4.jpg"
        session['user_worlds'] = get_users_worlds(user.id)
        user.profile_photo = "https://avatars.githubusercontent.com/u/17078488?v=4.jpg"
        login_user(user)


# Google OAuth login route
@app.route('/login')
def google_login():
    redirect_uri = url_for('authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = google.authorize_access_token()
    session['token'] = token
    resp = google.get('userinfo')
    user_info = resp.json()
    user = User()
    user.id = user_info['email']
    user.profile_photo = user_info['picture']
    login_user(user)
    session['profile_photo'] = user_info['picture']
    session['user_worlds'] = get_users_worlds(user.id)
    return redirect(url_for('home'))

@app.route('/logout')
def logout():
    token = session.get('token')  # Adjust this to the correct session key if needed
    
    # Revoke the token if it exists
    if token:
        revoke = requests.post(
            'https://accounts.google.com/o/oauth2/revoke',
            params={'token': token['access_token']},
            headers={'content-type': 'application/x-www-form-urlencoded'}
        )
    
    # Log out the user locally
    logout_user()
    
    # Clear the session
    session.clear()
    
    return render_template('logout.html')

@app.route('/')
def home():
    if not current_user.is_authenticated:
        return render_template('main.html')
    return render_template('main.html')

@app.route('/chat')
@local_login_required
def chat():
    world = request.args.get('world_id')
    if not check_world_access(world):
        return redirect(url_for('home'))


    print(f"User {current_user.id} accessed the chat page.")
    print("Entries For ",current_user.id, ": ", get_user_fact_count(current_user.id, world))

    all_proper_nouns = get_all_proper_nouns(world)

    return render_template('index.html', nouns=all_proper_nouns, world_id=world)

@app.route('/overview')
@local_login_required
def overview():   
    world = request.args.get('world_id')
    if not check_world_access(world):
        return redirect(url_for('home'))

    all_proper_nouns = get_all_proper_nouns(world)
    return render_template('overview.html', sections=get_overview_data(world), nouns=all_proper_nouns, world_id=world)

@app.route('/userfacts')
@local_login_required
def user_facts():
    world = request.args.get('world_id')
    if not check_world_access(world):
        return redirect(url_for('home'))
    
    return render_template('userfacts.html', categorized_facts=get_facts_by_user(current_user.id, world), nouns=get_nouns_by_user(current_user.id, world), world_id=world)

@app.route('/world_settings')
@local_login_required
def world_settings():
    world_id = request.args.get('world_id')
    if not check_world_admin_access(world_id):
        return redirect(url_for('home'))
    worlds = session.get("user_worlds")
    selected_world = []
    for world in worlds:
        if world['world_id'] == world_id:
            selected_world = world
    
    return render_template('world_settings.html', World=selected_world, world_id=world_id)

@app.route('/save_world_settings', methods=['POST'])
def save_world_settings():
    world_id = request.form['world_id']
    if not check_world_admin_access(world_id):
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        world_name = request.form['world_name']
        world_type = request.form['world_type']
        overview = request.form['overview']
        print(world_name)
        print(world_type)
        print(overview)
        # Assuming update_world_settings function takes these parameters and updates the database
        success = True# update_world_settings(world_name=world_name, world_type=world_type, overview=overview)
        
        if success:
            flash('World settings updated successfully!', 'success')
        else:
            flash('An error occurred while updating world settings.', 'error')
        
        return redirect(url_for('home'))



@socketio.on('connect')
def on_connect():
    if not current_user.is_authenticated:
        return False

@socketio.on('setup')
def on_setup(data):
    world_id = data['world_id']
    if not current_user.is_authenticated or not check_world_access(world_id):
        return False
    on_connect_emitters(current_user.id, world_id)

@socketio.on('create_conversation')
def handle_create_conversation(data):
    world_id = data['world_id']
    if not current_user.is_authenticated or not check_world_access(world_id):
        return False
    name = data['name']
    existing_conversations = get_user_conversations(current_user.id, world_id)
    has_convo = any(conversation['chat_name'] == name for conversation in existing_conversations)
    if(not has_convo):
        welcome_message = f"Hello {name}! Please introduce yourself, let me know who you are, what you do, etc., or just say hello! Remember, anything you come up with in this conversation will become canon (unless it conflicts with information I already have). If you don't want to say something wrong, you can always ask me what I know about a specific thing before responding to my question."
        sql_get_or_create_conversation(name, current_user.id, welcome_message, world=world_id)
        emit_conversation_created(name)

@socketio.on('send_message')
def handle_send_message(data): 
    world_id = data['world_id']
    if not current_user.is_authenticated or not check_world_access(world_id):
        return False  # Or handle appropriately
    message = {'text': data['message'], 'sender': 'user'}
    conversation_id = data['conversation_id']
    conversation = sql_get_or_create_conversation(conversation_id, current_user.id, world=world_id)
    if conversation:
        conversation = conversation
        emit_broadcast_message(conversation_id, message)
        res = {'text': message_gpt(message['text'], conversation_id, user_id=current_user.id, disable_canon=(conversation_id == database_agent_name), world=world_id), 'sender': 'system'}
        emit_broadcast_message(conversation_id, res)
        emit_user_fact_count(current_user.id, world_id)

@socketio.on('join_conversation')
def handle_join_conversation(data):
    world_id = data["world_id"]
    if not current_user.is_authenticated or not check_world_access(world_id):
        return False  # Or handle appropriately
    conversation_id = data['conversation_id']
    join_room(conversation_id)
    emit_conversation_history(conversation_id, current_user.id, world_id)

@socketio.on('leave_conversation')
def handle_leave_conversation(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    leave_room(data['conversation_id'])

@socketio.on('delete_conversation')
def handle_delete_conversation(data):
    world_id = data["world_id"]
    if not current_user.is_authenticated or not check_world_access(world_id):
        print(data["conversation_id"])
        print(current_user.id)
        print(world_id)
        print("NOT AUTHORIZED")
        return False  # Or handle appropriately
    leave_room(data['conversation_id'])
    delete_conversation(data['conversation_id'],current_user.id, world_id)

@socketio.on('request_welcome_message')
def request_welcome_message(data):
    world_id = data["world_id"]
    if not current_user.is_authenticated or not check_world_access(world_id):
        return False  # Or handle appropriately
    emit_welcome_message(world_id)

@socketio.on('request_nouns')
def request_nouns(data):
    world_id = data["world_id"]
    if not current_user.is_authenticated or not check_world_access(world_id):
        return False  # Or handle appropriately
    emit_proper_nouns(world_id)

@socketio.on('delete_fact')
def delete_fact(data):
    world_id = data["world_id"]
    if not current_user.is_authenticated or not check_world_access(world_id):
        return False  # Or handle appropriately
    delete_user_fact(current_user.id, data["id"], world_id)

@socketio.on('delete_noun')
def delete_noun(data):
    world_id = data["world_id"]
    if not current_user.is_authenticated or not check_world_access(world_id):
        return False  # Or handle appropriately
    delete_user_noun(current_user.id,data["id"],world_id)

def check_world_access(world_id):
    worlds = session.get("user_worlds")
    for world in worlds:
        if world['world_id'] == world_id:
            return True
    return False

def check_world_admin_access(world_id):
    worlds = session.get("user_worlds")
    for world in worlds:
        if world['world_id'] == world_id and world['access'] == 'admin':
            return True
    return False

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=6969)
    

