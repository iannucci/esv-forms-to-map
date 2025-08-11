from mattermostdriver.endpoints.base import Base
from tests.testdata.endpoints.boards import Boards

class Cards(Base):
    endpoint = "/boards"

	# /boards/{boardID}/cards
	def create_card(self, board_id, options):
		return self.client.post(self.endpoint + "/" + board_id + "/cards", options=options)

	def get_cards_for_board(self, channel_id, params=None):
        return self.client.get(Boards.endpoint + "/" + board_id + "/cards", params=params)

