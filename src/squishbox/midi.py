from threading import Thread

import alsa_midi

from .config import CONFIG


def _connect(client, src, dest):
    try:
        client.subscribe_port(src, dest)
    except alsa_midi.ALSAError as e:
        pass


def _disconnect(client, src, dest):
    try:
        client.unsubscribe_port(src, dest)
    except alsa_midi.ALSAError:
        pass


class SquishBoxMidi:
    """ALSA sequencer wrapper for SquishBox

    - creates in/out ports
    - automatically connects devices specified in midi_connections
    - provides methods for querying ports, sending messages
    """

    def __init__(self):
        self._client = alsa_midi.SequencerClient("SquishBox")
        self._outport = self._client.create_port(
            "SquishBox MIDI out",
            caps=alsa_midi.READ_PORT,
        )
        self._inport = self._client.create_port(
            "SquishBox MIDI in",
            caps=alsa_midi.WRITE_PORT,
        )
        self._inport.connect_from(alsa_midi.SYSTEM_ANNOUNCE)
        self._wrappers = {}
        self._listening = True
        self._thread = Thread(target=self._process, daemon=True)
        self._thread.start()


    def _process(self):
        while self._listening:
            evt = self._client.event_input(timeout=0.1)
            if evt and evt.type == alsa_midi.EventType.PORT_START:
                self.refresh()

    def close(self):
        self._listening = False
        self._thread.join()
        for wrapper in self._wrappers.values():
            wrapper.close()
        self._client.close()

    def ports(self, **kwargs):
        """Return a dictionary of ports keyed by port info string
        """
        return {
            f"{p.client_name.strip()}:{p.port_id}({p.name.strip()})": p
            for p in self._client.list_ports(**{
                "type": alsa_midi.PortType.ANY,
                "include_no_export": False,
                "include_midi_through": False,
            } | kwargs)
        }

    def refresh(self):
        """Reestablish MIDI connection graph"""
        conn = set(CONFIG.get("midi_connections", []))
        for src, sport in self.ports(input=True).items():
            for dest, dport in self.ports(output=True).items():
                allowed = {f"{src}>{dest}", f"any>{dest}", f"{src}>any", "any>any"}
                wrapper = self._wrappers.get(dest)
                if allowed & conn and src != dest:
                    if wrapper:
                        _disconnect(self._client, sport, dport)
                        _connect(wrapper._client, sport, wrapper._inport)
                    else:
                        _connect(self._client, sport, dport)
                else:
                    _disconnect(self._client, sport, dport)
                    if wrapper:
                        _disconnect(wrapper._client, sport, wrapper._inport)

    def send(self, evt):
        """Send a MIDI message triggered by a SquishBox button/control"""
        self._client.event_output(evt)
        self._client.drain_output()

    def wrap(self, portname):
        """Wrap a port with a hidden sequencer client"""
        port = self.ports().get(portname)
        if not port:
            return None
        self._wrappers[portname] = SquishBoxMidiWrapper(port)
        return self._wrappers[portname]


class SquishBoxMidiWrapper:
    """A container for a hidden ALSA client with in/out ports"""

    def __init__(self, port):
        self._client = alsa_midi.SequencerClient(
            "wrap_" + port.client_name.strip()
        )
        self._inport = self._client.create_port(
            "in",
            caps=alsa_midi.WRITE_PORT | alsa_midi.PortCaps.NO_EXPORT,
            type=alsa_midi.PortType.MIDI_GENERIC,
        )
        self._outport = self._client.create_port(
            "out",
            caps=alsa_midi.READ_PORT | alsa_midi.PortCaps.NO_EXPORT,
            type=alsa_midi.PortType.MIDI_GENERIC,
        )
        _connect(self._client, self._outport, port)

    def close(self):
        self._client.close()

    def send(self, evt):
        self._client.event_output(
            evt,
            port=self._outport,
            dest=alsa_midi.ALL_SUBSCRIBERS,
        )
        self._client.drain_output()

    def receive(self, **kwargs):
        return self._client.event_input(**kwargs)
