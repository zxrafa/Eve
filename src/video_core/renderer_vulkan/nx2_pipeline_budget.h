// SPDX-FileCopyrightText: Copyright 2026 Eve Emulator Project
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <algorithm>
#include <cstddef>

#include "common/common_types.h"

namespace Vulkan::Nx2PipelineBudget {

constexpr u64 GiB = 1024ULL * 1024ULL * 1024ULL;

/// Caps total live VkPipeline handles (graphics_cache + background_ready) by host physical RAM.
/// Each live NVIDIA/AMD graphics pipeline retains ~350-450 KiB of host/driver memory on top of
/// the 8 GiB Switch 2 guest heap, so uncapped prebuilds push 16 GiB hosts into swap thrashing.
[[nodiscard]] constexpr size_t ComputeLivePipelineCap(u64 host_ram_bytes) noexcept {
    if (host_ram_bytes != 0 && host_ram_bytes <= 18 * GiB) {
        return 2500;
    }
    if (host_ram_bytes != 0 && host_ram_bytes <= 26 * GiB) {
        return 5000;
    }
    return 8000;
}

/// Caps how many deferred disk pipelines are prebuilt in the background per session.
/// Entries are processed newest-first, warming the most likely needed shaders without
/// holding tens of thousands of deserialized FileEnvironment vectors in heap memory.
[[nodiscard]] constexpr size_t ComputeDeferredPrebuildCap(u64 host_ram_bytes) noexcept {
    if (host_ram_bytes != 0 && host_ram_bytes <= 18 * GiB) {
        return 2048;
    }
    if (host_ram_bytes != 0 && host_ram_bytes <= 26 * GiB) {
        return 4096;
    }
    return 8192;
}

/// Keeps background shader prebuilding to 1 worker on <= 12-thread CPUs (e.g. 6C/12T Zen 2 APUs
/// with small per-CCX L3 caches) so the 4 guest CPU cores and 2 split GPU threads never starve.
[[nodiscard]] constexpr size_t ComputeBackgroundPrebuildThreads(size_t logical_cores) noexcept {
    if (logical_cores <= 12) {
        return 1;
    }
    return std::clamp<size_t>(logical_cores / 4, 1, 4);
}

static_assert(ComputeLivePipelineCap(15 * GiB) == 2500);
static_assert(ComputeLivePipelineCap(24 * GiB) == 5000);
static_assert(ComputeLivePipelineCap(32 * GiB) == 8000);
static_assert(ComputeDeferredPrebuildCap(15 * GiB) == 2048);
static_assert(ComputeBackgroundPrebuildThreads(12) == 1);
static_assert(ComputeBackgroundPrebuildThreads(16) == 4);

} // namespace Vulkan::Nx2PipelineBudget
