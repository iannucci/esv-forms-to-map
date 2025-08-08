#!/usr/bin/env python
'''Simple Winlink Server that accepts incoming messages'''

__author__ = "Bob Iannucci"
__copyright__ = "Copyright 2025, Bob Iannucci"
__license__ = "MIT"
__maintainer__ = __author__
__email__ = "bob@rail.com"
__status__ = "Experimental"

import subprocess
import platform
import os
import struct
import logging
import tempfile

SOH = 0x01
NUL = 0x00
STX = 0x02
EOT = 0x04

GO_EXECUTABLE = 'decompress_lzhuf'

class B2Attachment:
	def __init__(self, filename, size):
		self.filename = filename  # Name of the attachment file
		self.data = None
		self.size = size  # SExpected size in bytes

class B2Message:
	def __init__(self, message_id, raw_data, decompressed_size, compressed_size, enable_debug=False) -> int:
		self.message_id = message_id  # for debugging
		self.enable_debug = enable_debug
		self.raw_data = raw_data
		self.header_length = None
		self.subject = None
		self.offset = None
		self.transmitted_checksum = None
		self.compressed_data = bytearray()
		self.compressed_size = compressed_size
		self.decompressed_data = None
		self.decompressed_size = decompressed_size
		self.headers = ""
		self.body = ""
		self.attachments = []

		# Set up logging
		self.logger = logging.getLogger(__name__)
		self._setup_logging()

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

	# Returns the index of the next unprocessed byte in raw_data
	def parse(self) -> int:
		# Position 0: SOH
		byte_index = 0
		if self.raw_data[byte_index] != SOH:
			raise ValueError("Expected SOH at start of message")
		self._log_debug(f"Found SOH")
		# raw_data_len = len(self.raw_data)
		# self._log_debug(f"Handling raw data block of length {raw_data_len}")
		
		# Position 1: One byte length field which covers the SUBJECT, a NUL, an ASCII LENGTH field called
		# the OFFSET, and another NUL
		byte_index += 1
		self.header_length = self.raw_data[byte_index]
		self._log_debug(f"Header length is <{self.header_length}>")

		# Position 2..2+Read subject
		byte_index += 1
		end_subject = self.raw_data.index(NUL, byte_index)
		self.subject = self.raw_data[byte_index:end_subject].decode("ascii")
		self._log_debug(f"Subject is <{self.subject}>")

		# Another NUL
		byte_index = end_subject
		if self.raw_data[byte_index] != NUL:
			raise ValueError("Expected NUL after subject field")

		# Read offset
		byte_index += 1
		end_offset = self.raw_data.index(NUL, byte_index)
		offset_str = self.raw_data[byte_index:end_offset].decode("ascii")
		self.offset = int(offset_str)
		self._log_debug(f"Offset is {self.offset}")

		byte_index = end_offset + 1  # end_offset points to NUL; skip over it
		# compressed_index = 0
		if self.offset != 0:
			if self.raw_data[byte_index] != STX or self.raw_data[byte_index+1] != 0x06:
				raise ValueError("Expected STX 0x06 before lead-bytes")
			byte_index += 2
			self.compressed_data[0:6] = self.raw_data[byte_index:byte_index+6] # these are the "lead bytes" and this probably
																			 # NOT the right way to handle them
			byte_index += 6
			# compressed_index += 6

		# Accumulate data in blocks:
		# <STX><LEN><BYTES>  Len is one byte long and represents the length of <BYTES>
		# <STX><LEN><BYTES>
		# ...
		# <EOT><CHECKSUM>

		# Accumulate bytes of the compressed message until we reach EOT
		while True: 
			if self.raw_data[byte_index] == STX:
				self._log_debug(f"Found STX at index {byte_index}")
				byte_index += 1
				stx_block_length = self.raw_data[byte_index] # from byte following this one to the next <STX> or <EOT>
				self._log_debug(f"Found LENGTH of {stx_block_length} at index {byte_index}")
				# with enough space left in the raw data?
				byte_index += 1  # pointing to first data byte

				# last_byte_index = byte_index + stx_block_length # pointing to the byte after the last data byte
				# last_compressed_index = compressed_index + stx_block_length

				# if last_byte_index > raw_data_len:
				# if block_length > raw_data_len:

				# 	raise ValueError(f"Malformed message block -- too short -- expected {last_byte_index} got {raw_data_len}")
				self._log_debug(f"Expecting compressed block of {stx_block_length} bytes at index {byte_index}")
				self.compressed_data.extend(self.raw_data[byte_index:byte_index+stx_block_length])
				byte_index += stx_block_length
				self._log_debug(f"Captured block of length {stx_block_length}")
			elif self.raw_data[byte_index] == EOT:
				self._log_debug(f"Found EOT at index {byte_index}")
				byte_index += 1
				self.transmitted_checksum = self.raw_data[byte_index]
				calculated_checksum = self._calculate_checksum()
				byte_index += 1
				if self.transmitted_checksum != calculated_checksum:
					raise ValueError(f"Checksum mismatch: expected 0x{calculated_checksum:02X}, got 0x{self.transmitted_checksum:02X}")
				else:
					self._log_debug(f"Checksum match")
					break
			else:
				# print(f'{self.raw_data[byte_index-1]:02X} {self.raw_data[byte_index]:02X}')
				raise ValueError(f"Malformed message block at index {byte_index} -- expected STX or EOT, got 0x{self.raw_data[byte_index]:02X}")

		# CRC-16, LENGTH, and compressed message
		compressed_data_len = len(self.compressed_data)  # Data begins after the <STX><LEN> and ends before <EOT><CHECKSUM>
		if compressed_data_len == self.compressed_size:
			self._log_debug(f"Compressed message plus header matches proposal: {compressed_data_len}")
		else:
			raise ValueError(f"Compressed message size {compressed_data_len} does not match proposal {self.compressed_size}")

		decompressed_data_len = int.from_bytes(self.compressed_data[2:6], byteorder='little')
		if decompressed_data_len == self.decompressed_size:
			self._log_debug(f"Decompressed message size matches proposal: {decompressed_data_len}")
		else:
			raise ValueError(f"Decompressed message size {decompressed_data_len} does not match proposal {self.decompressed_size}")

		try:
			with tempfile.NamedTemporaryFile(delete=False, mode='wb') as compressed_file:
				compressed_file_name = compressed_file.name
				compressed_file.write(self.compressed_data)
				compressed_file.close()
				with open(compressed_file_name, 'rb') as compressed_file:
					with tempfile.NamedTemporaryFile(delete=False, mode='w') as decompressed_file:
						decompressed_file_name = decompressed_file.name
						result = subprocess.run([GO_EXECUTABLE, compressed_file_name, decompressed_file_name], capture_output=True, text=True)
						decompressed_file.close()
						with open(decompressed_file_name, 'rb') as decompressed_file:
							self.decompressed_data = decompressed_file.read()   #.decode('ascii', errors='ignore')
							self._extract_message_parts()
		except Exception as e:
			self.logger.error(f"Decompression failed: {e}")
		# return (self.compressed_data, self.decompressed_data)
		return byte_index  # Returns the index of the next unprocessed byte in raw_data

	def _extract_message_parts(self):
		"""Extract headers and body from the decompressed data."""
		if self.decompressed_data:
			# Format of the message at this stage:
			# Headers in ASCII, each line terminated by \r\n
			#   <header1> <\r\n>
			#   <header2> <\r\n>
			#   ...
			#   <\r\n>  The header has no blank lines, so searching for <\r\n\r\n> is safe
			# Body is in ASCII and attachments are in binary
			#   <body> (if any) <\r\n> The body does not use <\r> for line separation
			#   <attachment1> (if any) <\r\n\r\n>
			#   <attachment2> (if any) <\r\n\r\n>
			#   ...
			#   <\r\n\r\n>
			header_binary, body_and_attachments_binary = self.decompressed_data.split(b"\r\n\r\n", 1)
			split_list = body_and_attachments_binary.split(b"\r\n", 1)
			body_binary = split_list[0] if len(split_list) > 0 else b""
			attachment_binary = split_list[1] if len(split_list) > 1 else b""
			# self._log_debug(f"Message parts: {len(message_parts)}")
			# for part in message_parts:
			# 	self._log_debug(f"Size: {len(part)}")
			self.headers = header_binary.decode('ascii', errors='ignore') 
			header_lines = self.headers.split("\n")
			body_length = 0
			for line in header_lines:
				parts = line.split()
				if line.startswith("File: "):
					b2attachment = B2Attachment(parts[2], int(parts[1]))
					self.attachments.append(b2attachment)
				if line.startswith("Body: "):
					body_length = int(parts[1]) if len(parts) > 1 else 0
			if body_length == 0:
				self.body = ""
				# if len(self.attachments) > 0 and len(message_parts) > 1:
				# 	attachment_binary = message_parts[1][2:]  
			else:
				self.body = body_binary.decode('ascii', errors='ignore')
				# if len(message_parts) > 2:
				# 	attachment_binary = message_parts[2][2:]

			for attachment in self.attachments:
				self._log_debug(f"Attachment expected size {attachment.size} Available {len(attachment_binary)}")
				if attachment.size + 2 <= len(attachment_binary):
					attachment.data = attachment_binary[:attachment.size]
					self._log_debug(f"Extracted attachment {attachment.filename} of size {attachment.size}")
					# Remove the extracted data from the binary stream
					attachment_binary = attachment_binary[attachment.size+2:]
		else:
			self.logger.error("Decompressed data is empty, cannot extract headers and body.")
