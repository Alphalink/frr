#!/usr/bin/env python
# SPDX-License-Identifier: GPL-2.0-or-later

#
# test_zebra_netns_vrf_delete.py
#
# Copyright (c) 2026 Alphalink
#

"""
test_zebra_netns_vrf_delete.py: when the netns of a VRF goes away, zebra
closes its netlink sockets while the dplane pthread may still be sending the
uninstall of the routes of that VRF. zebra used to exit on the EBADF of
recvmsg(). Several VRFs with many routes have their netns deleted at once.
"""

import os
import sys
import time

import pytest

CWD = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(CWD, "../"))

from lib.topogen import Topogen, TopoRouter, get_topogen
from lib.topolog import logger

pytestmark = [pytest.mark.staticd]

VRFS = 8
ROUTES = 200
ROUNDS = 4


def build_topo(tgen):
    "One router, no link: each VRF only holds a dummy interface."
    tgen.add_router("r1")


def setup_module(mod):
    "Start zebra and staticd with the netns VRF backend."
    tgen = Topogen(build_topo, mod.__name__)
    tgen.start_topology()

    r1 = tgen.gears["r1"]

    if r1.check_capability(TopoRouter.RD_ZEBRA, "--vrfwnetns") is False:
        pytest.skip("VRF NETNS backend not available on FRR")
    if os.system("ip netns list") != 0:
        pytest.skip("NETNS not available on system")

    r1.use_netns_vrf()
    r1.load_frr_config(
        os.path.join(CWD, "r1/frr.conf"),
        [(TopoRouter.RD_ZEBRA, None), (TopoRouter.RD_STATIC, None)],
    )
    tgen.start_router()


def teardown_module(mod):
    tgen = get_topogen()
    tgen.stop_topology()


def create_vrfs(r1, rnd):
    "Create the VRFs of a round, each with a dummy interface and its routes"
    cmds = ["configure terminal"]
    for i in range(1, VRFS + 1):
        vrf = "vrf{}-{}".format(rnd, i)
        r1.net.add_netns(vrf)
        r1.run("ip -n {} link add dum0 type dummy".format(vrf))
        r1.run("ip -n {} address add 10.0.{}.1/24 dev dum0".format(vrf, i))
        r1.run("ip -n {} link set dum0 up".format(vrf))
        cmds.append("vrf {}".format(vrf))
        for j in range(ROUTES):
            cmds.append(
                "ip route 172.16.{}.{}/32 10.0.{}.2".format(j // 250, j % 250, i)
            )
        cmds.append("exit-vrf")
    r1.vtysh_multicmd("\n".join(cmds))


def routes_installed(r1, vrf):
    "Number of the static routes of the VRF installed in its netns"
    out = r1.run("ip -n {} route show".format(vrf))
    return len([line for line in out.splitlines() if line.startswith("172.16.")])


def test_delete_vrf_netns_with_routes():
    "Zebra survives the netns of VRFs with routes deleted at once"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    r1 = tgen.gears["r1"]

    for rnd in range(ROUNDS):
        create_vrfs(r1, rnd)
        for i in range(1, VRFS + 1):
            vrf = "vrf{}-{}".format(rnd, i)
            for _ in range(60):
                if routes_installed(r1, vrf) == ROUTES:
                    break
                time.sleep(1)
            assert routes_installed(r1, vrf) == ROUTES, "routes of {} missing".format(
                vrf
            )

        logger.info("round %d: deleting the netns of %d VRFs", rnd, VRFS)
        r1.run(
            "for i in $(seq 1 {}); do ip netns del vrf{}-$i & done; wait".format(
                VRFS, rnd
            )
        )
        time.sleep(5)
        assert not r1.check_router_running(), "a daemon died, round {}".format(rnd)

        cmds = ["configure terminal"]
        for i in range(1, VRFS + 1):
            cmds.append("no vrf vrf{}-{}".format(rnd, i))
        r1.vtysh_multicmd("\n".join(cmds))


def test_memory_leak():
    "Run the memory leak test and report results."
    tgen = get_topogen()
    if not tgen.is_memleak_enabled():
        pytest.skip("Memory leak test/report is disabled")

    tgen.report_memory_leaks()


if __name__ == "__main__":
    args = ["-s"] + sys.argv[1:]
    sys.exit(pytest.main(args))
