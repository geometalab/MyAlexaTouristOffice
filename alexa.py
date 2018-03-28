import urllib.request, json, time, datetime
from dateutil import tz
import boto3
from boto3.dynamodb.conditions import Key, Attr
# --------------- Helpers that build all of the responses ----------------------$
CardTitlePrefix = "MyTouristOffice"
ort = "Rapperswil"
destination = ""
i = 0


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            if o % 1 > 0:
                return float(o)
            else:
                return int(o)
        return super(DecimalEncoder, self).default(o)

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
            'title': CardTitlePrefix + " - " + title,
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
    speech_output = "Willkommen bei MeiTouristOffice. Sie können mich nach "\
    "Zugverbindungen oder Touristeninformationen fragen."
    
    # If the user either does not reply to the welcome message or says something
    # that is not understood, they will be prompted again with this text.
    
    reprompt_text = "Wollten Sie nicht etwas von mir wissen? Sie können mich " \
    "nach Zugverbindungen oder Touristeninformationen fragen."
    should_end_session = False
    return build_response(session_attributes, build_speechlet_response(card_title, speech_output, reprompt_text, should_end_session))
    
def get_help_response():
    card_title = "Hilfe"
    speech_output = "Sie können mich fragen, wann ein Zug an einen bestimmten Ort fährt. Ich kann Ihnen auch Auskunft"\
    " über bestimmte Touristenaktionen geben, zum Beispiel welche Sehenswürdigkeiten es in Rapperswil gibt."
    should_end_session = True
    return build_response({}, build_speechlet_response(card_title, speech_output, None, should_end_session))

def handle_session_end_request():
    card_title = "Session vorbei"
    speech_output = "Auf Wiedersehen bei MeiTouristOffice!"
    # Setting this to true ends the session and exits the skill.
    should_end_session = True
    return build_response({}, build_speechlet_response(card_title, speech_output, None, should_end_session))
   
def buildurl(intent):
    url = "http://transport.opendata.ch/v1/connections?"
    destination = intent['slots']['Destination']['value']
    params = {'from' : 'Rapperswil', 'to' : destination, 'limit' : 3}
    
    url += urllib.parse.urlencode(params)
    return url
    
def scheduling(intent):
    skipped = False
    new_index = 1
    data = {}
    
    if 'Destination' in intent['slots']:
        destination = intent['slots']['Destination']['value']
        
    if(destination.lower() == "rapperswil"):
        return build_response({}, build_speechlet_response("Fahrplan nach Rapperswil", "Sie sind bereits hier! Bitte fragen Sie nochmal.", "Kann ich sonst noch etwas für Sie tun?", False))
    
    else:
        url = buildurl(intent)
        with urllib.request.urlopen(url) as myurl:
            data = json.loads(myurl.read().decode())
        # Vorbereitung sprachliche Ausgabe des Messwertes
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
        
        if skipped:
            new_index = 2
        else:
            new_index = 1
            
        dep_time_epoch = data["connections"][new_index]["sections"][0]["departure"]["departureTimestamp"]
        readabletime = datetime.datetime.fromtimestamp(dep_time_epoch, tzlocal).strftime('%H:%M')
        
        response += " oder eine " + data["connections"][new_index]["products"][0]
        response += " um " + readabletime
        response += " auf Gleis " + data["connections"][new_index]["sections"][0]["departure"]["platform"]
        return build_response({}, build_speechlet_response("Fahrplan nach " + destination.title(), response, "Danke für ihre Zeit und bis zum nächsten Mal!", False))
        
def tourist_info(intent):
    suchObjekt = intent['slots']['Suche']['value']
    response = "FEHLER"
    #Regenaktivitaeten
    if suchObjekt.lower() == 'reagan':
        table = dynamodb.Table('Activities')
        dbresponse = table.scan(
            FilterExpression=Key('id').between(0, table.item_count-1)
        )
        response = 'Bei Regen können Sie '
        response+=' oder '.join(str(i['activity']) for i in dbresponse['Items'])
        
    #Badeorte
    elif suchObjekt.lower() == 'baden' or suchObjekt.lower() == 'badeorte':
        table = dynamodb.Table('Badeorte')
        dbresponse = table.scan(
            FilterExpression=Key('id').between(0, table.item_count-1)
        )
        response = 'Baden können Sie im '
        response+=' oder im '.join(str(i['badeort']) for i in dbresponse['Items'])

    #Restaurants
    elif suchObjekt.lower() == 'essen' or suchObjekt.lower() == 'restaurant':
        table = dynamodb.Table('Essen')
        dbresponse = table.scan(
            FilterExpression=Key('id').between(0, table.item_count-1)
        )
        response = 'Wenn sie am See essen wollen, sind Sie im '
        for i in dbresponse['Items']:
            if str(i['is_am_see']) == 'True':
                response+=' ' + str(i['restaurant'])
                response+=', '
        response += ' genau richtig.'
        response += ' Ansonsten gibt es noch das'
        for i in dbresponse['Items']:
            if str(i['is_am_see']) == 'False':
                response+=' ' + str(i['restaurant'])
                if not i['id'] == table.item_count-1:
                    response+=', '
                    
    #Points of Interest
    elif suchObjekt.lower() == 'attraktionen' or suchObjekt.lower() == 'sehenswürdigkeiten':
        table = dynamodb.Table('PointsOfInterest')
        dbresponse = table.scan(
            FilterExpression=Key('id').between(0, table.item_count-1)
        )
        response = 'Die Sehenswürdigkeiten der Stadt sind '
        response+=', '.join(str(i['poi']) for i in dbresponse['Items'])
                
    #Events
    elif suchObjekt.lower() == 'events' or suchObjekt.lower() == 'los':
        table = dynamodb.Table('Events')
        dbresponse = table.scan(
            FilterExpression=Key('id').between(0, table.item_count-1)
        )
        response = 'Diesen Monat finden folgende Events statt: '
        dbresponse['Items'].sort(key=lambda el: el['datum'])
        #for i in dbresponse['Items']:
        #    response += 'Am ' + str(i['datum']) + ' ' + str(i['event']) + ', '
        response+=', '.join(f'Am {i["datum"]} {i["event"]}' for i in dbresponse['Items'])
        
    #Winter
    elif suchObjekt.lower() == 'winter' or suchObjekt.lower() == 'schnee':
        table = dynamodb.Table('Winter')
        dbresponse = table.scan(
            FilterExpression=Key('id').between(0, table.item_count-1)
        )
        response = 'Im Winter können Sie folgendes tun: '
        response+=', '.join(str(i["winter"]) for i in dbresponse['Items'])
    
    #Reden
    return build_response({}, build_speechlet_response("Hallo", response, "Danke für ihre Zeit und bis zum nächsten Mal!", False))

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
    if intent_name == "Schedule":
        return scheduling(intent)
    elif intent_name == "Tourist":
        return tourist_info(intent)
    elif intent_name == "AMAZON.HelpIntent":
        return get_help_response()
    elif intent_name == "AMAZON.CancelIntent" or intent_name == "AMAZON.StopIntent":
        return handle_session_end_request()
    else:
        raise ValueError("Invalid intent")
        
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
    if event['request']['type'] == "LaunchRequest":
        return on_launch(event['request'], event['session'])
    elif event['request']['type'] == "IntentRequest":
        return on_intent(event['request'], event['session'])
    elif event['request']['type'] == "SessionEndedRequest":
        return on_session_ended(event['request'], event['session'])
