import pymysql
from dotenv import load_dotenv
from openai import OpenAI
import json
import os
from decorators import timing_decorator
import summary_creator as sc

load_dotenv()
client = OpenAI()
vector_table = os.getenv('SQL_VECTOR_TABLE')
config = {
    'host': os.getenv('SQL_HOST'),   
    'port': 3333,                 
    'user': os.getenv('SQL_USER'),           
    'password': os.getenv('SQL_PASSWORD'),    
    'db': 'CWB',        
    'charset': 'utf8mb4',             
    'cursorclass': pymysql.cursors.DictCursor,
    'ssl': {
        'ca': 'singlestore_bundle.pem'
    }
}

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
max_fact_delta_for_overview_update = 5

# Establish a connection to the database
def get_db_connection():
    connection = pymysql.connect(**config)
    return connection

@timing_decorator
def get_embedding(text):
    # Request the embedding from the OpenAI API
    response = client.embeddings.create(
        input=text,
        model="text-embedding-3-small"  # Update to the appropriate model name if different
    )
    return response.data[0].embedding

def add_new_fact_to_vector_db(fact, user, category):
    vector = get_embedding(fact)
    add_new_fact_to_db(fact, user, category, vector)

def add_new_noun_to_vector_db(word, definition):
    vector = get_embedding(word+": "+definition)
    add_new_noun_to_db(word, definition, vector)

# Insert data into the table
def add_new_fact_to_db(text, user, category, embedding):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO "+vector_table+" (id, textv, vector, userid, category) VALUES (UUID(), %s, JSON_ARRAY_PACK(%s), %s, %s)"
            cursor.execute(sql, (text, json.dumps(embedding), user, category))
        connection.commit()
    finally:
        connection.close()

# Insert data into the table
def add_new_noun_to_db(word, definition, embedding):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO proper_nouns (id, word, definition, vector) VALUES (UUID(), %s, %s, JSON_ARRAY_PACK(%s))"
            cursor.execute(sql, (word, definition, json.dumps(embedding)))
        connection.commit()
    finally:
        connection.close()

def get_facts_by_user(userid):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT textv, category FROM facts_vector WHERE userid = %s ORDER BY category;"
            cursor.execute(sql, (userid))
            result = cursor.fetchall()

            categorized_facts = {}
            for fact in result:
                category = fact['category']
                if category not in categorized_facts:
                    categorized_facts[category] = []
                categorized_facts[category].append(fact['textv'])

            return categorized_facts
    finally:
        connection.close() 

def get_user_fact_count(userid):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT COUNT(*) FROM facts_vector WHERE userid = %s;"
            cursor.execute(sql, (userid))
            result = cursor.fetchall()
            return result[0]['COUNT(*)']
    finally:
        connection.close() 

def check_for_taxonomy_update():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT category, COUNT(*) FROM facts_vector WHERE category IS NOT NULL GROUP BY category;"
            cursor.execute(sql)
            result = cursor.fetchall()
    finally:
        connection.close()

    for row in result:
        category = row['category']
        count = row['COUNT(*)']
        category_count[category] = count

    print("Facts count by category:")
    cat_counts = ""
    for category, count in category_count.items():
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

def get_all_proper_nouns():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT word, definition FROM proper_nouns ORDER BY word"
            cursor.execute(sql)
            result = cursor.fetchall()
            return result
    finally:
        connection.close() 

def get_all_facts():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT textv, category FROM facts_vector"
            cursor.execute(sql)
            result = cursor.fetchall()
            return result
    finally:
        connection.close() 

def get_user_conversations(user_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT chat_name FROM chats WHERE user = %s;"
            cursor.execute(sql, (user_id))
            result = cursor.fetchall()
            return result
    finally:
        connection.close()

def sql_update_conversation_history(conversation_id, user_id, message, response_text, messages_history):
    new_message = {"sender": "user", "text": message}
    gpt_message = {"sender": "assistant", "text": response_text}
    messages = messages_history + [new_message, gpt_message]
    
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE chats SET messages = %s WHERE chat_name = %s AND user = %s;"
            cursor.execute(sql, (json.dumps(messages), conversation_id, user_id))
        connection.commit()
    finally:
        connection.close()

def sql_get_or_create_conversation(conversation_id, user, initial_message=""):  
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT chat_name, messages FROM chats WHERE chat_name = %s AND user = %s;"
            cursor.execute(sql,(conversation_id, user))
            result = cursor.fetchall()
            if not result:
                sql = "INSERT INTO chats (chat_id, chat_name, user, messages) VALUES (UUID(), %s, %s, %s)"
                if(initial_message!=""):
                    initial_message = {"sender": "assistant", "text": initial_message}
                cursor.execute(sql, (conversation_id, user, json.dumps([initial_message])))
                connection.commit()
                return {'name': conversation_id, 'messages': []}
            else:
                return {'name': conversation_id, 'messages': json.loads(result[0]["messages"])}
    finally:
        connection.close()

# Query data from the table
@timing_decorator
def vector_query(text, limit):
    connection = get_db_connection()
    search_vector = json.dumps(get_embedding(text))
    try:
        with connection.cursor() as cursor:
            sql = "select textv, dot_product(vector, JSON_ARRAY_PACK(%s)) as score from "+vector_table+" order by score desc limit %s;"
            cursor.execute(sql, (search_vector, limit))
            result = cursor.fetchall()
            print("Context Score Range")
            print(str(result[0]["score"])+"------>"+str(result[-1]["score"]))
            '''print("\n\n_________")
            print(text)
            print("\n_________\n")
            for row in result:
                print(row)
                print("_________")'''
            return result
    finally:
        connection.close()
