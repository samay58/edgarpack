# EdgarPack Demo 1: Filing Diff — META superintelligence finding
# Render: vhs demo/diff-hero-2026-04-15.tape
# Output: demo/diff-hero-2026-04-15.gif

Output demo/diff-hero-2026-04-15.gif

Set Theme "Catppuccin Mocha"
Set FontSize 16
Set FontFamily "Berkeley Mono"
Set Width 1400
Set Height 820
Set Padding 24
Set TypingSpeed 35ms

Hide
Type "export PATH='/Users/samaydhawan/Projects/active/edgarpack/.venv/bin:$PATH' && export EDGARPACK_USER_AGENT='Samay Dhawan samay58@gmail.com' && clear"
Enter
Sleep 400ms
Show

Type "# what changed in meta's 10-K this year"
Enter
Sleep 1200ms

Type "edgarpack diff --ticker META --form 10-K | grep -B1 -A2 'superintelligence'"
Enter
Sleep 9s

Sleep 2s
