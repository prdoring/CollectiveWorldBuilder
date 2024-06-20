var socket = io();

function showConfirm(button, id) {
    // Change the button text to "Confirm"
    button.textContent = 'Confirm';
    button.className = 'confirm-button';
    button.setAttribute('onclick', 'confirmDelete(this, "'+id+'")');
}

function confirmDelete(button, id) {
    // Get the fact element to be deleted
    var factElement = button.closest('li');
    var factText = factElement.textContent.replace('Confirm', '').trim();
    socket.emit('delete_fact', {id:id});
    // You can add an AJAX call here to delete the fact from the server
    // For example:
    // fetch('/delete_fact', {
    //     method: 'POST',
    //     body: JSON.stringify({ fact: factText }),
    //     headers: {
    //         'Content-Type': 'application/json'
    //     }
    // }).then(response => {
    //     if (response.ok) {
    //         // Remove the fact element from the DOM
    //         factElement.remove();
    //     }
    // });

    // For now, just remove the fact element from the DOM
    factElement.remove();
}
