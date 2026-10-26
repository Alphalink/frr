#!/usr/bin/env python
# SPDX-License-Identifier: ISC
#
# test_zebra_netns_exclude.py
#

"""
test_zebra_netns_exclude.py: zebra --netns-exclude with the netns VRF backend.

A namespace given with --netns-exclude belongs to another routing process.
zebra must not turn it into a VRF, neither at startup nor when it appears
later, and must leave the routes and nexthop groups installed there alone.
Without the option, zebra takes the nexthop object installed there with the
zebra protocol for its own and removes it from the kernel when it stops (on
10.5, at its startup sweep already), which drops the route using it.
"""

import os
import sys
import pytest

CWD = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(CWD, "../"))

from lib import topotest
from lib.topogen import Topogen, TopoRouter, get_topogen
from lib.topolog import logger
from lib.common_config import start_router_daemons
from functools import partial

MANAGED_VRF = "vrf-red"
EXCLUDED_NETNS = "vrf-other"
LATE_EXCLUDED_NETNS = "vrf-late"
LATE_MANAGED_NETNS = "vrf-new"

# What another routing process installs in its namespace: a nexthop object
# with the zebra protocol, a route using it and a route without object, both
# with the zebra static protocol (196).
FOREIGN_IFNAME = "other-dum"
FOREIGN_NH_ID = 100
FOREIGN_NHID_PREFIX = "192.0.2.0/24"
FOREIGN_PLAIN_PREFIX = "198.51.100.0/24"


def build_topo(tgen):
    "One router, one link to a switch."
    tgen.add_router("r1")
    sw = tgen.add_switch("s1")
    sw.add_link(tgen.gears["r1"])


def _install_foreign_content(router, netns):
    "Install, as another routing process would, routes and a nexthop object."
    router.run(
        "ip netns exec {0} ip link add {1} type dummy && "
        "ip netns exec {0} ip link set {1} up && "
        "ip netns exec {0} ip nexthop add id {2} dev {1} proto 11 && "
        "ip netns exec {0} ip route add {3} nhid {2} proto 196 && "
        "ip netns exec {0} ip route add {4} dev {1} proto 196".format(
            netns,
            FOREIGN_IFNAME,
            FOREIGN_NH_ID,
            FOREIGN_NHID_PREFIX,
            FOREIGN_PLAIN_PREFIX,
        )
    )


def _foreign_content(router, netns):
    "Return what is left of the foreign content in netns, as a set of labels."
    left = set()
    # router.run() joins stderr: an absent object must print nothing.
    cmd = "ip netns exec {} ip nexthop show id {} 2>/dev/null".format(
        netns, FOREIGN_NH_ID
    )
    if router.run(cmd).strip():
        left.add("nexthop")
    for prefix in (FOREIGN_NHID_PREFIX, FOREIGN_PLAIN_PREFIX):
        cmd = "ip netns exec {} ip route show {} proto 196".format(netns, prefix)
        if router.run(cmd).strip():
            left.add(prefix)
    return left


def _vrf_names(router):
    out = router.vtysh_cmd("show vrf")
    return {line.split()[1] for line in out.splitlines() if line.startswith("vrf ")}


def _log_count(router, pattern):
    cmd = "grep -c '{}' {}/zebra.log".format(pattern, router.gearlogdir)
    return int(router.run(cmd).strip() or 0)


def setup_module(mod):
    "Create the namespaces, the foreign content, then start zebra."
    tgen = Topogen(build_topo, mod.__name__)
    tgen.start_topology()

    r1 = tgen.gears["r1"]

    if r1.check_capability(TopoRouter.RD_ZEBRA, "--vrfwnetns") is False:
        pytest.skip("VRF NETNS backend not available on FRR")
    if os.system("ip netns list") != 0:
        pytest.skip("NETNS not available on system")

    r1.net.add_netns(MANAGED_VRF)
    r1.net.set_intf_netns("r1-eth0", MANAGED_VRF, up=True)
    r1.net.add_netns(EXCLUDED_NETNS)
    _install_foreign_content(r1, EXCLUDED_NETNS)

    r1.use_netns_vrf()
    exclude = "--netns-exclude {} --netns-exclude {}".format(
        EXCLUDED_NETNS, LATE_EXCLUDED_NETNS
    )
    r1.load_frr_config(
        os.path.join(CWD, "r1/frr.conf"), [(TopoRouter.RD_ZEBRA, exclude)]
    )
    tgen.start_router()


def teardown_module(_mod):
    tgen = get_topogen()
    r1 = tgen.gears["r1"]
    r1.net.reset_intf_netns("r1-eth0")
    for netns in (MANAGED_VRF, EXCLUDED_NETNS, LATE_EXCLUDED_NETNS, LATE_MANAGED_NETNS):
        r1.run("ip netns del {}".format(netns))


def test_excluded_netns_has_no_vrf():
    "The managed namespace becomes a VRF, the excluded one does not."
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    r1 = tgen.gears["r1"]
    test_func = lambda: MANAGED_VRF in _vrf_names(r1)
    _, result = topotest.run_and_expect(test_func, True, count=30, wait=1)
    assert result, "VRF {} not created".format(MANAGED_VRF)
    assert EXCLUDED_NETNS not in _vrf_names(r1), "excluded netns became a VRF"
    assert _log_count(r1, "NS {} excluded".format(EXCLUDED_NETNS)) == 1


def test_excluded_netns_content_survives_startup_sweep():
    "Routes and nexthop object of the excluded namespace stay in the kernel."
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    r1 = tgen.gears["r1"]
    test_func = lambda: _log_count(r1, "Sweeping the RIB") >= 1
    _, result = topotest.run_and_expect(test_func, True, count=30, wait=1)
    assert result, "startup sweep did not run"

    expected = {"nexthop", FOREIGN_NHID_PREFIX, FOREIGN_PLAIN_PREFIX}
    assert _foreign_content(r1, EXCLUDED_NETNS) == expected, "foreign content removed"


def test_excluded_netns_created_later():
    "A namespace in the list appearing at runtime is ignored, its removal too."
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    r1 = tgen.gears["r1"]
    r1.net.add_netns(LATE_EXCLUDED_NETNS)
    _install_foreign_content(r1, LATE_EXCLUDED_NETNS)

    test_func = partial(_log_count, r1, "NS {} excluded".format(LATE_EXCLUDED_NETNS))
    _, result = topotest.run_and_expect(test_func, 1, count=10, wait=1)
    assert result == 1, "creation of {} not seen as excluded".format(
        LATE_EXCLUDED_NETNS
    )
    assert LATE_EXCLUDED_NETNS not in _vrf_names(r1), "late excluded netns became a VRF"

    expected = {"nexthop", FOREIGN_NHID_PREFIX, FOREIGN_PLAIN_PREFIX}
    assert _foreign_content(r1, LATE_EXCLUDED_NETNS) == expected

    r1.run("ip netns del {}".format(LATE_EXCLUDED_NETNS))
    _, result = topotest.run_and_expect(test_func, 2, count=10, wait=1)
    assert result == 2, "removal of {} not seen as excluded".format(LATE_EXCLUDED_NETNS)
    assert _log_count(r1, "no VRF found using NS {}".format(LATE_EXCLUDED_NETNS)) == 0


def test_other_netns_created_later():
    "A namespace not in the list still becomes a VRF at runtime."
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    r1 = tgen.gears["r1"]
    r1.net.add_netns(LATE_MANAGED_NETNS)
    test_func = lambda: LATE_MANAGED_NETNS in _vrf_names(r1)
    _, result = topotest.run_and_expect(test_func, True, count=10, wait=1)
    assert result, "VRF {} not created at runtime".format(LATE_MANAGED_NETNS)

    r1.run("ip netns del {}".format(LATE_MANAGED_NETNS))
    _, result = topotest.run_and_expect(test_func, False, count=10, wait=1)
    assert not result, "VRF {} not removed".format(LATE_MANAGED_NETNS)


def test_excluded_netns_content_survives_zebra_shutdown():
    "A clean zebra shutdown leaves the excluded namespace content in the kernel."
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    r1 = tgen.gears["r1"]
    # SIGTERM, not the SIGKILL of kill_router_daemons(): only a clean
    # shutdown runs the cleanup that removes zebra's nexthop objects.
    pid = r1.run("cat /var/run/frr/zebra.pid").strip()
    assert pid.isdigit(), "zebra pid not found: {}".format(pid)
    r1.run("kill -TERM {}".format(pid))
    test_func = lambda: r1.run("test -d /proc/{} && echo up".format(pid)).strip()
    _, result = topotest.run_and_expect(test_func, "", count=30, wait=1)
    assert result == "", "zebra did not stop"

    expected = {"nexthop", FOREIGN_NHID_PREFIX, FOREIGN_PLAIN_PREFIX}
    assert _foreign_content(r1, EXCLUDED_NETNS) == expected, "foreign content removed"

    # The next tests need a running zebra, started with the same options.
    start_router_daemons(tgen, "r1", ["zebra"])
    test_func = lambda: MANAGED_VRF in _vrf_names(r1)
    _, result = topotest.run_and_expect(test_func, True, count=30, wait=1)
    assert result, "zebra did not come back"
    assert _foreign_content(r1, EXCLUDED_NETNS) == expected, "foreign content removed"


def test_memory_leak():
    "Run the memory leak test and report results."
    tgen = get_topogen()
    if not tgen.is_memleak_enabled():
        pytest.skip("Memory leak test/report is disabled")

    tgen.report_memory_leaks()


if __name__ == "__main__":
    args = ["-s"] + sys.argv[1:]
    sys.exit(pytest.main(args))
