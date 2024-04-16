from tinydb import TinyDB, Query
from collections import Counter
from dotenv import load_dotenv
from openai import OpenAI
import json
import time
import os
import threading
from database import *
from gpt import *

def call_update_overview():
    context = fetch_context()
    messages_for_overview = prepare_messages_for_overview(context)
    response_text = get_gpt_response(messages_for_overview).replace('```html',"")
    replace_html_content(response_text)
    print("Overview Updated...")

def prepare_messages_for_overview(context):

    messages_for_welcome = [
        {"role": "system", "content": context },
        {"role": "user", "content": "Based on the information you have about this city a very detailed web page containing organized comprehensive and verbose details of everything you know about this city. Only return the raw html"}
    ]
    return messages_for_welcome

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

def replace_html_content(new_content, file_path="templates/overview.html"):
    try:
        # Write the new content to the file
        with open(file_path, 'w') as file:
            file.write(new_content)

        print("Replacement successful.")
    except Exception as e:
        print("An error occurred:", e)

