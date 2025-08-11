# The Boards API is, hopefully, the same as the old Focalboard API
#
# https://htmlpreview.github.io/?https://github.com/mattermost/focalboard/blob/main/server/swagger/docs/html/index.html
#
# because Boards does not seem to appear in the Mattermost Swagger spec.


from mattermostdriver.endpoints.base import Base
from mattermostdriver.endpoints.teams import Teams

class Boards(Base):
	endpoint = "/boards"

	def create_board(self, options):
		return self.client.post(self.endpoint, options=options)

	def get_board(self, board_id):
		return self.client.get(self.endpoint + "/" + board_id)

	def get_board_by_name(self, team_id, board_name):
		return self.client.get(Teams.endpoint + "/" + team_id + "/boards/name/" + board_name)

