# FRR 10.5.5 Alphalink

Branche `10.5.5-alphalink2` : FRR 10.5.5 officiel plus quatre changements,
livrés dans le paquet Debian `bookworm-lisos`. Le README d'origine de FRR
suit plus bas.

Elle remplace `10.5.5-alphalink`, dont elle retire trois commits staticd non
nécessaires à la métrique (`f97435db48`, `f6f6f318c6`, `09f028eb40`).
`f6f6f318c6` (PR 23059) laisse non installées, après une rafale de sessions,
des statiques via une interface recréée : régression upstream, master et 10.8.

## Ce que la branche ajoute à FRR 10.5.5

- **Correctifs officiels** (18 commits) : les correctifs publiés par FRR sur
  `stable/10.5` après la 10.5.5, dont le plantage de bgpd sur
  `show bgp l2vpn evpn route vni all json`. Ils seront dans la future 10.5.6.
- **Métrique des routes statiques** (9 commits, FRR 10.7, PR 21296) :
  `ip route P NH metric M`. zebra choisit entre des chemins de même
  distance selon leur métrique, par exemple une statique de secours derrière BGP.
- **IPv4 via voisin IPv6** (`11267be4d2`, FRR 10.6) : une route IPv4 dont le
  voisin est IPv6 (BGP par interface, statique via `fe80::`) est installée
  `via inet6` au lieu de `169.254.0.1`, sans configuration.
- **Départage à égalité** (`20af103935`, FRR 10.8) : à distance et métrique
  égales, la route la plus récente gagne au lieu de la plus ancienne. Un
  écart de métrique, même d'une unité, reste le moyen d'avoir un choix stable.

## Branche `10.5.5-nhg-netns` : groupes de nexthop noyau avec le backend netns

Trois commits de plus (ticket 72002) : `413c014ecf` lève le verrou de 2020 qui
désactivait `zebra nexthop kernel enable` avec `--vrfwnetns` et fait porter la
netns par chaque groupe ; `d03d1423fc` distingue les groupes v4 et v6 à membres
« interface seule » ; `6ce1809985` ignore les événements noyau d'une autre netns
qui réutilisent un identifiant. Effet : les routes ECMP v6 sur interfaces
seules s'installent (le noyau refuse ces routes sans objet nexthop). La version
pour upstream est la branche `zebra-nhg-netns`, sur master, avec topotests.

### Condition de déploiement : un seul FRR écrit dans chaque netns vue par muli

zebra en mode `--vrfwnetns` tient chaque netns de `/run/netns` pour la sienne.
À son démarrage il lit les objets nexthop au protocole `zebra` et les routes aux
protocoles FRR qui s'y trouvent, puis son balayage de démarrage efface du noyau
tout ce qu'aucun client n'a réclamé. Mesuré sur maquette : si le RR de `mulirr`
a des objets et des routes, chaque redémarrage de `frr@muli` les supprime et le
RR ne remet pas ses routes (22 statiques « installées » dans sa RIB, 3 dans le
noyau). Même résultat avec FRR master.

En production la condition tient : le RR a `bgp no-rib`, aucune route statique
et `no zebra nexthop kernel enable`, donc rien à lire. Pour qu'elle n'ait plus
à tenir, cacher la netns au seul service `frr@muli`, sans toucher à FRR :

    # /etc/systemd/system/frr@muli.service.d/hide-mulirr.conf
    [Unit]
    After=ifupdown-netns@muli.service ifupdown-netns@mulirr.service
    Requires=ifupdown-netns@muli.service

    [Service]
    InaccessiblePaths=-/run/netns/mulirr

Validé sur maquette : `show vrf` de muli sans `mulirr`, session BGP avec le RR
intacte, redémarrage de muli sans aucune suppression chez le RR, netns créées
plus tard toujours découvertes. Limite : si `mulirr` est détruite puis recréée
pendant que `frr@muli` tourne, le nouveau montage se propage par-dessus le
masque jusqu'au prochain redémarrage de `frr@muli`. Contrôle : `vtysh -N muli
-c 'show vrf'` ne doit pas lister `mulirr`, `ip -n mulirr nexthop show` doit
rester vide.

## Build rapide

Sur un Debian 12 avec la source apt FRR 10.5
(`deb-src [signed-by=/usr/share/keyrings/frrouting.gpg] https://deb.frrouting.org/frr bookworm frr-10.5`)
et les dépendances de build installées (`sudo mk-build-deps -r -i debian/control`) :

    git switch 10.5.5-alphalink2
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
