SKIP_WRAPPERS = {
    0x20: "SendSyncRequestLight",
    0x42: "ReplyAndReceiveLight",
    0x7F: "CallSecureMonitor",
}

BIT_32 = 0
BIT_64 = 1

REG_SIZES = [4, 8]
SUFFIX_NAMES = ["64From32", "64"]
TYPE_SIZES = {
    # SVC types
    "ArbitrationType": 4,
    "BreakReason": 4,
    "CodeMemoryOperation": 4,
    "DebugThreadParam": 4,
    "DeviceName": 4,
    "HardwareBreakPointRegisterName": 4,
    "Handle": 4,
    "InfoType": 4,
    "InterruptType": 4,
    "IoPoolType": 4,
    "KernelDebugType": 4,
    "KernelTraceState": 4,
    "LimitableResource": 4,
    "MemoryMapping": 4,
    "MemoryPermission": 4,
    "PageInfo": 4,
    "ProcessActivity": 4,
    "ProcessInfoType": 4,
    "Result": 4,
    "SignalType": 4,
    "SystemInfoType": 4,
    "ThreadActivity": 4,

    # Arch-specific types
    "ilp32::LastThreadContext": 16,
    "ilp32::PhysicalMemoryInfo": 16,
    "ilp32::SecureMonitorArguments": 32,
    "lp64::LastThreadContext": 32,
    "lp64::PhysicalMemoryInfo": 24,
    "lp64::SecureMonitorArguments": 64,

    # Generic types
    "bool": 1,
    "int32_t": 4,
    "int64_t": 8,
    "uint32_t": 4,
    "uint64_t": 8,
    "void": 0,
}

TYPE_REPLACEMENTS = {
    "Address": ["uint32_t", "uint64_t"],
    # Preserve the AArch32 register layout while retaining the native 64-bit value.
    "AddressArbiterValue": ["int32_t", "int64_t"],
    "LastThreadContext": ["ilp32::LastThreadContext", "lp64::LastThreadContext"],
    "PhysicalAddress": ["uint64_t", "uint64_t"],
    "PhysicalMemoryInfo": ["ilp32::PhysicalMemoryInfo", "lp64::PhysicalMemoryInfo"],
    "SecureMonitorArguments": ["ilp32::SecureMonitorArguments", "lp64::SecureMonitorArguments"],
    "Size": ["uint32_t", "uint64_t"],
    "ThreadFunc": ["uint32_t", "uint64_t"],
}
