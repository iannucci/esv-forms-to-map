#!/usr/bin/env python
'''Simple Winlink Server that accepts incoming messages'''

__author__ = "Bob Iannucci"
__copyright__ = "Copyright 2025, Bob Iannucci"
__license__ = "MIT"
__maintainer__ = __author__
__email__ = "bob@rail.com"
__status__ = "Experimental"

# State definitions for the state machine as strings
import logging
import queue
import re 
import socket
from classes.WinlinkMailMessage import WinlinkMailMessage
import traceback

START = "START"
CONNECTED = "CONNECTED"
CALLSIGN_ENTRY = "CALLSIGN_ENTRY"
PASSWORD_VALIDATION = "PASSWORD_VALIDATION"
LOGIN_SUCCESS = "LOGIN_SUCCESS"
CLIENT_REQUEST = "CLIENT_REQUEST"
CLOSE_CONNECTION = "CLOSE_CONNECTION"

MAILBOX_FOLDER_NAME = "mailbox"


class WinlinkConnection:
	def __init__(self, connection, address, timeout, enable_debug=False):
		"""Initialize the connection handler and encapsulate socket handling."""
		self.connection = connection
		self.address = address
		self.timeout = timeout  # Unified timeout value for all operations
		self.enable_debug = enable_debug
		self.client_callsign = None
		self.client_password = None  
		self.author = None  
		self.version = None  
		self.feature_list = None  
		self.state = START  
		self.next_state = START  
		self.forward_login_callsign = None  
		self.pickup_callsigns = []  
		self.message_queue = queue.Queue()  
		
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
		if self.state != new_state:
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
				if len(data) > 0:
					self._log_debug(f"Sent: <{data.strip()}>")
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
			self._log_debug(f"Received: <{response_str}>")

			return response_str
		except socket.timeout:
			self._log_debug("Timeout occurred while waiting for input.")
			return None

	def _handle_start(self):
		"""Handle the start state."""
		self._log_debug("START state")
		self.state = CONNECTED  # Move to CONNECTED when starting the connection
		self.next_state = CONNECTED

	def _handle_connected(self):
		"""Handle the connected state."""
		self._log_debug("CONNECTED state")
		# The connection is already established, so move to CALLSIGN_ENTRY
		self.next_state = CALLSIGN_ENTRY

	def _handle_callsign_entry(self):
		"""Process the callsign."""
		self._log_debug("CALLSIGN_ENTRY state")
		callsign = self.wait_for_input("Callsign :\r")  # Wait for client input

		if callsign:
			self.client_callsign = callsign  # Save the callsign
			self.next_state = PASSWORD_VALIDATION  # Move to PASSWORD_VALIDATION state
		else:
			self.next_state = START  # Return to the START state

	def _handle_password_validation(self):
		"""Process the password."""
		self._log_debug("PASSWORD_VALIDATION state")
		# Prompt for password and wait for input
		password = self.wait_for_input("Password :\r")
		
		if password:
			self.client_password = password  # Save the password as an instance variable
			self.next_state = LOGIN_SUCCESS  # Move to LOGIN_SUCCESS state
		else:
			self.next_state = START  # Return to the START state

	def _handle_login_success(self):
		"""Handle successful login."""
		self._log_debug("LOGIN_SUCCESS state")
		
		# Send '[AREDN_BRIDGE-1.0-B2F$]' followed by a carriage return
		self.send_data("[AREDN_BRIDGE-1.0-B2F$]\r")
		
		# Send 'CMS>' followed by a carriage return
		self.send_data("CMS>\r")
		
		self.next_state = CLIENT_REQUEST  # Transition to CLIENT_REQUEST after login success

	def _handle_client_request(self):
		"""Handle the client's request after login."""
		self._log_debug("CLIENT_REQUEST state")
		request = self.wait_for_input("")  # Wait for client's request and strip trailing carriage return

		if request:
			if request.startswith("FC"):  
				self._handle_message_proposal(request)  
			elif request.startswith(";FW:"):
				self._handle_forward_message(request)  
			elif request.startswith(";PQ:"):
				self._handle_authentication_challenge(request)  
			elif request.startswith(";PM:"):
				self._handle_pending_message(request)  
			elif re.match(r"^\[.*\]$", request):  
				self._handle_sid(request)  
			elif request.startswith("; "):
				self._handle_comment(request)  
			elif request.startswith("F>"):
				self._handle_end_of_proposals(request)  
			elif request.startswith("FF"):  
				self._handle_no_messages(request)  
			else:
				self.next_state = CLOSE_CONNECTION  # Close connection if request type is unrecognized
		else:
			self.next_state = CLOSE_CONNECTION  # Close the connection if no valid request

	def _handle_comment(self, message):
		"""Handle comment messages that begin with '; '."""
		self._log_debug(f"Comment message: {message}")

	def _handle_forward_message(self, message):
		"""Handle forward messages that begin with ';FW:'."""
		self._log_debug(f"Forward message: {message}")
		# Implementation for handling forward message
		# (Extract forward_login_callsign, pickup_callsigns, etc.)

	def _handle_authentication_challenge(self, message):
		self._log_debug(f"Authentication challenge: {message}")
		pass

	def _handle_pending_message(self, message):
		self._log_debug(f"Pending message: {message}")
		pass

	def _handle_sid(self, message):
		"""Parse the message that starts with '[' and ends with ']'. Extract author, version, and feature list."""
		self._log_debug(f"SID message: {message}")
		
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
			self._log_debug(f"Server: Invalid SID format. Closing connection to {self.address}")
			self._close_connection()  # Close the connection if format is incorrect
			self.next_state = CLOSE_CONNECTION  # Close the connection


	def _handle_message_proposal(self, message):
		"""Handle 'FC' case -- message proposal"""
		self._log_debug(f"Message proposal: {message}")
		
		# Extracting message type, message ID, uncompressed size, and compressed size
		parts = message.split()
		if len(parts) >= 5:
			message_type = parts[1]
			message_id = parts[2]
			uncompressed_size = int(parts[3])
			compressed_size = int(parts[4])

			# Create a new Message instance with the extracted data
			new_message = WinlinkMailMessage(message_type, message_id, uncompressed_size, compressed_size, enable_debug=self.enable_debug)
			self.message_queue.put(new_message)
			self._log_debug(f"Message added to queue: {new_message.message_id} (Type: {new_message.message_type})")
		
		else:
			self._log_debug("Invalid message proposal format")

	def _handle_end_of_proposals(self, message):
		"""Handle 'F>' case"""
		self._log_debug(f"End of proposals")
		
		try:
			pending_messages = len(self.message_queue.queue)
			if pending_messages > 0:
				c = 'Y'
				# Tell the client we are ready to accept all the pending messages
				self.send_data(f"FS {c * pending_messages}\r")  
				raw_message_data = self._wait_for_messages()  # One big binary blob for all messages
				next_index = 0  # Start index for processing the received data

				while not self.message_queue.empty():
					message = self.message_queue.get()  # Get the first message in the queue
					self._log_debug(f"Processing message ID: {message.message_id}")
					message.capture(raw_message_data)  # Record the raw data
					next_index = message.parse()  # Parse the message at the beginning of raw_message_data and figure out where the next one starts
					message.save_message_to_files()
					raw_message_data = raw_message_data[next_index:]  # Remove the processed data from the buffer
					
				# Send "FF" followed by a carriage return after receiving the messages
				self.send_data("FF\r")
			
		except Exception as e:
			self._log_debug(f"Error handling end of proposal: {e}")
			self._close_connection()  # Close the connection in case of an error

	def _handle_no_messages(self, message):
		"""Handle the 'FF' request indicating no messages to process."""
		self._log_debug(f"No message condition: {message}")
		
		# Send "FQ" followed by a carriage return
		self.send_data("FQ\r")
		self._log_debug("Sent 'FQ' indicating no messages")

	def _wait_for_messages(self):
		"""Wait for all data from the client -- may include multiple messages"""
		# received_data = b""
		received_data = bytearray()
		self._log_debug(f"Ready to receive message data from client")
		try:
			while True:
				# Receive in chunks (you can adjust the chunk size if necessary)
				# chunk = self.connection.recv(min(4096, expected_size - len(received_data)))
				chunk = self.connection.recv(4096)
				if chunk is not None:
					self._log_debug(f"Received chunk of length {len(chunk)}")
				else:
					break  # If no more data is received, exit the loop
				received_data += chunk

			# Log the data received
			self._log_debug(f"Received {len(received_data)} bytes of data")
			
			return received_data
		except socket.timeout:
			return received_data

	def _close_connection(self):
		if self.connection:
			self.logger.info(f"Closing connection to {self.address}")
			self.connection.close
