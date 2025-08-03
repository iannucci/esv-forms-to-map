import socket
import threading
import logging
import time
import queue
import zlib

# State definitions for the state machine as strings
START = "START"
CONNECTED = "CONNECTED"
CALLSIGN_ENTRY = "CALLSIGN_ENTRY"
PASSWORD_VALIDATION = "PASSWORD_VALIDATION"
LOGIN_SUCCESS = "LOGIN_SUCCESS"
CLIENT_REQUEST = "CLIENT_REQUEST"
MESSAGE_UPLOAD = "MESSAGE_UPLOAD"
CLOSE_CONNECTION = "CLOSE_CONNECTION"

class MessageOffer:
    """Class to represent an incoming message offer."""
    pass

class ConnectionHandler:
    def __init__(self, connection, address, timeout=5, enable_debug=False):
        """Initialize the connection handler and encapsulate socket handling."""
        self.connection = connection
        self.address = address
        self.timeout = timeout  # Unified timeout value for all operations
        self.enable_debug = enable_debug
        self.client_callsign = None
        self.client_password = None  # Save password as an instance variable
        self.state = START  # Starting state
        self.next_state = START  # Next state to transition to
        
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
                elif self.state == MESSAGE_UPLOAD:
                    self._handle_message_upload()
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
        """Send prompt and wait for client response within timeout."""
        self.send_data(prompt)
        try:
            self.connection.settimeout(self.timeout)  # Use the same timeout for callsign entry
            response = self.connection.recv(1024).decode().strip()  # Receive client input
            return response
        except socket.timeout:
            self._log_debug(f"Timeout occurred while waiting for input.")
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
        print("Server: Waiting for client request.")
        request = self.wait_for_input("")  # Wait for client's request without a custom prompt

        if request:
            print(f"Server: Received client request: {request}")
            # You can add additional processing based on the request if needed
            self.next_state = MESSAGE_UPLOAD  # Move to the next state after handling the request
        else:
            print("Server: No valid request received. Closing connection.")
            self._close_connection()  # Close the connection if no valid request
            self.next_state = CLOSE_CONNECTION  # Close the connection

    def _handle_message_upload(self):
        """Handle message upload."""
        self._log_debug("Handling MESSAGE_UPLOAD state")
        # This would be handled in the connection handler during the message offer
        print("Server: Waiting for message upload.")
        self.next_state = CLOSE_CONNECTION  # Move directly to CLOSE_CONNECTION after message upload

    def _close_connection(self):
        """Close the connection."""
        if self.connection:
            self.logger.info(f"Closing connection to {self.address}")
            self.connection.close()

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
