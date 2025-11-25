from threading import Thread

from alsa_midi import SequencerClient, EventType, ALSAError, SYSTEM_ANNOUNCE, WRITE_PORT

from .config import CONFIG


def midi_ports(**kwargs):
    return {f"{p.client_name.strip()}:{p.port_id}({p.name.strip()})": p
            for p in sbclient.list_ports(**kwargs)}


def midi_connect():
    """Make MIDI connections as enumerated in config"""
    conn = set(CONFIG.get("midi_connections", []))
    for i, iport in midi_ports(input=True).items():
        for o, oport in midi_ports(output=True).items():
            if {f"{i}>{o}", f"any>{o}", f"{i}>any"} & conn:
                try:
                    sbclient.subscribe_port(iport, oport)
                except ALSAError:
                    pass
            else:
                try:
                    sbclient.unsubscribe_port(iport, oport)
                except ALSAError:
                    pass


def add_rule(rule):
    pass
    
    
def clear_rules():
    pass


def send_event():
    pass


def process_events():
    while listening:
        evt = sbclient.event_input()
        if evt.type == EventType.PORT_START:
            midi_connect()


sbclient = SequencerClient("SquishBox")
sbport = sbclient.create_port("SquishBox MIDI in", caps=WRITE_PORT)
sbport.connect_from(SYSTEM_ANNOUNCE)

listening = True
Thread(target=process_events, daemon=True).start()

