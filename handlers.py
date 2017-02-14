'''
Module contains two classes of handlers. In Handlers class
is placed all handling functionality. Handle class is additional

Vars:
    TYPES (dict) If names of package types will be changed then it
                 needs to be changed in this dictionary
'''


import copy
import logging


LOGGER = logging.getLogger(__name__)
TYPES = {
    'connect': 'connect',
    'disconnect': 'disconnect',
    'ping': 'ping',
    'get_chat_info': 'get_chat_info',
    'chat_info': 'chat_info',
    'relay': 'relay',
    'find_insert_place': 'find_insert_place',
    'insert_place': 'insert_place',
    'downtype': 'downtype'
}


class Handlers:
    def __init__(self, peer):
        self._peer = peer
        self._create_table()

    def __getitem__(self, key):
        return self._table[key]

    def _create_table(self):
        '''
        Create table of handlers. In all below functions second parameter
        is "rpacket" -- response packet.
        '''

        self._table = {
            TYPES['connect']: Handle(self._connect),
            TYPES['disconnect']: Handle(self._disconnect),
            TYPES['ping']: Handle(self._ping),
            TYPES['get_chat_info']: Handle(self._get_chat_info),
            TYPES['chat_info']: Handle(self._chat_info),
            TYPES['relay']: Handle(self._relay),
            TYPES['find_insert_place']: Handle(self._find_insert_place),
            TYPES['insert_place']: Handle(self._insert_place)
        }

    def _connect(self, rpacket):
        pass

    def _disconnect(self, rpacket):
        pass

    def _ping(self, rpacket):
        pass

    def _get_chat_info(self, rpacket):
        '''
        If packet's type is 'get_chat_info' then new user want to
        fetch information about chat. In this case we should send it to
        him
        '''

        packet = self._peer._create_packet('chat_info', self._peer._id,
                                           -1, rpacket['to_host'],
                                           rpacket['from_host'])
        connected = []
        for host, data in self._peer.connected.items():
            _data = copy.copy(data)
            _data['host'] = host
            connected.append(_data)
        packet['connected'] = connected

        print('[+] get_chat_info: Created response packet: %s' % packet)
        return packet

    def _chat_info(self, rpacket):
        '''
        Process information that we received via get_chat_info request
        '''

        ids = set()
        print('[+] chat_info: Fetched list of connected hosts: {}'
              .format(rpacket['connected']))
        for host_data in rpacket['connected']:
            host = tuple(host_data['host'])
            _id = host_data['id']
            username = host_data['username']

            self._peer._add_host(host, {'id': _id, 'username': username})
            self._peer.id2host[_id] = host

            ids.add(_id)
        own_id = self._peer.generate_id(ids)
        print('[+] Chosen id of current host: %d' % own_id)
        self._peer._id = own_id

    def _find_insert_place(self, rpacket, client_id=None, client_host=None,
                           relay=False):
        ''' Find node in the chat's tree for connecting client '''

        if (client_id and client_host) is None:
            client_id = rpacket['from_id']
            client_host = rpacket['from_host']

        # If node position in subtree of current machine
        if self._peer.low_bound < client_id < self._peer.up_bound:
            # if less than current node
            if client_id < self._peer._id:
                return self.__process_child('left', rpacket, relay)
            else:
                return self.__process_child('right', rpacket, relay)
        else:
            # Else in another subtree of parent
            if not relay:
                self._make_relay(rpacket)
        return False

    def __process_child(self, child_side, packet, relay=False):
        if child_side == 'left':
            node = self._peer._left
            neighbor = self._peer._right
            up_bound = self._peer._id
            low_bound = self._peer.low_bound
        else:
            node = self._peer._right
            neighbor = self._peer._left
            up_bound = self._peer.up_bound
            low_bound = self._peer._id

        if node is None:
            place_info = self._form_place(child_side, neighbor,
                                          self._peer._host, up_bound, low_bound)
            if child_side == 'left':
                self._peer._left = client_id
            else:
                self._peer._right = client_id
            packet = self.reverse_packet(TYPES['insert_place'])
            packet['place_info'] = place_info
            print('[+] Finded node location: {} for {}'
                  .format(place_info, place_info['from_host']))
            self._peer.send_message(client_host, packet)
            return True
        else:
            # Else we should relay it
            if not relay:
                self._make_relay(packet)
        return False

    def _make_relay(self, packet):
        packet['downtype'] = packet['type']
        packet['type'] = 'relay'
        packet['client_id'] = packet['from_id']
        packet['client_host'] = packet['from_host']
        self._relay(packet)

    def _form_place(self, side, neighbor, conn_host, up_bound, low_bound):
        return { 'side': side,
                 'neighbor': neighbor,
                 'conn_host': conn_host,
                 'up_bound': up_bound,
                 'low_bound': low_bound }

    def reverse_packet(self, packet, _type):
        return self._peer._create_packet(_type, packet['to_id'],
                                         packet['from_id'], packet['to_host'],
                                         packet['from_host'])

    def _insert_place(self, rpacket):
        pass

    def _relay(self, rpacket):
        '''
        Relay message to right direction
        '''

        if rpacket['downtype'] == 'find_insert_place':
            check_packet = copy.copy(rpacket)
            check_packet['type'] = check_packet['downtype']
            del check_packet['downtype']

            # If current machine have node position for asking client
            if self._find_insert_place(rpacket, relay=True):
                self._insert_place(rpacket)
                return

        # If receiver is found
        if rpacket['to_host'] == self._peer._host:
            rpacket['type'] = rpacket['downtype']
            del rpacket['downtype']
            self._table[rpacket['type']].handle(rpacket)
            return

        to_id = rpacket['to_id']
        host = None
        # Receiver in our subtree
        if self._peer.low_bound < to_id < self._peer.up_bound:
            if to_id < self._peer._id:
                host = self._peer._left
            else:
                host = self._peer._right
        else:
            host = self._peer._parent
        rpacket['from_host'] = self._peer._host
        rpacket['from_id'] = self._peer._id
        rpacket['to_host'] = host
        rpacket['to_id'] = self._peer.connected[host]['id']
        print('[*] Relaying packet {} to {}'
              .format(rpacket, rpacket['to_host']))
        self._peer.send_message(host, rpacket)


class Handle:
    def __init__(self, proc_func):
        self._proc_func = proc_func

    def handle(self, packet):
        return self._proc_func(packet)
