from alsa_midi import SequencerClient, EventType, SYSTEM_ANNOUCE

from threading import Thread

from .config import CONFIG


def midi_connect():
    """Make MIDI connections as enumerated in config"""
    oports = list_ports(output=True)
    iports = list_ports(input=True)
    for conn in CONFIG.get("midi_connections", []):
        oname, iname = conn.split(">")
        if oname in oports and iname in iports:
            oports[oname].connect_to(iports[iname])


def list_ports(input=None, output=None):
    return {f"{p.client_name.strip()}:{p.port_id}": p
            for p in sbclient.list_ports(input, output)}


def autoconnect():
    while listening:
        evt = sbclient.event_input()
        if evt.event = EventType.PORT_START:
            midi_connect()


sbclient = SequencerClient("SquishBox")
sbport = client.create_port("SquishBox MIDI 1")
sbport.connect_from(SYSTEM_ANNOUNCE)

listening = True
Thread(target=autoconnect, daemon=True).start()

