import os
import traceback
from collections import defaultdict

import requests
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


def create_ical_event(cal, board, cardId, title, description, startDate, dueDate):
    event = cal.add("vevent")
    event.add("summary").value = board.title + ": " + title
    assert (dueDate != None)
    if startDate:
        event.add("dtstart").value = startDate
        event.add("dtend").value = dueDate

    else:
        event.add("dtstart").value = dueDate

    if description:
        event.add("description").value = description
    event.add("url").value = WEKAN_HOST + "/b/" + board.id + "/x/" + cardId


class CachedResponse:
    def __init__(self):
        self.response = b''
        self.lastUpdateTimestamp = 0
        self.userId = None


userCachedResponse = CachedResponse()


def get_user_boards1(curAPI, user_id):
    boards_data = curAPI.api_call("/api/users/{}/boards".format(user_id))
    return [Board(curAPI, curBoardData) for curBoardData in boards_data]


@app.errorhandler(500)
def internal_error(exception):
    print("500 error caught")
    print(traceback.format_exc())


def checkCardHasField(cardInfo, name):
    if name in cardInfo and cardInfo[name] is not None:
        return cardInfo[name]
    else:
        return None


def checkCardHasCustomField(cardInfo, boardCustomFieldIdMap, name):
    hasThisFild = name in boardCustomFieldIdMap
    if not hasThisFild:
        # This field does not exist in this board
        return None
    fieldId = boardCustomFieldIdMap[name]
    customFiledDict = {i['_id']: i for i in cardInfo['customFields']}

    if fieldId not in customFiledDict:
        # This field does not exist in this card
        return None

    if 'value' in customFiledDict[fieldId]:
        return customFiledDict[fieldId]['value']
    else:
        return None


@app.route('/', methods=['GET'])
def do_GET():
    curTimestamp = time.time()

    if False or curTimestamp - userCachedResponse.lastUpdateTimestamp > CACHE_SEC:
        # print('Fetch', curTimestamp - userCachedResponse.lastUpdateTimestamp, CACHE_SEC)

        wekan_api = WekanApi(
            WEKAN_HOST, {"username": WEKAN_USER, "password": WEKAN_PASSWORD}
        )

        cal = vobject.iCalendar()
        boards = None
        boards = get_user_boards1(wekan_api, wekan_api.user_id)
        for board in boards:
            if board.title == 'Templates':
                continue
            print('Processing boards', board.title)
            boardExport = wekan_api.api_call("/api/boards/" + board.id + '/export?authToken=' + wekan_api.token)
            customFieldIdMap = {card['name']: card['_id'] for card in boardExport['customFields']}
            for card in boardExport['cards']:
                if not card['archived']:
                    dueAt = checkCardHasField(card, 'dueAt')
                    if dueAt:
                        dueAt = dateutil.parser.parse(dueAt)

                    myDueAt = checkCardHasCustomField(card, customFieldIdMap, 'MyDueAt')
                    if myDueAt:
                        dueAt = dateutil.parser.parse(myDueAt)
                    startAt = checkCardHasField(card, 'startAt')
                    if startAt:
                        startAt = dateutil.parser.parse(startAt)
                    unfinished = checkCardHasCustomField(card, customFieldIdMap, 'Unfinished')
                    endAt = checkCardHasField(card, 'endAt')
                    if endAt:
                        endAt = dateutil.parser.parse(endAt)

                    if not unfinished and dueAt is not None and endAt is None:
                        # Do not list cards that are unfinished
                        create_ical_event(cal, board, card['_id'], card['title'], card['description'], startAt, dueAt)
        userCachedResponse.lastUpdateTimestamp = curTimestamp
        userCachedResponse.cacheResponse = cal.serialize().encode()

    return Response(userCachedResponse.cacheResponse, mimetype='text/calendar')


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
