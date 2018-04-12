import urllib.request
import json
import time
import datetime
from operator import itemgetter

import boto3
from dateutil import tz
from boto3.dynamodb.conditions import Key, Attr

# --------------- Helpers that build all of the responses ----------------------$
card_title_prefix = "MyTouristOffice"
echo_ort = "Rapperswil"
response = "Ich habe noch gar nichts gesagt! Wollen Sie mich etwas fragen?"

dynamodb = boto3.resource('dynamodb', region_name='eu-west-1')


def build_speechlet_response(title, output, reprompt_text, should_end_session):
    """
    Build a speechlet JSON representation of the title, output text,
    reprompt text & end of session
    """
    return {
        'outputSpeech': {
            'type': 'PlainText',
            'text': output
        },
        'card': {
            'type': 'Simple',
            'title': card_title_prefix + " - " + title,
            'content': output.replace("MeiTouristOffice", "MyTouristOffice")
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'PlainText',
                'text': reprompt_text
            }
        },
        'shouldEndSession': should_end_session
    }


def build_response(session_attributes, speechlet_response):
    """
    Build the full response JSON from the speechlet response
    """
    return {
        'version': '1.0',
        'sessionAttributes': session_attributes,
        'response': speechlet_response
    }


# --------------- Functions that control the skill's behavior ------------------

def get_welcome_response():
    session_attributes = {}
    card_title = "Willkommen!"
    speech_output = "Willkommen bei Mei Tourist Office. Sie können mich nach " \
                    "Verbindungen mit dem Ö V oder Touristeninformationen fragen. Ich verstehe nur Hochdeutsch."

    # If the user either does not reply to the welcome message or says something
    # that is not understood, they will be prompted again with this text.

    reprompt_text = "Wollten Sie nicht etwas von mir wissen? Sie können mich " \
                    "nach Verbindungen mit dem Ö V oder Touristeninformationen fragen."
    should_end_session = False
    return build_response(session_attributes,
                          build_speechlet_response(
                              "Willkommen", speech_output, reprompt_text, should_end_session))


def get_help_response():
    card_title = "Hilfe"
    speech_output = "Sie können mich fragen, wann ein Zug an einen bestimmten Ort fährt. " \
                    "Ich kann Ihnen auch Auskunft über bestimmte Touristenaktionen geben, " \
                    "zum Beispiel welche Sehenswürdigkeiten es in " + echo_ort + " gibt."
    should_end_session = True
    return build_response({}, build_speechlet_response(card_title, speech_output, None, should_end_session))


def handle_session_end_request():
    card_title = "Session vorbei"
    speech_output = "Auf Wiedersehen bei MeiTouristOffice!"
    # Setting this to true ends the session and exits the skill.
    should_end_session = True
    return build_response({}, build_speechlet_response(card_title, speech_output, None, should_end_session))


def schedule_url(intent):
    url = "http://transport.opendata.ch/v1/connections?"
    destination = intent['slots']['Destination']['value']
    params = {'from': echo_ort, 'to': destination, 'limit': 3}

    url += urllib.parse.urlencode(params)
    return url


def scheduling(intent):
    global response
    skipped = False
    data = {}

    destination = intent['slots']['Destination']['value']

    if destination.casefold() == echo_ort.casefold():
        return build_response({}, build_speechlet_response("Fahrplan nach " + echo_ort,
                                                           "Sie sind bereits hier! Bitte fragen Sie nochmal.",
                                                           "Kann ich sonst noch etwas für Sie tun?", False))

    else:
        url = schedule_url(intent)
        with urllib.request.urlopen(url) as myurl:
            data = json.loads(myurl.read().decode())
        dep_time_epoch = data["connections"][0]["sections"][0]["departure"]["departureTimestamp"]
        now_time = time.time()
        tzlocal = tz.tzoffset('CET', 3600)

        if now_time > dep_time_epoch:
            dep_time_epoch = data["connections"][1]["sections"][0]["departure"]["departureTimestamp"]
            skipped = True

        readabletime = datetime.datetime.fromtimestamp(dep_time_epoch, tzlocal).strftime('%H:%M')
        response = "Nach " + data["connections"][0]["to"]["station"]["name"]
        response += " fährt eine " + data["connections"][0]["products"][0]
        response += " um " + readabletime
        response += " auf Gleis " + data["connections"][0]["sections"][0]["departure"]["platform"]

        new_index = 2 if skipped else 1

        dep_time_epoch = data["connections"][new_index]["sections"][0]["departure"]["departureTimestamp"]
        readabletime = datetime.datetime.fromtimestamp(dep_time_epoch, tzlocal).strftime('%H:%M')

        response += " oder eine " + data["connections"][new_index]["products"][0]
        response += " um " + readabletime
        response += " auf Gleis " + data["connections"][new_index]["sections"][0]["departure"]["platform"]
        return build_response({}, build_speechlet_response("Fahrplan nach " + destination.title(), response,
                                                           "Danke für ihre Zeit und bis zum nächsten Mal!", False))


def get_db_response():
    table = dynamodb.Table('Activities')
    return table.scan(
        FilterExpression=Key('id').between(0, table.item_count - 1)
    )


def tourist_info(intent):
    global response
    name = "Hallo"
    suchobjekt = intent['slots']['Suche']['value']
    response = "FEHLER"

    # Regenaktivitaeten
    # 'Reagan' wird von Amazon Alexa im JSON input mitgegeben wenn man 'Regen' sagt.
    if suchobjekt.casefold() == 'reagan' or suchobjekt.casefold() == 'regen':
        dbresponse = get_db_response()
        response = 'Bei Regen können Sie '
        #response += "=== " + str(dbresponse) + "==="
        response += ' oder '.join(str(a['activity']) for a in dbresponse['Items'] if a.get('rain_capable'))

    # Badeorte
    elif suchobjekt.casefold() in ('baden', 'badeorte', 'badeanstalten', 'badeanstalt'):
        name = "Badeorte"
        table = dynamodb.Table('PointsOfInterest')
        dbresponse = table.scan(
            FilterExpression=Key('id').between(0, table.item_count - 1)
        )
        response = 'Baden können Sie im '
        response += ' oder im '.join(
            str(a['poi'] + ', Preis: ' + str(a['preis']) + ". ") for a in dbresponse['Items'] if
            a.get("preis") is not None)

    # Restaurants
    elif suchobjekt.casefold() == 'essen' or suchobjekt.casefold() == 'restaurant':
        name = "Restaurants"
        table = dynamodb.Table('PointsOfInterest')
        dbresponse = table.scan(
            FilterExpression=Key('id').between(0, table.item_count - 1)
        )
        response = 'Wenn sie am See essen wollen, sind Sie im '
        # for a in dbresponse['Items']:

        response += ', '.join(str(a['poi']) for a in dbresponse['Items'] if a.get('is_am_see'))
        response += ' genau richtig.'
        response += ' Ansonsten gibt es noch das '
        # for i in dbresponse['Items']:
        response += ', '.join(
            str(a['poi']) for a in dbresponse['Items'] if a.get("is_am_see") is not None and not a.get("is_am_see"))

    # Points of Interest
    elif suchobjekt.casefold() == 'attraktionen' or suchobjekt.casefold() == 'sehenswürdigkeiten':
        name = "Sehenswürdigkeiten"
        table = dynamodb.Table('PointsOfInterest')
        dbresponse = table.scan(
            FilterExpression=Key('id').between(0, table.item_count - 1)
        )
        response = 'Die Sehenswürdigkeiten der Stadt sind '
        response += ', '.join(
            str(a['poi']) for a in dbresponse['Items'] if a.get("is_am_see") is None and a.get("preis") is None)

    # Events
    elif suchobjekt.casefold() == 'events' or suchobjekt.casefold() == 'los':
        name = "Events"
        table = dynamodb.Table('Events')
        dbresponse = table.scan(
            FilterExpression=Key('id').between(0, table.item_count - 1)
        )
        response = 'Diesen Monat finden folgende Events statt: '
        # dbresponse['Items'].sort(key=lambda el: el['datum'])
        dbresponse['Items'].sort(key=itemgetter('datum'))
        response += ', '.join(f'Am {a["datum"]} {a["event"]}' for a in dbresponse['Items'])

    # Winter
    elif suchobjekt.casefold() == 'winter' or suchobjekt.casefold() == 'schnee':
        name = "Winteraktivitäten"
        table = dynamodb.Table('Activities')
        dbresponse = table.scan()
        response = 'Im Winter können Sie folgendes tun: '
        response += ', '.join(str(a["activity"]) for a in dbresponse['Items'] if a.get("winter"))

    # Reden
    return build_response({}, build_speechlet_response(name, response, "Danke für ihre Zeit und bis zum nächsten Mal!",
                                                       False))


def repeat():
    global response
    return build_response({},
                          build_speechlet_response("Hallo", response, "Danke für ihre Zeit und bis zum nächsten Mal!",
                                                   False))


def danke():
    return build_response({},
                          build_speechlet_response("Auf Wiedersehen!", "Danke für ihre Zeit und bis zum nächsten Mal!",
                                                   "Danke für ihre Zeit und bis zum nächsten Mal!", True))


# --------------- Events ------------------

def on_session_started(session_started_request, session):
    """ Called when the session starts """
    print("on_session_started requestId=" + session_started_request['requestId']
          + ", sessionId=" + session['sessionId'])


def on_launch(launch_request, session):
    """ Called when the user launches the skill without specifying what they want """
    print("on_launch requestId=" + launch_request['requestId'] +
          ", sessionId=" + session['sessionId'])
    # Dispatch to your skill's launch
    return get_welcome_response()


def on_intent(intent_request, session):
    """ Called when the user specifies an intent for this skill """
    print("on_intent requestId=" + intent_request['requestId'] +
          ", sessionId=" + session['sessionId'])

    intent = intent_request['intent']
    intent_name = intent_request['intent']['name']

    # Dispatch to your skill's intent handlers
    intent_handlers = {
        "Schedule": lambda: scheduling(intent),
        "Tourist": lambda: tourist_info(intent),
        "Repeat": repeat,
        "Danke": danke,
        "AMAZON.HelpIntent": get_help_response,
        "AMAZON.CancelIntent": handle_session_end_request,
        "AMAZON.StopIntent": handle_session_end_request
    }

    try:
        intent_handler = intent_handlers[intent_name]
    except KeyError:
        raise ValueError("Invalid intent")

    return intent_handler()


def on_session_ended(session_ended_request, session):
    """ Called when the user ends the session. Is not called when the skill returns should_end_session=true """
    print("on_session_ended requestId=" + session_ended_request['requestId'] +
          ", sessionId=" + session['sessionId'])


# --------------- Main handler ------------------

def lambda_handler(event, context):
    """ Route the incoming request based on type (LaunchRequest, IntentRequest,
    etc.) The JSON body of the request is provided in the event parameter.
    """
    print(event)
    if event['session']['new']:
        on_session_started({'requestId': event['request']['requestId']},
                           event['session'])

    request_handlers = dict(
        LaunchRequest=lambda: on_launch(event['request'], event['session']),
        IntentRequest=lambda: on_intent(event['request'], event['session']),
        SessionEndedRequest=lambda: on_session_ended(event['request'], event['session']),
    )

    request_type = event['request']['type']
    return request_handlers[request_type]()
