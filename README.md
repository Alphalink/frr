# FRR 10.5.5 Alphalink

Branche `10.5.5-alphalink` : FRR 10.5.5 officiel plus quatre changements,
livrés dans le paquet Debian `bookworm-lisos`. Le README d'origine de FRR
suit plus bas.

## Ce que la branche ajoute à FRR 10.5.5

- **Correctifs officiels** (18 commits) : les correctifs publiés par FRR sur
  `stable/10.5` après la 10.5.5, dont le plantage de bgpd sur
  `show bgp l2vpn evpn route vni all json`. Ils seront dans la future 10.5.6.
- **Métrique des routes statiques** (12 commits, FRR 10.7, PR 21296 et
  suites) : `ip route P NH metric M`. zebra choisit entre des chemins de même
  distance selon leur métrique, par exemple une statique de secours derrière BGP.
- **IPv4 via voisin IPv6** (`11267be4d2`, FRR 10.6) : une route IPv4 dont le
  voisin est IPv6 (BGP par interface, statique via `fe80::`) est installée
  `via inet6` au lieu de `169.254.0.1`, sans configuration.
- **Départage à égalité** (`20af103935`, FRR 10.8) : à distance et métrique
  égales, la route la plus récente gagne au lieu de la plus ancienne. Un
  écart de métrique, même d'une unité, reste le moyen d'avoir un choix stable.

## Build rapide

Sur un Debian 12 avec la source apt FRR 10.5
(`deb-src [signed-by=/usr/share/keyrings/frrouting.gpg] https://deb.frrouting.org/frr bookworm frr-10.5`)
et les dépendances de build installées (`sudo mk-build-deps -r -i debian/control`) :

    git switch 10.5.5-alphalink
    git fetch https://github.com/FRRouting/frr tag frr-10.5.5
    export DEBFULLNAME="Prénom Nom" DEBEMAIL="prenom.nom@alphalink.fr"
    alphalink/build-deb.sh --rev 4            # 10.5.5-0~deb12u1+alphalink4
    alphalink/build-deb.sh --rev 4 --rc 1     # candidat : +alphalink4~rc1

Le script s'arrête au premier écart. Les `.deb` et `build.log` sont dans
`~/build-frr-<version>/`. `N` de `+alphalinkN` doit être supérieur à toute
version déjà publiée, sinon apt ne met pas à jour.

## Build à la main

Les mêmes étapes que le script, depuis la racine du clone :

    # 1. un patch par commit depuis le tag, sans l'outillage
    git format-patch --zero-commit -k --no-signature --no-base -o ../patches \
        frr-10.5.5..HEAD -- . ':(exclude)alphalink' ':(exclude)README.md'
    (cd ../patches && ls *.patch > series && wc -l series)

    # 2. contrôle : tag + patches doit redonner la branche (aucune sortie)
    git worktree add --detach ../verif frr-10.5.5
    git -C ../verif am -q -k ../patches/*.patch
    git diff $(git -C ../verif rev-parse HEAD) HEAD -- . ':(exclude)alphalink' ':(exclude)README.md'
    git worktree remove ../verif

    # 3. source Debian officielle, version figée, et pose des patches
    cd .. && apt-get source frr=10.5.5-0~deb12u1
    mkdir -p frr-10.5.5/debian/patches
    cp patches/*.patch patches/series frr-10.5.5/debian/patches/

    # 4. version, puis build
    cd frr-10.5.5
    dch -v 10.5.5-0~deb12u1+alphalink4 -D bookworm-lisos --force-distribution \
        "Alphalink: frr-10.5.5 + patches de la branche 10.5.5-alphalink"
    dpkg-buildpackage -us -uc -b -j4 2>&1 | tee ../build.log

    # 5. contrôles : autant de patches appliqués que générés, tests passés
    grep -c 'dpkg-source: info: applying ' ../build.log
    grep -E '^=+ .*passed.* =+$' ../build.log

Le build part du tag `frr-10.5.5` et non de `stable/10.5`, parce que le
paquet source Debian est la 10.5.5 figée : partir de `stable/10.5`
ferait perdre les 18 correctifs sans aucune erreur.

---

<p align="center">
<img src="http://docs.frrouting.org/en/latest/_static/frr-icon.svg" alt="Icon" width="20%"/>
</p>

FRRouting
=========

FRR is free software that implements and manages various IPv4 and IPv6 routing
protocols. It runs on nearly all distributions of Linux and BSD and
supports all modern CPU architectures.

FRR currently supports the following protocols:

* BGP
* OSPFv2
* OSPFv3
* RIPv1
* RIPv2
* RIPng
* IS-IS
* PIM-SM/MSDP
* LDP
* BFD
* Babel
* PBR
* OpenFabric
* VRRP
* EIGRP (alpha)
* NHRP (alpha)

Installation & Use
------------------

For source tarballs, see the
[releases page](https://github.com/FRRouting/frr/releases).

For Debian and its derivatives, use the APT repository at
[https://deb.frrouting.org/](https://deb.frrouting.org/).

Instructions on building and installing from source for supported platforms may
be found in the
[developer docs](http://docs.frrouting.org/projects/dev-guide/en/latest/building.html).

Once installed, please refer to the [user guide](http://docs.frrouting.org/)
for instructions on use.

Community
---------

The FRRouting email list server is located
[here](https://lists.frrouting.org/listinfo) and offers the following public
lists:

| Topic             | List                         |
|-------------------|------------------------------|
| Development       | dev@lists.frrouting.org      |
| Users & Operators | frog@lists.frrouting.org     |
| Announcements     | announce@lists.frrouting.org |

For chat, we currently use [Slack](https://frrouting.slack.com). You can join
by clicking the "Slack" link under the
[Participate](https://frrouting.org/community) section of our website.


Contributing
------------

FRR maintains [developer's documentation](http://docs.frrouting.org/projects/dev-guide/en/latest/index.html)
which contains the [project workflow](http://docs.frrouting.org/projects/dev-guide/en/latest/workflow.html)
and expectations for contributors. Some technical documentation on project
internals is also available.

We welcome and appreciate all contributions, no matter how small!


Security
--------

To report security issues, please use our security mailing list:

```
security [at] lists.frrouting.org
```
