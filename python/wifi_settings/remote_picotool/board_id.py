"""
Functions which search for compatible hardware on a network.

Copyright (c) 2026 Jack Whitham

SPDX-License-Identifier: BSD-3-Clause
"""

from ..exceptions import *
from .remote_picotool_cfg import RemotePicotoolCfg
from ..configuration import BOARD_ID_SIZE

import asyncio 
import re
import socket
import typing

RESPONDER_REQUEST_MAGIC =  b"PWS?"
RESPONDER_REPLY_MAGIC =    b"PWS:"

async def get_pico_address_for_board_id(
        board_id: typing.Optional[str],
        config: RemotePicotoolCfg) -> str:
    """Get a Pico IP address by searching for a board.

    See get_list_of_boards_for_board_id for information about the search.
    This function restricts the search to finding only one board."""

    matches = await get_list_of_boards_for_board_id(board_id, config)
    if len(matches) == 0:
        raise RemoteError(f"No Pico W devices responded to the board id search '{board_id}'")
    if len(matches) != 1:
        raise RemoteError(f"Multiple ({len(matches)}) Pico W devices responded to board id search '{board_id}', " +
                    "please use a more precise search criteria with --id, use the --address option, " +
                    "or 'list' to list the ID of all boards.")
    return list(matches.keys())[0]

async def get_list_of_boards_for_board_id(board_id: typing.Optional[str],
        config: RemotePicotoolCfg) -> typing.Dict[str, str]:
    """Get a list of boards that match a given id.

    This is done by broadcasting a UDP packet containing a request,
    then waiting for --search-timeout seconds while collecting replies.

    Broadcast is used because multicast does not work reliably with typical home WiFi hotspots.

    The OS requires broadcast packets to be sent from a specific network interface.
    The IP address of a suitable interface can be specified with --search-interface;
    otherwise, the interface associated with the default route is used.
    """

    # Check board ID is valid. You can specify all or part of a board ID,
    # so the board ID can be 0 to 16 hex digits.
    if not board_id:
        board_id = ""
    board_id = board_id.upper()

    if ((len(board_id) > (BOARD_ID_SIZE * 2))
    or (re.match(r"^[0-9A-F]*$", board_id) is None)):
        raise LocalError(f"The board --id parameter must be a hex value with up to {BOARD_ID_SIZE * 2} digits")

    # Find a network interface to be used for the search.
    search_interface = config.search_interface
    if not search_interface:
        # Determine which network interface is used for the default route, by considering what
        # happens if we wish to send a packet to an address on the Internet (e.g. "1.0.0.0").
        # No packets are actually sent.
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            s.connect(("1.0.0.0", 9))
            (search_interface, _) = s.getsockname()
        except Exception:
            raise LocalError("Unable to determine which network interface can be used for "
                        + "broadcast, please use --search-interface") from None
        s.close()

    # Set up the search
    matches: typing.Dict[str, str] = {}
    expected_size = (len(RESPONDER_REPLY_MAGIC) + (BOARD_ID_SIZE * 2))
    request = RESPONDER_REQUEST_MAGIC + board_id.encode("ascii")
    broadcast = "255.255.255.255"

    class ReceivedBoardIDProtocol(asyncio.DatagramProtocol):
        def datagram_received(self, reply: bytes, addr: typing.Any) -> None:
            # reply might contain a board ID (but could be anything)
            if len(reply) < expected_size:
                return
            if not reply.startswith(RESPONDER_REPLY_MAGIC):
                return

            received_board_id = reply[len(RESPONDER_REPLY_MAGIC):expected_size].decode("ascii", errors="ignore")
            if len(received_board_id) != (BOARD_ID_SIZE * 2):
                return

            if str(board_id) not in received_board_id:
                return

            matches[addr[0]] = received_board_id

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except Exception:
        # SO_REUSEPORT isn't supported on every OS
        pass
    try:
        s.bind((search_interface, 0))
    except Exception:
        raise LocalError(f"Unable to bind to '{search_interface}' for broadcast") from None

    transport, protocol = await asyncio.get_event_loop().create_datagram_endpoint(
        protocol_factory=ReceivedBoardIDProtocol, sock=s)

    # Transmit the request
    transport.sendto(request, addr=(broadcast, config.port))
    # Await replies
    await asyncio.sleep(config.search_timeout)
    transport.close()
    # Return a mapping of { address -> board_id }
    return matches
