CXX_PART_2 = r"""
        auto other = optimized.leases.begin();
        for (const auto& [id, range] : reference.leases) {
            Require(id == other->first && SameRange(range, other->second), "lease contents");
            ++other;
        }
        for (const auto& range : reference.Effective()) {
            Query(range.gpu - 1, 1);
            Query(range.gpu, range.size);
            Query(range.gpu + range.size - 1, 1);
            Query(range.gpu + range.size, 1);
        }
    }

    u64 Step(Operation op) {
        ++steps;
        ++kinds[static_cast<size_t>(op.kind)];
        history.push_back(op);
        if (history.size() > 16) {
            history.pop_front();
        }
        const auto a = Apply(reference, op);
        const auto b = Apply(optimized, op);
        try {
            Require(a.success == b.success, "update success");
            Require(a.lease == b.lease, "returned lease ID");
            Require(a.changes.size() == b.changes.size(), "change count");
            for (size_t i = 0; i < a.changes.size(); ++i) {
                const auto& x = a.changes[i];
                const auto& y = b.changes[i];
                Require(SameRange(x.range, y.range) && x.map == y.map && x.native == y.native,
                        "change contents/order");
                ++changes;
                native_changes += x.native;
                unmap_changes += !x.map;
            }
            State();
            Query(op.gpu, op.size);
            Query(op.cpu, op.size);
            Query(op.gpu + op.size, 0);
            Query(Max, Max);
        } catch (...) {
            std::cerr << "Failed at operation " << steps << ", last operations (kind gpu cpu size):\n";
            for (const auto& item : history) {
                std::cerr << static_cast<int>(item.kind) << ' ' << item.gpu << ' ' << item.cpu
                          << ' ' << item.size << '\n';
            }
            std::cerr << "Reference update:\n";
            DumpUpdate(a);
            std::cerr << "Optimized update:\n";
            DumpUpdate(b);
            throw;
        }
        if (op.kind != Kind::Reset) {
            accepted += a.success;
            rejected += !a.success;
        }
        return a.lease;
    }
};

void Edges(Audit& audit) {
    const std::array<u64, 11> values{0, 1, 2, 0xfff, 0x1000, 0x1001,
                                    Max / 2, Max - 0x1000, Max - 2, Max - 1, Max};
    for (const u64 gpu : values) {
        for (const u64 size : values) {
            audit.Step({Kind::Reset});
            audit.Step({Kind::Map, gpu, gpu, size});
            const u64 lease = audit.Step({Kind::Acquire, gpu, 0, size});
            audit.Step({Kind::Unmap, gpu, 0, size});
            audit.Step({Kind::Release, lease});
            audit.Step({Kind::Release, lease});
            for (const u64 cpu : values) {
                audit.Step({Kind::Map, gpu, cpu, size});
                audit.Step({Kind::Unmap, gpu, 0, size});
            }
            for (const u64 offset : values) {
                for (const u64 bound : values) {
                    audit.Image(gpu, bound, offset, size);
                }
            }
        }
    }
    audit.Step({Kind::Reset});
    audit.Step({Kind::Map, 10, 100, 100});
    audit.Step({Kind::Unmap, 30, 0, 20});
    audit.Step({Kind::Map, 20, 0, 70});
    audit.Step({Kind::Acquire, 20, 0, 1});
    audit.Step({Kind::Unmap, 0, 0, 200});
    const u64 outer = audit.Step({Kind::Acquire, 10, 0, 100});
    const u64 inner = audit.Step({Kind::Acquire, 30, 0, 20});
    const u64 duplicate = audit.Step({Kind::Acquire, 30, 0, 20});
    const u64 adjacent = audit.Step({Kind::Acquire, 110, 0, 20});
    audit.Step({Kind::Map, 0, 0, 140});
    audit.Step({Kind::Map, 30, 300, 1});
    audit.Step({Kind::Unmap, 20, 0, 100});
    audit.Step({Kind::Release, inner});
    audit.Step({Kind::Release, outer});
    audit.Step({Kind::Release, duplicate});
    audit.Step({Kind::Release, adjacent});
    const u64 stale = audit.Step({Kind::Acquire, 0, 0, Max});
"""
