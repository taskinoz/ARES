# GoldHEN (real PS4) tools

`harnesses/adapters/goldhen.py` deploys and observes homebrew on a real PS4
running [GoldHEN](https://github.com/GoldHEN/GoldHEN). It uses three services
GoldHEN provides: FTP on port 2121, the kernel log on TCP 3232, and plugin
loading from `/data/GoldHEN/plugins.ini` when a title starts.

```powershell
$env:ARES_PS4_HOST = '192.168.1.50'
python harnesses/adapters/goldhen.py upload --file build/my_plugin.prx /data/GoldHEN/plugins/my_plugin.prx
python harnesses/adapters/goldhen.py enable-plugin --title CUSA04013 `
    --plugin /data/GoldHEN/plugins/my_plugin.prx --backup reports/plugins.ini.bak
python harnesses/adapters/goldhen.py klog --out reports/klog.txt --duration 300 --until 'ready'
python harnesses/adapters/goldhen.py lastboot --log reports/klog.txt --tag '[MyPlugin]'
```

## Commands

| Command | Does |
| --- | --- |
| `ls PATH` | Lists a remote folder (read-only) |
| `upload --file LOCAL REMOTE`, `--tree DIR REMOTE_DIR` | Uploads files or trees. Skips files whose size already matches, so an interrupted upload can run again. Every sent file is verified by size. `--always` sends regardless |
| `enable-plugin --title ID --plugin PATH --backup FILE` | Adds the plugin under `[ID]` in `plugins.ini`, keeping other sections and lines. Saves the old file locally first; does nothing if it is already listed |
| `klog --out FILE` | Appends the kernel log to a file, reconnecting when it drops. `--duration` and `--until REGEX` end it |
| `lastboot --log FILE` | Summarises the last boot: lines with `--tag`, then any crash (signal, thread, and `rip`/`BrF`/`BrT` mapped to module and offset) |

`lastboot` finds a boot by `--boot-marker REGEX` (your plugin's first log line)
or, by default, the last `--- connected` line `klog` writes. With
`--elf my_plugin.elf --elf-module my_plugin` it names the function for crash
addresses in your plugin's text segment (needs `llvm-nm` on `PATH` and the ELF
from the same build).

## GoldHEN quirks

- GoldHEN's FTP `SIZE` reports a `.prx`'s *decrypted* size and `RETR` sends it
  decrypted, so size checks use `LIST`.
- GoldHEN serves one kernel-log reader at a time. A second reader gets
  `failed to open klog`; the recorder waits 30 s and retries.
- A quiet kernel log is normal, so the recorder never drops a connection for
  silence. TCP keepalive notices a console that restarted.
- Kernel crash reports list each module's `text` and `data` ranges; the
  summary uses them to turn addresses into module offsets.
- Plugins are loaded when the title starts; restart the game after enabling
  one.

## Safety

- `upload` and `enable-plugin` change the console. Ask its owner before
  running them, and say what goes where.
- The raw kernel log contains whatever the game prints, possibly sign-in
  tokens. Keep it in `reports/` (git-ignored) and share `lastboot` output,
  which replaces lines that look like they carry a secret. The filter is a
  pattern match, so still read before you share.
- Remote paths must be absolute; `..` is rejected.

## Tests

```powershell
python -m unittest harnesses/adapters/test_ps4_harnesses.py
```

The tests use a fake FTP object and a local socket; no console is needed.
