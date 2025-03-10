document.addEventListener('DOMContentLoaded', function() {
    const chatMessages = document.getElementById('chat-messages');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    const confirmBtn = document.getElementById('confirm-btn') || document.querySelector('.btn-confirm');
    const cancelBtn = document.getElementById('cancel-btn') || document.querySelector('.btn-cancel');
    const msAuthBtn = document.getElementById('ms-auth-btn') || document.querySelector('button[id^="ms-auth"]');
    
    // Meeting details elements
    const meetingDate = document.getElementById('meeting-date');
    const meetingTime = document.getElementById('meeting-time');
    const meetingDuration = document.getElementById('meeting-duration');
    const meetingAttendees = document.getElementById('meeting-attendees');
    const meetingStatus = document.getElementById('meeting-status');
    
    // Authentication status
    let isAuthenticated = false;
    
    // Check authentication status on page load
    checkAuthStatus();
    
    // Initialize meeting details
    let meetingDetails = {
        date: null,
        time: null,
        duration: null,
        attendees: [],
        status: 'pending'
    };
    
    // Function to add a message to the chat
    function addMessage(text, isUser = false) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message');
        messageDiv.classList.add(isUser ? 'user-message' : 'bot-message');
        
        // Support for multi-line messages with proper formatting
        if (text.includes('\n')) {
            const formattedText = text.split('\n').map(line => {
                // Check if the line starts with a bullet point
                if (line.trim().startsWith('*')) {
                    return `<div class="list-item">${line}</div>`;
                }
                // Check for Teams meeting links
                else if (line.toLowerCase().includes('teams meeting link:')) {
                    const parts = line.split('teams meeting link:', 2);
                    const linkPart = parts[1].trim();
                    return `<div>${parts[0]}teams meeting link: <a href="${linkPart}" target="_blank">${linkPart}</a></div>`;
                }
                return `<div>${line}</div>`;
            }).join('');
            messageDiv.innerHTML = formattedText;
        } else {
            messageDiv.textContent = text;
        }
        
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    // Function to update meeting details panel
    function updateMeetingDetails(details) {
        if (meetingDate) meetingDate.textContent = details.date || 'Not specified';
        if (meetingTime) meetingTime.textContent = details.time || 'Not specified';
        if (meetingDuration) meetingDuration.textContent = details.duration || 'Not specified';
        
        // Update attendees list
        if (meetingAttendees) {
            meetingAttendees.innerHTML = '';
            if (details.attendees && details.attendees.length > 0) {
                details.attendees.forEach(attendee => {
                    const li = document.createElement('li');
                    li.textContent = attendee;
                    meetingAttendees.appendChild(li);
                });
            } else {
                const li = document.createElement('li');
                li.textContent = 'No attendees added';
                meetingAttendees.appendChild(li);
            }
        }
        
        // Update status
        if (meetingStatus) {
            meetingStatus.className = 'meeting-status';
            if (details.is_confirmed) {
                meetingStatus.classList.add('status-confirmed');
                meetingStatus.textContent = 'Confirmed';
                
                // Enable/disable buttons based on status
                if (confirmBtn) confirmBtn.disabled = true;
                if (cancelBtn) cancelBtn.disabled = false;
            } else if (details.is_cancelled) {
                meetingStatus.classList.add('status-cancelled');
                meetingStatus.textContent = 'Cancelled';
                
                // Enable/disable buttons based on status
                if (confirmBtn) confirmBtn.disabled = true;
                if (cancelBtn) cancelBtn.disabled = true;
            } else {
                meetingStatus.classList.add('status-pending');
                meetingStatus.textContent = 'Pending';
                
                // Enable/disable buttons
                const canConfirm = details.date && details.time && details.attendees && details.attendees.length > 0;
                if (confirmBtn) confirmBtn.disabled = !canConfirm;
                if (cancelBtn) cancelBtn.disabled = false;
            }
        }
        
        // If there's a Teams link, add it to the UI
        if (details.teams_link) {
            const teamsLinkDiv = document.getElementById('teams-link');
            if (teamsLinkDiv) {
                teamsLinkDiv.innerHTML = `<a href="${details.teams_link}" target="_blank">Join Teams Meeting</a>`;
            } else {
                // Create a teams link section if it doesn't exist
                const detailsContainer = meetingStatus.parentElement.parentElement;
                const teamsSection = document.createElement('div');
                teamsSection.className = 'detail-item';
                teamsSection.innerHTML = `
                    <h3>Teams Meeting</h3>
                    <div id="teams-link"><a href="${details.teams_link}" target="_blank">Join Teams Meeting</a></div>
                `;
                detailsContainer.appendChild(teamsSection);
            }
        }
    }
    
    // Function to check authentication status
    async function checkAuthStatus() {
        try {
            const response = await fetch('/api/auth/status');
            const data = await response.json();
            isAuthenticated = data.authenticated;
            
            // Update auth button text
            if (msAuthBtn) {
                msAuthBtn.textContent = isAuthenticated ? 'Disconnect from Microsoft' : 'Connect to Microsoft';
            }
        } catch (error) {
            console.error('Error checking auth status:', error);
        }
    }
    
    // Function to send message to the bot and get response
    async function sendMessage(message) {
        try {
            // Show a typing indicator
            const typingIndicator = document.createElement('div');
            typingIndicator.classList.add('message', 'bot-message', 'typing-indicator');
            typingIndicator.innerHTML = '<span></span><span></span><span></span>';
            chatMessages.appendChild(typingIndicator);
            chatMessages.scrollTop = chatMessages.scrollHeight;
            
            // Make actual API call to backend
            const response = await fetch('/api/bot', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ message })
            });
            
            // Remove typing indicator
            if (typingIndicator.parentNode) {
                chatMessages.removeChild(typingIndicator);
            }
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            // Update authentication status if provided
            if (data.is_authenticated !== undefined) {
                isAuthenticated = data.is_authenticated;
                if (msAuthBtn) {
                    msAuthBtn.textContent = isAuthenticated ? 'Disconnect from Microsoft' : 'Connect to Microsoft';
                }
            }
            
            // Update meeting details from the server response
            if (data.meeting_details) {
                meetingDetails = data.meeting_details;
                updateMeetingDetails(meetingDetails);
            }
            
            // Add bot's response to chat
            addMessage(data.response);
            
        } catch (error) {
            console.error('Error:', error);
            addMessage('Sorry, I encountered an error. Please try again.');
        }
    }
    
    // Event listener for send button
    if (sendButton) {
        sendButton.addEventListener('click', function() {
            const message = userInput.value.trim();
            if (message) {
                addMessage(message, true);
                userInput.value = '';
                sendMessage(message);
            }
        });
    }
    
    // Event listener for Enter key
    if (userInput) {
        userInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                const message = userInput.value.trim();
                if (message) {
                    addMessage(message, true);
                    userInput.value = '';
                    sendMessage(message);
                }
            }
        });
    }
    
    // Connect to Microsoft button
    if (msAuthBtn) {
        msAuthBtn.addEventListener('click', async function() {
            if (isAuthenticated) {
                // Logout
                try {
                    const response = await fetch('/api/auth/logout');
                    const data = await response.json();
                    
                    if (data.success) {
                        isAuthenticated = false;
                        msAuthBtn.textContent = 'Connect to Microsoft';
                        addMessage("You've been disconnected from Microsoft. Your calendar will no longer be updated.", true);
                    }
                } catch (error) {
                    console.error('Error logging out:', error);
                }
            } else {
                // Login
                try {
                    addMessage("Connecting to Microsoft...", true);
                    console.log("Requesting Microsoft auth URL...");
                    const response = await fetch('/connect-microsoft');
                    console.log("Response received:", response);
                    const data = await response.json();
                    console.log("Auth data:", data);
                    
                    if (data.success && data.auth_url) {
                        console.log("Auth URL received, redirecting to:", data.auth_url);
                        // Small delay to ensure logs are visible
                        setTimeout(() => {
                            window.location.href = data.auth_url;
                        }, 100);
                    } else {
                        console.error("Auth failed:", data);
                        addMessage("Sorry, there was a problem connecting to Microsoft. Please try again.");
                    }
                } catch (error) {
                    console.error('Error connecting to Microsoft:', error);
                    addMessage("Sorry, there was a problem connecting to Microsoft. Please try again.");
                }
            }
        });
    }
    
    // Confirm Meeting button
    if (confirmBtn) {
        confirmBtn.addEventListener('click', function() {
            addMessage("Confirm meeting", true);
            sendMessage("Yes, confirm the meeting");
        });
    }
    
    // Cancel Meeting button
    if (cancelBtn) {
        cancelBtn.addEventListener('click', function() {
            addMessage("Cancel meeting", true);
            sendMessage("Cancel this meeting");
        });
    }
    
    // Check for auth success or error in URL query params
    const urlParams = new URLSearchParams(window.location.search);
    const authSuccess = urlParams.get('auth');
    const authError = urlParams.get('error');
    
    if (authSuccess === 'success') {
        // Clean up the URL
        window.history.replaceState({}, document.title, '/');
        
        // Update auth status
        checkAuthStatus();
        
        // Add success message
        addMessage("✅ Successfully connected to Microsoft! Your meetings will now be added to your calendar.", true);
    } else if (authError) {
        // Clean up the URL
        window.history.replaceState({}, document.title, '/');
        
        // Add error message
        addMessage(`❌ There was a problem connecting to Microsoft: ${authError}`, true);
    }
    
    // Auto-focus the input field
    if (userInput) {
        userInput.focus();
    }
    
    // Add the initial bot greeting
    addMessage("Hello! I'm your meeting scheduling assistant. How can I help you today?");
    
    // Initialize meeting details
    updateMeetingDetails(meetingDetails);
});