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
from datetime import datetime
import json

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
		# Header fields
		self.message_id = message_id
		self.date = datetime.now()
		self.body_length = 0
		self.sender = ""
		self.recipient = ""
		self.subject = ""
		self.position = {"latitude": 0.0, "longitude": 0.0}
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

		while True: 
			if self.raw_data[byte_index] == STX:
				self._log_debug(f"Found STX at index {byte_index}")
				byte_index += 1
				stx_block_length = self.raw_data[byte_index] # from byte following this one to the next <STX> or <EOT>
				self._log_debug(f"Found LENGTH of {stx_block_length} at index {byte_index}")
				byte_index += 1  # pointing to first data byte

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
		self._log_debug(f"JSON: {self.json_header()}")
		return byte_index  # Returns the index of the next unprocessed byte in raw_data

	def _extract_message_parts(self):
		"""Extract headers and body from the decompressed data."""
		if self.decompressed_data:

			header_binary, body_and_attachments_binary = self.decompressed_data.split(b"\r\n\r\n", 1)
			split_list = body_and_attachments_binary.split(b"\r\n", 1)
			body_binary = split_list[0] if len(split_list) > 0 else b""
			attachment_binary = split_list[1] if len(split_list) > 1 else b""
			self.headers = header_binary.decode('ascii', errors='ignore') 
			header_lines = self.headers.split("\n")
			self.body_length = 0
			for line in header_lines:
				parts = line.split()
				part = line.split(" ",1)
				# Body: 28
				# Date: 2025/08/08 20:40
				# From: W6EI-2
				# Subject: Test
				# To: BOB
				# File: 21385 39D0D08F-D670-435E-AEB6-FE2A2936E900.jpg
				# X-Location: 37.420281N, 122.120632W (GPS)
				if line.startswith("Body: "):
					self.body_length = int(parts[1]) if len(parts) > 1 else 0
				elif line.startswith("Date: "):  # Date: 2025/08/08 20:40
					self.date = datetime.strptime(part[1], "%Y/%m/%d %H:%M") if len(part) > 1 else datetime.now()
				elif line.startswith("From: "):
					self.sender = part[1] if len(part) > 1 else "Unknown"
				elif line.startswith("Subject: "):
					self.subject = part[1] if len(part) > 1 else "Unknown"
				elif line.startswith("To: "):
					self.recipient = part[1] if len(part) > 1 else "Unknown"
				elif line.startswith("X-Location: "):
					i = line.replace(",", "").split()
					if len(i) == 4:
						lat = float(i[1][:-1])
						if i[1][-1] == "N":
							latitude = lat
						else:
							latitude = 0 - lat
						lon = i[2][:-1]
						if i[2][-1] == "E":
							longitude = lon
						else:
							longitude = 0 - lon
						self.position = { "latitude": latitude, "longitude": longitude}
					else:
						self.position = {"latitude": 0.0, "longitude": 0.0}
					self.to = part[1] if len(part) > 1 else "Unknown"
				elif line.startswith("File: "):
					b2attachment = B2Attachment(parts[2], int(parts[1]))
					self.attachments.append(b2attachment)
			if self.body_length == 0:
				self.body = ""
			else:
				self.body = body_binary.decode('ascii', errors='ignore')

			for attachment in self.attachments:
				self._log_debug(f"Attachment expected size {attachment.size} Available {len(attachment_binary)}")
				if attachment.size + 2 <= len(attachment_binary):
					attachment.data = attachment_binary[:attachment.size]
					self._log_debug(f"Extracted attachment {attachment.filename} of size {attachment.size}")
					# Remove the extracted data from the binary stream
					attachment_binary = attachment_binary[attachment.size+2:]
		else:
			self.logger.error("Decompressed data is empty, cannot extract headers and body.")

	def json_header(self):
		'''Produce JSON string of message header information'''
		python_dict = {
			"message_id": self.message_id,
			"date": self.date,
			"sender": self.sender,
			"recipient": self.recipient,
			"subject": self.subject,
			"position": self.position
		}

		return json.dumps(python_dict, indent = 4, default=str)