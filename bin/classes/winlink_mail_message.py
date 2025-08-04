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
import base64
import zlib

MAILBOX_FOLDER_NAME = "mailbox"


class WinlinkMailMessage:
    """Class to represent a message with its metadata."""
    
    def __init__(self, message_type=None, message_id=None, uncompressed_size=None, compressed_size=None):
        """Initialize the message with the necessary instance variables."""
        self.message_type = message_type  # Type of the message (e.g., proposal, etc.)
        self.message_id = message_id  # Unique identifier for the message
        self.uncompressed_size = uncompressed_size  # Uncompressed size of the message
        self.compressed_size = compressed_size  # Compressed size of the message
        self.filename = None
        self.raw_data = None  # To store the raw data received
        self.headers = None
        self.body_and_attachments = None
        self.body = None
        self.attachments = None

    def _split_body_and_attachments(self):
        """Split the body from binary attachments in the message."""
        # Assuming binary attachments are base64-encoded and follow a specific delimiter in the message.
        # This part needs to be adjusted based on how the body and attachments are structured in the message.
        body = ""
        attachments = ""

        # For simplicity, let's assume attachments are marked with a specific delimiter like '[ATTACHMENT]'.
        if '[ATTACHMENT]' in self.body_and_attachments:
            self.body, self.attachments = self.body_and_attachments.split('[ATTACHMENT]', 1)
        else:
            self.body = self.body_and_attachments  # No attachments, all is body

        return self.body, self.attachments

    def record_messsage_data(self, data):
        """Decode the raw .b2f data (base64 + zlib), split into headers, body, and binary, and save them."""
        try:
            self.raw_data = data
            decoded_data = base64.b64decode(self.raw_data)
            decompressed_data = zlib.decompress(decoded_data)
            decoded_message = decompressed_data.decode('ascii')
            self.headers, self.body_and_attachments = decoded_message.split("\n\n", 1)
            self.body, self.attachments = self._split_body_and_attachments()
            
        except Exception as e:
            self._log_debug(f"Error decoding and splitting message: {e}")

    def save_message_to_files(self):
        """Save the raw data and the decoded data to files."""
        try:
            if not os.path.exists(MAILBOX_FOLDER_NAME):
                os.makedirs(MAILBOX_FOLDER_NAME)
            self._save_headers_to_file()
            self._save_body_to_file()
            self._save_attachments_to_files()
        except Exception as e:
            self._log_debug(f"Error saving message to file: {e}")

    def _save_raw_data_to_file(self):
        """Save the raw data to a .b2f file."""
        try:
            raw_file_name = f"{self.filename}-headers.b2f"
            with open(raw_file_name, 'wb') as f:
                f.write(self.raw_data)
            self._log_debug(f"Raw data saved to {raw_file_name}")
        except Exception as e:
            self._log_debug(f"Error saving raw data: {e}")

    def _save_headers_to_file(self):
        """Save the headers to a .txt file."""
        try:
            headers_file_name = f"{self.filename}-headers.txt"
            with open(headers_file_name, 'w') as f:
                f.write(self.headers)
            self._log_debug(f"Headers saved to {headers_file_name}")
        except Exception as e:
            self._log_debug(f"Error saving headers: {e}")

    def _save_body_to_file(self):
        """Save the body to a .txt file."""
        try:
            body_file_name = f"{self.filename}-body.txt"
            with open(body_file_name, 'w') as f:
                f.write(self.body)
            self._log_debug(f"Body saved to {body_file_name}")
        except Exception as e:
            self._log_debug(f"Error saving body: {e}")

    def _save_attachments_to_files(self):
        """Save any binary attachments to separate .bin files."""
        try:
            if self.attachments is not None:
                # For each attachment, we decode and save it as a binary file
                attachment_data = base64.b64decode(self.attachments)  # Decode base64-encoded attachment
                attachment_file_name = f"{self.filename}-attachment.bin"
                with open(attachment_file_name, 'wb') as f:
                    f.write(attachment_data)
                self._log_debug(f"Attachment saved to {attachment_file_name}")
        except Exception as e:
            self._log_debug(f"Error saving attachments: {e}")
