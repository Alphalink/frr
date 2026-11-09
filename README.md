# FRR 10.7.1 Alphalink

Branche `10.7.1-alphalink_rib-tiebreak-type` : la branche `10.7.1-alphalink`
(candidat rc9) plus le départage par type de route à distance et métrique
égales (ticket 71266), en cours de validation. Le paquet Debian est publié
dans `bookworm-lisos`. Le README d'origine de FRR suit plus bas.

## Ce que la branche ajoute à FRR 10.7.1

- **Correctifs officiels** (16 commits) : des correctifs repris de FRR
  upstream après la 10.7.1, dont le plantage de bgpd sur
  `show bgp l2vpn evpn route vni all json`.
- **Groupes de nexthops du noyau avec le backend netns** (`f1644de9d0` et
  son test) : zebra installe les groupes de nexthops dans le netns de la VRF.
- **Sessions PPP et routes du noyau** (`1851902f97` à `e0a86f82e4`) : zebra
  ne demande plus la vitesse d'une interface PPP, et ne garde ni ne supprime
  à tort les routes du noyau lors des rafales de connexions et déconnexions.
- **EVPN et netns** (`1ed4518461` à `6db22047a2`) : plus de plantage ni
  d'état périmé quand une vxlan, une VRF ou un netns disparaît.
- **Départage à égalité** (`bf27b6352f`, FRR 10.8, puis `25d3cb016a` et son
  test) : à distance et métrique égales, le type de route dont la distance
  par défaut est la plus basse gagne (statique 1 avant BGP 20 ou 200), au
  lieu de la route la plus ancienne ou la plus récente. Une statique
  redistribuée dans BGP ne reste plus bloquée hors de la RIB. Avec ce
  correctif, le `table-map` qui ajoute 1 à la métrique BGP doit être retiré
  dans la même intervention que la mise à jour du paquet.

Les commits Alphalink de ces groupes sont proposés à FRR upstream, une PR
par correctif sur master.

## Build rapide

Sur un Debian 12 avec la source apt FRR 10.7
(`deb-src [signed-by=/usr/share/keyrings/frrouting.gpg] https://deb.frrouting.org/frr bookworm frr-10.7`)
et les dépendances de build installées (`sudo mk-build-deps -r -i debian/control`) :

    git switch 10.7.1-alphalink_rib-tiebreak-type
    git fetch https://github.com/FRRouting/frr tag frr-10.7.1
    export DEBFULLNAME="Prénom Nom" DEBEMAIL="prenom.nom@alphalink.fr"
    alphalink/build-deb.sh --rev 7 --rc 10    # 10.7.1-0~deb12u1+alphalink7~rc10

Le script s'arrête au premier écart. Les `.deb` et `build.log` sont dans
`~/build-frr-<version>/`. Le numéro de version doit changer à chaque build
installé sur une machine, sinon `dpkg-query` ne distingue pas deux paquets
différents et apt ne met pas à jour.

## Build à la main

Les mêmes étapes que le script. La source Debian et le clone sont côte à
côte : le clone ne va pas dans l'arbre de la source.

    # 1. source Debian officielle, version figée
    apt-get source frr=10.7.1-0~deb12u1
    (cd frr-10.7.1 && sudo mk-build-deps -r -i debian/control)

    # 2. un patch par commit depuis le tag, sans l'outillage
    git clone git@github.com:Alphalink/frr.git --branch 10.7.1-alphalink_rib-tiebreak-type
    cd frr
    git log --oneline -1
    git format-patch --zero-commit -k --no-signature --no-base \
        -o ../frr-10.7.1/debian/patches \
        frr-10.7.1..HEAD -- . ':(exclude)alphalink' ':(exclude)README.md'

    # 3. contrôle : tag + patches doit redonner la branche (aucune sortie)
    git worktree add --detach ../verif frr-10.7.1
    git -C ../verif am -q -k ../frr-10.7.1/debian/patches/*.patch
    git diff $(git -C ../verif rev-parse HEAD) HEAD -- . ':(exclude)alphalink' ':(exclude)README.md'
    git worktree remove ../verif

    # 4. liste des patches, version, puis build, depuis la source Debian
    cd ../frr-10.7.1
    (cd debian/patches && ls *.patch > series && wc -l series)
    dch -v 10.7.1-0~deb12u1+alphalink7~rc10 -D bookworm-lisos --force-distribution \
        -u medium "Alphalink: frr-10.7.1 + patches de la branche 10.7.1-alphalink_rib-tiebreak-type"
    dpkg-buildpackage -us -uc -b -j4 2>&1 | tee ../build.log

    # 5. contrôles : autant de patches appliqués que générés, tests passés
    grep -c 'dpkg-source: info: applying ' ../build.log
    grep -E '^=+ .*passed.* =+$' ../build.log

Trois erreurs passent sans message d'erreur et donnent un paquet faux :
- la liste `series` absente ou écrite ailleurs que dans
  `frr-10.7.1/debian/patches/` : quilt n'applique rien, le paquet est le
  10.7.1 officiel ;
- un dossier `debian/patches/` qui contenait déjà des patches d'un build
  précédent : ils sont appliqués en plus ;
- `dch -l+alphalink` au lieu de `-v` : chaque build depuis une source neuve
  porte le même numéro `+alphalink1`.

Le build part du tag `frr-10.7.1` et non de `stable/10.7`, parce que le
paquet source Debian est la 10.7.1 figée.

---

<p align="center">
<img src="https://docs.frrouting.org/en/latest/_static/frr-icon.svg" alt="Icon" width="20%"/>
</p>

FRRouting
=========

[![github-ci](https://github.com/FRRouting/frr/actions/workflows/github-ci.yml/badge.svg?branch=master)](https://github.com/FRRouting/frr/actions/workflows/github-ci.yml)
[![Documentation Status](https://readthedocs.org/projects/frrouting/badge/?version=latest)](https://docs.frrouting.org/en/latest/)

FRR is free software that implements and manages various IPv4 and IPv6 routing
protocols. It runs on nearly all distributions of Linux and BSD and
supports all modern CPU architectures. The project website is
[frrouting.org](https://frrouting.org/).

FRR currently supports the following protocols:

* BGP
* OSPFv2
* OSPFv3
* RIPv1
* RIPv2
* RIPng
* IS-IS
* PIM (SM, DM, SSM, MSDP)
* LDP
* BFD
* Babel
* PBR
* OpenFabric
* VRRP
* EIGRP (alpha)
* NHRP (alpha)

Not every protocol or feature is available on every platform; see the
[feature matrix](https://docs.frrouting.org/en/latest/about.html#feature-matrix)
in the user guide.

**Centralized FRR configuration (work in progress):** the **mgmtd** daemon
applies **YANG** configuration to the routing protocol daemons through the
**northbound** API (instead of each daemon only having its own legacy
configuration path). **Not all daemons are migrated yet**; expect ongoing
changes. See [mgmtd](https://docs.frrouting.org/en/latest/mgmtd.html) in the
user guide.

Installation & Use
------------------

For source tarballs, see the
[releases page](https://github.com/FRRouting/frr/releases).

Pre-built packages: APT for Debian and derivatives
([deb.frrouting.org](https://deb.frrouting.org/)), and RPM for RHEL, Fedora,
and related distributions ([rpm.frrouting.org](https://rpm.frrouting.org/)).

Instructions on building and installing from source for supported platforms may
be found in the
[developer docs](https://docs.frrouting.org/projects/dev-guide/en/latest/building.html).

Once installed, please refer to the [user guide](https://docs.frrouting.org/)
for instructions on use.

Community
---------

See [lists.frrouting.org](https://lists.frrouting.org/) for the list index,
subscription, and archives. The public lists include:

| Topic             | List                         |
|-------------------|------------------------------|
| Development       | dev@lists.frrouting.org      |
| Users & Operators | frog@lists.frrouting.org     |
| Announcements     | announce@lists.frrouting.org |

For chat, we use [Slack](https://frrouting.slack.com). New members can join
via the invite link on the [community](https://frrouting.org/community/) page.


Contributing
------------

See [submitting patches and enhancements](https://docs.frrouting.org/projects/dev-guide/en/latest/workflow.html#submitting-patches-and-enhancements)
and the [commit guidelines](https://docs.frrouting.org/projects/dev-guide/en/latest/workflow.html#commit-guidelines)
when contributing. FRR maintains
[developer's documentation](https://docs.frrouting.org/projects/dev-guide/en/latest/index.html)
with the full [project workflow](https://docs.frrouting.org/projects/dev-guide/en/latest/workflow.html)
and contributor expectations; technical documentation on internals is also
available.

We welcome and appreciate all contributions, no matter how small!


License
-------

Per-file licenses use SPDX identifiers; see `COPYING` and `doc/licenses/`.
The combined work is generally understood to be distributable under **GNU
General Public License version 2 or later** (GPLv2+); see `COPYING` for
details. FRR's documentation uses a separate custom permissive license (see
`COPYING` for background).


Security
--------

To report security issues, please use our security mailing list:

```
security [at] lists.frrouting.org
```
