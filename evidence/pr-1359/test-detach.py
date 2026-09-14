#!/usr/bin/env python3
"""Compile actual pre/post modeset functions against bookkeeping test doubles."""
from pathlib import Path
import argparse
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PATH = 'src/common/displayport/src/dp_connectorimpl.cpp'
COMMITS = {
    '610': 'e4a5faa2567f28c8eabe0ebb6422b6d0abcf37eb',
    '615': '61dcc93722ecb418bb5f2e00923f05b4b8051dd1',
    'pr1359': 'bd5d6119ca1ed030ad26d06d1b3e980873ff0336',
}


def function(source, name):
    start = source.index('void ConnectorImpl::' + name + '(')
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


PREFIX = r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>
using NvU32 = uint32_t;
#define NV_MAX_HEADS 4
#define NVBIT(i) (1u << (i))
#define DP_ASSERT(...) ((void)0)
#define DP_PRINTF(...) ((void)0)
struct Group { bool attached = true; };
struct Modeset { unsigned headIndex; };
struct Head { Group *pTarget; Modeset *pModesetParams; };
struct DpPreModesetParams { unsigned headMask = 0; Head head[4]{}; };
struct MainLink {
    bool dynamic = false;
    bool isInternalPanelDynamicMuxCapable() { return dynamic; }
};
struct ConnectorImpl {
    bool connectorActive = true, bIsDiscoveryDetectActive = false;
    bool isDiscoveryDetectComplete = true, previousPlugged = false;
    bool bClientForcedConnected = false, bFECEnable = false;
    MainLink link;
    MainLink *main = &link;
    unsigned inTransitionHeadMask = 0;
    Group *perHeadAttachedGroup[4]{};
    std::vector<Group *> pendingDetach;
    int detaches = 0, detachEnds = 0, attaches = 0, attachEnds = 0;
    bool needToEnableFEC(const DpPreModesetParams &) { return false; }
    void notifyDetachBegin(Group *g) { assert(g); ++detaches; pendingDetach.push_back(g); }
    void notifyDetachEnd() {
        assert(!pendingDetach.empty());
        ++detachEnds;
        pendingDetach.back()->attached = false;
        pendingDetach.pop_back();
    }
    void notifyAttachBegin(Group *, const Modeset &) { ++attaches; }
    void notifyAttachEnd(bool) { ++attachEnds; }
    void dpPreModeset(const DpPreModesetParams &);
    void dpPostModeset();
};
'''

TESTS = r'''
int main() {
    Group oldHead, newHead;
    DpPreModesetParams detach;
    detach.headMask = NVBIT(2);
    // A target outside headMask must not turn this into an attach request.
    detach.head[1].pTarget = &newHead;
    ConnectorImpl c;
    c.perHeadAttachedGroup[2] = &oldHead;
    c.dpPreModeset(detach);
    assert(oldHead.attached && c.detachEnds == 0);
    c.dpPostModeset();
#if STOCK_615
    assert(c.detaches == 0 && c.detachEnds == 0 && oldHead.attached);
    assert(c.perHeadAttachedGroup[2] == &oldHead);
#else
    assert(c.detaches == 1 && c.detachEnds == 1 && !oldHead.attached);
    assert(c.perHeadAttachedGroup[2] == nullptr);
#endif
    assert(c.inTransitionHeadMask == 0);
#if TEST_GUARDS
    Modeset timing{3};
    DpPreModesetParams attach;
    attach.headMask = NVBIT(3);
    attach.head[3] = {&newHead, &timing};
    ConnectorImpl rejected;
    rejected.dpPreModeset(attach);
    rejected.dpPostModeset();
    assert(rejected.attaches == 0 && rejected.inTransitionHeadMask == 0);

    DpPreModesetParams mixed = attach;
    mixed.headMask |= NVBIT(2);
    rejected.perHeadAttachedGroup[2] = &oldHead;
    rejected.dpPreModeset(mixed);
    rejected.dpPostModeset();
    assert(rejected.attaches == 0 && rejected.detaches == 0);
    assert(rejected.perHeadAttachedGroup[2] == &oldHead);
    assert(rejected.inTransitionHeadMask == 0);

    for (int mode = 0; mode < 3; ++mode) {
        ConnectorImpl allowed;
        allowed.previousPlugged = mode == 0;
        allowed.bClientForcedConnected = mode == 1;
        allowed.link.dynamic = mode == 2;
        allowed.dpPreModeset(attach);
        allowed.dpPostModeset();
        assert(allowed.attaches == 1 && allowed.attachEnds == 1);
        assert(allowed.perHeadAttachedGroup[3] == &newHead);
        assert(allowed.inTransitionHeadMask == 0);
    }
    for (int mode = 0; mode < 3; ++mode) {
        ConnectorImpl blocked;
        blocked.connectorActive = mode != 0;
        blocked.bIsDiscoveryDetectActive = mode == 1;
        blocked.isDiscoveryDetectComplete = mode != 2;
        blocked.perHeadAttachedGroup[2] = &oldHead;
        blocked.dpPreModeset(detach);
        blocked.dpPostModeset();
        assert(blocked.detaches == 0 && blocked.inTransitionHeadMask == 0);
    }
    ConnectorImpl connected;
    connected.previousPlugged = true;
    connected.perHeadAttachedGroup[2] = &oldHead;
    oldHead.attached = true;
    connected.dpPreModeset(detach);
    connected.dpPostModeset();
    assert(connected.detaches == 1 && !oldHead.attached);
#endif
    for (unsigned mask = 0; mask < 16; ++mask) {
        ConnectorImpl multi;
        Group groups[4];
        DpPreModesetParams request;
        request.headMask = mask;
        for (unsigned i = 0; i < 4; ++i)
            multi.perHeadAttachedGroup[i] = &groups[i];
        multi.dpPreModeset(request);
        for (const auto &group : groups)
            assert(group.attached);
        multi.dpPostModeset();
        for (unsigned i = 0; i < 4; ++i) {
            const bool detached = !STOCK_615 && (mask & NVBIT(i));
            assert(groups[i].attached == !detached);
            assert(multi.perHeadAttachedGroup[i] == (detached ? nullptr : &groups[i]));
        }
        assert(multi.inTransitionHeadMask == 0 && multi.pendingDetach.empty());
    }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--fixed-source', type=Path,
                        help='also test a prepared fixed driver source directory')
    args = parser.parse_args()
    variants = []
    for name, commit in COMMITS.items():
        result = subprocess.run(['git', 'show', f'{commit}:{PATH}'],
                                cwd=args.repo, capture_output=True, text=True)
        if result.returncode:
            parser.error(f'missing {name} source {commit}; fetch the refs listed in README.md')
        variants.append((name, result.stdout, int(name == '615'), int(name != '610')))
    if args.fixed_source:
        variants.append(('fixed-source', (args.fixed_source / PATH).read_text(), 0, 1))

    with tempfile.TemporaryDirectory(prefix='dp-detach-test-') as tmp:
        for name, source, stock, guards in variants:
            code = PREFIX + function(source, 'dpPreModeset') + function(source, 'dpPostModeset') + TESTS
            cpp = Path(tmp) / (name + '.cpp')
            binary = Path(tmp) / name
            cpp.write_text(code)
            subprocess.run([args.cxx, '-std=c++11', '-Wall', '-Wextra', '-Werror',
                            f'-DSTOCK_615={stock}', f'-DTEST_GUARDS={guards}',
                            str(cpp), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
            print(name + ': expected detach behavior and applicable guards verified')
    print('These tests exercise source control flow, not GPU/firmware behavior.')


if __name__ == '__main__':
    main()
