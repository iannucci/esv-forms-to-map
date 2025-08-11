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

from mattermostdriver import Driver as MattermostBaseDriver
from testdata.endpoints.boards import Boards
from testdata.MattermostAuth import auth_info

class MattermostExtendedDriver(MattermostBaseDriver):
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

driver = MattermostExtendedDriver(auth_info)
# Result:
# {'id': 'd3xhx4599fnzzyxyiuwrm4j45h', 'create_at': 1750281423552, 'update_at': 1753413261178, 
# 'delete_at': 0, 'username': 'w6ei', 'auth_data': '', 'auth_service': '', 'email': 'bob@rail.com', 
# 'nickname': 'Bob', 'first_name': 'Bob', 'last_name': 'Iannucci', 'position': 'sysadmin', 
# 'roles': 'system_admin system_user', 
# 
# 'notify_props': {'auto_responder_active': 'false', 
# 'auto_responder_message': 'Hello, I am out of office and unable to respond to messages.', 
# 'calls_desktop_sound': 'true', 'calls_notification_sound': 'Calm', 'channel': 'true', 
# 'comments': 'never', 'desktop': 'all', 'desktop_notification_sound': 'Upstairs', 
# 'desktop_sound': 'true', 'desktop_threads': 'all', 'email': 'true', 'email_threads': 'all', 
# 'first_name': 'false', 'highlight_keys': '', 'mention_keys': '', 'push': 'all', 'push_status': 'online', 
# 'push_threads': 'all'}, 

# 'last_password_update': 1750281423552, 'last_picture_update': 1753413261178, 
# 'locale': 'en', 
# 
# 'timezone': {'automaticTimezone': 'America/Los_Angeles', 'manualTimezone': '', 'useAutomaticTimezone': 'true'}, 

# 'remote_id': '', 'disable_welcome_email': False}




login_dict = driver.login()
# print(driver.users.get_user( user_id='me' ) )  works
# print(driver.teams.get_team_by_name( 'myTeam' )) does not know the team name

# Returns a dict
pa_team = driver.teams.get_teams()[1]

# Returns a list
channels = driver.channels.get_public_channels(pa_team['id'])
for channel in channels:
	print(channel['display_name'])