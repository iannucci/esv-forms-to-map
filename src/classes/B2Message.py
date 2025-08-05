#!/usr/bin/env python
'''Simple Winlink Server that accepts incoming messages'''

__author__ = "Bob Iannucci"
__copyright__ = "Copyright 2025, Bob Iannucci"
__license__ = "MIT"
__maintainer__ = __author__
__email__ = "bob@rail.com"
__status__ = "Experimental"

# The B2 format is documented at https://winlink.org/sites/default/files/downloads/winlink_data_flow_and_data_packaging.pdf
#
# The first B2 block begins with this header:
#   SOH – byte with hex value 01
#   length – Single byte containing length of the message subject + number of bytes to store the offset value (as an ASCII value) + 2
#   subject – The subject of the message
#   NUL – byte with hex value 00
#   offset – If the message is starting at an interrupted point, this is the byte offset of the starting point. 
#     If the message is starting at the beginning, the offset is 0 (zero). The offset value is stored as an ASCII string.
#   NUL – byte with hex value 00
#   If the starting offset is not zero, this information field is added (omitted if offset is 0):
#     STX – byte with hex value 02
#     6 – byte with hex value 06
#     lead-bytes – First 6 bytes of the compressed image.
#
# After the B2 header information, the compressed message image is formatted into multiple
# blocks with each block having the following contents:
#   STX – byte with hex value 02
#   block-length – byte with the value 250 for a full block or a smaller number for the final, short block.
#   data – As many data bytes from the compressed message image as specified by block-
# length. Full blocks have 250 data bytes, the final block may have fewer.
# An end block is added after the required number of data blocks. The end block has this format:
#   EOT – byte with hex value 04
#   checksum – Simple checksum of the compressed data bytes in the block converted to a
# byte value using this VB.NET code:
# CByte(((intCheckSum And &HFF) * -1) And &HFF)

import struct
import logging
import base64
import zlib

SOH = 0x01
NUL = 0x00
STX = 0x02
EOT = 0x04

class B2Message:
	def __init__(self, raw_data, enable_debug=False):
		self.enable_debug = enable_debug
		self.raw_data = raw_data
		self.header_length = None
		self.subject = None
		self.offset = None
		self.transmitted_checksum = None
		self.lead_bytes = None
		self.compressed_data = bytearray()
		self.headers = None
		self.body = None
		self.attachments = None

		# Set up logging
		self.logger = logging.getLogger(__name__)
		self._setup_logging()

		self._parse_b2_message()


	def _setup_logging(self):
		"""Set up logging configuration."""
		log_level = logging.DEBUG if self.enable_debug else logging.INFO
		logging.basicConfig(level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

	def _log_debug(self, message):
		"""Log debug messages if debugging is enabled."""
		if self.enable_debug:
			self.logger.debug(message)

	def _calculate_checksum(self) -> int:
		"""Checksum as described: ((sum & 0xFF) * -1) & 0xFF"""
		checksum = sum(self.compressed_data) & 0xFF
		return ((checksum * -1) & 0xFF)

	def _parse_b2_message(self):
		# Header processing
		# Position 0: SOH
		raw_index = 0
		if self.raw_data[raw_index] != SOH:
			raise ValueError("Expected SOH at start of message")
		self._log_debug(f"Found SOH")
		raw_data_len = len(self.raw_data)
		self._log_debug(f"Handling raw data block of length {raw_data_len}")
		
		# Position 1: One byte length field which covers the SUBJECT, a NUL, an ASCII LENGTH field called
		# the OFFSET, and another NUL
		raw_index += 1
		self.header_length = self.raw_data[raw_index]
		self._log_debug(f"Header length is <{self.header_length}>")

		# Position 2..2+Read subject
		raw_index += 1
		end_subject = self.raw_data.index(NUL, raw_index)
		self.subject = self.raw_data[raw_index:end_subject].decode("ascii")
		self._log_debug(f"Subject is <{self.subject}>")

		# Another NUL
		raw_index = end_subject
		if self.raw_data[raw_index] != NUL:
			raise ValueError("Expected NUL after subject field")

		# Read offset
		raw_index += 1
		end_offset = self.raw_data.index(NUL, raw_index)
		offset_str = self.raw_data[raw_index:end_offset].decode("ascii")
		self.offset = int(offset_str)
		self._log_debug(f"Offset is {self.offset}")

		raw_index = end_offset + 1  # end_offset points to NUL; skip over it
		compressed_index = 0
		if self.offset != 0:
			if self.raw_data[raw_index] != STX or self.raw_data[raw_index+1] != 0x06:
				raise ValueError("Expected STX 0x06 before lead-bytes")
			raw_index += 2
			self.compressed_data[0:6] = self.raw_data[raw_index:raw_index+6]
			raw_index += 6
			compressed_index += 6

		# Accumulate data in blocks:
		# <STX><LEN><BYTES>
		# <STX><LEN><BYTES>
		# ...
		# <EOT><CHECKSUM>
		while raw_index < raw_data_len:
			if self.raw_data[raw_index] == STX:
				self._log_debug(f"Found STX at index {raw_index}")
				raw_index += 1
				block_length = self.raw_data[raw_index]
				self._log_debug(f"Found LENGTH of {block_length} at index {raw_index}")
				# with enough space left in the raw data?
				raw_index += 1
				last_raw_index = raw_index + block_length
				last_compressed_index = compressed_index + block_length
				if last_raw_index > raw_data_len:
					raise ValueError(f"Malformed message block -- too short -- expected {last_raw_index} got {raw_data_len}")
				self._log_debug(f"Expecting compressed block of {block_length} bytes at index {raw_index}")
				self.compressed_data[compressed_index:last_compressed_index] = self.raw_data[raw_index:last_raw_index]
				compressed_index = last_compressed_index
				raw_index = last_raw_index
				self._log_debug(f"Captured block of length {block_length}")
			elif self.raw_data[raw_index] == EOT:
				self._log_debug(f"Found EOT at index {raw_index}")
				raw_index += 1
				self.transmitted_checksum = self.raw_data[raw_index]
				calculated_checksum = self._calculate_checksum()
				if self.transmitted_checksum != calculated_checksum:
					raise ValueError(f"Checksum mismatch: expected 0x{calculated_checksum:02X}, got 0x{self.transmitted_checksum:02X}")
				else:
					self._log_debug(f"Checksum match")
					break
			else:
				print(f'{self.raw_data[raw_index-1]:02X} {self.raw_data[raw_index]:02X}')
				raise ValueError(f"Malformed message block at index {raw_index} -- expected STX or EOT, got 0x{self.raw_data[raw_index]:02X}")

		decoded_data = base64.b64decode(self.compressed_data)
		decompressed_data = zlib.decompress(decoded_data)
		decoded_message = decompressed_data.decode('ascii')
		print(decoded_message)
		self.headers, self.body_and_attachments = decoded_message.split("\n\n", 1)
		self.body, self.attachments = self._split_body_and_attachments()

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
