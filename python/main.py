#!/usr/bin/env python
'''Simple Winlink Server that accepts incoming messages'''

__author__ = "Bob Iannucci"
__copyright__ = "Copyright 2025, Bob Iannucci"
__license__ = "MIT"
__maintainer__ = __author__
__email__ = "bob@rail.com"
__status__ = "Experimental"

import socket
import threading
from classes.WinlinkConnection import WinlinkConnection

LISTEN_IP = "0.0.0.0"
LISTEN_PORT = 8772
SIMULTANEOUS_CONNECTION_MAX = 5
CONNECTION_READ_TIMEOUT_SECONDS = 1


class WinlinkServer:
	def __init__(self, host=LISTEN_IP, port=LISTEN_PORT):
		"""Initialize the server with default host and port."""
		self.host = host
		self.port = port

	def start_server(self):
		"""Main listening loop that accepts new connections."""
		server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			server_socket.bind((self.host, self.port))
		except socket.error as e:
			print(f"Error binding to {self.host}:{self.port} - {e}")
			return
		server_socket.listen(SIMULTANEOUS_CONNECTION_MAX)  
		print(f"Server is listening on {self.host}:{self.port}")

		try:
			while True:
				# Accept a new connection
				connection, address = server_socket.accept()
				print(f"Connection established with {address}")

				# Fork a new thread to handle the connection
				handler = WinlinkConnection(connection, address, timeout=CONNECTION_READ_TIMEOUT_SECONDS, enable_debug=True)
				threading.Thread(target=handler.handle_connection).start()
		
		except KeyboardInterrupt:
			print("Winlink Server interrupted, shutting down...")
		finally:
			server_socket.close()

if __name__ == "__main__":
	server = WinlinkServer()
	server.start_server()
