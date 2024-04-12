from flask import Flask, redirect, url_for, session, render_template_string, render_template, request
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from authlib.integrations.flask_client import OAuth
from flask_socketio import SocketIO, emit, join_room, leave_room
from tinydb import TinyDB, Query
from collections import Counter
from dotenv import load_dotenv
from openai import OpenAI
import json
import time
import os
import threading


load_dotenv()

client = OpenAI()
print(os.getenv('OPENAI_API_KEY'))
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

# Initialize TinyDB and specify the database file
facts_db = TinyDB('facts_db.json')
conversations_db = TinyDB('conversations_db.json')
user_facts_db = TinyDB('user_facts_db.json')
# Use tables for different types of data, e.g., conversations

conversations_table = conversations_db.table('conversations')
facts_table = facts_db.table('facts')
user_facts_table = user_facts_db.table('user_facts')
last_overview_fact_count = len(facts_table.all())
max_fact_delta_for_overview_update = 20

print("Current Fact Count: ", last_overview_fact_count)

categories_list = [
    "Overview",
    "Neighborhoods",
    "People",
    "Society and Culture",
    "Economy and Trade",
    "Law and Order",
    "Religion and Magic",
    "Infrastructure and Technology",
    "Outside Influences"
]

proper_nouns_table = facts_db.table('proper_nouns')

# Read the initial system message from GPT_Prompt.txt and store it in a variable
with open('GPT_Prompt.txt', 'r', encoding='utf-8') as file:
    initial_system_message_text = file.read().strip()
with open('Fact_Prompt.txt', 'r', encoding='utf-8') as file:
    fact_message_text = file.read().strip()


def print_facts_count_by_category():
    """
    Fetches all facts from the database, counts the number of facts in each category,
    and prints the counts, including 0 for categories without entries.
    """
    # Initialize counts for all categories to 0
    category_counts = {category: 0 for category in categories_list}
    
    # Fetch all facts from the database
    all_facts = facts_table.all()
    
    # Count facts by category found in the database
    categories_in_facts = [fact['category'] for fact in all_facts if 'category' in fact]
    counted = Counter(categories_in_facts)
    
    # Update the initialized counts with actual counts from the database
    category_counts.update(counted)
    
    # Print the count of facts for each category
    print("Facts count by category:")
    cat_counts = ""
    for category, count in category_counts.items():
        cat_counts += f"{category}: {count} \n"
        print(f"{category}: {count}")
    return cat_counts

def fetch_context():
    # Fetch all records
    all_facts = facts_table.all()
    all_proper_nouns = proper_nouns_table.all()

    # Format as a string (customize this according to your needs)
    context = "Known Facts:\n"
    context += "\n".join([f"{fact['category']}: {fact['fact']}" for fact in all_facts])
    context += "\n\nKnown Proper Nouns:\n"
    context += "\n".join([f"{noun['word']}: {noun['definition']}" for noun in all_proper_nouns])

    return context

def insert_unique_items(table, items):
    for item in items:
        # Check if the item already exists in the table
        if not table.search(Query().data == item):
            table.insert(item)


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
    print("messagegpt:"+user_id)
    fact_response_thread = threading.Thread(target=call_get_fact_response, args=(messages_for_fact,user_id,))
    fact_response_thread.start()

    update_conversation_history(conversation_id, message, response_text, messages_history)
    print_facts_count_by_category()
    return response_text

def get_or_create_conversation(conversation_id):
    """Retrieve or create a new conversation in the database."""
    Conversation = Query()
    conversation = conversations_table.search(Conversation.name == conversation_id)
    if not conversation:
        conversations_table.insert({'name': conversation_id, 'messages': []})
        return {'name': conversation_id, 'messages': []}
    return conversation[0]

def prepare_messages_for_gpt(messages_history, message, context, initial_system_message):
    """Prepare the messages for the GPT model, including system messages."""
    gpt_chat_history = [{"role": msg["sender"], "content": msg["text"]} for msg in messages_history][-100:]
    messages_for_gpt = [
        {"role": "system", "content": "city information DB: " + context},
        {"role": "system", "content": initial_system_message}
    ] + gpt_chat_history + [{"role": "user", "content": message}]
    return messages_for_gpt

def prepare_messages_for_fact(context, message, last_message, fact_message):
    """Prepare messages for fetching facts, including the last assistant message and the new user message."""
    messages_for_fact = [
        {"role": "system", "content": context + "\n" + fact_message},
        {"role": "user", "content": message}
    ]
    if last_message:
        messages_for_fact.insert(1, {"role": "assistant", "content": last_message})
    return messages_for_fact

def prepare_messages_for_relevant_history(context, message, last_message):
    """Prepare messages for fetching facts, including the last assistant message and the new user message."""

    com_string = "Interviewee: '" + message + "'"
    if last_message:
        com_string = "Interviewer: '" + last_message + "' " + com_string

    messages_for_history = [
        {"role": "system", "content": context },
        {"role": "user", "content": "based on the following exchange, please give a summary of any relevant information from your facts data or proper nouns that would help the interviewer in responding. \n"+com_string}
    ]
    return messages_for_history

def prepare_messages_for_welcome_message(context):

    messages_for_welcome = [
        {"role": "system", "content": context },
        {"role": "user", "content": "if you were an interviewer with this database of information can you give me a list of 5 topics in which you want to gather more information?  please respond in a UL html with no additional characters"}
    ]
    return messages_for_welcome

def prepare_messages_for_overview(context):

    messages_for_welcome = [
        {"role": "system", "content": context },
        {"role": "user", "content": "Based on the information you have about this city a very detailed web page containing organized comprehensive and verbose details of everything you know about this city. Only return the raw html"}
    ]
    return messages_for_welcome

def call_update_overview():
    context = fetch_context()
    messages_for_overview = prepare_messages_for_overview(context)
    response_text = get_gpt_response(messages_for_overview).replace('```html',"")
    replace_html_content(response_text)
    print("Overview Updated...")

def get_gpt_response(messages_for_gpt):
    """Get a response from the GPT model."""
    completion = client.chat.completions.create(
        model="gpt-4-0125-preview",
        messages=messages_for_gpt
    )
    print(completion.usage)
    return completion.choices[0].message.content

def get_gpt3_response(messages_for_gpt):
    """Get a response from the GPT model."""
    completion = client.chat.completions.create(
        model="gpt-3.5-turbo-0125",
        messages=messages_for_gpt
    )
    print(completion.usage)
    return completion.choices[0].message.content

def call_get_fact_response(messages_for_fact, user_id):
    """Call get_fact_response in a separate thread."""
    fact_response_json = get_fact_response(messages_for_fact)
    print("CGFR: "+ user_id)
    process_new_information(fact_response_json, user_id)

def get_fact_response(messages_for_fact):
    """Get a response from the GPT model focused on facts."""
    fact_completion = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        response_format={"type": "json_object"},
        messages=messages_for_fact
    )
    try:
        return json.loads(fact_completion.choices[0].message.content)
    except json.JSONDecodeError:
        print("Failed to decode JSON from GPT response")
        return {"error": "Could not process the response from the server."}

def update_conversation_history(conversation_id, message, response_text, messages_history):
    """Update the conversation history in the database."""
    new_message = {"sender": "user", "text": message}
    gpt_message = {"sender": "assistant", "text": response_text}
    Conversation = Query()
    conversations_table.update({'messages': messages_history + [new_message, gpt_message]}, Conversation.name == conversation_id)


def process_new_information(fact_response_json, user_id):
    """Process new information received from the fact response."""
    new_info = fact_response_json.get('new_info', [])
    new_proper_nouns = fact_response_json.get('new_proper_nouns', [])
    if new_info or new_proper_nouns:
        print("New Proper Nouns:", new_proper_nouns)
        insert_unique_items(facts_table, new_info)
        for info in new_info:
            info["user"] = user_id
        
        print("New Info:", new_info)
        insert_unique_items(user_facts_table, new_info)
        insert_unique_items(proper_nouns_table, new_proper_nouns)
        start_update_overview()


@app.route('/')
@login_required
def home():
    print(f"User {current_user.id} accessed the home page.")
    return render_template('index.html')

@app.route('/overview')
def overview():
    return render_template('overview.html')

@socketio.on('connect')
def on_connect():
    # Emit the existing conversation names to the connected client
    User = Query()
    filtered_conversations = [conversation for conversation in conversations_table.search(User.user == current_user.id)]
    # Extract 'name' from each filtered conversation
    existing_conversations = [{'name': conversation['name']} for conversation in filtered_conversations]
    emit('existing_conversations', existing_conversations)

@socketio.on('create_conversation')
def handle_create_conversation(data):
    name = data['name']
    Conversation = Query()
    # Check if the conversation already exists
    if not conversations_table.search(Conversation.name == name):
        # Insert new conversation if it doesn't exist
        welcome_message = {"sender": "assistant", "text": "Hello "+name+"! Please introduce yourself, let me know who you are, what you do etc, or just say hello! \n Remember, anything you come up with in this conversation will become canon (unless it conflicts with information I already have) if you don't want to say something wrong, you can always ask me what I know about a specific thing before responding to my question."}
        conversations_table.insert({'name': name, 'messages': [welcome_message], 'user':current_user.id})
        print(name)
        emit('conversation_created_all', {'name': name}, broadcast=True)
        emit('conversation_created', {'name': name})

@socketio.on('send_message')
def handle_send_message(data):
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
        print("handle Send: "+ data["user_id"])
        res =  {'text': message_gpt(message['text'], conversation_id, user_id = data["user_id"]), 'sender': 'system'}
        emit('broadcast_message', {'conversation_id': conversation_id, 'message': res}, room=conversation_id)

        # Optionally handle server response similarly



@socketio.on('join_conversation')
def handle_join_conversation(data):
    conversation_id = data['conversation_id']
    join_room(conversation_id)
    Conversation = Query()
    conversation = conversations_table.search(Conversation.name == conversation_id)
    if conversation:
        # Send back the conversation's history
        emit('conversation_history', {'conversation_id': conversation_id, 'history': conversation[0]['messages'], 'user':current_user.id})
    

@socketio.on('leave_conversation')
def handle_leave_conversation(data):
    leave_room(data['conversation_id'])

@socketio.on('request_welcome_message')
def request_welcome_message(data):
     context = fetch_context()
     messages_for_welcome = prepare_messages_for_welcome_message(context)
     response_text = get_gpt_response(messages_for_welcome)
     emit('welcome_message', {'message': response_text})

def file_not_modified_for_hour(file_path="templates/overview.html"):
    # Check if the file exists
    if not os.path.exists(file_path):
        return True
    # Get the modification time of the file
    modification_time = os.path.getmtime(file_path)

    # Get the current time
    current_time = time.time()

    # Calculate the time difference in seconds
    time_difference = current_time - modification_time

    # Check if the file hasn't been modified for over an hour (3600 seconds)
    if time_difference > 3600:
        return True
    else:
        return False

def replace_html_content(new_content, file_path="templates/overview.html"):
    try:
        # Write the new content to the file
        with open(file_path, 'w') as file:
            file.write(new_content)

        print("Replacement successful.")
    except Exception as e:
        print("An error occurred:", e)

def update_overview():
    context = fetch_context()
    messages_for_overview = prepare_messages_for_overview(context)
    response_text = get_gpt_response(messages_for_overview).replace('```html',"")
    replace_html_content(response_text)

def start_update_overview():
    if(len(facts_table.all())-last_overview_fact_count > max_fact_delta_for_overview_update):
        print("Updating Overview Page")
        # Call get_fact_response on a separate thread
        overview_response_thread = threading.Thread(target=call_update_overview)
        overview_response_thread.start()
    else:
        print("No overview Update Needed")

start_update_overview()

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0')
