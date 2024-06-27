import pymysql
from dotenv import load_dotenv
from openai import OpenAI
import json
import os
from util.decorators import timing_decorator
import util.summary_creator as sc
import uuid
import datetime
from util.config import Config

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

overview_count = {
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

def add_new_fact_to_vector_db(fact, user, category, world):
    vector = get_embedding(fact)
    add_new_fact_to_db(fact, user, category, vector, world)

def add_new_noun_to_vector_db(word, definition, userid, world):
    vector = get_embedding(word+": "+definition)
    add_new_noun_to_db(word, definition, vector, userid, world)

# Insert data into the table
def add_new_fact_to_db(text, user, category, embedding, world):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO "+vector_table+" (id, textv, vector, userid, category, world_id) VALUES (UUID(), %s, JSON_ARRAY_PACK(%s), %s, %s, %s)"
            cursor.execute(sql, (text, json.dumps(embedding), user, category, world))
        connection.commit()
    finally:
        connection.close()

# Insert data into the table
def add_new_noun_to_db(word, definition, embedding, userid, world):
    connection = get_db_connection()
    try:
         with connection.cursor() as cursor:
            # Check if the word already exists in the table
            sql_check = "SELECT id FROM proper_nouns WHERE word = %s and world_id=%s"
            cursor.execute(sql_check, (word,world))
            result = cursor.fetchone()
            
            if result:
                # If the word exists, update the entry
                sql_update = "UPDATE proper_nouns SET definition = %s, vector = JSON_ARRAY_PACK(%s) WHERE id = %s and world_id=%s"
                cursor.execute(sql_update, (definition, json.dumps(embedding), result['id'], world))
            else:
                # If the word does not exist, insert a new entry
                sql_insert = "INSERT INTO proper_nouns (id, word, definition, vector, userid, world_id) VALUES (UUID(), %s, %s, JSON_ARRAY_PACK(%s), %s, %s)"
                cursor.execute(sql_insert, (word, definition, json.dumps(embedding),userid, world))
            
            connection.commit()
    finally:
        connection.close()

def get_facts_by_user(userid, world):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT id, textv, category FROM facts_vector WHERE userid = %s and world_id=%s ORDER BY category;"
            cursor.execute(sql, (userid, world))
            result = cursor.fetchall()

            categorized_facts = {}
            for fact in result:
                category = fact['category']
                if category not in categorized_facts:
                    categorized_facts[category] = []
                categorized_facts[category].append({'id':fact['id'],'fact':fact['textv']})
            return categorized_facts
    finally:
        connection.close() 

def get_nouns_by_user(userid, world):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT id, word, definition FROM proper_nouns WHERE userid = %s and world_id=%s ORDER BY word ASC;"
            cursor.execute(sql, (userid, world))
            result = cursor.fetchall()
            return result
    finally:
        connection.close() 

def delete_user_fact(userid, factid, world):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "DELETE FROM facts_vector WHERE userid = %s AND id = %s and world_id=%s"
            cursor.execute(sql, (userid,factid,world))
            result = cursor.fetchall()
            connection.commit()
            print(f"deleted fact id: {factid}")
            check_for_taxonomy_update(world)
    finally:
        connection.close() 

def delete_user_noun(userid, nounId, world):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "DELETE FROM proper_nouns WHERE userid = %s AND id = %s and world_id=%s"
            cursor.execute(sql, (userid,nounId,world))
            result = cursor.fetchall()
            connection.commit()
            print(f"deleted noun id: {nounId}")
    finally:
        connection.close() 

def get_user_fact_count(userid, world):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT COUNT(*) FROM facts_vector WHERE userid = %s and world_id = %s;"
            cursor.execute(sql, (userid, world))
            result = cursor.fetchall()
            return result[0]['COUNT(*)']
    finally:
        connection.close() 

def get_category_fact_count(category, world):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT COUNT(*) FROM facts_vector WHERE category = %s and world_id = %s;"
            cursor.execute(sql, (category, world))
            result = cursor.fetchall()
            return result[0]['COUNT(*)']
    finally:
        connection.close() 

def get_overview_category_fact_count(category, world):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT FactCount from overview where TopCategory = %s and world_id = %s"
            cursor.execute(sql, (category, world))
            result = cursor.fetchall()
            if(result):
                return result[0]['FactCount']
            else:
                return 0
    finally:
        connection.close() 

def clear_overview_category(category, world):
    # DELETE FROM overview WHERE TopSectionId = 'specific-top-section-id';
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "DELETE FROM overview WHERE TopCategory = %s and world_id=%s"
            cursor.execute(sql, (category,world))
        connection.commit()
    finally:
        connection.close()

def insert_overview_entry(title, introduction, main_content, summary, parent_section_id, top_category, fact_count, world):
    # DELETE FROM overview WHERE TopSectionId = 'specific-top-section-id';
    new_uuid = str(uuid.uuid4())
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # SQL statement that inserts a new record and returns the new UUID
            sql = """
            INSERT INTO overview (ID, Title, Introduction, MainContent, Summary, ParentSectionID, TopCategory, FactCount, world_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            # Execute the SQL statement
            cursor.execute(sql, (new_uuid, title, introduction, main_content, summary, parent_section_id, top_category, fact_count, world))
            # Commit changes
            connection.commit()

            return new_uuid
    finally:
        # Close the connection
        connection.close()

def check_for_taxonomy_update(world):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT category, COUNT(*) FROM facts_vector WHERE category IS NOT NULL AND world_id=%s GROUP BY category;"
            cursor.execute(sql, (world))
            fact_result = cursor.fetchall()
            sql = "SELECT TopCategory, FactCount FROM overview WHERE ParentSectionID = '' AND world_id=%s;"
            cursor.execute(sql, (world))
            overview_result = cursor.fetchall()
    finally:
        connection.close()

    for row in fact_result:
        category = row['category']
        count = row['COUNT(*)']
        category_count[category] = count
    
    for row in overview_result:
        category = row['TopCategory']
        count = row['FactCount']
        overview_count[category] = count

    print(f"Facts count by category (Update at delta {Config.MAX_FACT_DELTA_FOR_OV_UPDATE}):")
    cat_counts = ""
    for category, count in category_count.items():
        ov_cat_count = overview_count[category]
        if not ov_cat_count:
            ov_cat_count = 0
        delta = abs(count - ov_cat_count)
        if delta > Config.MAX_FACT_DELTA_FOR_OV_UPDATE:
            print(f"{category}: {count} - UPDATING OVERVIEW with {(count-ov_cat_count)} new facts")
            sc.start_update_overview(category, world)
        else:
            print(f"{category}: FactDB:{count} - Overview:{ov_cat_count} (Delta: {delta})")
    return cat_counts

def get_overview_data(world):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT * FROM overview WHERE world_id = %s ORDER BY Title ASC"
            cursor.execute(sql, (world))
            result = cursor.fetchall()
            return build_overview_tree(result)
    finally:
        connection.close() 

def build_overview_tree(records):
    tree = {}
    nodes = {}

    # Create a dictionary for each record using its ID as the key
    for record in records:
        nodes[record['ID']] = {
            'ID': record['ID'],
            'Modified': record['Modified'],
            'Title': record['Title'],
            'Introduction': record['Introduction'],
            'MainContent': record['MainContent'],
            'Summary': record['Summary'],
            'ParentSectionID': record['ParentSectionID'],
            'TopCategory': record['TopCategory'],
            'FactCount': record['FactCount'],
            'children': []
        }

    # Assign children to their respective parents
    for node in nodes.values():
        parent_id = node['ParentSectionID']
        if parent_id and parent_id in nodes:
            nodes[parent_id]['children'].append(node)
        elif not parent_id:
            # If no parent ID, this is a root node
            tree[node['ID']] = node
    formatted_tree = format_tree(tree)
    return formatted_tree

def format_tree(tree):
    def format_node(node):
        # Create the formatted data structure for a single node
        formatted_node = {
            'data': {
                'sectionTitle': node['Title'],
                'sectionContent': {
                    'introduction': node['Introduction'],
                    'mainContent': node['MainContent'],
                    'summary': node['Summary']
                },
                'subsections': [format_node(child) for child in node['children']]
            },
            'time': node['Modified'].strftime("%m/%d/%y %I:%M%p")  # Adjust date format if needed
        }
        return formatted_node

    # Handle multiple root nodes (top-level sections without parents)
    formatted_output = [format_node(root) for root_id, root in tree.items()]
    return formatted_output


def get_all_proper_nouns(world):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT word, definition FROM proper_nouns WHERE world_id=%s ORDER BY word"
            cursor.execute(sql, (world))
            result = cursor.fetchall()
            return result
    finally:
        connection.close() 

def get_all_facts(world):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT textv, category FROM facts_vector WHERE world_id=%s"
            cursor.execute(sql, (world))
            result = cursor.fetchall()
            return result
    finally:
        connection.close() 

def get_user_conversations(user_id, world):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT chat_name FROM chats WHERE user = %s AND world_id=%s;"
            cursor.execute(sql, (user_id,world))
            result = cursor.fetchall()
            return result
    finally:
        connection.close()

def sql_update_conversation_history(conversation_id, user_id, message, response_text, messages_history, world):
    new_message = {"sender": "user", "text": message}
    gpt_message = {"sender": "assistant", "text": response_text}
    messages = messages_history + [new_message, gpt_message]
    
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE chats SET messages = %s WHERE chat_name = %s AND user = %s AND world_id = %s;"
            cursor.execute(sql, (json.dumps(messages), conversation_id, user_id, world))
        connection.commit()
    finally:
        connection.close()

def sql_get_or_create_conversation(conversation_id, user, initial_message="", world=""):  
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT chat_name, messages FROM chats WHERE chat_name = %s AND user = %s AND world_id = %s;"
            cursor.execute(sql,(conversation_id, user, world))
            result = cursor.fetchall()
            if not result:
                sql = "INSERT INTO chats (chat_id, chat_name, user, messages, world_id) VALUES (UUID(), %s, %s, %s, %s)"
                if(initial_message!=""):
                    initial_message = {"sender": "assistant", "text": initial_message}
                cursor.execute(sql, (conversation_id, user, json.dumps([initial_message]), world))
                connection.commit()
                return {'name': conversation_id, 'messages': []}
            else:
                return {'name': conversation_id, 'messages': json.loads(result[0]["messages"])}
    finally:
        connection.close()

def delete_conversation(conversation_id, user, world):  
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "DELETE FROM chats WHERE chat_name = %s AND user = %s AND world_id = %s"
            cursor.execute(sql, (conversation_id, user, world))
            connection.commit()
            print(f"deleted chat: {conversation_id}  {world}")
    finally:
        connection.close() 

def get_users_worlds(user_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # First query to get user worlds
            sql = "SELECT * FROM users_worlds WHERE user_id = %s;"
            cursor.execute(sql, (user_id,))
            user_worlds = cursor.fetchall()
            world_ids=[]
            # Extracting world_ids
            world_ids = [uw['world_id'] for uw in user_worlds]
            world_access = {uw['world_id']:uw['access'] for uw in user_worlds}
            # If there are no world_ids, return an empty list
            if not world_ids:
                return []

            # Second query to get worlds
            format_strings = ','.join(['%s'] * len(world_ids))
            sql = f"SELECT * FROM worlds WHERE id IN ({format_strings});"
            cursor.execute(sql, world_ids)
            worlds = cursor.fetchall()
            for world in worlds:
                world['access'] = world_access[world['id']]
            return worlds
    finally:
        connection.close()
# Query data from the table
@timing_decorator
def vector_query(text, limit, world_id):
    connection = get_db_connection()
    search_vector = json.dumps(get_embedding(text))
    try:
        with connection.cursor() as cursor:
            sql = """
            SELECT textv, dot_product(vector, JSON_ARRAY_PACK(%s)) as score
            FROM {vector_table}
            WHERE world_id = %s
            ORDER BY score DESC
            LIMIT %s;
            """.format(vector_table=vector_table)
            cursor.execute(sql, (search_vector, world_id, limit))
            result = cursor.fetchall()
            if result:
                print("Context Score Range")
                print(str(result[0]["score"])+"------>"+str(result[-1]["score"]))
            return result
    finally:
        connection.close()

