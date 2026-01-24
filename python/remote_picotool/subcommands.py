
def subcommand_info(args: argparse.Namespace) -> None:
    """Print information gathered from a device that is running pico-wifi-settings.""" 
    config = RemotePicotoolCfg(args)
    update_secret_hash = config.update_secret_hash
    pico_info = PicoInfo()

    async def run() -> None:
        try:
            reader, writer = await get_pico_connection(config)
            client = Client(update_secret_hash, reader, writer)
            (result_data, result_value) = await client.run(ID_PICO_INFO_HANDLER)
            pico_info.contents = result_data
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    asyncio.run(run())

    if args.raw:
        print("Raw data")
        print(pico_info.contents.decode("utf-8", errors="ignore"))

    # Additional reporting for a partition (if present)
    partition = ""
    if pico_info.flash_program_range[0] != pico_info.flash_range[0]:
        partition = f"""
 partition end:     0x{pico_info.flash_reusable_range[1]:08x}"""

    # Reporting
    print(f"""\
Wifi Settings File
 hostname:          {pico_info.name}
 ip address:        {pico_info.get_str("ip")}
 
Program Information
 name:              {pico_info.get_str("program")}
 features:          {pico_info.get_str("feature")}
 binary start:      0x{pico_info.flash_program_range[0]:08x}
 binary end:        0x{pico_info.flash_program_range[1]:08x}{partition}
 wifi-settings at:  0x{pico_info.flash_wifi_settings_file_range[0]:08x}

Build Information
 sdk version:       {pico_info.get_str("sdk_version")}
 wifi-settings ver: {pico_info.get_str("wifi_settings_version")}
 build date:        {pico_info.get_str("build_date")}
 build attributes:  {pico_info.get_str("build_attribute")}

Device Information
 type:              {pico_info.type_name}
 revision:          {pico_info.revision}
 flash size:        0x{pico_info.flash_size:08x}
 flash sector size: 0x{pico_info.flash_sector_size:08x}
 board id:          {pico_info.board_id}""")

class UpdateRebootMode(enum.Enum):
    REBOOT = enum.auto()
    UPDATE_REBOOT = enum.auto()
    UPDATE = enum.auto()
    REBOOT_BOOTLOADER = enum.auto()

def subcommand_update_reboot(args: argparse.Namespace) -> None:
    config = RemotePicotoolCfg(args)
    mode = typing.cast(UpdateRebootMode, args.mode)

    request_data = b""
    if mode in (UpdateRebootMode.UPDATE, UpdateRebootMode.UPDATE_REBOOT):
        file_type = get_file_type(args.filename)
        if file_type == FileType.NOT_FOUND:
            raise LocalError(f"File '{args.filename}' does not exist")
        elif file_type != FileType.WIFI_SETTINGS:
            raise LocalError(
                f"File '{args.filename}' does not appear to be a wifi-settings file; " +
                "this command requires a wifi-settings file in UTF-8 format, max size " +
                f"{MAX_WIFI_SETTINGS_FILE_SIZE} bytes.")
        request_data = args.filename.read_bytes()

    msg_type = ID_UPDATE_REBOOT_HANDLER
    if mode == UpdateRebootMode.UPDATE:
        msg_type = ID_UPDATE_HANDLER

    parameter = 0
    if mode == UpdateRebootMode.REBOOT_BOOTLOADER:
        parameter = 1

    update_secret_hash = config.update_secret_hash

    async def run() -> None:
        try:
            reader, writer = await get_pico_connection(config)
            (result_data, result_value) = await Client(
                update_secret_hash, reader, writer).run(
                    handler_id=msg_type,
                    request_data=request_data,
                    parameter=parameter)

            if (result_value == PICO_ERROR_NOT_PERMITTED) and (msg_type == ID_UPDATE_HANDLER):
                raise RemoteError(
                    "'Not Permitted' error received: this error comes from "
                    "flash_safe_execute() and indicates that your firmware lacks support "
                    "for safe multicore Flashing. You can use 'update_reboot' instead "
                    "of 'update' as a workaround.")
            if mode == UpdateRebootMode.UPDATE:
                if result_value != len(request_data):
                    raise PicoError(result_value)

            if result_value < 0:
                raise PicoError(result_value)

            if mode == UpdateRebootMode.REBOOT:
                print("Reboot requested")
            elif mode == UpdateRebootMode.UPDATE_REBOOT:
                print("Update and reboot requested")
            elif mode == UpdateRebootMode.UPDATE:
                print("Updated ok")
            elif mode == UpdateRebootMode.REBOOT_BOOTLOADER:
                print("Reboot to bootloader requested")

        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    asyncio.run(run())

def subcommand_save(args: argparse.Namespace) -> None:
    config = RemotePicotoolCfg(args)
    update_secret_hash = config.update_secret_hash

    # Sanity check for the file type
    file_type = get_file_type(args.filename)
    if args.filename.name.lower().endswith(".uf2") or file_type == FileType.UF2:
        raise LocalError(f"File '{args.filename}' specifies a UF2 firmware file; " +
                          "this command requires a memory image file (.bin)")
    elif args.filename.name.lower().endswith(".elf") or file_type == FileType.ELF:
        raise LocalError(f"File '{args.filename}' specifies an ELF file; " +
                          "this command requires a memory image file (.bin)")
    elif file_type == FileType.WIFI_SETTINGS:
        raise LocalError(f"File '{args.filename}' is a text file and would be overwritten")

    async def run() -> None:
        try:
            reader, writer = await get_pico_connection(config)
            client = Client(update_secret_hash, reader, writer)

            # Get the Pico info first, in order to know enough about the program and Flash memory
            (result_data, result_value) = await client.run(ID_PICO_INFO_HANDLER)
            pico_info = PicoInfo(result_data)

            # Determine the range to be downloaded
            if args.range:
                # User provides an exact range
                range_start = args.range[0]
                range_end = args.range[1]
            elif args.all:
                # All Flash to be downloaded
                (range_start, range_end) = pico_info.flash_range
                range_start += pico_info.logical_offset
                range_end += pico_info.logical_offset
            else:
                # Current program to be downloaded
                (range_start, range_end) = pico_info.flash_program_range
                range_start += pico_info.logical_offset
                range_end += pico_info.logical_offset

            if range_start >= range_end:
                raise LocalError(f"Range is not valid: 0x{range_start:08x} .. 0x{range_end:08x}")

            # Request data
            with open(args.filename, "wb") as fd:
                while range_start < range_end:
                    size = min(pico_info.max_data_size, range_end - range_start)
                    request_data = READ_PARAMETER.pack(range_start, size)
                    try:
                        (result_data, result_value) = await client.run(ID_READ_HANDLER, request_data)
                    except BadHandlerError:
                        raise NeedsMoreRemoteFeaturesError("save") from None

                    if result_value < 0:
                        raise PicoError(result_value)
                    fd.write(result_data)
                    range_start += size

            print("Save ok")

        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    asyncio.run(run())

def subcommand_load(args: argparse.Namespace) -> None:
    config = RemotePicotoolCfg(args)
    update_secret_hash = config.update_secret_hash

    async def run() -> None:
        try:
            reader, writer = await get_pico_connection(config)
            client = Client(update_secret_hash, reader, writer)

            await do_load(client, args.filename, args.offset, False)

        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    asyncio.run(run())

def subcommand_ota(args: argparse.Namespace) -> None:
    config = RemotePicotoolCfg(args)
    update_secret_hash = config.update_secret_hash

    async def run() -> None:
        try:
            reader, writer = await get_pico_connection(config)
            client = Client(update_secret_hash, reader, writer)

            # Load the data into Flash
            (copy_to_offset, file_reader) = await do_load(client, args.filename, None, True)

            # Verify on the Pico, then install
            ota_firmware_update_parameter_data = OTA_FIRMWARE_UPDATE_PARAMETER.pack(
                    file_reader.lower_bound, file_reader.size,
                    copy_to_offset, file_reader.size) + file_reader.get_sha256()
            (result_data, result_value) = await client.run(ID_OTA_FIRMWARE_UPDATE_HANDLER,
                request_data=ota_firmware_update_parameter_data)
    
            if result_value != 0:
                # Verification failed on the Pico
                raise PicoError(result_value)
            print("Verify ok - install command accepted: "
                  f"0x{file_reader.lower_bound:08x} .. 0x{file_reader.upper_bound:08x} -> "
                  f"0x{copy_to_offset:08x} .. 0x{copy_to_offset + file_reader.size:08x}")

        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    asyncio.run(run())

def subcommand_list(args: argparse.Namespace) -> None:
    config = RemotePicotoolCfg(args)

    async def run() -> None:
        matches = await get_list_of_boards_for_board_id(config.board_id, config)

        for (address, board_id) in sorted(matches.items()):
            print(f"{address:15s} {board_id}")
        if len(matches) == 0:
            print("No Pico W devices found")

    asyncio.run(run())
