from flask import Flask, request, jsonify, send_from_directory, redirect, url_for, session
import os
import sys
from dotenv import load_dotenv
import logging
import secrets

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Add the project root to the path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the bot and Microsoft Graph extensions
from bot.conversation import MeetingSchedulerBot
from bot_extensions import MeetingSchedulerWithGraphAPI

# Create Flask app with explicit static folder and url path
app = Flask(__name__, static_folder='static', static_url_path='')

# Set a secret key for session management
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(16))

# Initialize the bot
model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models', 'saved')
intent_model_path = os.path.join(model_dir, 'intent_model.pt')
entity_model_path = os.path.join(model_dir, 'entity_model.pt')

# Check if model files exist
if not os.path.exists(intent_model_path) or not os.path.exists(entity_model_path):
    logger.warning("Model files not found at specified paths, using default paths instead.")
    intent_model_path = 'models/saved/intent_model.pt'
    entity_model_path = 'models/saved/entity_model.pt'

# Initialize the bot
bot = MeetingSchedulerBot(
    intent_model_path=intent_model_path,
    entity_model_path=entity_model_path
)

# Initialize Microsoft Graph integration
graph_integration = MeetingSchedulerWithGraphAPI()

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/bot', methods=['POST'])
def process_message():
    data = request.json
    if not data or 'message' not in data:
        return jsonify({'error': 'No message provided'}), 400
    
    message = data['message']
    response = bot.process_message(message)
    
    # Get current meeting state
    meeting_state = bot.get_current_meeting_state()
    
    # Debug logging
    logger.info(f"DEBUG: Current session info: {session}")
    logger.info(f"DEBUG: User authenticated: {'user_id' in session}")
    if 'user_id' in session:
        logger.info(f"DEBUG: User ID from session: {session.get('user_id')}")
    
    # If meeting is confirmed and we need to schedule in Microsoft Calendar
    if meeting_state.get('is_confirmed', False) and not meeting_state.get('graph_scheduled', False):
        try:
            # Check if user is authenticated
            user_id = session.get('user_id')
            logger.info(f"DEBUG: Using user_id from session for scheduling: {user_id}")
            
            if user_id:
                # Get the current meeting context
                meeting_context = bot.state.get_current_meeting()
                logger.info(f"DEBUG: Meeting context for scheduling: {meeting_context.to_dict()}")
                
                # Schedule the meeting in Microsoft Graph
                result = graph_integration.schedule_meeting(meeting_context, user_id)
                logger.info(f"DEBUG: Schedule meeting result: {result}")
                
                if result['success']:
                    # Update meeting state with Graph API information
                    meeting_state['graph_scheduled'] = True
                    meeting_state['graph_meeting_id'] = result.get('meeting_id')
                    
                    # Safely extract Teams link if available
                    online_meeting = result.get('response', {}).get('onlineMeeting')
                    if online_meeting and 'joinUrl' in online_meeting:
                        meeting_state['teams_link'] = online_meeting.get('joinUrl')
                        # Add Teams meeting link to response if available
                        response += f"\n\nTeams meeting link: {meeting_state['teams_link']}"
                    else:
                        # Regular meeting created but no Teams link
                        logger.info("Meeting created successfully but no Teams link available")
                        meeting_state['teams_link'] = None
                        response += "\n\nMeeting has been added to your calendar."
                else:
                    logger.error(f"Failed to schedule meeting in Microsoft Graph: {result.get('error')}")
                    
                    # If there was an error but it's authentication related, suggest login
                    if "token" in str(result.get('error')).lower() or "auth" in str(result.get('error')).lower():
                        response += "\n\nI couldn't create the Microsoft Teams meeting. Please click 'Connect to Microsoft' to authorize calendar access."
            else:
                # User not authenticated, add login message
                response += "\n\nTo create this meeting in your Microsoft calendar, please click 'Connect to Microsoft' to authorize access."
        except Exception as e:
            logger.error(f"Error scheduling meeting in Microsoft Graph: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    # If meeting is cancelled and it was scheduled in Graph
    elif meeting_state.get('is_cancelled', False) and meeting_state.get('graph_scheduled', False):
        try:
            # Check if user is authenticated
            user_id = session.get('user_id')
            
            if user_id:
                # Get the current meeting context
                meeting_context = bot.state.get_current_meeting()
                
                # Cancel the meeting in Microsoft Graph
                result = graph_integration.cancel_meeting(meeting_context)
                
                if result['success']:
                    meeting_state['graph_scheduled'] = False
                    meeting_state['graph_meeting_id'] = None
                    meeting_state['teams_link'] = None
                else:
                    logger.error(f"Failed to cancel meeting in Microsoft Graph: {result.get('error')}")
            else:
                # User not authenticated, add login message
                response += "\n\nTo cancel this meeting in your Microsoft calendar, please click 'Connect to Microsoft' to authorize access."
        except Exception as e:
            logger.error(f"Error cancelling meeting in Microsoft Graph: {str(e)}")
    
    return jsonify({
        'response': response,
        'meeting_details': meeting_state,
        'is_authenticated': 'user_id' in session
    })

@app.route('/connect-microsoft')
def connect_microsoft():
    """Initiate Microsoft authentication flow"""
    try:
        print("Generating auth URL...")
        # Generate the authorization URL with PKCE
        auth_url, state, code_verifier = graph_integration.get_auth_url()
        
        # Store the state and code_verifier in session for CSRF and PKCE
        session['oauth_state'] = state
        session['code_verifier'] = code_verifier
        
        print(f"Generated auth URL: {auth_url}")
        print(f"State: {state}")
        print(f"Code verifier (length): {len(code_verifier)}")
        print(f"Session after storing state: {session}")
        
        # Return the auth URL - the frontend will redirect to this URL
        return jsonify({
            'success': True,
            'auth_url': auth_url
        })
    except Exception as e:
        logger.error(f"Error initiating Microsoft auth: {str(e)}")
        print(f"Detailed auth error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/auth/callback')
def auth_callback():
    """Handle callback from Microsoft authentication"""
    try:
        print("inside callback")
        # Get the code and state from query parameters
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        error_description = request.args.get('error_description')
        
        # Print all query parameters for debugging
        print(f"Auth callback query parameters: {dict(request.args)}")
        print(f"Current session: {session}")
        
        # Check if there was an error
        if error:
            logger.error(f"Auth error: {error} - {error_description}")
            return redirect(f"/?error={error}")
        
        # Verify state to prevent CSRF attacks
        if state != session.get('oauth_state'):
            print(f"State mismatch: {state} vs {session.get('oauth_state')}")
            return redirect('/?error=invalid_state')
        
        # Get the code_verifier from session (may not be used in this flow)
        code_verifier = session.get('code_verifier', 'not_used_in_this_flow')
        
        # Exchange code for token
        result = graph_integration.handle_auth_callback(code, code_verifier)
        print(f"Token exchange result: {result}")
        
        if result.get('success'):
            # Store user ID in session
            session['user_id'] = result['user_id']
            return redirect('/?auth=success')
        else:
            logger.error(f"Auth error: {result.get('error')} - {result.get('error_description')}")
            return redirect(f"/?error={result.get('error')}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Error in auth callback: {str(e)}")
        return redirect(f"/?error={str(e)}")

@app.route('/api/auth/status')
def auth_status():
    """Check if user is authenticated"""
    return jsonify({
        'authenticated': 'user_id' in session,
        'user_id': session.get('user_id')
    })

@app.route('/api/auth/logout')
def logout():
    """Log the user out by clearing the session"""
    session.clear()
    return jsonify({
        'success': True
    })

# Add explicit routes for static files to ensure they're correctly found
@app.route('/styles.css')
def serve_css():
    return send_from_directory('static', 'styles.css')

@app.route('/script.js')
def serve_js():
    return send_from_directory('static', 'script.js')

if __name__ == '__main__':
    # Create static directory if it doesn't exist
    if not os.path.exists('static'):
        os.makedirs('static')
        print("Created static directory")
    
    # Check if the static files exist, show warning if not
    css_path = os.path.join('static', 'styles.css')
    js_path = os.path.join('static', 'script.js')
    html_path = os.path.join('static', 'index.html')
    
    if not os.path.exists(css_path):
        print(f"WARNING: CSS file not found at {css_path}")
    
    if not os.path.exists(js_path):
        print(f"WARNING: JavaScript file not found at {js_path}")
    
    if not os.path.exists(html_path):
        print(f"WARNING: HTML file not found at {html_path}")
    
    print("Starting Flask server...")
    app.run(debug=True)