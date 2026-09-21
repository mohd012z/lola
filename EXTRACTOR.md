# Lola universal extraction

Lola now includes a dependency-light Python static extractor:

```bash
python lola_extract.py /path/to/file
python lola_extract.py /path/to/file -o .lola-extract --stdout
```

Outputs include `evidence360.json` and an evidence-backed text scaffold. EX4 produces
`reconstructed.mq4.txt`; EX5 produces `reconstructed.mq5.txt`.

## Built-in pipeline

`/deep-dive /allcode /codestring /extractormodule /extractorrefactoring
/refactoringcode /codeencode /codeencoder /library /sources /ghidra /frida
/js /vbscript /scripts /toolsextractor`

The core scanner fingerprints any readable file, maps entropy at 64/256/1024/4096/16384
byte scales, extracts ASCII and conservative UTF-16 evidence with offsets, scans bounded
numeric candidates, inventories embedded file signatures and URLs, and classifies MQL
and script-language markers.

Ghidra is an optional static-analysis source for genuine native PE/ELF content. EX4/EX5
is not assumed to be native x86/x64. Frida remains optional, authorized, attach-only
runtime evidence and is not part of default extraction.

Imported targets are read-only and are never executed by the universal extractor.
Protected code is not decrypted or bypassed. Generated MQ4/MQ5 text is an evidence-backed
scaffold and is not represented as unavailable original source.
