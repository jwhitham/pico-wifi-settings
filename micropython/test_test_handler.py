import asyncio
import os
import remote_picotool

ID_TEST_HANDLER_1 = remote_picotool.ID_FIRST_USER_HANDLER + 1
ID_TEST_HANDLER_2 = remote_picotool.ID_FIRST_USER_HANDLER + 2
ID_TEST_HANDLER_3 = remote_picotool.ID_FIRST_USER_HANDLER + 3
MAX_DATA_SIZE = 4096
SIZES = [16, 1, 15, 17, 0, 500, 511, 513, MAX_DATA_SIZE, MAX_DATA_SIZE - 1]
INT_MIN = -0x80000000
INT_MAX = 0x7fffffff


async def remote_handler_run_test_handler() -> None:
    try:
        config = remote_picotool.RemotePicotoolCfg()
        print("Connecting", flush=True)
        reader, writer = await remote_picotool.get_pico_connection(config)
        client = remote_picotool.Client(config.update_secret_hash, reader, writer)

        # Test - info dump
        pico_info = remote_picotool.PicoInfo()
        await pico_info.load(client)
        assert pico_info.get_int("micropython") != 0

        # Test - out of range data sizes
        for size in [MAX_DATA_SIZE + 1, -1, MAX_DATA_SIZE + (1 << 32)]:
            try:
                print("out of range data size", size, " ", end="", flush=True)
                size = MAX_DATA_SIZE + 1
                parameter = -size
                request_data = bytearray(size)
                (result_data, result_value) = await client.run(ID_TEST_HANDLER_1, request_data, parameter)
                raise Exception()
            except remote_picotool.BadParameterError:
                print("OK")

            writer.close()
            await writer.wait_closed()
            print("Reconnecting", flush=True)
            reader, writer = await remote_picotool.get_pico_connection(config)
            client = remote_picotool.Client(config.update_secret_hash, reader, writer)
            
        # Test - sending and receiving data of various sizes
        for size in SIZES:
            assert size <= MAX_DATA_SIZE
            parameter = -size
            print("test_handler_1", size, parameter, end="", flush=True)
            request_data = os.urandom(size)
            expected_result_data = bytearray(size)
            expected_result = -10
            for i in range(size):
                if request_data[i] == 0x41:
                    expected_result -= 1
                expected_result_data[i] = request_data[i] ^ 0xac

            print(", sending", end="", flush=True)
            (result_data, result_value) = await client.run(ID_TEST_HANDLER_1, request_data, parameter)
            print(", checking", len(result_data), result_value, end="")
            assert result_value == expected_result
            assert len(result_data) == size
            assert result_data == bytes(expected_result_data)
            print(", OK", flush=True)

        # Test - receiving more data than was sent
        for parameter in SIZES + [-1, MAX_DATA_SIZE + 1, INT_MIN, INT_MAX]:
            size = 0
            print("test_handler_2", size, parameter, end="", flush=True)
            expected_result = parameter ^ 1
            request_data = b""
            if parameter < 0:
                expected_result_data = bytearray(0)
            elif parameter < MAX_DATA_SIZE:
                expected_result_data = bytearray(parameter)
            else:
                expected_result_data = bytearray(MAX_DATA_SIZE)
            for i in range(len(expected_result_data)):
                expected_result_data[i] = (i + 1) & 0xff

            print(", sending", end="", flush=True)
            (result_data, result_value) = await client.run(ID_TEST_HANDLER_2, request_data, parameter)
            print(", checking", len(result_data), result_value, end="")
            assert result_value == expected_result
            assert len(result_data) == len(expected_result_data)
            assert result_data == bytes(expected_result_data)
            print(", OK", flush=True)

        # Test - edge cases for parameters and result values
        for (parameter, expected_result) in {
                INT_MIN: -1,
                INT_MAX: -2,
                0: -3,
                -1: INT_MIN,
                -2: INT_MAX,
                -3: INT_MIN, # INT_MAX + 1 truncated
                -4: INT_MAX, # INT_MIN - 1 truncated
                -5: 0x789abcde, # truncated
                1: -4,
        }.items():
            size = 0
            print("test_handler_3", size, parameter, end="", flush=True)
            request_data = b""
            print(", sending", end="", flush=True)
            (result_data, result_value) = await client.run(ID_TEST_HANDLER_3, request_data, parameter)
            print(", checking", len(result_data), result_value, end="")
            assert result_value == expected_result
            assert len(result_data) == 0
            print(", OK", flush=True)

        # Test - input data size is transferred precisely
        for size in [1, 123, MAX_DATA_SIZE]:
            parameter = size
            print("test_handler_3", size, parameter, end="", flush=True)
            request_data = bytearray(size)
            expected_result = -3
            print(", sending", end="", flush=True)
            (result_data, result_value) = await client.run(ID_TEST_HANDLER_3, request_data, parameter)
            print(", checking", len(result_data), result_value, end="")
            assert result_value == expected_result, (result_value, expected_result)
            assert len(result_data) == 0
            print(", OK", flush=True)

        print("Tests ok")
    finally:
        writer.close()
        await writer.wait_closed()

async def run() -> None:
    await remote_handler_run_test_handler()

if __name__ == "__main__":
    asyncio.run(run())
