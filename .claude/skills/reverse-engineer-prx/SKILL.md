---
name: reverse-engineer-prx
description: Find and verify functions, globals, vtables and ConCommands in decrypted PS4 modules (.prx, eboot.bin) or x86-64 ELFs with the ARES prx_inspect tool - strings to code xrefs, relocated pointer tables, byte patterns, disassembly - and check RPak texture platforms and pdef layouts for ports. Use when porting a Respawn game or mod to PS4, matching a PC function to its PS4 counterpart, or explaining a crash address.
---

# Reverse-engineer a PS4 module

Tool: `tools/prx_inspect.py` (standard library; `disasm` needs `pip install
capstone`). Every command prints JSON and never modifies the module.

## Ground rules

- Work on **decrypted** modules from the user's own console dump. Never commit
  or redistribute them.
- Addresses are **module-relative VAs**, written `engine+0x1234`. Load
  addresses change every run. Record the module's SHA-256 (`info`) with every
  address: offsets are only valid for that build.
- Pointer tables are zero in the file and filled by RELATIVE relocations.
  `ptr` and `xrefs` apply them. Raw `dump` bytes do not.

## Procedure

1. **Identify:** `python tools/prx_inspect.py info engine.prx` gives hash,
   segments (`va_to_file` is the VA-to-offset delta), relocation counts.
2. **Strings first:** `strings engine.prx "map_name"`, then
   `xrefs engine.prx --string map_name --exact` lists the code that loads it
   (`lea`, `mov`, ...). Hits are candidates.
3. **Confirm:** `disasm engine.prx 0xHIT --length 64` and read the
   surrounding calls and arguments. For a ConCommand registration, the
   pattern is `lea rdi, object; lea rsi, name; lea rdx, callback; lea rcx,
   help; call ConCommand::ConCommand`.
4. **Callers and tables:** `xrefs engine.prx 0xFUNC` finds calls, jumps and
   relocated pointers (vtables). `ptr engine.prx 0xVTABLE --count 24` reads a
   vtable as the game sees it.
5. **Shared code across modules:** match distinctive instruction bytes with
   `find MODULE "48 8b 05 ?? ?? ?? ?? 48 85 c0"`; rip-relative operands differ
   per module, so wildcard them.
6. **PC counterparts:** the same game on PC is the same source with another
   compiler. Match by strings, constants and call structure, never by offset.
   PS4 builds often inline what PC calls.
7. **Verify live** when it matters: `test-shadps4` skill, `peek --module
   engine --offset 0x…`.

## Port checks

- RPaks for PS4 must carry PS4-layout textures:
  `python tools/rpak_platform.py --scan MODS --require ps4`. PC textures render
  black. Compressed paks must be decompressed first.
- Save layout: `python tools/pdef.py size|layout|diff`. The engine's
  persistence buffer has a fixed size; diff a modded pdef against the base.

## Record what you find

Write each verified address with module, build hash, how it was verified
(static, or live in shadPS4/hardware) and the evidence. Mark guesses as guesses.
