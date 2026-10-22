# AperiSolve — native setup (CTF steganalysis workbench)

Upstream [Zeecka/AperiSolve](https://github.com/Zeecka/AperiSolve) @ `ab97840` (v3.7.12),
running natively on this machine. Four local modifications are applied
(uncommitted — see `git diff`); everything else is stock upstream.

## Quick start

```bash
./setup.sh     # once: venv, deps, gettext catalogs, SQLite schema, tool probe
./start.sh     # redis -> rq worker -> flask, then open http://127.0.0.1:5000
./stop.sh      # tear down
```

Logs land in `logs/`. Env vars are in `env.local.sh` (`source` it if running by hand).

`start.sh` prints every reachable address on success. On this host that is:

```
local:  http://127.0.0.1:5000/
LAN:    http://192.168.204.138:5000/      eth0, the 192.168.204.0/24 segment
LAN:    http://10.0.3.1:5000/            lxcbr0 bridge
```

## Network exposure

`FLASK_HOST=0.0.0.0` in `env.local.sh`, so the server answers on loopback and
every interface at once. To narrow it, edit that variable — set it to
`192.168.204.138` to serve the LAN only, or back to `127.0.0.1` for local-only.

Binding `0.0.0.0` also publishes the `lxcbr0` bridge address, which a LAN-only
bind would not. To keep both localhost and LAN while hiding the bridge, either
bind the specific address and accept losing loopback, or filter the port:

```bash
sudo iptables -A INPUT ! -i eth0 -p tcp --dport 5000 -j DROP
```

Consider before exposing this beyond a trusted network:

- **No authentication.** Anyone who can reach the port can upload, read any
  result whose 32-hex hash they know, and call `/remove/<hash>`.
- **Uploaded files are fed to third-party binaries.** 16 of the 19 registered
  analyzers shell out to one; `color_remapping`, `decomposer` and `pcrt` are
  pure Python. `binwalk --extract` is the broadest attack surface, since it
  hands attacker-controlled bytes to external utilities (`tar`, `dd`, …) and
  writes whatever they emit.
  - Extractor containment is delegated, not enforced by AperiSolve. binwalk
    rewrites escaping **symlinks** itself (`symlink_sanitizer` in
    `binwalk/modules/extractor.py`, on unless `-1` is passed), but it does not
    validate ordinary extracted filenames — `os.path.join(extraction_directory, f)`
    is taken as-is. In practice the extraction utilities it invokes do their
    own member-path sanitization, which is the actual barrier. Treat this as
    unverified-by-design rather than a proven-safe boundary.
  - `foremost` is not part of this surface: it carves known signatures out of
    raw bytes into a flat output directory and never unpacks an archive, so
    archive-entry path traversal does not apply to it.
- Upstream's hardening is a baseline only (`X-Frame-Options: SAMEORIGIN`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy`,
  `Permissions-Policy`); see `aperisolve/app.py:_register_error_handlers` and
  the `after_request` hooks.

Two mitigations are already in place: `MAX_STORE_TIME=86400` shortens the window
uploaded files sit on disk, and the rate limiter exempts only loopback
(`aperisolve/limits.py:is_local_request`), so LAN clients are throttled while
local use is not.

## Differences from upstream Docker Compose

| Upstream | Here | Why |
|---|---|---|
| `postgres` service, `psycopg2-binary` | SQLite at `./aperisolve.db` | Avoids standing up a DB server; `models.py` uses no Postgres-specific types |
| `redis` service | localhost `redis-server` on 6379 | Worker and rate limiter both need it; `start.sh` launches it |
| `MAX_CONTENT_LENGTH=1 MB` | 16 MB | The 1 MB cap returns HTTP 413 *before* any analyzer runs, which rejects most CTF images |

`psycopg2-binary` is intentionally not installed — SQLite makes it dead weight.

Missing external binaries are not fatal. `base_analyzer.analyze()` records
`{"status": "error", ...}` per analyzer and `workers.run_analyzer` catches the
re-raise, so one dead tool never aborts the submission.

## Analyzer tool binaries

`setup.sh` probes for these and prints `[ok]`/`[MISS]`. Install with:

```bash
sudo apt-get install -y foremost steghide pngcheck graphicsmagick ffmpeg expect
```

Two are not packaged anywhere on Kali and must be built or fetched:

```bash
# OpenStego 0.8.6 — version pinned in the upstream Dockerfile
wget https://github.com/syvaidya/openstego/releases/download/openstego-0.8.6/openstego_0.8.6-1_all.deb
sudo dpkg -i openstego_0.8.6-1_all.deb

# jsteg — Go, pinned commit. GOFLAGS=-mod=mod is required: the vendored
# modules.txt predates Go 1.27 and the build fails on a consistency check.
git clone https://github.com/lukechampine/jsteg.git && cd jsteg
git checkout cf206c26c711db215c11cb61bb479113ae8be275
GOFLAGS=-mod=mod go build -o /tmp/jsteg ./cmd/jsteg && sudo install -m 0755 /tmp/jsteg /usr/local/bin/jsteg

# jphide / jpseek — C, pinned commit. The Makefile needs patching before it
# will link against the bundled jpeg-8a.
sudo apt-get install -y libjpeg-dev autoconf
git clone https://github.com/h3xx/jphs.git && cd jphs
git checkout 33a11e1bad146f5e9c0d3fe6475812a1cedb9b7e
cp /path/to/AperiSolve/docker/config.guess /path/to/AperiSolve/docker/config.sub jpeg-8a/
(cd jpeg-8a && chmod +x config.guess config.sub && ./configure && make)

# The five sed lines from Dockerfile:32-36 — without all of them the link fails.
sed -i 's/open(seekfilename,O_WRONLY|O_TRUNC|O_CREAT)/open(seekfilename,O_WRONLY|O_TRUNC|O_CREAT, 0644)/' jpseek.c
sed -i 's/^LIBS = .*/JPEG_OBJS = $(filter-out jpeg-8a\/cjpeg.o jpeg-8a\/djpeg.o jpeg-8a\/jpegtran.o jpeg-8a\/rdjpgcom.o jpeg-8a\/wrjpgcom.o,$(wildcard jpeg-8a\/*.o))/' Makefile
sed -i 's/^LDFLAGS = .*/LDFLAGS =/' Makefile
sed -i 's/^jphide: \(.*\)$/jphide: \1 $(JPEG_OBJS)/' Makefile
sed -i 's/^jpseek: \(.*\)$/jpseek: \1 $(JPEG_OBJS)/' Makefile

make && sudo install -m 0755 jphide jpseek /usr/local/bin/
```

`expect` is required even though no analyzer names it as its tool: `jpseek.py`
drives the interactive passphrase prompt through `expect -c`. The `identify`
analyzer also invokes plain `identify`, not `gm identify`, so install
`graphicsmagick-imagemagick-compat` if `identify` is absent.

### Known tool limitations on this host

- **outguess** — absent from Kali repos, and the source
  (`resurrecting-open-source-projects/outguess`) does not compile against a
  modern GCC: its bundled `jpeg-6b-steg/jpeglib.h` declares `jpeg_std_error`,
  `jpeg_CreateCompress` and friends with zero parameters, so every call site is
  a hard error. `-w -fcommon -std=gnu89` do not help; the headers need patching.
  The analyzer is `deep_only` and JPEG-only, so it is the cheapest to skip.
- **steghide / jphide embedding** — both write 0-byte output files on this
  Debian build (`steghide embed` reports success then produces nothing; jphide
  does the same). Extraction and `steghide info` both work correctly, which is
  all AperiSolve invokes. Only manual payload-crafting for round-trip tests is
  affected.
- **jsteg** needs a color JPEG large enough for the payload; it refuses
  grayscale and small images.

## Local modifications

Four in total. The first two unblock BMP analysis; the last two are the same
stderr-versus-exit-status defect in two more analyzers.

### 1. `aperisolve/analyzers/zsteg.py` — `accepts`

`accepts` gated the analyzer to PNG, so `get_analyzers(deep, tags)` skipped it
for any BMP: a BMP upload produced 10 analyzer results and no `zsteg` key. zsteg
itself supports BMP; the gate was stricter than the tool. `steghide`, by
contrast, already lists `bmp` in its own `accepts`.

```diff
-    accepts = frozenset({"png"})
+    accepts = frozenset({"png", "bmp"})
```

### 2. `aperisolve/analyzers/zsteg.py` — `is_error`

The original treated any stderr output as failure. zsteg writes advisory lines
to stderr on a successful run — for a BMP with trailing padding, exactly
`[?] 2 bytes of extra data after image end (IEND), offset = 0x269b0e` — while
exiting 0. Because `get_results()` returns `process_error()` (stderr only) once
`is_error` is true, the stdout carrying the extracted payload was discarded.

```diff
-        return bool(stderr) or "PNG::NotSupported" in stdout[:100]
+        return returncode != 0 or "PNG::NotSupported" in stdout[:100]
```

### 3. `aperisolve/analyzers/binwalk.py` — drop `--run-as=root`

The command passed `--run-as=root`, which upstream needs because its container
runs as root. binwalk refuses to even load its Extractor module in that
combination for a non-root caller (`binwalk/modules/extractor.py`: the
`runas_uid != os.getuid() and os.getuid() != 0` guard), so every native run
died with `ModuleException` before scanning anything. Omitting the flag makes
binwalk extract as the current user, which is also the safer default on a
service that is now reachable from the LAN.

```diff
             "-e",
             self.img,
-            "--run-as=root",
         ]
```

### 4. `aperisolve/analyzers/binwalk.py` — `is_error`

Same defect as the zsteg case: binwalk exits 0 but writes
`WARNING: One or more files failed to extract` to stderr whenever a signature
has no helper utility, so any clean scan of a file with no extractable payload
was reported as an error.

```diff
-        return len(stderr) > 0 and not zip_exist
+        return returncode != 0 and not zip_exist
```

## Verified on this host

`qs.bmp` — 11 analyzers run, 9 `ok`, 2 `error`. The two errors are correct
negative results rather than missing tools: `openstego` needs a password and
`steghide` reports no payload, both true of this file.

```
zsteg  ok  b1,msb,bY .. text: "qwxf{you_say_chick_beautiful?}"
```

jsteg round-trip through the platform, to confirm the compiled binary is wired
up rather than merely present: `jsteg hide` a payload into a JPEG, upload it,
and the `jsteg` analyzer returns the payload verbatim.

## Gotcha when re-testing

`submission_hash` is `md5(image_bytes + filename + password)`. Re-uploading an
unchanged file with unchanged options hits the existing submission and returns
early without enqueuing a job, so a second run silently reuses stale results.
Force a fresh run by clearing state:

```bash
source env.local.sh
.venv/bin/python -c "
from aperisolve.app import create_app; from aperisolve.models import db
from aperisolve.config import RESULT_FOLDER; import shutil
app=create_app()
with app.app_context(): db.drop_all(); db.create_all()
shutil.rmtree(RESULT_FOLDER, ignore_errors=True)"
```
