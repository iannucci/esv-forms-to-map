from mattermostdriver.endpoints.base import Base

class Boards(Base):
    endpoint = "/boards"

    def create_board(self, options):
        return self.client.post(self.endpoint, options=options)

