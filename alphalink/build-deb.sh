#!/bin/bash
# Build the Alphalink FRR Debian package on a Debian 12 builder.
#
# Takes the official FRR source package (apt source), adds every commit of
# this branch since UPSTREAM_TAG as a quilt patch, sets the Alphalink
# version and runs dpkg-buildpackage. See README.md, "Construire le paquet".
#
# Usage: alphalink/build-deb.sh --rev N [--rc K] [--jobs J] [--workdir DIR]
#   --rev N    Alphalink revision: version suffix +alphalinkN (mandatory)
#   --rc K     release candidate: suffix +alphalinkN~rcK (optional)
#   --jobs J   parallel make jobs (default 4, shared builder)
#   --workdir  build directory (default ~/build-frr-<version>)
set -euo pipefail

# The source package and the tag MUST be the same FRR release.
readonly UPSTREAM_TAG="frr-10.5.5"
readonly DEB_SRC_VERSION="10.5.5-0~deb12u1"
readonly DEB_DIST="bookworm-lisos"
# Paths that belong to this tooling, never shipped as patches.
readonly EXCLUDES=(":(exclude)alphalink" ":(exclude)README.md")

die() { echo "STOP: $*" >&2; exit 1; }
step() { echo; echo "=== $*"; }

parse_args() {
	REV="" RC="" JOBS=4 WORKDIR=""
	while [ $# -gt 0 ]; do
		case "$1" in
		--rev) REV="${2:-}"; shift 2 ;;
		--rc) RC="${2:-}"; shift 2 ;;
		--jobs) JOBS="${2:-}"; shift 2 ;;
		--workdir) WORKDIR="${2:-}"; shift 2 ;;
		*) die "unknown argument: $1 (see header of $0)" ;;
		esac
	done
	[[ "$REV" =~ ^[1-9][0-9]*$ ]] || die "--rev N required (N >= 1)"
	[[ -z "$RC" || "$RC" =~ ^[1-9][0-9]*$ ]] || die "--rc must be >= 1"
	[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || die "--jobs must be >= 1"
	VERSION="${DEB_SRC_VERSION}+alphalink${REV}${RC:+~rc${RC}}"
	WORKDIR="${WORKDIR:-$HOME/build-frr-${VERSION//\~/_}}"
}

# The branch must be committed and based on the same release as the source.
check_repo() {
	[ -z "$(git status --porcelain)" ] || die "uncommitted changes"
	git rev-parse -q --verify "refs/tags/$UPSTREAM_TAG" >/dev/null ||
		die "tag $UPSTREAM_TAG missing: git fetch upstream --tags"
	git merge-base --is-ancestor "$UPSTREAM_TAG" HEAD ||
		die "HEAD does not descend from $UPSTREAM_TAG"
	[ ! -e "$WORKDIR" ] || die "$WORKDIR exists, pick another --workdir"
}

# A commit mixing tooling and FRR code would be silently cut in half.
check_no_mixed_commits() {
	local sha in_tool in_code
	for sha in $(git rev-list --no-merges "$UPSTREAM_TAG..HEAD"); do
		in_tool=$(git diff-tree --no-commit-id --name-only -r "$sha" \
			-- alphalink README.md | wc -l)
		in_code=$(git diff-tree --no-commit-id --name-only -r "$sha" \
			-- . "${EXCLUDES[@]}" | wc -l)
		[ "$in_tool" -eq 0 ] || [ "$in_code" -eq 0 ] ||
			die "commit $sha mixes alphalink/README.md and FRR code"
	done
}

export_patches() {
	local dir="$1"
	git format-patch -q --zero-commit -k --no-signature --no-base \
		-o "$dir" "$UPSTREAM_TAG..HEAD" -- . "${EXCLUDES[@]}"
	local f
	for f in "$dir"/*.patch; do basename "$f"; done > "$dir/series"
	PATCH_COUNT=$(( $(wc -l < "$dir/series") ))
	[ "$PATCH_COUNT" -gt 0 ] || die "no patch generated"
	echo "$PATCH_COUNT patches"
}

# Applying the patches on the tag must give back this branch, file for file.
verify_patches() {
	local dir="$1" tree="$2"
	git worktree add -q --detach "$tree" "$UPSTREAM_TAG"
	git -C "$tree" -c user.name=check -c user.email=check@invalid \
		am -q -k "$dir"/*.patch || die "git am failed on $UPSTREAM_TAG"
	git diff --quiet "$(git -C "$tree" rev-parse HEAD)" HEAD \
		-- . "${EXCLUDES[@]}" || die "patched tag differs from HEAD"
	git worktree remove --force "$tree"
	echo "tag + patches = HEAD (outside alphalink/ and README.md)"
}

fetch_source() {
	mkdir -p "$WORKDIR"
	(cd "$WORKDIR" && apt-get source -q "frr=$DEB_SRC_VERSION") ||
		die "apt source failed: deb-src for FRR 10.5 configured?"
	SRC_DIR="$WORKDIR/frr-${DEB_SRC_VERSION%%-*}"
	head -1 "$SRC_DIR/debian/changelog" | grep -qF "($DEB_SRC_VERSION)" ||
		die "unexpected debian/changelog version"
	grep -qx '3.0 (quilt)' "$SRC_DIR/debian/source/format" ||
		die "source format is not 3.0 (quilt)"
	[ ! -e "$SRC_DIR/debian/patches/series" ] ||
		die "source already has debian/patches/series, review it first"
}

check_build_deps() {
	dpkg-query -W -f='${Status}' frr-build-deps 2>/dev/null |
		grep -q 'ok installed' && return 0
	die "build deps missing, run once: (cd $SRC_DIR &&" \
		"sudo mk-build-deps -r -i debian/control), then rerun"
}

install_patches() {
	local dir="$1"
	mkdir -p "$SRC_DIR/debian/patches"
	cp "$dir"/*.patch "$dir/series" "$SRC_DIR/debian/patches/"
}

set_version() {
	local head
	head=$(git rev-parse --short=10 HEAD)
	: "${DEBEMAIL:?set DEBEMAIL (work address) and DEBFULLNAME}"
	(cd "$SRC_DIR" && dch -v "$VERSION" -D "$DEB_DIST" \
		--force-distribution -u medium \
		"Alphalink: $UPSTREAM_TAG + $PATCH_COUNT patches from branch" \
		"$(git rev-parse --abbrev-ref HEAD) at $head. See README.md.")
	head -1 "$SRC_DIR/debian/changelog" | grep -qF "($VERSION)" ||
		die "dch did not set $VERSION"
}

build() {
	local rc
	set +e
	(cd "$SRC_DIR" && dpkg-buildpackage -us -uc -b -j"$JOBS") 2>&1 |
		tee "$WORKDIR/build.log"
	rc=${PIPESTATUS[0]}
	set -e
	[ "$rc" -eq 0 ] || die "dpkg-buildpackage exit $rc, see build.log"
}

# Proof from the log, not from the exit code alone.
check_build_log() {
	local log="$WORKDIR/build.log" applied summary
	applied=$(grep -c 'dpkg-source: info: applying ' "$log" || true)
	[ "$applied" -eq "$PATCH_COUNT" ] ||
		die "$applied patches applied, $PATCH_COUNT expected"
	# FRR unit tests run through pytest; automake's TOTAL is always 0.
	summary=$(grep -E '^=+ .*passed.* =+$' "$log" | tail -1 || true)
	[ -n "$summary" ] || die "no pytest summary: unit tests did not run"
	echo "unit tests: $summary"
	! grep -qE '^=+ .*(failed|error).* =+$' "$log" ||
		die "unit test failures in build.log"
	ls -1 "$WORKDIR"/*"+alphalink${REV}${RC:+~rc${RC}}_"*.deb
}

main() {
	parse_args "$@"
	cd "$(git rev-parse --show-toplevel)"
	check_repo
	check_no_mixed_commits
	local tmp
	tmp=$(mktemp -d)
	step "1/5 patches $UPSTREAM_TAG..HEAD"
	export_patches "$tmp/patches"
	verify_patches "$tmp/patches" "$tmp/verify"
	step "2/5 source frr=$DEB_SRC_VERSION into $WORKDIR"
	fetch_source
	check_build_deps
	install_patches "$tmp/patches"
	cp -r "$tmp/patches" "$WORKDIR/patches"
	step "3/5 version $VERSION"
	set_version
	step "4/5 dpkg-buildpackage (long)"
	build
	step "5/5 checks"
	check_build_log
	echo "OK $VERSION, $PATCH_COUNT patches, log $WORKDIR/build.log"
}

main "$@"
