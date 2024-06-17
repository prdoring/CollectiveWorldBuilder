from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import Flask, redirect, url_for, session, render_template, request, current_app
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from sqldb import get_user_fact_count, sql_get_or_create_conversation, get_all_proper_nouns, get_user_conversations
from gpt import get_welcome_message
from config import Config

def emit_existing_comversations(existing_conversations):
    emit('existing_conversations', existing_conversations)

def emit_user_fact_count(user_id):
    emit('user_fact_count', {'count': get_user_fact_count(user_id)})

def emit_conversation_created(name):
    emit('conversation_created', {'name': name})

def emit_broadcast_message(conversation_id, message):
    emit('broadcast_message', {'conversation_id': conversation_id, 'message': message}, room=conversation_id)

def emit_conversation_history(conversation_id, user_id):
    conversation = sql_get_or_create_conversation(conversation_id, user_id)
    if conversation:
        emit('conversation_history', {'conversation_id': conversation_id, 'history': conversation['messages'], 'user': user_id})

def emit_welcome_message():
    emit('welcome_message', {'message': get_welcome_message()})

def emit_proper_nouns():
    emit('nouns_list', {'nouns': get_all_proper_nouns()})

def on_connect_emitters(user_id):
    existing_conversations = get_user_conversations(user_id)
    # Check if any conversation has the name "DATABASE" - This is used for the non content creation talking to the DB
    has_database_conversation = any(conversation['chat_name'] == Config.DATABASE_AGENT_NAME for conversation in existing_conversations)
    if(not has_database_conversation):
        print("creating db agent")
        welcome_message = "I am an agent for you to communicate with the database without generating canon, please use me to ask anything about this world."
        sql_get_or_create_conversation(Config.DATABASE_AGENT_NAME, user_id, welcome_message)
        existing_conversations = get_user_conversations(user_id)
    emit_existing_comversations(existing_conversations)
    emit_user_fact_count(user_id)