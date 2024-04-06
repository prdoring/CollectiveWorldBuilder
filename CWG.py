from flask import Flask, render_template
from flask_socketio import SocketIO, emit, join_room, leave_room
from tinydb import TinyDB, Query
from openai import OpenAI
from dotenv import load_dotenv
from collections import Counter
import json

load_dotenv()

client = OpenAI()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app)

# Initialize TinyDB and specify the database file
facts_db = TinyDB('facts_db.json')
conversations_db = TinyDB('conversations_db.json')
# Use tables for different types of data, e.g., conversations

conversations_table = conversations_db.table('conversations')
facts_table = facts_db.table('facts')


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
    initial_system_message = file.read().strip()
with open('Fact_Prompt.txt', 'r', encoding='utf-8') as file:
    fact_message = file.read().strip()

    print(initial_system_message)

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


def message_gpt(message, conversation_id):
    Conversation = Query()
    conversation = conversations_table.search(Conversation.name == conversation_id)
    context = fetch_context()
    # If the conversation does not exist in the database, initialize it
    print(conversation_id)
    if not conversation:
        conversations_table.insert({'name': conversation_id, 'messages': []})
        conversation = [{'name': conversation_id, 'messages': []}]
    
    # Extract the current conversation's message history
    messages_history = conversation[0]['messages']
    
    # Prepare messages for GPT-3 call, including history
    messages_for_gpt = [
        {"role": "system", "content": "city information DB: " + context},
        {"role": "system", "content": initial_system_message}
    ]
    messages_for_fact = [
        {"role": "system", "content": context + "\n" + fact_message}
    ]
    
    # Add history messages and the new message to the GPT call
    gpt_chat_history = []
    for msg in messages_history:
        gpt_chat_history.append({"role": msg["sender"], "content": msg["text"]})
    gpt_chat_history = gpt_chat_history[-100:]
    messages_for_gpt+=(gpt_chat_history)
    # Append the new user message
    messages_for_gpt.append({"role": "user", "content": message})
    last_message = gpt_chat_history[-1:][0].get("content")

    if(last_message):
        messages_for_fact.append({"role": "assistant", "content": last_message})
    messages_for_fact.append({"role": "user", "content": message})
    # GPT-3 call with conversation history
    print(messages_for_gpt)
    completion = client.chat.completions.create(
        model="gpt-4-0125-preview",
        messages=messages_for_gpt
    )

    fact_completion = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        response_format={"type": "json_object"},
        messages=messages_for_fact
    )

    print(completion.usage)

    # Attempt to parse the JSON string to a Python dictionary
    try:
        fact_response_json = json.loads(fact_completion.choices[0].message.content)
    except json.JSONDecodeError:
        print("Failed to decode JSON from GPT response")
        return "Error: Could not process the response from the server."
    

    response_text = completion.choices[0].message.content

    # Update the conversation history in TinyDB
    new_message = {"sender": "user", "text": message}
    gpt_message = {"sender": "assistant", "text": response_text}  # Adjust "system" to "gpt" or "server" as per your schema
    conversations_table.update({'messages': messages_history + [new_message, gpt_message]}, Conversation.name == conversation_id)

    # Handle new facts and proper nouns
    new_info = fact_response_json.get('new_info', [])
    new_proper_nouns = fact_response_json.get('new_proper_nouns', [])
    if new_info:
        print(new_info)
    if new_proper_nouns:
        print(new_proper_nouns)
    
    insert_unique_items(facts_table, new_info)
    insert_unique_items(proper_nouns_table, new_proper_nouns)

    print_facts_count_by_category()
    return response_text





@app.route('/')
def home():
    return render_template('index.html')

@socketio.on('connect')
def on_connect():
    # Emit the existing conversation names to the connected client
    existing_conversations = [{'name': conversation['name']} for conversation in conversations_table.all()]
    emit('existing_conversations', existing_conversations)

@socketio.on('create_conversation')
def handle_create_conversation(data):
    name = data['name']
    Conversation = Query()
    # Check if the conversation already exists
    if not conversations_table.search(Conversation.name == name):
        # Insert new conversation if it doesn't exist
        welcome_message = {"sender": "assistant", "text": "Hello "+name+"! Please introduce yourself, let me know who you are, what you do etc, or just say hello! \n Remember, anything you come up with in this conversation will become canon (unless it conflicts with information I allready have) if you don't want to say something wrong, you can always ask me what I know about a specific thing before responding to my question."}
        conversations_table.insert({'name': name, 'messages': [welcome_message]})
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
        res =  {'text': message_gpt(message['text'], conversation_id), 'sender': 'system'}
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
        emit('conversation_history', {'conversation_id': conversation_id, 'history': conversation[0]['messages']})
    

@socketio.on('leave_conversation')
def handle_leave_conversation(data):
    leave_room(data['conversation_id'])

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0')
