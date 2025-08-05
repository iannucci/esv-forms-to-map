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
		self.compressed_data = None

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
		checksum = sum(self.raw_data) & 0xFF
		return ((checksum * -1) & 0xFF)

	def _parse_b2_message(self):
		index = 0
		if self.raw_data[index] != SOH:
			raise ValueError("Expected SOH at start of message")
		index += 1

		self._log_debug(f"Found SOH")

		# Length of subject + offset string + 2 (for 2 NULs)
		self.header_length = self.raw_data[index]
		index += 1

		self._log_debug(f"Header length is {self.header_length}")

		# Read subject
		end_subject = self.raw_data.index(NUL, index)
		self.subject = self.raw_data[index:end_subject].decode("ascii")
		index = end_subject + 1

		self._log_debug(f"Subject is <{self.subject}>")

		# Read offset
		end_offset = self.raw_data.index(NUL, index)
		offset_str = self.raw_data[index:end_offset].decode("ascii")
		self.offset = int(offset_str)
		index = end_offset + 2  # Skip over the NUL

		self._log_debug(f"Offset is {self.offset}")

		lead_bytes_local = b''
		if self.offset != 0:
			if self.raw_data[index] != STX or self.raw_data[ptr+1] != 0x06:
				raise ValueError("Expected STX 0x06 before lead-bytes")
			ptr += 2
			lead_bytes_local = self.raw_data[index:index+6]
			index += 6
   
		if self.raw_data[index] != STX:
			raise ValueError("Expected STX at start of the compressed message")
		index += 1
  
		block_length = int(self.raw_data[index])
		index +=1

		# Parse data blocks
		compressed_data_local = bytearray()
  
		while index < len(self.raw_data):
			byte = self.raw_data[index]
			if byte == STX:
				ptr += 1
				block_length = self.raw_data[index]
				ptr += 1
				block_data = self.raw_data[ptr:ptr+block_length]
				compressed_data_local.extend(block_data)
				ptr += block_length
			elif byte == EOT:
				ptr += 1
				self.transmitted_checksum = self.raw_data[ptr]
				calculated_checksum = self._calculate_checksum(compressed_data_local)
				if self.transmitted_checksum != calculated_checksum:
					raise ValueError(f"Checksum mismatch: expected {calculated_checksum:02X}, got {self.transmitted_checksum:02X}")

				self.lead_bytes = lead_bytes_local,
				self.compressed_data = bytes(compressed_data_local)
			else:
				raise ValueError(f"Unexpected byte {byte:02X} at position {ptr}")

		raise ValueError("EOT block not found")
