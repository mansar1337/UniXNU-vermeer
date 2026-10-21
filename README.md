# XNU source build for the vermeer port

This repository completed the first build milestone for Redmi K70 (SM8550):
a source-built ARM64 XNU Mach-O with symbols, using the pinned UniXNU build
driver. [Run 39630167656](https://github.com/mansar1337/UniXNU-vermeer/actions/runs/39630167656)
on commit `58e31c79db44e0f0e4e3917d7823ee69d4501150` passed compilation,
final linking and collection. The downloaded artifact was independently
checked for format, source-provider symbols, SHA-256 and POST HMAC.

The result is a build baseline, not a phone boot image. It selects UniXNU's
generic BCM2837/4 KiB machine configuration. The name is the upstream page
layout configuration, not a claim that the phone has Broadcom hardware.
SM8550 CPU/platform archives, Apple-format device tree and the loader
handoff remain future work. UFS, GPU and touch drivers are disabled.
The architectural timer entry is also disabled until ArmCpu is linked;
enabling it without the interrupt provider is rejected by the local check.

## Pinned basis

- [UniXNU](https://github.com/UniXNU/UniXNU) at
  `b6ae99c17194e6a18fd819d3148e69fe405e91fc`.
- Apple XNU `10063.141.1` at
  `d8b80295118ef25ac3a784134bcf95cd8e88109f` (Darwin 23.6 / iOS 17).
- The remaining Apple reference versions and submodule commits are those
  pinned by that UniXNU revision; the build report records module origins
  and submodule revisions.

The build uses the upstream source crypto and pthread providers, applies
its kernel patches and fills the source provider's POST HMAC field. It
does not prelink a proprietary kernelcache and does not need an IPSW at
this stage. Runtime crypto selftests remain untested.

`tools/build_source_kernel.py` uses the upstream build driver through the
same parser, context, module resolution and kernel builder. It stops
before `kernel.prelink`, which the normal `unixnu build kernel` command
would run next. The source reference checkout is left unchanged.

## Run

Publish this directory as your own GitHub repository, enable Actions, then
run **XNU source kernel (vermeer build baseline)** in the Actions tab.
The workflow runs only when manually requested; pushes do not start it.
It uses `macos-15` with Xcode and installs the same basic tools required by
UniXNU's workflow.

After publishing to `OWNER/REPOSITORY`, the equivalent command is:

```bash
gh workflow run xnu-source.yml -R OWNER/REPOSITORY
gh run list -R OWNER/REPOSITORY -w xnu-source.yml
gh run download RUN_ID -R OWNER/REPOSITORY -D out/download
```

An artifact is uploaded even if the build fails. A downloaded artifact or
successful upload does not establish build success: check the job result
and `kernel/build-report.json`.

On a Mac with the dependencies and the pinned upstream checkout:

```bash
python3 tools/build_source_kernel.py --unixnu /path/to/UniXNU --out out --jobs 4
```

The source/configuration check also works on Linux:

```bash
python3 tools/build_source_kernel.py --unixnu ../sources/UniXNU --check
```

## Expected result

- `kernel.development.vermeer-build.macho`: ordinary ARM64 MH_EXECUTE.
- `symbols.txt`, upstream symbol products, build logs and `SHA256SUMS`.
- `build-report.json`: format, source/module revisions, configuration and
  explicit untested boot/platform status.
- `crypto-hmac.json`: source provider build-time HMAC record.

The collector requires an iOS 17 ARM64 Mach-O with an entry command,
source crypto and pthread symbols, and a matching HMAC report. Compile,
link or collection failure fails the job; it is not reported as success.

## Build results

[Run 39614669422](https://github.com/mansar1337/UniXNU-vermeer/actions/runs/39614669422)
on commit `4d8bb69` failed with:

```text
Architectural timer entry requires the actual ArmCpu interrupt provider
```

The initial configuration enabled `XNU_NATIVE_ARCH_TIMER` while disabling
`XNU_ARMCPU`. The source-build baseline now disables both and checks this
dependency before fetching/building. No upstream dependency check was
removed. The configuration regression checks and subsequent macOS
compile/link passed.

[Run 39616227056](https://github.com/mansar1337/UniXNU-vermeer/actions/runs/39616227056)
on commit `28efe79` compiled XNU and the source pthread/crypto archives.
Both 529-source crypto passes had zero compile failures. Final linking
stopped at `_native_legacy_display_probe`: an upstream optional display
probe was referenced even though its driver was disabled.

The build now copies the pinned kernel patches into its local build tree
and guards that registration block with `XNU_NATIVE_LEGACY_DISPLAY`, just
like the other legacy display call. The upstream checkout stays unchanged;
the input patch hash is checked and the effective patch hash is recorded.
A compile/symbol regression check proves the reference is absent when
the feature is disabled and present when enabled. The third macOS run
passed the final link and collector; its source kernel has no reference
to the disabled display probe.

Successful result:

- XNU 10063.141.1 / Darwin 23.6.0, DEVELOPMENT, ARM64, 4 KiB pages.
- `kernel.development.vermeer-build.macho`: 21,376,600 bytes.
- Kernel SHA-256:
  `a06ef5334d95c00b677ffaa2320868a684abbc4fe6f2e4c4c2a040b8c57edf04`.
- Artifact ZIP SHA-256:
  `80deac3818820448dbefb0008b5077ff5c5342e47a5f5b50cb311b5283887e36`.
- Crypto plain/namespaced builds: 529 C sources each, zero failures.

The final build succeeded with compiler/linker warnings. The earlier
bootstrap pass intentionally stops at linking before source archives are
built; errors in that bootstrap log are not the final build result.
Source-provider HMAC bytes were recomputed locally and match the report.
Runtime crypto selftests and phone boot remain untested.

## Next port milestone

Inspect `UniXNU-sheng` (same SM8550 SoC), `ArmCpu`, `ArmDTPlatform` and
`DarwinBoot`; add the minimal CPU/platform archives and a vermeer ADT.
The existing Silicium port supplies stock-derived memory/DT information
and working UEFI display/storage. Active framebuffer address, stride,
runtime RAM and CPU entry state need measurement before phone boot.

No workflow here runs fastboot, builds userdata or installs iOS. There is
no phone flash command. The current Silicium images remain separate.

Upstream code and patches come from their own repositories and remain
under their respective licenses; this repository contains only the build
configuration, workflow and collector written for this experiment.
