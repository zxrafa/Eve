CXX_PART_3 = r"""
    audit.Step({Kind::Reset});
    audit.Step({Kind::Acquire, Max - 1, 0, 1});
    audit.Step({Kind::Release, stale});
    audit.Step({Kind::Reset});
    for (u64 i = 0; i < 1024; ++i) {
        audit.Step({Kind::Map, i * 16, i * 32, 8});
    }
    audit.Step({Kind::Map, 8194, 0, 2});
    audit.Step({Kind::Unmap, 8193, 0, 4});
    const u64 distant = audit.Step({Kind::Acquire, 1ULL << 40, 0, 16});
    audit.Step({Kind::Unmap, 0, 0, 16384});
    audit.Step({Kind::Release, distant});
    audit.Step({Kind::Reset});
}

void Random(Audit& audit, u64 seed, u64 operations) {
    std::mt19937_64 random(seed);
    for (u64 i = 0; i < operations; ++i) {
        const u64 mode = (i / 256) % 3;
        const auto address = [&]() -> u64 {
            const u64 value = random() % 256;
            return mode == 0 ? value : mode == 1 ? Max - value : value * 0x1000;
        };
        u64 gpu = address();
        u64 cpu = random() % 2 ? gpu : address();
        u64 size = 1 + random() % 64;
        if (mode == 2) {
            size *= 0x1000;
        }
        switch (random() % 24) {
        case 0: size = 0; break;
        case 1: size = Max; break;
        case 2: size = gpu == 0 ? Max : Max - gpu + 1; break;
        case 3: gpu = random(); cpu = random(); break;
        default: break;
        }
        const u64 choice = random() % 12;
        if (i % 256 == 0) {
            audit.Step({Kind::Reset});
        } else if (choice < 4 || choice == 11) {
            audit.Step({Kind::Map, gpu, cpu, size});
        } else if (choice < 6) {
            audit.Step({Kind::Unmap, gpu, 0, size});
        } else if (choice < 9) {
            audit.Step({(i / 256) % 4 == 0 ? Kind::Map : Kind::Acquire, gpu, cpu, size});
        } else {
            u64 id = random() % (audit.reference.next_lease + 4);
            if (!audit.reference.leases.empty() && random() % 4 != 0) {
                auto it = audit.reference.leases.begin();
                std::advance(it, random() % audit.reference.leases.size());
                id = it->first;
            }
            audit.Step({Kind::Release, id});
        }
        audit.Query(random(), random());
        audit.Image(gpu, size, random() % 0x2000, random() % 0x2000);
    }
}

int main(int argc, char** argv) {
    if (argc != 3) {
        return 2;
    }
    const u64 seed = std::stoull(argv[1]);
    const u64 operations = std::stoull(argv[2]);
    Audit audit;
    try {
        Edges(audit);
        Random(audit, seed, operations);
    } catch (const std::exception& error) {
        std::cerr << "FAIL seed=" << seed << " operations=" << operations << ": "
                  << error.what() << '\n';
        return 1;
    }
    std::cout << "PASS seed=" << seed << " randomized=" << operations
              << " total=" << audit.steps << " accepted=" << audit.accepted
              << " rejected=" << audit.rejected << " changes=" << audit.changes
              << " native_changes=" << audit.native_changes
              << " unmap_changes=" << audit.unmap_changes << '\n';
    std::cout << "map=" << audit.kinds[0] << " unmap=" << audit.kinds[1]
              << " acquire=" << audit.kinds[2] << " release=" << audit.kinds[3]
              << " reset=" << audit.kinds[4] << '\n';
}
"""
