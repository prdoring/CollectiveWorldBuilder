from dotenv import load_dotenv
from openai import OpenAI
import json
import time
from database import *
from summary_creator import *

load_dotenv()
client = OpenAI()

# Read the initial system message from GPT_Prompt.txt and store it in a variable
with open('GPT_Prompt.txt', 'r', encoding='utf-8') as file:
    initial_system_message_text = file.read().strip()
with open('Fact_Prompt.txt', 'r', encoding='utf-8') as file:
    fact_message_text = file.read().strip()
with open('Overview_Prompt.txt', 'r', encoding='utf-8') as file:
    overview_message_text = file.read().strip()


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
    fact_response_json = get_gpt_json_response(messages_for_fact)
    process_new_information(fact_response_json, user_id)

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
        #start_update_overview()

def get_gpt_json_response(messages_for_fact):
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