# Windows Invocation

Use PowerShell or the Codex/Claude Code process runner. Resolve
`<SSH_SKILL_ROOT>` from the loaded skill before invoking Python.

```powershell
python "<SSH_SKILL_ROOT>\scripts\ssh_skill.py" doctor --json
python "<SSH_SKILL_ROOT>\scripts\ssh_skill.py" exec example-host "hostname"
python "<SSH_SKILL_ROOT>\scripts\ssh_skill.py" upload example-host "C:\Temp\app.zip" "/tmp/app.zip"
```

- Use Windows path syntax only for local paths and the script path.
- Keep remote paths in POSIX form.
- Do not prepend environment assignments intended for MSYS or Bash.
- Do not wrap the call in a second PowerShell command string.
- The runtime prefers `%SystemRoot%\System32\OpenSSH\ssh.exe`, then PATH.
- The local agent check uses the Windows `ssh-agent` service and `ssh-add.exe`.
- Parse stdout as the single result and stderr as optional progress. Both use
  ASCII-safe JSON, including when local or remote paths contain non-ASCII text.

If `python` is unavailable, select an installed Python 3.10-3.13 executable
without changing the SSH operation or adding a shell wrapper.

## When The Remote Target Is Windows

The remote login shell is often Git Bash (POSIX), so inline `exec` text
crosses three interpreters: the local shell, the CLI argv, then the remote
shell. Follow Inline Command Text Rules in SKILL.md; the confirmed traps:

- Wrap Windows file arguments in double quotes and use backslash form.
  `sqlcmd -i` rejects a forward-slash path with the false error
  `-E and -U/-P are mutually exclusive`; only the path form is wrong.
- Backslash escapes outside double quotes are eaten by a POSIX layer
  (`\a` becomes BEL), so an unquoted backslash path arrives mangled.
- A single quote in the command text closes local quoting early; SQL and
  other quoted content must go into an uploaded file, never inline.
- Prefix the local call with `MSYS_NO_PATHCONV=1` when an argument such as
  `cmd /c ...` would be rewritten as a POSIX path.
- Remote console output is commonly GBK; convert on the local side
  (`| iconv -f GBK -t UTF-8`) or keep output ASCII and filter locally.
