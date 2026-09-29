"""Verify raw iCoDer webhook bytes before parsing or processing. Python stdlib only.

Persist event_id with a UNIQUE constraint in the receiving application's DB
before applying effects. Return 2xx for an already processed event. Never treat
receipt as clinical approval; retrieve the result with server-side credentials.
"""
import hashlib
import hmac
import json
import time

def verify_notification(raw: bytes, signature: str, secret: str, *, timestamp=None):
    if len(raw)>8192 or len(secret)<32:raise ValueError('Invalid notification')
    try:issued,mac=signature.split('.',1);issued=int(issued)
    except (ValueError,AttributeError):raise ValueError('Invalid signature')
    current=int(time.time()) if timestamp is None else int(timestamp)
    if abs(current-issued)>300:raise ValueError('Expired signature')
    expected=hmac.new(secret.encode(),str(issued).encode()+b'.'+raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,mac):raise ValueError('Invalid signature')
    event=json.loads(raw)
    if not isinstance(event,dict) or event.get('event_id')!=str(event.get('job_id'))+':terminal':raise ValueError('Invalid event')
    return event
