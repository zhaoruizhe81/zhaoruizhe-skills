# Renderer Selection

## Goal

Choose the renderer by the meaning of the content, not by habit or file suffix.

The skill currently exposes three rendering paths through `scripts/render_snippet.py`:

- `--lexer`: syntax-highlighted code renderer
- `--plain-text`: plain text renderer
- `--ansi`: ANSI terminal renderer

## Fast Decision Table

| Content type | Recommended renderer | Typical theme | Notes |
| --- | --- | --- | --- |
| Python, JavaScript, Java, YAML, JSON, XML, shell script source | `--lexer` | `light` | Use filename inference or explicit `--lexer` |
| Plain Chinese/English paragraph | `--plain-text` | `light` | Best for notes and report正文 |
| Plain terminal log without ANSI escapes | `--plain-text` | `dark` | Best for screenshot-like shell output |
| Terminal log with ANSI escape sequences | `--ansi` | `dark` | Preserves colored terminal output |
| Windows command prompt text without colors | `--plain-text` | `light` | White background often matches cmd screenshots |
| Config or code pasted inside a `.txt` file | `--lexer` if syntax matters, else `--plain-text` | usually `light` | Decide by content, not extension |

## Common Mistakes

### Mistake 1: Using `--lexer` for terminal logs

Do not do this just because the file is text and contains commands.

Bad fit:

```text
[root@node ~]# ip addr show ens33
inet 192.168.100.141/24 ...
```

Use `--plain-text --theme dark` unless ANSI color escapes are present.

### Mistake 2: Using `--plain-text` for ANSI output

If the content contains `\x1b[`, `\u001b[`, `\033[`, or came from `--color=always`, use `--ansi`. Otherwise the image will lose the intended colors.

### Mistake 3: Choosing theme by habit

- Code snippets in reports: usually `light`
- Terminal screenshots: usually `dark`
- Windows cmd-style content: often `light`

## Examples

### Code snippet

```bash
python3 scripts/render_snippet.py \
  --input /path/example.py \
  --output /tmp/example.png
```

### Plain terminal log

```bash
python3 scripts/render_snippet.py \
  --input /path/ip_addr.txt \
  --plain-text \
  --theme dark \
  --output /tmp/ip_addr.png
```

### ANSI terminal output

```bash
python3 scripts/render_snippet.py \
  --text '\033[32mSUCCESS\033[0m done' \
  --ansi \
  --decode-escapes \
  --theme dark \
  --output /tmp/success.png
```
