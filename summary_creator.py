import threading
import database as db
from gpt import *

def call_update_overview(category):
    context = db.fetch_context()
    messages_for_overview = prepare_messages_for_overview(context, category)
    response_text = get_gpt_json_response(messages_for_overview)
    print(response_text)
    db.update_overview_db(category, response_text)
    print(category," Overview Updated")

def prepare_messages_for_overview(context, category=""):
    messages_for_welcome = [
        {"role": "system", "content": context },
        {"role": "user", "content": "This Wiki section is about "+ category +" "+overview_message_text}
    ]
    return messages_for_welcome

def start_update_overview(category):
    overview_response_thread = threading.Thread(target=call_update_overview, args=(category,))
    overview_response_thread.start()


