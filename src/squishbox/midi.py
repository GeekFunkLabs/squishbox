from threading import Thread

import alsa_midi

from .config import CONFIG


def midi_ports(**kwargs):
    return {f"{p.client_name.strip()}:{p.port_id}({p.name.strip()})": p
        for p in sbclient.list_ports(**{"type": alsa_midi.PortType.ANY} | kwargs)}


def midi_connect():
    """Make MIDI connections as enumerated in config"""
    conn = set(CONFIG.get("midi_connections", []))
    for src, sport in midi_ports(input=True).items():
        for dest, dport in midi_ports(output=True).items():
            if {f"{src}>{dest}", f"any>{dest}", f"{src}>any"} & conn:
                try:
                    sbclient.subscribe_port(sport, dport)
                except alsa_midi.ALSAError:
                    pass
            else:
                try:
                    sbclient.unsubscribe_port(sport, dport)
                except alsa_midi.ALSAError:
                    pass


def process_events():
    while listening:
        evt = sbclient.event_input()
        if evt.type == alsa_midi.EventType.PORT_START:
            midi_connect()


sbclient = alsa_midi.SequencerClient("SquishBox")
sbport = sbclient.create_port("SquishBox MIDI in", caps=alsa_midi.WRITE_PORT)
sbport.connect_from(alsa_midi.SYSTEM_ANNOUNCE)

listening = True
Thread(target=process_events, daemon=True).start()

