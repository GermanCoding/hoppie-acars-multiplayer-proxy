#!/usr/bin/env python3
import os
import threading
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import PlainTextResponse
import httpx
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field

app = FastAPI(title="Hoppie ACARS Multiplayer Proxy", version="0.1")

UPSTREAM = os.getenv("HOPPIE_UPSTREAM", "https://www.hoppie.nl/acars/system/connect.html")
MAIN_LOGON = os.getenv("HOPPIE_LOGON")
if not MAIN_LOGON:
    raise ValueError("HOPPIE_LOGON environment variable not set")
ALLOWED_LOGONS = os.getenv("ALLOWED_LOGONS", "").split(",")
MESSAGE_LOCK = threading.Lock()

@dataclass
class IncomingMessage:
    data: str
    seen_logons: Set[str] = field(default_factory=set)

@dataclass
class OutgoingCPDLCMessage:
    payload: str
    from_callsign: str
    to_callsign: str
    sending_logon: str
    upstream_response: str

@dataclass
class CallsignData:
    last_poll: Optional[datetime] = None
    messages: List[IncomingMessage] = field(default_factory=list)

class HoppieError(Exception):
    """Error returned by Hoppie"""
    
    def __init__(self, error_text: str):
        self.error_text = error_text
        super().__init__(self.error_text)
    
    def __str__(self):
        return self.error_text

RECEIVED_MESSAGES: Dict[str, CallsignData] = {}
SEND_MESSAGES: List[OutgoingCPDLCMessage] = []

def is_poll_needed(last_poll: Optional[datetime], timeout_seconds: int = 45) -> bool:
    """Check if a new poll is needed based on the last poll time."""
    if last_poll is None:
        return True
    return last_poll < datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)

def clean_received_messages():
    for callsign, data in list(RECEIVED_MESSAGES.items()):
        data.messages = [msg for msg in data.messages if len(msg.seen_logons) < len(ALLOWED_LOGONS)]
        if not data.messages:
            del RECEIVED_MESSAGES[callsign]

def clean_send_messages():
    SEND_MESSAGES[:] = SEND_MESSAGES[-20:]  # Keep only the last 20 messages

def response(content: str) -> PlainTextResponse:
    print(f"DEBUG: responding with: {content}")
    return PlainTextResponse(content=content, status_code=200, media_type="text/html")

def poll_upstream(callsign: str):
    """
    Poll the upstream server for new messages.
    """
    clean_received_messages()
    params = {
        "from": callsign,
        "logon": MAIN_LOGON,
        "type": "poll",
        "to": "SERVER"
    }
    try:
        with httpx.Client() as client:
            resp = client.get(UPSTREAM, params=params)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail="Upstream error")
            text = resp.text
            if text.startswith("error"):
                raise HoppieError(error_text=text)
            elif text.startswith("ok"):
                def extract_messages(s: str):
                    messages = []
                    current_message = ""
                    current_depth = 0
                    for char in s:
                        if char == '{':
                            current_depth += 1
                        if current_depth > 0:
                            current_message += char
                        if char == '}':
                            current_depth -= 1
                            if current_depth == 0:
                                messages.append(current_message)
                                current_message = ""
                    return messages
                messages = extract_messages(text)
            else:
                raise HTTPException(status_code=502, detail=f"Unexpected response: {text}")
            
            if callsign not in RECEIVED_MESSAGES:
                RECEIVED_MESSAGES[callsign] = CallsignData()
            
            data = RECEIVED_MESSAGES[callsign]
            data.last_poll = datetime.now(timezone.utc)
            for message in messages:
                data.messages.append(IncomingMessage(
                    data=message,
                    seen_logons=set()
                ))
    except (httpx.RequestError, HTTPException) as e:
        raise HTTPException(status_code=502, detail=f"Upstream request failed: {e}")
    
def send_upstream(callsign_from: str | None, callsign_to: str | None, packet: str | None, packet_type: str | None) -> str:
    """
    Send a message to upstream.
    """
    params = {
        "logon": MAIN_LOGON,
        "from": callsign_from,
        "to": callsign_to,
        "type": packet_type,
        "packet": packet
    }
    try:
        with httpx.Client() as client:
            resp = client.get(UPSTREAM, params=params)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail="Upstream error")
            return resp.text
    except (httpx.RequestError | HTTPException) as e:
        return "error {{{e}}}"

def handle_poll(callsign: str, logon: str) -> PlainTextResponse:
    try:
        try:
            if callsign not in RECEIVED_MESSAGES:
                poll_upstream(callsign)
            elif is_poll_needed(RECEIVED_MESSAGES[callsign].last_poll):
                poll_upstream(callsign)
        except HoppieError as e:
            return response(e.error_text)

        messages = [msg for msg in RECEIVED_MESSAGES[callsign].messages if logon not in msg.seen_logons]
        for msg in messages:
            msg.seen_logons.add(logon)

        if not messages:
            return response("ok")
        else:
            return response("ok " + " ".join(msg.data for msg in messages) + " ")
    except HTTPException as e:
        return response(f"error {{{e.detail}}}")
    
def handle_telex_cpdlc(logon: str, callsign_from: str, callsign_to: str, packet: str, packet_type: str) -> PlainTextResponse:
    clean_send_messages()
    for previous_message in SEND_MESSAGES:
        if (previous_message.from_callsign == callsign_from and previous_message.to_callsign == callsign_to and
            previous_message.payload == packet):
            if previous_message.sending_logon == logon:
                print(f"Debug: Same station sent duplicate message: {previous_message}")
                #print("Debug: Sending anyway...")
                #return response(send_upstream(callsign_from, callsign_to, packet, packet_type))
            else:
                print(f"Debug: Duplicate message from synchronized CPDLC client, skipping")
            return response(previous_message.upstream_response)   
    print(f"Debug: Sending new CPDLC message from {callsign_from} to {callsign_to}: {packet}")
    upstream_response = send_upstream(callsign_from, callsign_to, packet, packet_type)
    new_message = OutgoingCPDLCMessage(
        from_callsign=callsign_from,
        to_callsign=callsign_to,
        payload=packet,
        sending_logon=logon,
        upstream_response=upstream_response
    )
    SEND_MESSAGES.append(new_message)
    return response(upstream_response)
    
def handle_fallback(callsign_from: str | None, callsign_to: str | None, packet: str | None, packet_type: str) -> PlainTextResponse:
    """
    Fallback handler for unknown/basic message types.
    """
    return response(send_upstream(callsign_from, callsign_to, packet, packet_type))

@app.api_route("/acars/system/connect.html", methods=["GET", "POST"])
def connect(
    logon: str | None = Query(None, alias="logon"),
    from_callsign: str | None = Query(None, alias="from"),
    to_callsign: str | None  = Query(None, alias="to"),
    msg_type: str | None = Query(None, alias="type"),
    packet: str | None = Query(None, alias="packet")
):
    with MESSAGE_LOCK:
        print(f"Got request with logon={logon} from={from_callsign} to={to_callsign} type={msg_type} packet={packet}")

        if not logon and not from_callsign and not to_callsign and not msg_type and not packet:
            return response("error {no parameters given}")

        if not logon:
            return response("error {no logon given}")

        # Vulnerable to timing side channels, but most of this stuff is plain HTTP anyway... :(
        if logon not in ALLOWED_LOGONS:
            print(f"DEBUG: Valid logons {ALLOWED_LOGONS}, {logon} not in them")
            return response("error {invalid logon code}")

        if not msg_type:
            return response("error {no packet type given}")
        
        match msg_type:
            case "poll":
                if not from_callsign:
                    return response("error {from callsign required for polling}")
                return handle_poll(from_callsign, logon)
            case "cpdlc" | "telex":
                if not from_callsign or not to_callsign or not packet:
                    return response("error {from/to callsigns and packet payload required for sending cpdlc/telex}")
                return handle_telex_cpdlc(logon, from_callsign, to_callsign, packet, msg_type)
            case _:
                return handle_fallback(from_callsign, to_callsign, packet, msg_type)
