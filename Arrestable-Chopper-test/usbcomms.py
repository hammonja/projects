from cffi import FFI


class USBComms:
    """Python wrapper for the usbcomms DLL exported functions.

    All buffer allocation and encoding is handled internally so client code
    does not need to interact with cffi directly.
    """

    _CDEF = """
        int BI_usb_initialise(int pid, int vid);
        int BI_usb_collect(int vid, char* PIDList);
        int BI_usb_get_info(int infoPID, char* DescLst, char* AddrLst);
        int BI_usb_send(int sendpid, int _addr, char* _msg);
        int BI_usb_enter(int enterpid, int _addr, char* _msg);
        void BI_usb_version(char* s);

        int BI_usb_initialise_serial(char* serial);
        int BI_usb_collect_serial(char* SerialList);
        int BI_usb_get_info_serial(char* serial, char* DescLst, char* AddrLst);
        int BI_usb_send_serial(char* serial, int _addr, char* _msg);
        int BI_usb_enter_serial(char* serial, int _addr, char* _msg);
    """

    _BUFFER_SIZE = 4096

    def __init__(self, dll_path: str):
        self._ffi = FFI()
        self._ffi.cdef(self._CDEF)
        self._lib = self._ffi.dlopen(dll_path)

    def initialise(self, pid: int, vid: int) -> int:
        return self._lib.BI_usb_initialise(pid, vid)

    def collect(self, vid: int) -> tuple:
        buf = self._ffi.new("char[]", self._BUFFER_SIZE)
        rc = self._lib.BI_usb_collect(vid, buf)
        return rc, self._ffi.string(buf).decode("ascii")

    def get_info(self, pid: int) -> tuple:
        desc_buf = self._ffi.new("char[]", self._BUFFER_SIZE)
        addr_buf = self._ffi.new("char[]", self._BUFFER_SIZE)
        rc = self._lib.BI_usb_get_info(pid, desc_buf, addr_buf)
        desc = self._ffi.string(desc_buf).decode("ascii")
        addrs = self._ffi.string(addr_buf).decode("ascii")
        return rc, desc, addrs

    def send(self, pid: int, addr: int, msg: str) -> int:
        return self._lib.BI_usb_send(pid, addr, msg.encode("ascii"))

    def enter(self, pid: int, addr: int, msg: str) -> int:
        return self._lib.BI_usb_enter(pid, addr, msg.encode("ascii"))

    def version(self) -> str:
        buf = self._ffi.new("char[]", self._BUFFER_SIZE)
        self._lib.BI_usb_version(buf)
        return self._ffi.string(buf).decode("ascii")

    def initialise_serial(self, serial: str) -> int:
        return self._lib.BI_usb_initialise_serial(serial.encode("ascii"))

    def collect_serial(self) -> tuple:
        buf = self._ffi.new("char[]", self._BUFFER_SIZE)
        rc = self._lib.BI_usb_collect_serial(buf)
        return rc, self._ffi.string(buf).decode("ascii")

    def get_info_serial(self, serial: str) -> tuple:
        desc_buf = self._ffi.new("char[]", self._BUFFER_SIZE)
        addr_buf = self._ffi.new("char[]", self._BUFFER_SIZE)
        rc = self._lib.BI_usb_get_info_serial(serial.encode("ascii"), desc_buf, addr_buf)
        desc = self._ffi.string(desc_buf).decode("ascii")
        addrs = self._ffi.string(addr_buf).decode("ascii")
        return rc, desc, addrs

    def send_serial(self, serial: str, addr: int, msg: str) -> int:
        return self._lib.BI_usb_send_serial(serial.encode("ascii"), addr, msg.encode("ascii"))

    def enter_serial(self, serial: str, addr: int, msg: str) -> int:
        return self._lib.BI_usb_enter_serial(serial.encode("ascii"), addr, msg.encode("ascii"))
