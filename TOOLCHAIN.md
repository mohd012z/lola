# Lola Managed Toolchain

Lola keeps **tool definitions and managers in Git**, while third-party binaries stay outside Git under:

```text
.lola-tools/
```

This avoids committing large external packages or redistributing them unintentionally.

## Managed tools

| Tool | Lola mode | Pinned/detected | Notes |
|---|---|---:|---|
| Apktool | managed download | 3.0.3 | SHA-256 pinned; Java required |
| Gradle | managed download | 9.7.1 | official binary ZIP + official SHA-256 |
| Ghidra | managed download | 12.1.3 | desktop managed mode; JDK 25 required |
| Hermes / hermesc | project/system detect | project-matched | prefer target React Native toolchain |
| JADX | system detect | system | used for decompiled source |
| AAPT/AAPT2 | system detect | Android SDK | manifest/resource support |
| apksigner/keytool | system detect | Android SDK/JDK | signature/certificate support |
| bundletool | system detect | system | AAB/APKS support |
| ADB | system detect | Android SDK/Termux | authorized runtime observation |
| Frida | system detect | system | optional authorized runtime observation |

## Why Hermes is project-matched

Modern React Native ships Hermes with the React Native toolchain. Using a mismatched compiler can create incompatible Hermes bytecode. Lola therefore prefers a matching `hermesc` from the target project or system toolchain rather than blindly installing an unrelated release.

## CLI

Show status:

```bash
python lola_toolchain.py status
```

For a React Native project:

```bash
python lola_toolchain.py status --project /path/to/project
```

Install a managed tool:

```bash
python lola_toolchain.py install apktool
python lola_toolchain.py install gradle
python lola_toolchain.py install ghidra
```

Remove only Lola's managed copy:

```bash
python lola_toolchain.py remove apktool
```

Show the executable/launch command:

```bash
python lola_toolchain.py path apktool
python lola_toolchain.py path gradle
python lola_toolchain.py path ghidra
```

## Android / Termux

Recommended managed/detected layout:

```text
Termux
├── Python
├── Java
├── Lola
│   ├── toolchain.json
│   ├── lola_toolchain.py
│   └── .lola-tools/
│       ├── apktool/
│       └── gradle/
├── ADB              optional
├── JADX             optional
└── Hermes           project/system detection
```

Ghidra is not auto-installed on Termux. Its current desktop release requires JDK 25 and is large; Lola marks it detect-only/unsupported for managed Termux installation rather than forcing it onto the phone.

## Integrity

Managed downloads use one of:

- pinned SHA-256 stored in `toolchain.json`
- official checksum URL

Archives are checked before activation. ZIP extraction rejects paths escaping the target directory.

## GitHub repository policy

Third-party binaries are **not committed**.

Git stores:

```text
toolchain.json
lola_toolchain.py
TOOLCHAIN.md
.github/workflows/toolchain-check.yml
```

Runtime/downloaded content stays in:

```text
.lola-tools/
```

and is ignored by Git.
