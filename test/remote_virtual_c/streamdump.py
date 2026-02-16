"""Decrypt a remote_picotool data stream given the correct update_secret.

To obtain a suitable dump file:

1.  use Wireshark to record all network traffic.
    Find a packet from the TCP stream used by the remote_picotool tool protocol.
    Then open the menu: Analyze -> Follow -> TCP Stream
    Choose Entire conversation (... bytes)
    Choose Show data as: Hex Dump
    Click Save as... -> text file
    Use the --wireshark option to read the text file

2.  record all data sent via TCP (just the payloads, no headers) in two binary
    files with names like "tcp_send_1" and "tcp_recv_1".
    Put these in the same directory.
    Use --binary tcp_send_1 to read both files.
    (This format is used by fake_lwip.c when running test cases.)

Note: remote_picotool's protocol doesn't provide perfect forward secrecy, i.e. it's
possible to recover all data from a network packet recording if the update_secret
is known. This program does exactly that.
"""

import hashlib, hmac, struct, typing, argparse, pathlib, sys
import pyaes # type: ignore
import wifi_settings


from wifi_settings import aes
from wifi_settings.aes import AES_BLOCK_SIZE
from wifi_settings.protocol import HEADER_STRUCT, DATA_HASH_SIZE, HEADER_DATA_HASH_OFFSET
MAX_DATA_SIZE = 4096

def decoder_wireshark(secret_hash: bytes, conversation: typing.IO) -> None:
    # Split up the lines in the conversation
    server_to_client = b""
    client_to_server = b""
    for line in conversation:
        fields = line.split()
        assert len(fields) >= (AES_BLOCK_SIZE + 1)
        data = bytes([int(value, 16) for value in fields[1:AES_BLOCK_SIZE + 1]])
        if line.startswith(" "):
            server_to_client += data
        else:
            client_to_server += data

    return decoder(secret_hash, server_to_client, client_to_server)

def decoder_binary(secret_hash: bytes, tcp_data_file: pathlib.Path) -> None:
   
    send_file_name = tcp_data_file.parent / tcp_data_file.name.replace("recv", "send")
    recv_file_name = tcp_data_file.parent / tcp_data_file.name.replace("send", "recv")
    server_to_client = send_file_name.read_bytes()
    client_to_server = recv_file_name.read_bytes()

    return decoder(secret_hash, server_to_client, client_to_server)

def print_hex_dump(prefix: str, data: bytes) -> None:
    print(prefix, data.hex(" "), end="  ")
    for byte in data:
        if 0x20 <= byte <= 0x7e:
            print(chr(byte), end="")
        else:
            print('.', end="")
    print()

def decoder(secret_hash: bytes, server_to_client: bytes, client_to_server: bytes) -> None:
    # Skip the greeting
    assert server_to_client[0] == wifi_settings.ID_GREETING
    assert server_to_client[1] == wifi_settings.version.PROTOCOL_VERSION
    num_blocks = server_to_client[2]
    assert num_blocks >= 1
    server_to_client = server_to_client[AES_BLOCK_SIZE * num_blocks:]

    # Here is the client's request
    assert client_to_server[0] == wifi_settings.ID_REQUEST
    client_challenge = client_to_server[1:AES_BLOCK_SIZE]
    client_to_server = client_to_server[AES_BLOCK_SIZE:]

    # Here is the server's challenge
    assert server_to_client[0] == wifi_settings.ID_CHALLENGE
    server_challenge = server_to_client[1:AES_BLOCK_SIZE]
    server_to_client = server_to_client[AES_BLOCK_SIZE:]

    # Here is the client's authentication
    assert client_to_server[0] == wifi_settings.ID_AUTHENTICATION
    client_auth_expect = client_to_server[1:AES_BLOCK_SIZE]
    client_to_server = client_to_server[AES_BLOCK_SIZE:]

    # Here is the server's authentication
    assert server_to_client[0] == wifi_settings.ID_RESPONSE
    server_auth_expect = server_to_client[1:AES_BLOCK_SIZE]
    server_to_client = server_to_client[AES_BLOCK_SIZE:]
    print("Handshake messages were sent")

    # Check the authentication
    def gen_auth(session_data: bytes) -> bytes:
        return hmac.HMAC(key=secret_hash, msg=session_data, digestmod=hashlib.sha256).digest()

    if client_auth_expect != gen_auth(client_challenge + server_challenge + b"CA")[:AES_BLOCK_SIZE - 1]:
        print("Error: the update_secret used by streamdump.py does not match the one used for the recording")
        print("Do you need a different --secret?")
        sys.exit(1)

    assert server_auth_expect == gen_auth(client_challenge + server_challenge + b"SA")[:AES_BLOCK_SIZE - 1]

    # Set up encryption
    c2s_key = gen_auth(client_challenge + server_challenge + b"CK")
    s2c_key = gen_auth(client_challenge + server_challenge + b"SK")
    client_transmit = aes.AES256CBCFactory(c2s_key)
    server_transmit = aes.AES256CBCFactory(s2c_key)

    # Here is the client's confirmation
    assert client_to_server[0] == wifi_settings.ID_ACKNOWLEDGE
    client_to_server = client_to_server[AES_BLOCK_SIZE:]
    print("Handshake was ok, keys were set up")

    # Now everything will be encrypted
    while len(client_to_server) != 0:
        # Read a reply header from the client
        request_header = client_transmit.decrypt(client_to_server[:AES_BLOCK_SIZE])
        client_to_server = client_to_server[AES_BLOCK_SIZE:]

        # Decode request header
        (request_data_size, parameter,
            msg_type, request_hash) = struct.unpack(HEADER_STRUCT, request_header)
        check_request_hash = hashlib.sha256()
        check_request_hash.update(request_header[:HEADER_DATA_HASH_OFFSET])
        print("Request from client: data_size {} parameter {} msg_type {} hash {}".format(
                request_data_size, parameter, msg_type, request_hash.hex()))
        assert 0 <= request_data_size <= MAX_DATA_SIZE

        # Capture the data and print it
        while request_data_size > 0:
            data = client_transmit.decrypt(client_to_server[:AES_BLOCK_SIZE])
            client_to_server = client_to_server[AES_BLOCK_SIZE:]

            print_hex_dump("   >>", data)
            check_request_hash.update(data[:min(AES_BLOCK_SIZE, request_data_size)])
            request_data_size -= AES_BLOCK_SIZE

        request_hash_expect = check_request_hash.digest()[:DATA_HASH_SIZE] 
        if request_hash_expect == request_hash:
            print("   Request data hash is ok")
        else:
            print("   Request data hash is bad, calculated as", request_hash_expect.hex())

        if len(server_to_client) == 0:
            break

        # Server should respond with a reply header
        reply_header = server_transmit.decrypt(server_to_client[:AES_BLOCK_SIZE])
        server_to_client = server_to_client[AES_BLOCK_SIZE:]
            
        # Decode reply header
        (reply_data_size, parameter, msg_type, reply_hash) = struct.unpack(HEADER_STRUCT, reply_header)
        check_reply_hash = hashlib.sha256()
        check_reply_hash.update(reply_header[:HEADER_DATA_HASH_OFFSET])
        print("Reply from server: data_size {} parameter {} msg_type {} hash {}".format(
                reply_data_size, parameter, msg_type, reply_hash.hex()))
        assert 0 <= reply_data_size <= MAX_DATA_SIZE
        received_data_size = 0

        # Capture the data and print it
        while reply_data_size > 0:
            if len(server_to_client) < AES_BLOCK_SIZE:
                print("  Reply is truncated: short block size {} with reply_data_size {} received_data_size {}".format(
                        len(server_to_client), reply_data_size, received_data_size))
                break
            data = server_transmit.decrypt(server_to_client[:AES_BLOCK_SIZE])
            server_to_client = server_to_client[AES_BLOCK_SIZE:]

            print_hex_dump("   <<", data)
            check_reply_hash.update(data[:min(AES_BLOCK_SIZE, reply_data_size)])
            reply_data_size -= AES_BLOCK_SIZE
            received_data_size += AES_BLOCK_SIZE

        reply_hash_expect = check_reply_hash.digest()[:DATA_HASH_SIZE] 
        if reply_hash_expect == reply_hash:
            print("   Reply data hash is ok")
        else:
            print("   Reply data hash is bad, calculated as", reply_hash_expect.hex())
        print()

if __name__ == "__main__":
    parser = argparse.ArgumentParser("streamdump",
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    wifi_settings.remote_picotool.RemotePicotoolCfg.add_config_options(parser)
    parser.add_argument("--wireshark",
        type=pathlib.Path,
        help="Dump file of TCP stream from Wireshark (text)")
    parser.add_argument("--binary",
        type=pathlib.Path,
        help="Binary tcp_send_ or tcp_recv_ file")

    args = parser.parse_args(sys.argv[1:] or ["--help"])
    config = wifi_settings.remote_picotool.RemotePicotoolCfg(args)
    if args.wireshark:
        decoder_wireshark(config.update_secret_hash, open(args.wireshark, "rt"))
    elif args.binary:
        decoder_binary(config.update_secret_hash, args.binary)
