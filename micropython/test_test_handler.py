import asyncio
import os
import remote_picotool

ID_USER = remote_picotool.ID_FIRST_USER_HANDLER

async def remote_handler_run_test_handler() -> None:
    try:
        config = remote_picotool.RemotePicotoolCfg()
        reader, writer = await remote_picotool.get_pico_connection(config)
        client = remote_picotool.Client(config.update_secret_hash, reader, writer)

        for size in [16, 1, 15, 17, 0, 500, 511, 513, 4096, 4095]:
            print("Test size", size, end="", flush=True)
            request_data = os.urandom(size)
            expected_result_data = bytearray(size)
            parameter = -len(request_data)
            expected_result = -10
            for i in range(size):
                if request_data[i] == 0x41:
                    expected_result -= 1
                expected_result_data[i] = request_data[i] ^ 0xac

            print(", sending", end="", flush=True)
            (result_data, result_value) = await client.run(ID_USER, request_data, parameter)
            print(", checking", len(result_data), result_value, end="")
            assert result_value == expected_result
            assert len(result_data) == size
            assert result_data == bytes(expected_result_data)
            print(", OK", flush=True)

    finally:
        writer.close()
        await writer.wait_closed()

async def run() -> None:
    await remote_handler_run_test_handler()

if __name__ == "__main__":
    asyncio.run(run())
