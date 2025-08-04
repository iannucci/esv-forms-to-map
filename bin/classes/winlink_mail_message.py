#!/usr/bin/env python
'''Simple Winlink Server that accepts incoming messages'''

__author__ = "Bob Iannucci"
__copyright__ = "Copyright 2025, Bob Iannucci"
__license__ = "MIT"
__maintainer__ = __author__
__email__ = "bob@rail.com"
__status__ = "Experimental"

class WinlinkMailMessage:
    """Class to represent a message with its metadata."""
    
    def __init__(self, message_type=None, message_id=None, uncompressed_size=None, compressed_size=None):
        """Initialize the message with the necessary instance variables."""
        self.message_type = message_type  # Type of the message (e.g., proposal, etc.)
        self.message_id = message_id  # Unique identifier for the message
        self.uncompressed_size = uncompressed_size  # Uncompressed size of the message
        self.compressed_size = compressed_size  # Compressed size of the message
        self.raw_data = None  # To store the raw data received

