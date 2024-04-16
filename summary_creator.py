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
    for category in categories_list:
        messages_for_overview = prepare_messages_for_overview(context, category)
        response_text = get_gpt_json_response(messages_for_overview)
        print(response_text)
        #replace_html_content(response_text)
        update_overview_db(category, response_text)
    print("Overview Updated...")

def prepare_messages_for_overview(context, category=""):

    messages_for_welcome = [
        {"role": "system", "content": context },
        {"role": "user", "content": "This Wiki section is about "+ category +" "+overview_message_text}
    ]
    return messages_for_welcome

def update_overview():
    context = fetch_cat_context("Neighborhoods")
    messages_for_overview = prepare_messages_for_overview(context,"Neighborhoods")
    response_text = get_gpt_json_response(messages_for_overview)
    #print(response_text)
    #replace_html_content(response_text)

def start_update_overview():
    #TODO: with the more comprehensive update logic, we should base updates on category deltas... Turned off for now.
    if(False):#len(facts_table.all())-last_overview_fact_count > max_fact_delta_for_overview_update):
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

