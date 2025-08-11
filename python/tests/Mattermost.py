#!/usr/bin/env python
'''Uses Mattermost API'''

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

from mattermostdriver import Driver as MattermostBase
from testdata.endpoints.boards import Boards
from testdata.MattermostAuth import auth_info

class Mattermost(MattermostBase):
	def __init__(self, auth_dict):
		super().__init__(auth_dict)

# API via the Mattermost Base Python driver (https://github.com/Vaelor/python-mattermost-driver)
#
# <instance> = Driver(auth_info_dict)
# <instance>.login() does just that
# <instance>.users.get_user_by_username('...')
# <instance>.users.get_user(user_id='...')
# <instance>.teams.get_teams(params={...})
# <instance>.channels.create_channel(options={
#     'team_id': 'some_team_id',
#     'name': 'team-name',
#     'display_name': 'descriptive printname',
#     'type': 'O'
# })
# <instance>.init_websocket(event_handler)
# <instance>.disconnect()   to disconnect the websocket
# <instance>.posts.create_post(options={
#     'channel_id': channel_id,
#     'message': 'This is the important file',
#     'file_ids': [file_id]})

user=Mattermost(auth_info)
print(user.login())
