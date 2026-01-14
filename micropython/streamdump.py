
# Wireshark: Analyze -> Follow -> TCP Stream
# Choose Entire conversation (... bytes)
# Choose Show data as: Hex Dump
# Click Save as... -> text file

# Expected format similar to:
#     00000000  46 01 05 0d 37 44 34 37  44 46 37 33 41 37 41 33   F...7D47 DF73A7A3
#     00000010  33 42 43 37 0d 6d 69 63  72 6f 70 79 74 68 6f 6e   3BC7.mic ropython
#     00000020  20 70 69 63 6f 2d 77 69  66 69 2d 73 65 74 74 69    pico-wi fi-setti
#     00000030  6e 67 73 20 76 65 72 73  69 6f 6e 20 30 2e 33 2e   ngs vers ion 0.3.
#     00000040  31 0d 0a 00 00 00 00 00  00 00 00 00 00 00 00 00   1....... ........
# 00000000  47 b4 ce b1 d9 f0 80 aa  99 2f b4 fa 37 99 47 08   G....... ./..7.G.
# ....
# Every line is always 16 bytes because this is the AES_BLOCK_SIZE

import hashlib, hmac, struct, typing
import pyaes # type: ignore

import remote_picotool


BLOCK_SIZE = remote_picotool.AES_BLOCK_SIZE
HEADER_STRUCT = "<IiB7s"
HEADER_DATA_HASH_OFFSET = BLOCK_SIZE - remote_picotool.DATA_HASH_SIZE
MAX_DATA_SIZE = 4096

def decoder(secret_bytes: bytes, conversation: typing.IO) -> None:
    # Split up the lines in the conversation
    server_to_client = b""
    client_to_server = b""
    for line in conversation:
        fields = line.split()
        assert len(fields) >= (BLOCK_SIZE + 1)
        data = bytes([int(value, 16) for value in fields[1:BLOCK_SIZE + 1]])
        if line.startswith(" "):
            server_to_client += data
        else:
            client_to_server += data
            
    # Compute the secret hash
    secret_hash = b"\x00" * 32
    for i in range(4096):
        secret_hash = hashlib.sha256(secret_hash + secret_bytes).digest()

    # Skip the greeting
    assert server_to_client[0] == remote_picotool.ID_GREETING
    assert server_to_client[1] == remote_picotool.PROTOCOL_VERSION
    num_blocks = server_to_client[2]
    assert num_blocks >= 1
    server_to_client = server_to_client[BLOCK_SIZE * num_blocks:]

    # Here is the client's request
    assert client_to_server[0] == remote_picotool.ID_REQUEST
    client_challenge = client_to_server[1:BLOCK_SIZE]
    client_to_server = client_to_server[BLOCK_SIZE:]

    # Here is the server's challenge
    assert server_to_client[0] == remote_picotool.ID_CHALLENGE
    server_challenge = server_to_client[1:BLOCK_SIZE]
    server_to_client = server_to_client[BLOCK_SIZE:]

    # Here is the client's authentication
    assert client_to_server[0] == remote_picotool.ID_AUTHENTICATION
    client_auth_expect = client_to_server[1:BLOCK_SIZE]
    client_to_server = client_to_server[BLOCK_SIZE:]

    # Here is the server's authentication
    assert server_to_client[0] == remote_picotool.ID_RESPONSE
    server_auth_expect = server_to_client[1:BLOCK_SIZE]
    server_to_client = server_to_client[BLOCK_SIZE:]
    print("Handshake messages were sent")

    # Check the authentication
    def gen_auth(session_data: bytes) -> bytes:
        return hmac.HMAC(key=secret_hash, msg=session_data, digestmod=hashlib.sha256).digest()

    assert client_auth_expect == gen_auth(client_challenge + server_challenge + b"CA")[:BLOCK_SIZE - 1]
    assert server_auth_expect == gen_auth(client_challenge + server_challenge + b"SA")[:BLOCK_SIZE - 1]

    # Set up encryption
    c2s_key = gen_auth(client_challenge + server_challenge + b"CK")
    s2c_key = gen_auth(client_challenge + server_challenge + b"SK")
    client_transmit = pyaes.aes.AESModeOfOperationCBC(key=c2s_key, iv=b"\x00" * BLOCK_SIZE)
    server_transmit = pyaes.aes.AESModeOfOperationCBC(key=s2c_key, iv=b"\x00" * BLOCK_SIZE)

    # Here is the client's confirmation
    assert client_to_server[0] == remote_picotool.ID_ACKNOWLEDGE
    client_to_server = client_to_server[BLOCK_SIZE:]
    print("Handshake was ok, keys were set up")

    # Now everything will be encrypted
    while len(client_to_server) != 0:
        # Read a reply header from the client
        request_header = client_transmit.decrypt(client_to_server[:BLOCK_SIZE])
        client_to_server = client_to_server[BLOCK_SIZE:]

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
            data = client_transmit.decrypt(client_to_server[:BLOCK_SIZE])
            client_to_server = client_to_server[BLOCK_SIZE:]

            print("   Request", data.hex(" "), repr(data))
            check_request_hash.update(data[:min(BLOCK_SIZE, request_data_size)])
            request_data_size -= BLOCK_SIZE

        request_hash_expect = check_request_hash.digest()[:remote_picotool.DATA_HASH_SIZE] 
        if request_hash_expect == request_hash:
            print("   Request data hash is ok")
        else:
            print("   Request data hash is bad, calculated as", request_hash_expect.hex())

        if len(server_to_client) == 0:
            break

        # Server should respond with a reply header
        reply_header = server_transmit.decrypt(server_to_client[:BLOCK_SIZE])
        server_to_client = server_to_client[BLOCK_SIZE:]
            
        # Decode reply header
        (reply_data_size, parameter, msg_type, reply_hash) = struct.unpack(HEADER_STRUCT, reply_header)
        check_reply_hash = hashlib.sha256()
        check_reply_hash.update(reply_header[:HEADER_DATA_HASH_OFFSET])
        print("Reply from server: data_size {} parameter {} msg_type {} hash {}".format(
                reply_data_size, parameter, msg_type, reply_hash.hex()))
        assert 0 <= reply_data_size <= MAX_DATA_SIZE

        # Capture the data and print it
        while reply_data_size > 0:
            data = server_transmit.decrypt(server_to_client[:BLOCK_SIZE])
            server_to_client = server_to_client[BLOCK_SIZE:]

            print("   Reply", data.hex(" "), repr(data))
            check_reply_hash.update(data[:min(BLOCK_SIZE, reply_data_size)])
            reply_data_size -= BLOCK_SIZE

        reply_hash_expect = check_reply_hash.digest()[:remote_picotool.DATA_HASH_SIZE] 
        if reply_hash_expect == reply_hash:
            print("   Reply data hash is ok")
        else:
            print("   Reply data hash is bad, calculated as", reply_hash_expect.hex())

if __name__ == "__main__":
    decoder(b"funkytown", open("/tmp/tt.txt", "rt"))
