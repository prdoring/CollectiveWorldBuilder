var socket = io();

function showConfirm(button, id) {
    // Change the button text to "Confirm"
    button.textContent = 'Confirm';
    button.className = 'confirm-button';
    button.setAttribute('onclick', 'confirmDelete(this, "'+id+'")');
}

function showConfirmNoun(button, id) {
    // Change the button text to "Confirm"
    button.textContent = 'Confirm';
    button.className = 'confirm-button';
    button.setAttribute('onclick', 'confirmDeleteNoun(this, "'+id+'")');
}

function confirmDelete(button, id) {
    // Get the fact element to be deleted
    var factElement = button.closest('li');
    var factText = factElement.textContent.replace('Confirm', '').trim();
    socket.emit('delete_fact', {id:id, world_id:world});
    factElement.remove();
}

function confirmDeleteNoun(button, id) {
    // Get the fact element to be deleted
    var factElement = button.closest('li');
    var factText = factElement.textContent.replace('Confirm', '').trim();
    socket.emit('delete_noun', {id:id, world_id:world});
    factElement.remove();
}
