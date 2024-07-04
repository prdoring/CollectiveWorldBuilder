var socket = io();



function updateNouns(nouns){
    properNouns = nouns;
}

function createTooltip(word, definition) {
    return `<span class="tooltip">${word}<span class="tooltiptext">${definition}</span></span>`;
}

document.getElementById('messageInput').addEventListener('keypress', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});
var currentConversationId = null;

document.getElementById('chat').addEventListener('click', function(e) {
    document.querySelector('.conversations').classList.add('collapsed');
});

document.getElementById('message-input').addEventListener('click', function(e) {
    document.querySelector('.conversations').classList.add('collapsed');
});


document.getElementById('newConversationForm').addEventListener('submit', function(e) {
    e.preventDefault();
    var name = document.getElementById('newConversationName').value.trim();
    if (name) {
        socket.emit('create_conversation', {name: name, world_id:world});
        document.getElementById('newConversationName').value = ''; // Clear input
    }
});

document.getElementById('newConversationName').addEventListener('input', function() {
    // Get the input field and button
    var input = document.getElementById('newConversationName');
    var button = document.querySelector('#newConversationForm button');

    // Disable the button if the input is empty, enable it otherwise
    button.disabled = !input.value.trim();
});

// Initially disable the button since the input is empty on load
document.querySelector('#newConversationForm button').disabled = true;


socket.on('conversation_created_all', function(data) {
    var conversationList = document.getElementById('conversationList');
    var newConversation = document.createElement('li');
    newConversation.textContent = data.name;
    newConversation.setAttribute('onclick', `joinConversation('${data.name}')`);
    newConversation.id = data.name;
    conversationList.appendChild(newConversation);
});

socket.on('conversation_created', function(data) {
    var conversationList = document.getElementById('conversationList');
    var newConversation = document.createElement('li');
    newConversation.textContent = data.name;
    newConversation.setAttribute('onclick', `joinConversation('${data.name}')`);
    newConversation.id = data.name;
    conversationList.appendChild(newConversation);
    joinConversation(data.name); // Auto-select the newly created conversation
});

socket.on('user_fact_count', function(data) {
    document.getElementById("your-contributions").innerHTML = data.count+" Contributions!";
});

socket.on('nouns_list', function(data) {
    updateNouns(data.nouns); // Auto-select the newly created conversation
});


function joinConversation(conversationId) {
    if (currentConversationId) {
        socket.emit('leave_conversation', {conversation_id: currentConversationId, world_id:world});
    }
    document.querySelectorAll('.conversations li').forEach(li => {
        li.classList.remove('active');
    });
    var selectedConversation = document.getElementById(conversationId);
    if (selectedConversation) {
        selectedConversation.classList.add('active');
    }
    currentConversationId = conversationId;
    socket.emit('join_conversation', {conversation_id: conversationId, world_id:world});
    document.getElementById('messages').innerHTML = ''; // Clear current messages
    document.getElementById('messageInput').disabled = false;
    document.querySelector('.btn.btn-primary').disabled = false;
    if(conversationId == "DATABASE") {
        document.getElementById('chatTitle').innerHTML = "<h5>DOES NOT CREATE LORE</h5>"
    } else {
        document.getElementById('chatTitle').innerHTML = "<h5>"+conversationId+"</h5>" + getDeleteButtonHtml()
    }
    document.querySelector('.conversations').classList.toggle('collapsed');
}

function deleteConversation(conversationId) {
    socket.emit('delete_conversation', {conversation_id: conversationId, world_id:world});
    currentConversationId = null;
    document.getElementById('messages').innerHTML = ''; // Clear current messages
    document.getElementById('messageInput').disabled = true;
    document.querySelector('.btn.btn-primary').disabled = true;
    document.getElementById('chatTitle').innerHTML = "";
    var element = document.getElementById(conversationId);
        if (element) {
            element.remove();
        }
    
    document.querySelector('.conversations').classList.remove('collapsed');
}

function getDeleteButtonHtml(){
    return '<button class="delete-button" onclick="showConfirm(this,\''+currentConversationId+'\')"><i class="fas fa-trash-alt"></i></button>';
}

function showConfirm(button, id) {
    // Change the button text to "Confirm"
    button.textContent = 'Confirm (Will not delete lore)';
    button.className = 'confirm-button';
    button.setAttribute('onclick', 'deleteConversation("'+id+'")');
}


function sendMessage() {
    var messageInput = document.getElementById('messageInput');
    var sendButton = document.querySelector('.btn.btn-primary');
    var message = messageInput.value.trim();
    if (!message) return;

    // Disable the message input and send button immediately after sending a message
    messageInput.disabled = true;
    sendButton.disabled = true;
    document.getElementById('typingIndicator').style.display = 'block';

    // Send the message to the server
    socket.emit('send_message', {message: message, conversation_id: currentConversationId, world_id:world});

    // Clear the message input field
    messageInput.value = '';
}

socket.on('connect', function() {
    socket.emit('setup', {world_id:world});
    // No need to do anything here for now, the server will automatically send existing conversations
});

socket.on('existing_conversations', function(conversations) {
    var conversationList = document.getElementById('conversationList');
    conversationList.innerHTML = ''; // Clear the list before adding
    conversations.forEach(function(conversation) {
        var newConversation = document.createElement('li');
        if(conversation.chat_name == "DATABASE") {
            newConversation.textContent = "Information Agent";
        } else {
            newConversation.textContent = conversation.chat_name;
        }
        
        newConversation.setAttribute('onclick', `joinConversation('${conversation.chat_name}')`);
        newConversation.id = conversation.chat_name;
        conversationList.appendChild(newConversation);
    });
});


socket.on('conversation_history', function(data) {
    var messages = document.getElementById('messages');
    messages.innerHTML = ''; // Clear existing messages
    data.history.forEach(function(message) {
        displayMessage(message); // Pass the whole message object
    });
});

socket.on('broadcast_message', function(data) {
    if (data.conversation_id === currentConversationId) {
        displayMessage(data.message); // Pass the whole message object
    }
});

socket.on('welcome_message', function(data) {
    
    if (currentConversationId==null) {
        socket.emit('request_nouns',{world_id:world});
        displayWelcomeMessage(data.message); // Pass the whole message object
        
    }
});

function displayMessage(messageData, senderOverride) {
    var messages = document.getElementById('messages');
    var wrapper = document.createElement('div');
    wrapper.classList.add('message-wrapper');

    var newMessage = document.createElement('div');
    // Adjust this line to use messageData.text
    mess_text = marked.parse(messageData.text || messageData); // Fallback to messageData if .text is not available
    properNouns.forEach(noun => {
                        const regex = new RegExp(`\\b${noun.word}\\b`, 'g');
                        mess_text = mess_text.replace(regex, (match) => createTooltip(match, noun.definition));
                    });
    
    newMessage.innerHTML = mess_text; // Fallback to messageData if .text is not available
    newMessage.classList.add('message-bubble');
    // Use senderOverride if provided, else fall back to messageData.sender
    var sender = senderOverride || messageData.sender;
    if (sender === 'user') {
        newMessage.classList.add('user-message');
    } else {
        newMessage.classList.add('server-message');
                
        // Re-enable the message input and send button
        document.getElementById('messageInput').disabled = false;
        document.querySelector('.btn.btn-primary').disabled = false;
        document.getElementById('typingIndicator').style.display = 'none';
    }

    wrapper.appendChild(newMessage);
    messages.appendChild(wrapper);
    messages.scrollTop = messages.scrollHeight;
}

function displayWelcomeMessage(message){
    var messages = document.getElementById('messages');
    var wrapper = document.createElement('div');
    wrapper.classList.add('message-wrapper');

    var newMessage = document.createElement('div');
    // Adjust this line to use messageData.text
    properNouns.forEach(noun => {
                        const regex = new RegExp(`\\b${noun.word}\\b`, 'g');
                        message = message.replace(regex, (match) => createTooltip(match, noun.definition));
                    });
    newMessage.innerHTML = message
    newMessage.classList.add('message-bubble');
    newMessage.classList.add('server-message');
    wrapper.appendChild(newMessage);
    messages.appendChild(wrapper);
    document.getElementById('typingIndicator').style.display = 'none';
}


// You might also want a function to handle leaving a conversation or when no conversation is selected
function handleNoConversationSelected() {
    document.getElementById('messageInput').disabled = true;
    document.querySelector('.btn.btn-primary').disabled = true;
}

// Initially, no conversation is selected, so inputs are disabled
handleNoConversationSelected();


document.addEventListener('DOMContentLoaded', function() {
    var hamburgerMenu = document.querySelector('.hamburger-menu');
    var conversationsSection = document.querySelector('.conversations');

    hamburgerMenu.addEventListener('click', function() {
        conversationsSection.classList.toggle('collapsed');
    });
    displayWelcomeMessage("<h2>Welcome!</h2><br/>To get started make a character and get to talking!  <br/><br/>If you are looking for inspiration wait here and you will be given a list of the top things the interviewer wants to know!<br/>")
    socket.emit('request_welcome_message',{world_id:world});
});


const messageInput = document.getElementById('messageInput');
    
    messageInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });