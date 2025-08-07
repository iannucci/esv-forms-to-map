#!/usr/bin/env python
'''Accepts a B2Message as a file and extracts the contents'''

__author__ = "Bob Iannucci"
__copyright__ = "Copyright 2025, Bob Iannucci"
__license__ = "MIT"
__maintainer__ = __author__
__email__ = "bob@rail.com"
__status__ = "Experimental"

import sys
import os

this_path = os.path.dirname(__file__)
src_path = os.path.abspath(os.path.join(this_path, '../'))
sys.path.insert(0, src_path)

import datetime
import logging
from classes.B2Message import B2Message 

def extract(filename, uncompressed_len, compressed_len):
	with open(f'{this_path}/{filename}', 'rb') as f:
		raw_data = f.read()
	b2 = B2Message(raw_data, uncompressed_len, compressed_len, True)
	return True

# FC EM MQ2TOYZRMM2D 22514 22314
if extract('MQ2TOYZRMM2D_message_with_header.b2f', 22514, 22314):
    print('Success')