---
name: deploy-goldhen-plugin
description: Install a plugin or mod files on a real PS4 running GoldHEN over FTP, enable it in plugins.ini, record the kernel log and summarise the last boot or crash, with the ARES GoldHEN adapter. Use to test a PS4 homebrew plugin or port (e.g. PS4 Northstar) on hardware, or to diagnose a console crash from the kernel log.
---

# Deploy and observe on a GoldHEN PS4

Adapter: `harnesses/adapters/goldhen.py`. Guide: `harnesses/docs/goldhen.md`.

## Rules

- **Ask the console's owner before `upload` or `enable-plugin`.** Say which
  files go where. Reading (`ls`, `klog`) is fine once they gave the address.
- Never paste the raw kernel log into chats, issues or knowledge bases: it can
  hold sign-in tokens. Use `lastboot` output and read it first.
- Keep logs and backups under `reports/` (git-ignored).

## Procedure

1. **Reach the console.** `python harnesses/adapters/goldhen.py ls /data/GoldHEN --host ADDRESS`
   (or set `ARES_PS4_HOST`). No answer: GoldHEN's FTP server is off, or the
   address is wrong.
2. **Start recording** in the background before launching the game:
   `goldhen.py klog --out reports/ps4/klog.txt --duration 600`.
3. **Upload** (after asking):
   - Plugin: `goldhen.py upload --file build/x.prx /data/GoldHEN/plugins/x.prx --always`
   - Mod tree: `goldhen.py upload --tree dist/mods /data/<project>/mods`
   Sizes are checked through `LIST`; rerun after an interruption.
4. **Enable** once: `goldhen.py enable-plugin --title CUSAxxxxx --plugin /data/GoldHEN/plugins/x.prx --backup reports/ps4/plugins.ini.bak`.
5. **Ask the owner to start the title** (plugins load at title start), then
   wait for the plugin's log lines.
6. **Summarise:** `goldhen.py lastboot --log reports/ps4/klog.txt --boot-marker 'FIRST LINE REGEX' --tag '[Tag]'`.
   Add `--elf build/x.elf --elf-module x` for crash symbols (needs `llvm-nm`).

## Reading a crash

`rip` is where it faulted; `BrF`→`BrT` is the last branch taken. A module
offset in your plugin plus the ELF gives the function. An offset in a game
module is a game address: look it up with `python tools/prx_inspect.py disasm
MODULE 0xOFFSET` (decrypted module, same title version).

## Differences from shadPS4

Real hardware is stricter: misaligned or unmapped accesses, timing, and
networking differ. A plugin that works in shadPS4 still needs a hardware run.
Record each difference you confirm.
