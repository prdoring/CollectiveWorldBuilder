import pymysql
from dotenv import load_dotenv
from openai import OpenAI
import json
import os
from decorators import timing_decorator

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

@timing_decorator
def get_embedding(text):
    # Request the embedding from the OpenAI API
    response = client.embeddings.create(
        input=text,
        model="text-embedding-3-small"  # Update to the appropriate model name if different
    )
    return response.data[0].embedding

# Establish a connection to the database
def get_db_connection():
    connection = pymysql.connect(**config)
    return connection


def add_new_fact_to_vector_db(fact):
    vector = get_embedding(fact)
    add_embedding_data(fact,vector)

# Insert data into the table
def add_embedding_data(text, embedding):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO "+vector_table+" (id, textv, vector) VALUES (UUID(), %s, JSON_ARRAY_PACK(%s))"
            cursor.execute(sql, (text, json.dumps(embedding)))
        connection.commit()
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
