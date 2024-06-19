import threading
from apis.sqldb import clear_overview_category, insert_overview_entry, get_overview_data, get_category_fact_count, get_overview_category_fact_count
from apis.gpt import *
import json


def call_update_overview(category):
    cat_count = get_category_fact_count(category)
    # return if we are currently updating the category.
    context = fetch_context()
    taxonomy = call_update_taxonomy(category, context)
    #Clear Old Entries from the DB
    clear_overview_category(category)
    print(category + " - Overview Cleared")
    loop_taxonomy(taxonomy, taxonomy, top_category=category, context=context, cat_count=cat_count)
    print(category," Overview Updated")

def loop_taxonomy(obj, taxonomy, cat_count=0, top_category="", parent_category="", context=fetch_context()):
    if isinstance(obj, dict):
        for key, value in obj.items():
            parent_category = insert_overview_entry(key,"","","",parent_category,top_category, cat_count)
            loop_taxonomy(value, taxonomy, cat_count, top_category, parent_category, context)
    elif isinstance(obj, list):
        for item in obj:
            loop_taxonomy(item, taxonomy, cat_count, top_category, parent_category, context)
    else:
        entry = get_gpt_response(prepare_messages_for_new_overview(context, taxonomy, obj))
        insert_overview_entry(obj,"",entry,"",parent_category,top_category,cat_count)


def prepare_messages_for_new_overview(context, taxonomy, category):

    messages_for_overview = [
        {"role": "system", "content": context },
        {"role": "user", "content": "IMPORTANT! DO NOT USE MARKEDOWN, your response should only be text, without explination or formatting.  Based on the information provided and only the information provided Please provied a one paragraph entry for a wiki about "+ category + "containing information with respect to it's place in the following information taxonomy: "+json.dumps(taxonomy)}
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



