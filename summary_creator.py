import threading
import database as db
from gpt import *

def call_update_overview(category):
    context = db.fetch_context()
    taxonomy = call_update_taxonomy(category, context)
    messages_for_overview = prepare_messages_for_overview(context, category, taxonomy)
    response_text = get_gpt_json_response(messages_for_overview)
    print(response_text)
    db.update_overview_db(category, response_text)
    print(category," Overview Updated")

def prepare_messages_for_overview(context, category="", taxonomy=""):
    messages_for_overview = [
        {"role": "system", "content": context },
        {"role": "user", "content": "This Wiki section is about "+ category +" "+overview_message_text+ "\n Use the following taxonomy to structure the information"+str(taxonomy)}
    ]
    return messages_for_overview

def start_update_overview(category):
    overview_response_thread = threading.Thread(target=call_update_overview, args=(category,))
    overview_response_thread.start()

def call_update_taxonomy(category, context):
    messages_for_taxonomy = prepare_messages_for_taxonomy(context, category)
    response_text = get_gpt_json_response(messages_for_taxonomy)
    return response_text

def prepare_messages_for_taxonomy(context, category=""):
    messages_for_tax = [
        {"role": "system", "content": context },
        {"role": "user", "content": "This Wiki section is about "+ category +" "+taxonomy_message_text}
    ]
    return messages_for_tax

def start_update_taxonomy(category):
    overview_response_thread = threading.Thread(target=call_update_taxonomy, args=(category,))
    overview_response_thread.start()



