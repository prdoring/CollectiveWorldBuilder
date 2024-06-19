document.addEventListener("DOMContentLoaded", function() {

    function createTooltip(word, definition) {
        return `<span class="tooltip">${word}<span class="tooltiptext">${definition}</span></span>`;
    }

    function processNode(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            let text = node.nodeValue;
            properNouns.forEach(noun => {
                const regex = new RegExp(`\\b${noun.word}\\b`, 'g');
                text = text.replace(regex, (match) => createTooltip(match, noun.definition));
            });

            if (text !== node.nodeValue) {
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = text;
                while (tempDiv.firstChild) {
                    node.parentNode.insertBefore(tempDiv.firstChild, node);
                }
                node.parentNode.removeChild(node);
            }
        } else if (node.nodeType === Node.ELEMENT_NODE) {
            if (!node.classList.contains('tooltip') && !node.classList.contains('tooltiptext')) {
                Array.from(node.childNodes).forEach(childNode => processNode(childNode));
            }
        }
    }

    function replaceProperNouns() {
        const contentBlocks = document.querySelectorAll('.main-content, .summary, .introduction');
        contentBlocks.forEach(block => {
            Array.from(block.childNodes).forEach(childNode => processNode(childNode));
        });
    }

    replaceProperNouns();


    const toggleSwitch = document.getElementById('toggleSwitch');
    const toggleableElements = document.querySelectorAll('.subsubsectionlink');

     toggleSwitch.addEventListener('change', function() {
        toggleableElements.forEach(element => {
            if (toggleSwitch.checked) {
                element.classList.remove('hidden');
            } else {
                element.classList.add('hidden');
            }
        });
    });
});