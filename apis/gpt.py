import json
import threading

from dotenv import load_dotenv
from openai import OpenAI

from util.summary_creator import *
from util.decorators import timing_decorator

from apis.sqldb import (
    add_new_fact_to_vector_db, add_new_noun_to_vector_db, get_all_proper_nouns, 
    get_all_facts, get_or_create_conversation, update_conversation_history, 
    vector_query, check_for_taxonomy_update
)

load_dotenv()
client = OpenAI()

gpt4_model = "gpt-4o"
gpt3_model = "gpt-4o"

# Read the initial system message from GPT_Prompt.txt and store it in a variable
with open('prompts/GPT_Prompt.txt', 'r', encoding='utf-8') as file:
    initial_system_message_text = file.read().strip()
with open('prompts/Fact_Prompt.txt', 'r', encoding='utf-8') as file:
    fact_message_text = file.read().strip()
with open('prompts/Overview_Prompt.txt', 'r', encoding='utf-8') as file:
    overview_message_text = file.read().strip()
with open('prompts/Taxonomy_Prompt.txt', 'r', encoding='utf-8') as file:
    taxonomy_message_text = file.read().strip()


def get_gpt_response(messages_for_gpt):
    """Get a response from the GPT model."""
    completion = client.chat.completions.create(
        model=gpt4_model,
        messages=messages_for_gpt
    )
    return completion.choices[0].message.content

@timing_decorator
def get_gpt3_response(messages_for_gpt):
    """Get a response from the GPT model."""
    completion = client.chat.completions.create(
        model=gpt3_model,
        messages=messages_for_gpt
    )
    return completion.choices[0].message.content

def fetch_context(world):
    all_facts = get_all_facts(world)
    all_proper_nouns = get_all_proper_nouns(world)
    context = "Known Facts:\n"
    context += "\n".join([f"{fact['category']}: {fact['textv']}" for fact in all_facts])
    context += "\n\nKnown Proper Nouns:\n"
    context += "\n".join([f"{noun['word']}: {noun['definition']}" for noun in all_proper_nouns])

    return context

def call_get_fact_response(messages_for_fact, user_id, world):
    """Call get_fact_response in a separate thread."""
    fact_response_json = get_gpt_json_response(messages_for_fact)
    return process_new_information(fact_response_json, user_id, world)

def process_new_information(fact_response_json, user_id, world):
    """Process new information received from the fact response."""
    new_info = fact_response_json.get('new_info', [])
    new_proper_nouns = fact_response_json.get('new_proper_nouns', [])
    new_added = {'noun':False, 'fact': False}
    if new_info or new_proper_nouns:
        print("New Proper Nouns:", new_proper_nouns)
        for info in new_info:
            new_added["fact"] = True
            add_new_fact_to_vector_db(info["fact"], user_id, info["category"], world)
            info["user"] = user_id
        for noun in new_proper_nouns:
            add_new_noun_to_vector_db(noun["word"],noun["definition"], user_id, world)
            new_added["noun"] = True
        
        print("New Info:", new_info)
        check_for_taxonomy_update(world)
    return new_added

def get_gpt_json_response(messages_for_fact):
    """Get a response from the GPT model focused on facts."""
    fact_completion = client.chat.completions.create(
        model=gpt4_model,
        response_format={"type": "json_object"},
        messages=messages_for_fact
    )
    try:
        return json.loads(fact_completion.choices[0].message.content)
    except json.JSONDecodeError:
        print("Failed to decode JSON from GPT response")
        return {"error": "Could not process the response from the server."}
    
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

def get_welcome_message(world):
    context = fetch_context(world)
    messages_for_welcome = prepare_messages_for_welcome_message(context)
    response_text = get_gpt_response(messages_for_welcome)
    return response_text

def message_gpt(message, conversation_id, initial_system_message=initial_system_message_text, fact_message=fact_message_text, user_id = "system", disable_canon = True, world=""):
    """Process and respond to a message in a conversation using GPT, including system and fact messages."""
    conversation = get_or_create_conversation(conversation_id, user_id, world=world)
    context = fetch_context(world)

    # request relevant history summary

    messages_history = conversation['messages']
    last_message = messages_history[-1]['text'] if messages_history else None

    relevant_history = json.dumps(vector_query(message, 35, world))
    messages_for_gpt = prepare_messages_for_gpt(messages_history, message, relevant_history, initial_system_message)
    messages_for_fact = prepare_messages_for_fact(context, message, last_message, fact_message)

    response_text = get_gpt_response(messages_for_gpt)

    # Call get_fact_response on a separate thread unless it is disabled
    if(not disable_canon):
        fact_response_thread = threading.Thread(target=call_get_fact_response, args=(messages_for_fact,user_id, world))
        fact_response_thread.start()
    update_conversation_history(conversation_id, user_id, message, response_text, messages_history, world)
    return response_text
