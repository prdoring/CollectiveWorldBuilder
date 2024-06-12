import threading
from tinydb import TinyDB, Query
from collections import Counter
from dotenv import load_dotenv
from openai import OpenAI
import json
import time
import os
import summary_creator as sc
from datetime import datetime

# Initialize TinyDB and specify the database file
db_lock = threading.Lock()

def init_dbs():
    facts_db = TinyDB('dbs/facts_db.json')
    conversations_db = TinyDB('dbs/conversations_db.json')
    user_facts_db = TinyDB('dbs/user_facts_db.json')
    overview_db = TinyDB('dbs/overview_db.json')

    # Use tables for different types of data, e.g., conversations
    conversations_table = conversations_db.table('conversations')
    facts_table = facts_db.table('facts')
    user_facts_table = user_facts_db.table('user_facts')
    proper_nouns_table = facts_db.table('proper_nouns')
    overview_table = overview_db.table('overview')
    
    return {
        'facts_db': facts_db,
        'conversations_db': conversations_db,
        'user_facts_db': user_facts_db,
        'overview_db': overview_db,
        'conversations_table': conversations_table,
        'facts_table': facts_table,
        'user_facts_table': user_facts_table,
        'proper_nouns_table': proper_nouns_table,
        'overview_table': overview_table
    }

dbs = init_dbs()
last_overview_fact_count = len(dbs['facts_table'].all())
max_fact_delta_for_overview_update = 5

categories_list = [
    "Overview",
    "Neighborhoods",
    "People",
    "Society and Culture",
    "Economy and Trade",
    "Law and Order",
    "Religion and Magic",
    "Infrastructure and Technology",
    "Outside Influences",
    "Other"
]

category_count = {
    "Overview": 0,
    "Neighborhoods": 0,
    "People": 0,
    "Society and Culture": 0,
    "Economy and Trade": 0,
    "Law and Order": 0,
    "Religion and Magic": 0,
    "Infrastructure and Technology": 0,
    "Outside Influences": 0,
    "Other": 0
}
init_category_count = category_count.copy()

def current_date_time():
    return datetime.now().strftime("%m/%d/%y %I:%M%p").lower()

def fetch_context():
    dbs = init_dbs()
    all_facts = dbs['facts_table'].all()
    all_proper_nouns = dbs['proper_nouns_table'].all()

    context = "Known Facts:\n"
    context += "\n".join([f"{fact['category']}: {fact['fact']}" for fact in all_facts])
    context += "\n\nKnown Proper Nouns:\n"
    context += "\n".join([f"{noun['word']}: {noun['definition']}" for noun in all_proper_nouns])

    return context

def fetch_cat_context(category):
    dbs = init_dbs()
    CatQuery = Query()
    category_entries = dbs['user_facts_table'].search(CatQuery.category == category)

    context = "Known Facts about " + category + ":\n"
    context += "\n".join([f"{fact['category']}: {fact['fact']}" for fact in category_entries])

    return context

def get_category_entry(category):
    dbs = init_dbs()
    CatQuery = Query()
    category_entries = dbs['user_facts_table'].search(CatQuery.category == category)
    return category_entries

def insert_unique_items(table, items):
    dbs = init_dbs()
    for item in items:
        if not dbs[table].search(Query().data == item):
            dbs[table].insert(item)

def print_facts_count_by_category():
    dbs = init_dbs()
    category_counts = {category: 0 for category in categories_list}
    all_facts = dbs['facts_table'].all()

    categories_in_facts = [fact['category'] for fact in all_facts if 'category' in fact]
    counted = Counter(categories_in_facts)
    category_counts.update(counted)

    print("Facts count by category:")
    cat_counts = ""
    for category, count in category_counts.items():
        cat_counts += f"{category}: {count} \n"
        category_count[category] = count
        if init_category_count[category] == 0:
            init_category_count[category] = count

        if count - init_category_count[category] > max_fact_delta_for_overview_update:
            print(f"{category}: {count} - UPDATING OVERVIEW")
            sc.start_update_overview(category)
            init_category_count[category] = count
        else:
            print(f"{category}: {count}")
    return cat_counts

def update_conversation_history(conversation_id, message, response_text, messages_history):
    dbs = init_dbs()
    new_message = {"sender": "user", "text": message}
    gpt_message = {"sender": "assistant", "text": response_text}
    Conversation = Query()
    dbs['conversations_table'].update({'messages': messages_history + [new_message, gpt_message]}, Conversation.name == conversation_id)

def get_or_create_conversation(conversation_id):
    dbs = init_dbs()
    Conversation = Query()
    conversation = dbs['conversations_table'].search(Conversation.name == conversation_id)
    if not conversation:
        dbs['conversations_table'].insert({'name': conversation_id, 'messages': []})
        return {'name': conversation_id, 'messages': []}
    return conversation[0]

def update_overview_db(category, data):
    with db_lock:
        dbs = init_dbs()
        cat = Query()
        entry = dbs['overview_table'].search(cat.category == category)
        if entry:
            dbs['overview_table'].remove(cat.category == category)
        dbs['overview_table'].insert({'category': category, 'time': current_date_time(), 'data': data})
