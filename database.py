import threading
from tinydb import TinyDB, Query
from datetime import datetime

# Initialize TinyDB and specify the database file
db_lock = threading.Lock()

def init_dbs():
    overview_db = TinyDB('dbs/overview_db.json')
    overview_table = overview_db.table('overview')
    
    return {
        'overview_db': overview_db,
        'overview_table': overview_table
    }

dbs = init_dbs()
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


def insert_unique_items(table, items):
    dbs = init_dbs()
    for item in items:
        if not dbs[table].search(Query().data == item):
            dbs[table].insert(item)

def update_overview_db(category, data):
    with db_lock:
        dbs = init_dbs()
        cat = Query()
        entry = dbs['overview_table'].search(cat.category == category)
        if entry:
            dbs['overview_table'].remove(cat.category == category)
        dbs['overview_table'].insert({'category': category, 'time': current_date_time(), 'data': data})
