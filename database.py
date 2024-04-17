from tinydb import TinyDB, Query
from collections import Counter
from dotenv import load_dotenv
from openai import OpenAI
import json
import time
import os
import threading
import summary_creator as sc

# Initialize TinyDB and specify the database file
facts_db = TinyDB('facts_db.json')
conversations_db = TinyDB('conversations_db.json')
user_facts_db = TinyDB('user_facts_db.json')
overview_db = TinyDB('overview_db.json')
# Use tables for different types of data, e.g., conversations

conversations_table = conversations_db.table('conversations')
facts_table = facts_db.table('facts')
user_facts_table = user_facts_db.table('user_facts')
proper_nouns_table = facts_db.table('proper_nouns')
overview_table = overview_db.table('overview')
last_overview_fact_count = len(facts_table.all())
max_fact_delta_for_overview_update = 10

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

category_count = {
    "Overview":0,
    "Neighborhoods":0,
    "People":0,
    "Society and Culture":0,
    "Economy and Trade":0,
    "Law and Order":0,
    "Religion and Magic":0,
    "Infrastructure and Technology":0,
    "Outside Influences":0,
    "Other":0
}
init_category_count = category_count.copy()

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

def fetch_cat_context(category):
    CatQuery = Query()
    category_entries = user_facts_table.search(CatQuery.category == category)
    # Format as a string (customize this according to your needs)
    context = "Known Facts about "+category+":\n"
    context += "\n".join([f"{fact['category']}: {fact['fact']}" for fact in category_entries])

    return context

def insert_unique_items(table, items):
    for item in items:
        # Check if the item already exists in the table
        if not table.search(Query().data == item):
            table.insert(item)


def print_facts_count_by_category():
    """
    Fetches all facts from the database, counts the number of facts in each category,
    and prints the counts, including 0 for categories without entries.

    If the category delta is over threshold spin off category overview update.
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
        category_count[category] = count
        if(init_category_count[category] == 0):
            init_category_count[category] = count

        if(count - init_category_count[category]>max_fact_delta_for_overview_update):
            print(f"{category}: {count} - UPDATING OVERVIEW")
            sc.start_update_overview(category)
            init_category_count[category] = count
        else:
            print(f"{category}: {count}")
    return cat_counts

def update_conversation_history(conversation_id, message, response_text, messages_history):
    """Update the conversation history in the database."""
    new_message = {"sender": "user", "text": message}
    gpt_message = {"sender": "assistant", "text": response_text}
    Conversation = Query()
    conversations_table.update({'messages': messages_history + [new_message, gpt_message]}, Conversation.name == conversation_id)

def get_or_create_conversation(conversation_id):
    """Retrieve or create a new conversation in the database."""
    Conversation = Query()
    conversation = conversations_table.search(Conversation.name == conversation_id)
    if not conversation:
        conversations_table.insert({'name': conversation_id, 'messages': []})
        return {'name': conversation_id, 'messages': []}
    return conversation[0]

def update_overview_db(category, data):
    cat = Query()
    entry = overview_table.search(cat.category == category)
    if entry:
        overview_table.remove(cat.category == category)
    overview_table.insert({'category': category, 'data': data})
