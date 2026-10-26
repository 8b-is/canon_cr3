# Python API recovery

The `canon_cr3.Image` and `CmtdData` API is restored from commit
`9f687336db77fee34e81c85e3e0121b01977b40c`, retaining the original GPLv3
headers and attribution. Those files were removed in
`dc85a1ff493bf2523314936fd13f11ff03ad4102` while their API tests remained.

This recovery corrects the historical `stsz` helper calls and validates box
and CTMD lengths before advancing. Top-level boxes of size zero consume the
rest of the input; nested zero-sized boxes are rejected. Extended headers,
container prefixes and parent bounds are checked. A nesting limit of 128 is
a parser resource policy. Atom layout reference:
https://developer.apple.com/documentation/quicktime-file-format/atoms

The package uses CalVer 2026.10.26, requires Python 3.10 or later, and ships
both `canon_cr3` and the existing `CRaw3` modules. Its runtime uses the
Python standard library. The original CLI remains a separate implementation.

Run `python -m unittest discover -s tests` from the repository root. The API
fixture resolves relative to its test file and requires the tracked
`samples/IMG_0482_raw.CR3` file, including in sparse checkouts.

The sample tests cover one Canon EOS M50 image and malformed synthetic
inputs. They do not establish support for every camera, complete format
conformance, or a comprehensive security audit. The separate CLI now checks
the same box-boundary and progress conditions before dispatching payloads.
Its regression tests invoke the actual command with bounded subprocesses.
`CRaw3.Ctmd` also checks index, picture, record and payload boundaries, rejects
non-progressing payload sizes and bounds each TIFF parser to its own payload.
Known scalar records require their complete fixed headers. The TIFF parser's
internal offsets and other payload parsers still require separate review.
