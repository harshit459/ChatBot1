document.addEventListener('DOMContentLoaded', function() {
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const chatMessages = document.getElementById('chat-messages');
    let isProcessing = false;

    // Function to add a message to the chat
    function addMessage(content, isUser = false, isThinking = false, isError = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${isUser ? 'user' : isError ? 'error' : 'bot'}`;
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        
        if (isThinking) {
            messageContent.innerHTML = `
                <div class="thinking">
                    <span class="thinking-text">Thinking</span>
                    <span class="dots">...</span>
                </div>
            `;
            messageDiv.dataset.thinking = true;
        } else {
            if (isError) {
                messageContent.innerHTML = `<div class="error-message">❌ ${content}</div>`;
            } else {
                messageContent.textContent = content;
            }
        }
        
        messageDiv.appendChild(messageContent);
        chatMessages.appendChild(messageDiv);
        
        // Scroll to the bottom
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return messageDiv;
    }

    // Remove thinking message
    function removeThinking() {
        const thinkingMsg = chatMessages.querySelector('[data-thinking="true"]');
        if (thinkingMsg) {
            thinkingMsg.remove();
        }
    }

    // Handle form submission
    chatForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        if (isProcessing) {
            return; // Prevent multiple submissions
        }
        
        const message = userInput.value.trim();
        if (!message) return;

        // Clear input and disable
        userInput.value = '';
        isProcessing = true;
        userInput.disabled = true;

        // Add user message to chat
        addMessage(message, true);
        
        // Add thinking message
        const thinkingMsg = addMessage('', false, true);

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'include',  // This is important for cookies
                body: JSON.stringify({ message: message })
            });

            if (response.status === 401) {
                // Redirect to login page if not authenticated
                window.location.href = '/login';
                return;
            }

            const data = await response.json();
            
            // Remove thinking message
            thinkingMsg.remove();

            if (response.ok) {
                // Add bot response to chat
                addMessage(data.response);
            } else {
                // Add error message with specific error if available
                const errorMessage = data.error || 'Sorry, I encountered an error. Please try again.';
                addMessage(errorMessage, false, false, true);
            }
        } catch (error) {
            // Remove thinking message
            thinkingMsg.remove();
            // Add error message
            addMessage('Network error. Please check your connection and try again.', false, false, true);
            console.error('Error:', error);
        } finally {
            // Re-enable input
            isProcessing = false;
            userInput.disabled = false;
            userInput.focus();
        }
    });

    // Add initial greeting
    addMessage('Hello! How can I help you today?');
});