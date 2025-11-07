from threading import Thread

from alsa_midi import SequencerClient, EventType, ALSAError, SYSTEM_ANNOUNCE

from .config import CONFIG


def midi_ports(**kwargs):
    return {f"{p.client_name.strip()}:{p.port_id}": p
            for p in sbclient.list_ports(**kwargs)}


def midi_connect():
    """Make MIDI connections as enumerated in config"""
    for iname, iport in midi_ports(input=True).items():
        for oname, oport in midi_ports(output=True).items():
            if f"{iname}>{oname}" in CONFIG.get("midi_connections", []):
                try:
                    sbclient.subscribe_port(iport, oport)
                except ALSAError:
                    pass
            else:
                try:
                    sbclient.unsubscribe_port(iport, oport)
                except ALSAError:
                    pass


def autoconnect():
    while listening:
        evt = sbclient.event_input()
        if evt.type == EventType.PORT_START:
            midi_connect()


sbclient = SequencerClient("SquishBox")
sbport = sbclient.create_port("SquishBox MIDI 1")
sbport.connect_from(SYSTEM_ANNOUNCE)

listening = True
Thread(target=autoconnect, daemon=True).start()

