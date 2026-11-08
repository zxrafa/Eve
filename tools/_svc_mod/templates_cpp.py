PROLOGUE_CPP = """
#include <type_traits>

#include "core/arm/arm_interface.h"
#include "core/core.h"
#include "core/hle/kernel/k_process.h"
#include "core/hle/kernel/svc.h"

namespace Kernel::Svc {

static uint32_t GetArg32(std::span<uint64_t, 8> args, int n) {
    return uint32_t(args[n]);
}

static void SetArg32(std::span<uint64_t, 8> args, int n, uint32_t result) {
    args[n] = result;
}

static uint64_t GetArg64(std::span<uint64_t, 8> args, int n) {
    return args[n];
}

static void SetArg64(std::span<uint64_t, 8> args, int n, uint64_t result) {
    args[n] = result;
}

// Like bit_cast, but handles the case when the source and dest
// are differently-sized.
template <typename To, typename From>
    requires(std::is_trivial_v<To> && std::is_trivially_copyable_v<From>)
static To Convert(const From& from) {
    To to{};
    if constexpr (sizeof(To) >= sizeof(From))
        std::memcpy(std::addressof(to), std::addressof(from), sizeof(From));
    else
        std::memcpy(std::addressof(to), std::addressof(from), sizeof(To));
    return to;
}
"""

EPILOGUE_CPP = """
void Call(Core::System& system, u32 imm) {
    auto& kernel = system.Kernel();
    auto& process = GetCurrentProcess(kernel);
    std::array<uint64_t, 8> args;
    kernel.CurrentPhysicalCore().SaveSvcArguments(process, args);
    LOG_TRACE(Kernel_SVC, "#{:#x} [0]={:#x} [1]={:#x} [2]={:#x} [3]={:#x} [4]={:#x} [5]={:#x} [6]={:#x}",
        imm,
        GetArg32(args, 0), GetArg32(args, 1), GetArg32(args, 2),
        GetArg32(args, 3), GetArg32(args, 4), GetArg32(args, 5), GetArg32(args, 6));
    //kernel.EnterSVCProfile();
    if (process.Is64Bit())
        Call64(system, imm, args);
    else
        Call32(system, imm, args);
    //kernel.ExitSVCProfile();
    kernel.CurrentPhysicalCore().LoadSvcArguments(process, args);
}

} // namespace Kernel::Svc
"""
