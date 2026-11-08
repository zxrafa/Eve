CXX_PART_1 = r"""
#include <array>
#include <cstdlib>
#include <deque>
#include <iostream>
#include <iterator>
#include <random>
#include <stdexcept>
#include <string>
#include "reference.h"
#include "optimized.h"

using Reference = MappingReference::Nx2GpuMappingTable;
using Optimized = MappingOptimized::Nx2GpuMappingTable;
constexpr u64 Max = std::numeric_limits<u64>::max();

enum class Kind { Map, Unmap, Acquire, Release, Reset };

struct Operation {
    Kind kind;
    u64 gpu{};
    u64 cpu{};
    u64 size{};
};

template <typename A, typename B>
bool SameRange(const A& a, const B& b) {
    return a.gpu == b.gpu && a.cpu == b.cpu && a.size == b.size;
}

void Require(bool condition, const char* what) {
    if (!condition) {
        throw std::runtime_error(what);
    }
}

template <typename A, typename B>
void CheckRanges(const A& a, const B& b) {
    Require(a.size() == b.size(), "range count");
    for (size_t i = 0; i < a.size(); ++i) {
        Require(SameRange(a[i], b[i]), "range contents/order");
    }
}

template <typename T>
typename T::Update Apply(T& table, Operation op) {
    switch (op.kind) {
    case Kind::Map: return table.Map(op.gpu, op.cpu, op.size);
    case Kind::Unmap: return table.Unmap(op.gpu, op.size);
    case Kind::Acquire: return table.Acquire(op.gpu, op.size);
    case Kind::Release: return table.Release(op.gpu);
    case Kind::Reset: table.Reset(); return {};
    }
    std::abort();
}

template <typename T>
void DumpUpdate(const T& update) {
    std::cerr << "success=" << update.success << " lease=" << update.lease << '\n';
    for (const auto& change : update.changes) {
        std::cerr << "  gpu=" << change.range.gpu << " cpu=" << change.range.cpu
                  << " size=" << change.range.size << " map=" << change.map
                  << " native=" << change.native << '\n';
    }
}

struct Audit {
    Reference reference;
    Optimized optimized;
    std::deque<Operation> history;
    u64 steps{};
    u64 accepted{};
    u64 rejected{};
    u64 changes{};
    u64 native_changes{};
    u64 unmap_changes{};
    std::array<u64, 5> kinds{};

    void Query(u64 address, u64 size) const {
        Require(reference.Lookup(address) == optimized.Lookup(address), "lookup");
        Require(reference.UsesBacking(address, size) == optimized.UsesBacking(address, size),
                "backing overlap");
        Require(reference.HasNativeOverlap(address, size) ==
                    optimized.HasNativeOverlap(address, size), "native overlap");
        Require(Reference::Valid(address, size) == Optimized::Valid(address, size), "validity");
    }

    void Image(u64 address, u64 bound, u64 offset, u64 size) const {
        const auto a = Reference::ImageRange(address, bound, offset, size);
        const auto b = Optimized::ImageRange(address, bound, offset, size);
        Require(a.has_value() == b.has_value(), "image validity");
        if (a) {
            Require(SameRange(*a, *b), "image range");
        }
    }

    void State() const {
        CheckRanges(reference.Effective(), optimized.Effective());
        CheckRanges(reference.mappings, optimized.mappings);
        Require(reference.next_lease == optimized.next_lease, "next lease ID");
        Require(reference.leases.size() == optimized.leases.size(), "lease count");
"""
