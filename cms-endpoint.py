import socket
import threading
import logging
import time
import queue
import re

# State definitions for the state machine as strings
START = "START"
CONNECTED = "CONNECTED"
CALLSIGN_ENTRY = "CALLSIGN_ENTRY"
PASSWORD_VALIDATION = "PASSWORD_VALIDATION"
LOGIN_SUCCESS = "LOGIN_SUCCESS"
CLIENT_REQUEST = "CLIENT_REQUEST"
CLOSE_CONNECTION = "CLOSE_CONNECTION"

class Message:
    """Class to represent a message with its metadata."""
    
    def __init__(self, message_type=None, message_id=None, uncompressed_size=None, compressed_size=None):
        """Initialize the message with the necessary instance variables."""
        self.message_type = message_type  # Type of the message (e.g., proposal, etc.)
        self.message_id = message_id  # Unique identifier for the message
        self.uncompressed_size = uncompressed_size  # Uncompressed size of the message
        self.compressed_size = compressed_size  # Compressed size of the message
        self.raw_data = None  # To store the raw data received

class ConnectionHandler:
    def __init__(self, connection, address, timeout=5, enable_debug=False):
        """Initialize the connection handler and encapsulate socket handling."""
        self.connection = connection
        self.address = address
        self.timeout = timeout  # Unified timeout value for all operations
        self.enable_debug = enable_debug
        self.client_callsign = None
        self.client_password = None  # Save password as an instance variable
        self.author = None  # Instance variable for author
        self.version = None  # Instance variable for version (optional)
        self.feature_list = None  # Instance variable for feature list
        self.state = START  # Starting state
        self.next_state = START  # Next state to transition to
        self.forward_login_callsign = None  # Instance variable for forward login callsign
        self.pickup_callsigns = []  # List to store pickup callsigns as tuples
        self.message_queue = queue.Queue()  # Initialize a message queue to hold incoming messages
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        self._setup_logging()

    def _setup_logging(self):
        """Set up logging configuration."""
        log_level = logging.DEBUG if self.enable_debug else logging.INFO
        logging.basicConfig(level=log_level,
                            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        
    def _log_debug(self, message):
        """Log debug messages if debugging is enabled."""
        if self.enable_debug:
            self.logger.debug(message)

    def _log_state_change(self, new_state):
        """Log the state change."""
        self._log_debug(f"State changed from {self.state} to {new_state}")
        self.state = new_state  # Update the current state

    def handle_connection(self):
        """Main loop to handle connection and state transitions."""
        try:
            while self.state != CLOSE_CONNECTION:  # Continue processing until CLOSE_CONNECTION state is reached
                if self.state == START:
                    self._handle_start()
                elif self.state == CONNECTED:
                    self._handle_connected()
                elif self.state == CALLSIGN_ENTRY:
                    self._handle_callsign_entry()
                elif self.state == PASSWORD_VALIDATION:
                    self._handle_password_validation()
                elif self.state == LOGIN_SUCCESS:
                    self._handle_login_success()
                elif self.state == CLIENT_REQUEST:
                    self._handle_client_request()
                else:
                    self._log_debug("Unknown state")
                    break

                # Set the state to the next state after the method finishes
                self._log_state_change(self.next_state)
        except Exception as e:
            self.logger.error(f"Error during connection handling: {e}")
        finally:
            self._close_connection()

    def send_data(self, data):
        """Send data back to the client."""
        try:
            if self.connection:
                self.connection.sendall(data.encode())
                self._log_debug(f"Sent data: {data}")
        except Exception as e:
            self.logger.error(f"Error sending data: {e}")

    def wait_for_input(self, prompt):
        """Send prompt and wait for client response, terminated by a carriage return."""
        self.send_data(prompt)
        try:
            self.connection.settimeout(self.timeout)  # Set the timeout for the connection
            response = b""
            
            # Keep reading until a carriage return (\r) is encountered
            while True:
                byte = self.connection.recv(1)  # Read one byte at a time
                if not byte:
                    break  # If there's no data, stop reading
                response += byte
                if byte == b'\r':  # Carriage return indicates the end of the line
                    break

            response_str = response.decode()  # Convert bytes to a string
            response_str = response_str.rstrip("\r")  # Strip the carriage return

            # Debug: Log the received data for inspection
            self._log_debug(f"Received data: {response_str}")

            return response_str
        except socket.timeout:
            self._log_debug("Timeout occurred while waiting for input.")
            return None

    def _handle_start(self):
        """Handle the start state."""
        self._log_debug("Handling START state")
        self.state = CONNECTED  # Move to CONNECTED when starting the connection
        self.next_state = CONNECTED

    def _handle_connected(self):
        """Handle the connected state."""
        self._log_debug("Handling CONNECTED state")
        # The connection is already established, so move to CALLSIGN_ENTRY
        self.next_state = CALLSIGN_ENTRY

    def _handle_callsign_entry(self):
        """Process the callsign."""
        self._log_debug("Handling CALLSIGN_ENTRY state")
        callsign = self.wait_for_input("Callsign :\r")  # Wait for client input

        if callsign:
            print(f"Server: Received callsign: {callsign}")
            self.client_callsign = callsign  # Save the callsign
            self.next_state = PASSWORD_VALIDATION  # Move to PASSWORD_VALIDATION state
        else:
            print("Server: No valid callsign received. Closing connection.")
            self._close_connection()  # Close the connection if no valid callsign
            self.next_state = START  # Return to the START state

    def _handle_password_validation(self):
        """Process the password."""
        self._log_debug("Handling PASSWORD_VALIDATION state")
        # Prompt for password and wait for input
        password = self.wait_for_input("Password :\r")
        
        if password:
            print(f"Server: Received password: {password}")  # Print the received password
            self.client_password = password  # Save the password as an instance variable
            self.next_state = LOGIN_SUCCESS  # Move to LOGIN_SUCCESS state
        else:
            print("Server: No valid password received. Closing connection.")
            self._close_connection()  # Close the connection if no valid password
            self.next_state = START  # Return to the START state

    def _handle_login_success(self):
        """Handle successful login."""
        self._log_debug("Handling LOGIN_SUCCESS state")
        
        # Send '[AREDN_BRIDGE-1.0-B2F$]' followed by a carriage return
        self.send_data("[AREDN_BRIDGE-1.0-B2F$]\r")
        
        # Send 'CMS>' followed by a carriage return
        self.send_data("CMS>\r")
        
        print("Server: Login successful.")
        self.next_state = CLIENT_REQUEST  # Transition to CLIENT_REQUEST after login success

    def _handle_client_request(self):
        """Handle the client's request after login."""
        self._log_debug("Handling CLIENT_REQUEST state")
        request = self.wait_for_input("").rstrip("\r")  # Wait for client's request and strip trailing carriage return

        if request:
            print(f"Server: Received client request: {request}")

            if request.startswith("FC"):  # Now handle 'FC' instead of ';FC:'
                self._handle_message_proposal(request)  # Call _handle_message_proposal for FC messages
            elif request.startswith(";FW:"):
                self._handle_forward_message(request)  # Call _handle_forward_message for FW messages
            elif request.startswith(";PQ:"):
                self._handle_authentication_challenge(request)  # Call _handle_authentication_challenge for PQ messages
            elif request.startswith(";PM:"):
                self._handle_pending_message(request)  # Call _handle_pending_message for PM messages
            elif re.match(r"^\[.*\]$", request):  # Use regex to match bracketed messages
                self._parse_sid(request)  # Call _parse_sid for bracketed messages
            elif request.startswith("; "):
                self._handle_comment(request)  # Call _handle_comment for comment messages
            elif request.startswith("F>"):
                self._handle_end_of_proposal(request)  # Call _handle_end_of_proposal for F> messages
            else:
                print(f"Server: Unknown request '{request}'. Closing connection.")
                self._close_connection()  # Close connection if request type is unrecognized
                self.next_state = CLOSE_CONNECTION  # Close the connection

        else:
            print("Server: No valid request received. Closing connection.")
            self._close_connection()  # Close the connection if no valid request
            self.next_state = CLOSE_CONNECTION  # Close the connection

    def _handle_comment(self, message):
        """Handle comment messages that begin with '; '."""
        self._log_debug(f"Handling comment message: {message}")
        
        # You can process the comment here, depending on the protocol.
        # For now, it simply logs the message.
        print(f"Server: Comment received: {message}")
        
        # No need to change state, just process the comment and continue.
        # The main loop will handle the state transition.

    def _handle_forward_message(self, message):
        """Handle forward messages that begin with ';FW:'."""
        self._log_debug(f"Handling forward message: {message}")
        # Implementation for handling forward message
        # (Extract forward_login_callsign, pickup_callsigns, etc.)

    def _handle_message_proposal(self, message):
        """Handle messages that begin with 'FC'."""
        self._log_debug(f"Handling message proposal: {message}")
        # Implementation for handling message proposal
        # (Extract message metadata and queue it)

    def _handle_end_of_proposal(self, message):
        """Handle messages that begin with 'F>'."""
        self._log_debug(f"Handling end of proposal message: {message}")
        
        # Process messages in the queue in FIFO order
        try:
            while not self.message_queue.empty():
                message_instance = self.message_queue.get()  # Get the first message in the queue
                self._log_debug(f"Processing message ID: {message_instance.message_id}")
                
                # Await up to uncompressed_size bytes of data from the client
                self.send_data("Waiting for message data...\r")  # Optional prompt
                data = self._wait_for_data(message_instance.uncompressed_size)
                
                # Store the raw data in the message instance
                message_instance.raw_data = data
                
                # Send "FF" followed by a carriage return after receiving the data
                self.send_data("FF\r")
                print(f"Server: Received message data for ID: {message_instance.message_id}")
        
        except Exception as e:
            self._log_debug(f"Error handling end of proposal: {e}")
            self._close_connection()  # Close the connection in case of an error

    def _wait_for_data(self, expected_size):
        """Wait for the expected amount of data from the client with a 1-second timeout."""
        data = b""
        try:
            start_time = time.time()
            while len(data) < expected_size:
                if time.time() - start_time > 1:  # Timeout after 1 second
                    break
                chunk = self.connection.recv(1024)  # Receive up to 1024 bytes at a time
                if not chunk:
                    break
                data += chunk  # Append the received chunk
        except Exception as e:
            self._log_debug(f"Error receiving data: {e}")
        return data

    def _handle_authentication_challenge(self, message):
        """Handle messages that begin with ';PQ:' for authentication challenge."""
        self._log_debug(f"Handling authentication challenge: {message}")
        # Further handling for authentication challenge can be added here
        print(f"Server: Authentication challenge: {message}")

    def _handle_pending_message(self, message):
        """Handle messages that begin with ';PM:' for pending message."""
        self._log_debug(f"Handling pending message: {message}")
        # Further handling for pending messages can be added here
        print(f"Server: Pending message: {message}")

    def _close_connection(self):
        """Close the connection."""
        if self.connection:
            self.logger.info(f"Closing connection to {self.address}")
            self.connection.close()

    def _parse_sid(self, message):
        """Parse the message that starts with '[' and ends with ']'. Extract author, version, and feature list."""
        self._log_debug(f"Handling SID message: {message}")
        
        # Remove the brackets and split by '-'
        content = message[1:-1]  # Strip the surrounding brackets
        parts = content.split('-')
        
        if len(parts) >= 2:  # We expect at least author and feature list
            self.author = parts[0]  # First parameter is the author
            self.version = parts[1] if len(parts) > 2 else None  # Optional: Second parameter is the version (or None if missing)
            self.feature_list = parts[2] if len(parts) > 2 else parts[1]  # Third parameter is the feature list, or version if no third part

            # Log the extracted parameters for debugging
            self._log_debug(f"Author: {self.author}, Version: {self.version}, Feature List: {self.feature_list}")
        else:
            print("Server: Invalid SID format. Closing connection.")
            self._close_connection()  # Close the connection if format is incorrect
            self.next_state = CLOSE_CONNECTION  # Close the connection

class TelnetServer:
    def __init__(self, host="0.0.0.0", port=8772):
        """Initialize the server with default host and port."""
        self.host = host
        self.port = port

    def start_server(self):
        """Main listening loop that accepts new connections."""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((self.host, self.port))
        server_socket.listen(5)  # Allow up to 5 pending connections
        print(f"Server is listening on {self.host}:{self.port}")

        try:
            while True:
                # Accept a new connection
                connection, address = server_socket.accept()
                print(f"Connection established with {address}")

                # Fork a new thread to handle the connection
                handler = ConnectionHandler(connection, address, timeout=5, enable_debug=True)
                threading.Thread(target=handler.handle_connection).start()
        
        except KeyboardInterrupt:
            print("Server interrupted, shutting down...")
        finally:
            server_socket.close()

if __name__ == "__main__":
    server = TelnetServer()  # Default to host=0.0.0.0 and port=8772
    server.start_server()
