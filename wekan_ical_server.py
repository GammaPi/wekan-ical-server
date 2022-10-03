import os
import traceback
from collections import defaultdict

from wekanapi.models import Board
from wekanapi import WekanApi
from flask import Flask, request, Response
import vobject
import dateutil.parser
import time
import urllib.parse

LISTEN_HOST = os.environ.get("LISTEN_HOST", default="127.0.0.1")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", default=8091))
WEKAN_HOST = os.environ["WEKAN_HOST"]
WEKAN_USER = os.environ["WEKAN_USER"]
WEKAN_PASSWORD = os.environ["WEKAN_PASSWORD"]
CACHE_SEC = int(os.environ.get("CACHE_SEC", default=-1))  # In seconds

app = Flask(__name__)


def create_ical_event(cal, board, card, card_info):
    event = cal.add("vevent")
    event.add("summary").value = board.title + ": " + card_info["title"]
    event.add("dtstart").value = dateutil.parser.parse(card_info["dueAt"])


    if "description" in card_info:
        event.add("description").value = card_info["description"]
    event.add("url").value = WEKAN_HOST + "/b/" + board.id + "/x/" + card.id


class CachedResponse:
    def __init__(self):
        self.response = b''
        self.lastUpdateTimestamp = 0
        self.userId = None


responseCacheDict = defaultdict(CachedResponse)


def get_user_boards1(curAPI, user_id):
    boards_data = curAPI.api_call("/api/users/{}/boards".format(user_id))
    return [Board(curAPI, curBoardData) for curBoardData in boards_data]


@app.errorhandler(500)
def internal_error(exception):
    print("500 error caught")
    print(traceback.format_exc())


@app.route('/', methods=['GET'])
def do_GET():
    curTimestamp = time.time()

    username = request.args.get('username')

    if username == None:
        return Response(response='Invalid parameter for username', status=400)

    userCachedResponse = responseCacheDict[username]

    if curTimestamp - userCachedResponse.lastUpdateTimestamp > CACHE_SEC:
        userCachedResponse.lastUpdateTimestamp = curTimestamp

        wekan_api = WekanApi(
            WEKAN_HOST, {"username": WEKAN_USER, "password": WEKAN_PASSWORD}
        )

        if userCachedResponse.userId is None:
            # Find this user
            userDataList = wekan_api.api_call("/api/users")

            # Find matched username
            for userData in userDataList:
                if userData['username'] == username:
                    userCachedResponse.userId = userData['_id']
                    break
            if userCachedResponse.userId is None:
                return Response(response='No user found', status=400)

        cal = vobject.iCalendar()
        boards = None
        boards = get_user_boards1(wekan_api, userCachedResponse.userId)
        for board in boards:
            if board.title == 'Templates':
                continue
            cardslists = board.get_cardslists()
            for cardslist in cardslists:
                cards = cardslist.get_cards()
                for card in cards:
                    info = card.get_card_info()
                    if "dueAt" in info and info["dueAt"] is not None:
                        create_ical_event(cal, board, card, info)

        userCachedResponse.cacheResponse = cal.serialize().encode()
    return Response(userCachedResponse.cacheResponse, mimetype='text/calendar')


if __name__ == "__main__":
    app.run(debug=True)
