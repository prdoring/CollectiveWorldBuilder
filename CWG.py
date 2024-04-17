from flask import Flask, redirect, url_for, session, render_template, request
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from authlib.integrations.flask_client import OAuth
from flask_socketio import SocketIO, emit, join_room, leave_room
from tinydb import Query
from dotenv import load_dotenv
import os
import threading
from summary_creator import *
from database import *
from gpt import *


load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET')
app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.getenv('GOOGLE_CLIENT_SECRET')
app.config['GOOGLE_DISCOVERY_URL'] = (
    "https://accounts.google.com/.well-known/openid-configuration"
)

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
def user_loader(email):
    user = User()
    user.id = email
    return user

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
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


socketio = SocketIO(app)



# Read the initial system message from GPT_Prompt.txt and store it in a variable
with open('GPT_Prompt.txt', 'r', encoding='utf-8') as file:
    initial_system_message_text = file.read().strip()
with open('Fact_Prompt.txt', 'r', encoding='utf-8') as file:
    fact_message_text = file.read().strip()

# Function to count the number of entries for a specific user
def count_user_entries(user_name, table=user_facts_table):
    UserQuery = Query()
    # Search for entries where the 'user' field matches the given username
    user_entries = table.search(UserQuery.user == user_name)
    # Return the count of entries
    return len(user_entries)

def message_gpt(message, conversation_id, initial_system_message=initial_system_message_text, fact_message=fact_message_text, user_id = "system"):
    """Process and respond to a message in a conversation using GPT, including system and fact messages."""
    conversation = get_or_create_conversation(conversation_id)
    context = fetch_context()

    # request relevant history summary

    messages_history = conversation['messages']
    last_message = messages_history[-1]['text'] if messages_history else None

    message_for_relevant_history = prepare_messages_for_relevant_history(context, message, last_message)
    relevant_history = get_gpt3_response(message_for_relevant_history)
    print(relevant_history)
    messages_for_gpt = prepare_messages_for_gpt(messages_history, message, relevant_history, initial_system_message)
    messages_for_fact = prepare_messages_for_fact(context, message, last_message, fact_message)

    response_text = get_gpt_response(messages_for_gpt)

    # Call get_fact_response on a separate thread
    fact_response_thread = threading.Thread(target=call_get_fact_response, args=(messages_for_fact,user_id,))
    fact_response_thread.start()

    update_conversation_history(conversation_id, message, response_text, messages_history)
    return response_text

@app.route('/')
@login_required
def home():
    print(f"User {current_user.id} accessed the home page.")
    print("Entries For ",current_user.id, ": ", count_user_entries(current_user.id))
    return render_template('index.html')

@app.route('/overview')
@login_required
def overview():
    dat = []
    for category in categories_list:
        overviewQuery = Query()
        snc = overview_table.search(overviewQuery.category == category)
        if(snc):
            print(snc[0]['time'])
            dat.append({'data':snc[0]['data']['wikiSection'],'time':snc[0]['time']})
    return render_template('overview.html', sections=dat)

@app.route('/userfacts')
@login_required
def user_facts():
    all_facts = user_facts_table.all()
    UserQuery = Query()
    # Search for entries where the 'user' field matches the given username
    user_entries = user_facts_table.search(UserQuery.user == current_user.id)
    all_facts = user_entries
    categorized_facts = {}
    for fact in all_facts:
        category = fact['category']
        if category not in categorized_facts:
            categorized_facts[category] = []
        categorized_facts[category].append(fact['fact'])
    return render_template('userfacts.html', categorized_facts=categorized_facts)


@socketio.on('connect')
def on_connect():
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    # Emit the existing conversation names to the connected client
    User = Query()
    filtered_conversations = [conversation for conversation in conversations_table.search(User.user == current_user.id)]
    # Extract 'name' from each filtered conversation
    existing_conversations = [{'name': conversation['name']} for conversation in filtered_conversations]
    emit('existing_conversations', existing_conversations)
    emit('user_fact_count', {'count': count_user_entries(current_user.id)})

@socketio.on('create_conversation')
def handle_create_conversation(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    name = data['name']
    Conversation = Query()
    # Check if the conversation already exists
    if not conversations_table.search(Conversation.name == name):
        # Insert new conversation if it doesn't exist
        welcome_message = {"sender": "assistant", "text": "Hello "+name+"! Please introduce yourself, let me know who you are, what you do etc, or just say hello! \n Remember, anything you come up with in this conversation will become canon (unless it conflicts with information I already have) if you don't want to say something wrong, you can always ask me what I know about a specific thing before responding to my question."}
        conversations_table.insert({'name': name, 'messages': [welcome_message], 'user':current_user.id})
        emit('conversation_created_all', {'name': name}, broadcast=True)
        emit('conversation_created', {'name': name})

@socketio.on('send_message')
def handle_send_message(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    message = {'text': data['message'], 'sender': 'user'}
    conversation_id = data['conversation_id']
    Conversation = Query()
    # Append the message to the conversation's message list
    conversation = conversations_table.search(Conversation.name == conversation_id)
    if conversation:
        # Ensure there's only one conversation with the given name
        conversation = conversation[0]
        # Update the conversation record with the new message list
        emit('broadcast_message', {'conversation_id': conversation_id, 'message': message}, room=conversation_id)
        emit('user_fact_count', {'count': count_user_entries(current_user.id)})
        
        res =  {'text': message_gpt(message['text'], conversation_id, user_id = current_user.id), 'sender': 'system'}
        emit('broadcast_message', {'conversation_id': conversation_id, 'message': res}, room=conversation_id)
    
        # Optionally handle server response similarly

@socketio.on('join_conversation')
def handle_join_conversation(data):
    if not current_user.is_authenticated:
        return False  # Or handle appropriately
    conversation_id = data['conversation_id']
    join_room(conversation_id)
    Conversation = Query()
    conversation = conversations_table.search(Conversation.name == conversation_id)
    if conversation:
        # Send back the conversation's history
        emit('conversation_history', {'conversation_id': conversation_id, 'history': conversation[0]['messages'], 'user':current_user.id})
    

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
