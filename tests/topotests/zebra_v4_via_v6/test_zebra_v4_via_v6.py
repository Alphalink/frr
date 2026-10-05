#!/usr/bin/env python
# SPDX-License-Identifier: ISC

#
# test_zebra_v4_via_v6.py
#

"""
test_zebra_v4_via_v6.py: IPv4 static routes with IPv6 link-local nexthops
must be installed with RTA_VIA when "zebra v4-via-v6 rta-via" is configured,
so that the kernel resolves the neighbor through NDP (no RA, no 169.254.0.1).

Topology:  r2 --(10.0.1.0/24)-- r1 --(10.0.2.0/24)-- r3
"""

import os
import re
import sys

import pytest

CWD = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(CWD, "../"))

# pylint: disable=C0413
from lib import topotest
from lib.topogen import Topogen, get_topogen
from lib.common_config import step

pytestmark = [pytest.mark.staticd]


def build_topo(tgen):
    for rname in ("r1", "r2", "r3"):
        tgen.add_router(rname)

    tgen.add_link(tgen.gears["r1"], tgen.gears["r2"], "r1-eth0", "r2-eth0")
    tgen.add_link(tgen.gears["r1"], tgen.gears["r3"], "r1-eth1", "r3-eth0")


def setup_module(mod):
    tgen = Topogen(build_topo, mod.__name__)
    tgen.start_topology()

    for rname, router in tgen.routers().items():
        router.load_frr_config(os.path.join(CWD, "{}/frr.conf".format(rname)))

    tgen.start_router()


def teardown_module():
    get_topogen().stop_topology()


def link_local(router, ifname):
    out = router.cmd("ip -6 addr show dev {} scope link".format(ifname))
    m = re.search(r"inet6 (fe80::[0-9a-f:]+)/", out)
    assert m, "no link-local address on {}: {}".format(ifname, out)
    return m.group(1)


def kernel_route(r1, prefix):
    return r1.cmd("ip route show {}".format(prefix))


def wait_kernel_route(r1, prefix, expected):
    def check():
        out = kernel_route(r1, prefix)
        return None if all(e in out for e in expected) else out

    _, result = topotest.run_and_expect(check, None, count=30, wait=1)
    assert result is None, "kernel route {}: {}".format(prefix, kernel_route(r1, prefix))


def ping(r1, dest):
    out = r1.cmd("ping -c 3 -W 2 {}".format(dest))
    return " 0% packet loss" in out


def test_single_nexthop_rta_via():
    "Static IPv4 route via fe80::x is installed with RTA_VIA and passes traffic"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    r1, r2 = tgen.gears["r1"], tgen.gears["r2"]
    ll2 = link_local(r2, "r2-eth0")

    step("No RA is sent: the 169.254.0.1 neighbor must never exist")
    r1.vtysh_cmd(
        "configure terminal\nip route 1.1.1.1/32 {} r1-eth0".format(ll2)
    )

    wait_kernel_route(r1, "1.1.1.1/32", ["via inet6 {}".format(ll2), "dev r1-eth0"])
    out = kernel_route(r1, "1.1.1.1/32")
    assert "169.254.0.1" not in out and "onlink" not in out, out

    step("End to end traffic")
    assert ping(r1, "1.1.1.1"), "ping 1.1.1.1 failed"


def test_multipath_rta_via():
    "ECMP of two IPv6 link-local nexthops"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    r1, r2, r3 = tgen.gears["r1"], tgen.gears["r2"], tgen.gears["r3"]
    ll2 = link_local(r2, "r2-eth0")
    ll3 = link_local(r3, "r3-eth0")

    r1.vtysh_cmd(
        "configure terminal\n"
        "ip route 2.2.2.2/32 {} r1-eth0\n"
        "ip route 2.2.2.2/32 {} r1-eth1".format(ll2, ll3)
    )

    wait_kernel_route(
        r1,
        "2.2.2.2/32",
        [
            "nexthop via inet6 {} dev r1-eth0".format(ll2),
            "nexthop via inet6 {} dev r1-eth1".format(ll3),
        ],
    )
    assert ping(r1, "2.2.2.2"), "ping 2.2.2.2 failed"


def test_mixed_ecmp_rta_via():
    "ECMP mixing an IPv6 link-local nexthop and a plain IPv4 nexthop"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    r1, r2 = tgen.gears["r1"], tgen.gears["r2"]
    ll2 = link_local(r2, "r2-eth0")

    # 3.3.3.3 lives on r3 (reached with a plain v4 gateway); a second path
    # through r2 is only there to check the encoding of a mixed nexthop set.
    r1.vtysh_cmd(
        "configure terminal\n"
        "ip route 3.3.3.3/32 10.0.2.2 r1-eth1\n"
        "ip route 3.3.3.3/32 {} r1-eth0".format(ll2)
    )

    wait_kernel_route(
        r1,
        "3.3.3.3/32",
        [
            "nexthop via inet6 {} dev r1-eth0".format(ll2),
            "nexthop via 10.0.2.2 dev r1-eth1",
        ],
    )


def test_rib_nexthop_installed():
    "RIB shows the IPv6 nexthop as installed"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    r1, r2 = tgen.gears["r1"], tgen.gears["r2"]
    ll2 = link_local(r2, "r2-eth0")

    out = r1.vtysh_cmd("show ip route 1.1.1.1/32 json", isjson=True)
    nh = out["1.1.1.1/32"][0]["nexthops"][0]
    assert nh["ip"] == ll2 and nh["installed"] is True, nh


def test_default_unchanged_without_knob():
    "Without the knob the historical 169.254.0.1 encoding is kept"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    r1, r2 = tgen.gears["r1"], tgen.gears["r2"]
    ll2 = link_local(r2, "r2-eth0")

    r1.vtysh_cmd("configure terminal\nno zebra v4-via-v6 rta-via")
    r1.vtysh_cmd(
        "configure terminal\n"
        "no ip route 1.1.1.1/32 {ll} r1-eth0\n"
        "ip route 1.1.1.1/32 {ll} r1-eth0".format(ll=ll2)
    )
    wait_kernel_route(r1, "1.1.1.1/32", ["via 169.254.0.1", "onlink"])


if __name__ == "__main__":
    args = ["-s"] + sys.argv[1:]
    sys.exit(pytest.main(args))
