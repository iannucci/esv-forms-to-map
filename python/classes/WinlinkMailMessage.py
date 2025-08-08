#!/usr/bin/env python
'''Simple Winlink Server that accepts incoming messages'''

__author__ = "Bob Iannucci"
__copyright__ = "Copyright 2025, Bob Iannucci"
__license__ = "MIT"
__maintainer__ = __author__
__email__ = "bob@rail.com"
__status__ = "Experimental"

import os
import datetime
import logging
from classes.B2Message import B2Message 

MAILBOX_FOLDER_NAME = "mailbox"


class WinlinkMailMessage:
	"""Class to represent a message with its metadata."""
	
	def __init__(self, message_type=None, message_id=None, uncompressed_size=None, compressed_size=None, enable_debug=False):
		"""Initialize the message with the necessary instance variables."""
		self.time_created = datetime.datetime.now()
		self.enable_debug = enable_debug
		self.message_type = message_type  # Type of the message (e.g., proposal, etc.)
		self.message_id = message_id  # Unique identifier for the message
		self.uncompressed_size = uncompressed_size  # Uncompressed size of the message
		self.compressed_size = compressed_size  # Compressed size of the message
		self.b2 = None

		if not os.path.exists(MAILBOX_FOLDER_NAME):
			os.makedirs(MAILBOX_FOLDER_NAME)

		julian_date = self.time_created.strftime("%Y%m%d%H%M%S")
		self.filename = f"{MAILBOX_FOLDER_NAME}/{julian_date}-{self.message_id}"

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

	def capture(self, raw_data) -> int:
		"""Capture the raw data and decode it."""
		# Record the raw data
		self.b2 = B2Message(self.message_id, raw_data, self.uncompressed_size, self.compressed_size, enable_debug=self.enable_debug)

	# Returns the index of the next unprocessed byte in raw_data
	def parse(self) -> int:
		return self.b2.parse()  # Returns the index of the next unprocessed byte in raw_data
		# self._log_debug(f"B2 subject: {self.b2.subject}")
		# self._save_raw_data_to_file()

	def save_message_to_files(self):
		"""Save the raw data and the decoded data to files."""
		try:
			self._save_headers_to_file()
			self._save_body_to_file()
			self._save_attachments_to_files()
		except Exception as e:
			self._log_debug(f"Error saving message to file: {e}")

	def _save_raw_data_to_file(self):
		"""Save the raw data to a .b2f file."""
		try:
			raw_filename = f"{self.filename}.b2f"
			with open(raw_filename, 'wb') as f:
				f.write(self.b2.raw_data)
			self._log_debug(f"Raw data saved to {raw_filename}")
		except Exception as e:
			self._log_debug(f"Error saving raw data: {e}")

	def _save_headers_to_file(self):
		"""Save the headers to a .txt file."""
		if self.b2.headers is not None:
			try:
				headers_filename = f"{self.filename}-headers.txt"
				with open(headers_filename, 'w') as f:
					f.write(self.b2.headers)
				self._log_debug(f"Headers saved to {headers_filename}")
			except Exception as e:
				self._log_debug(f"Error saving headers: {e}")
		else:
			self._log_debug(f"Error saving headers: None")

	def _save_body_to_file(self):
		"""Save the body to a .txt file."""
		if self.b2.body is not None:
			try:
				body_filename = f"{self.filename}-body.txt"
				with open(body_filename, 'w') as f:
					f.write(self.b2.body)
				self._log_debug(f"Body saved to {body_filename}")
			except Exception as e:
				self._log_debug(f"Error saving body: {e}")
		else:
			self._log_debug(f"Error saving body: None")

	def _save_attachments_to_files(self):
		"""Save any binary attachments to separate .bin files."""
		try:
			for attachment in self.b2.attachments:
				attachment_filename = f"{self.filename}-{attachment.filename}"
				with open(attachment_filename, 'wb') as f:
					f.write(attachment.data)
				self._log_debug(f"Attachment saved to {attachment_filename}")
		except Exception as e:
			self._log_debug(f"Error saving attachments: {e}")
