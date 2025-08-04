import os
import datetime
import base64
import zlib
import socket
import threading
import logging
import time
import queue
import re  # Import re for regular expressions

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
            # Ensure the connection is closed at the end of the method
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
            self.client_callsign = callsign  # Save the callsign
            self.next_state = PASSWORD_VALIDATION  # Move to PASSWORD_VALIDATION state
        else:
            self.next_state = START  # Return to the START state

    def _handle_password_validation(self):
        """Process the password."""
        self._log_debug("Handling PASSWORD_VALIDATION state")
        # Prompt for password and wait for input
        password = self.wait_for_input("Password :\r")
        
        if password:
            self.client_password = password  # Save the password as an instance variable
            self.next_state = LOGIN_SUCCESS  # Move to LOGIN_SUCCESS state
        else:
            self.next_state = START  # Return to the START state

    def _handle_login_success(self):
        """Handle successful login."""
        self._log_debug("Handling LOGIN_SUCCESS state")
        
        # Send '[AREDN_BRIDGE-1.0-B2F$]' followed by a carriage return
        self.send_data("[AREDN_BRIDGE-1.0-B2F$]\r")
        
        # Send 'CMS>' followed by a carriage return
        self.send_data("CMS>\r")
        
        self.next_state = CLIENT_REQUEST  # Transition to CLIENT_REQUEST after login success

    def _handle_client_request(self):
        """Handle the client's request after login."""
        self._log_debug("Handling CLIENT_REQUEST state")
        request = self.wait_for_input("").rstrip("\r")  # Wait for client's request and strip trailing carriage return

        if request:
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
            elif request.startswith("FF"):  # Handle FF messages
                self._handle_no_messages(request)  # Call _handle_no_messages for FF messages
            else:
                self.next_state = CLOSE_CONNECTION  # Close connection if request type is unrecognized

        else:
            self.next_state = CLOSE_CONNECTION  # Close the connection if no valid request

    def _handle_comment(self, message):
        """Handle comment messages that begin with '; '."""
        self._log_debug(f"Handling comment message: {message}")
        
        # Simply process the comment and continue without state change.
        self._log_debug(f"Comment received: {message}")

    def _handle_forward_message(self, message):
        """Handle forward messages that begin with ';FW:'."""
        self._log_debug(f"Handling forward message: {message}")
        # Implementation for handling forward message
        # (Extract forward_login_callsign, pickup_callsigns, etc.)

    def _handle_message_proposal(self, message):
        """Handle messages that begin with 'FC'."""
        self._log_debug(f"Handling message proposal: {message}")
        
        # Extracting message type, message ID, uncompressed size, and compressed size
        parts = message.split()
        if len(parts) >= 5:
            message_type = parts[1]
            message_id = parts[2]
            uncompressed_size = int(parts[3])
            compressed_size = int(parts[4])

            # Create a new Message instance with the extracted data
            new_message = Message(message_type, message_id, uncompressed_size, compressed_size)

            # Push the new message into the message queue for later processing
            self.message_queue.put(new_message)
            self._log_debug(f"Message added to queue: {new_message.message_id} (Type: {new_message.message_type})")
        
        else:
            # Handle invalid message format
            self._log_debug("Invalid message proposal format")

    def _handle_end_of_proposal(self, message):
        """Handle messages that begin with 'F>'."""
        self._log_debug(f"Handling end of proposal message: {message}")
        
        # Process messages in the queue in FIFO order
        try:
            while not self.message_queue.empty():
                message_instance = self.message_queue.get()  # Get the first message in the queue
                self._log_debug(f"Processing message ID: {message_instance.message_id}")
                
                # Await up to uncompressed_size bytes of data from the client
                self.send_data("FS Y\r")  # Send the prompt to the client
                data = self._wait_for_data(message_instance.uncompressed_size)
                
                # Store the raw data in the message instance
                message_instance.raw_data = data
                
                # Save the raw data to a file in the 'message/' folder
                self._save_message_to_file(message_instance)
                
                # Decode the raw data, split it, and save as necessary
                self._decode_and_split_message(message_instance)
                
                # Send "FF" followed by a carriage return after receiving the data
                self.send_data("FF\r")
        
        except Exception as e:
            self._log_debug(f"Error handling end of proposal: {e}")
            self._close_connection()  # Close the connection in case of an error

    def _save_message_to_file(self, message_instance):
        """Save the raw data to a .b2f file in the 'message/' folder."""
        try:
            # Ensure the 'message/' folder exists
            if not os.path.exists('message'):
                os.makedirs('message')
            
            # Get today's Julian date
            julian_date = datetime.datetime.now().strftime("%Y%j")  # Format: YYYYDDD
            
            # File path with Julian date and message ID
            file_name = f"message/{julian_date}-{message_instance.message_id}.b2f"
            
            # Write the raw data to the file
            with open(file_name, 'wb') as f:
                f.write(message_instance.raw_data)
            
            self._log_debug(f"Message data saved to {file_name}")
        except Exception as e:
            self._log_debug(f"Error saving message to file: {e}")

    def _decode_and_split_message(self, message_instance):
        """Decode the raw .b2f data (base64 + zlib), split into headers, body, and binary, and save them."""
        try:
            # Step 1: Base64 decode the raw .b2f data
            decoded_data = base64.b64decode(message_instance.raw_data)
            
            # Step 2: Decompress the decoded data using zlib
            decompressed_data = zlib.decompress(decoded_data)
            
            # Step 3: Convert the decompressed data to ASCII (B2F format is ASCII encoded)
            decoded_message = decompressed_data.decode('ascii')

            # Step 4: Split the decoded message into headers and body
            # We assume the headers and body are separated by two newlines
            headers, body_and_attachments = decoded_message.split("\n\n", 1)

            # Save the headers to a file
            self._save_headers_to_file(headers, message_instance)

            # Step 5: Separate body and attachments
            body, attachments = self._split_body_and_attachments(body_and_attachments)

            # Save the body to a text file
            self._save_body_to_file(body, message_instance)

            # Save the binary attachments (if any) to .bin files
            self._save_attachments_to_files(attachments, message_instance)
            
        except Exception as e:
            self._log_debug(f"Error decoding and splitting message: {e}")

    def _save_headers_to_file(self, headers, message_instance):
        """Save the headers to a .txt file."""
        try:
            # Get today's Julian date for naming the file
            julian_date = datetime.datetime.now().strftime("%Y%j")  # Format: YYYYDDD
            
            # File path for the headers .txt file
            headers_file_name = f"message/{julian_date}-{message_instance.message_id}-headers.txt"
            
            # Write the headers to the file
            with open(headers_file_name, 'w') as f:
                f.write(headers)
            
            self._log_debug(f"Headers saved to {headers_file_name}")
        except Exception as e:
            self._log_debug(f"Error saving headers: {e}")

    def _save_body_to_file(self, body, message_instance):
        """Save the body text to a .txt file."""
        try:
            # Get today's Julian date for naming the file
            julian_date = datetime.datetime.now().strftime("%Y%j")  # Format: YYYYDDD
            
            # File path for the body .txt file
            body_file_name = f"message/{julian_date}-{message_instance.message_id}-body.txt"
            
            # Write the body to the file
            with open(body_file_name, 'w') as f:
                f.write(body)
            
            self._log_debug(f"Body saved to {body_file_name}")
        except Exception as e:
            self._log_debug(f"Error saving body: {e}")

    def _split_body_and_attachments(self, body_and_attachments):
        """Split the body from binary attachments in the message."""
        # Assuming binary attachments are base64-encoded and follow a specific delimiter in the message.
        # This part needs to be adjusted based on how the body and attachments are structured in the message.
        body = ""
        attachments = ""

        # For simplicity, let's assume attachments are marked with a specific delimiter like '[ATTACHMENT]'.
        if '[ATTACHMENT]' in body_and_attachments:
            body, attachments = body_and_attachments.split('[ATTACHMENT]', 1)
        else:
            body = body_and_attachments  # No attachments, all is body

        return body, attachments

    def _save_attachments_to_files(self, attachments, message_instance):
        """Save any binary attachments to separate .bin files."""
        try:
            # Get today's Julian date for naming the file
            julian_date = datetime.datetime.now().strftime("%Y%j")  # Format: YYYYDDD
            
            # Split attachments (assuming they are base64-encoded)
            if attachments:
                # For each attachment, we decode and save it as a binary file
                attachment_data = base64.b64decode(attachments)  # Decode base64-encoded attachment
                
                # File path for the attachment .bin file
                attachment_file_name = f"message/{julian_date}-{message_instance.message_id}-attachment.bin"
                
                # Write the attachment to the file
                with open(attachment_file_name, 'wb') as f:
                    f.write(attachment_data)
                
                self._log_debug(f"Attachment saved to {attachment_file_name}")
        except Exception as e:
            self._log_debug(f"Error saving attachments: {e}")

    def _close_connection(self):
        """Close the connection."""
        if self.connection:
            print(f"Server: Closing connection to {self.address}")
            self.logger.info(f"Closing connection to {self.address}")
            self.connection.close()

    def _handle_no_messages(self, request):
        """Handle the ';FF:' request indicating no messages to process."""
        self._log_debug(f"Handling no messages: {request}")
        
        # Send "FQ" followed by a carriage return
        self.send_data("FQ\r")
        self._log_debug("Sent 'FQ' indicating no messages")

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
                print(f"Server: Invalid SID format. Closing connection to {self.address}")
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
