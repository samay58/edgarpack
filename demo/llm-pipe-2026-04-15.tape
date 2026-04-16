# EdgarPack Demo 3: LLM Pipe with Citations
# Render: vhs demo/llm-pipe-2026-04-15.tape
# Output: demo/llm-pipe-2026-04-15.gif

Output demo/llm-pipe-2026-04-15.gif

Set Theme "Catppuccin Mocha"
Set FontSize 16
Set FontFamily "Berkeley Mono"
Set Width 1400
Set Height 820
Set Padding 24
Set TypingSpeed 35ms

Hide
Type "export PATH='/Users/samaydhawan/Projects/active/edgarpack/.venv/bin:$PATH' && clear"
Enter
Sleep 400ms
Show

Type "# pipe meta's 10-K into claude, ask one question"
Enter
Sleep 1200ms

Type "cat packs/0001326801/0001628280-26-003942/filing.full.md | claude -p 'One sentence: what did Meta add to Business Overview this year about their vision? Cite the section.'"
Enter
Sleep 11s

Sleep 2s
