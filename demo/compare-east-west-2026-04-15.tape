# EdgarPack Demo 2: East-West Compare
# Render: vhs demo/compare-east-west-2026-04-15.tape
# Output: demo/compare-east-west-2026-04-15.gif

Output demo/compare-east-west-2026-04-15.gif

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

Type "# chinese AI labs and US hyperscalers, one table"
Enter
Sleep 1200ms

Type "edgarpack compare minimax zhipu BIDU GOOGL META --metrics revenue,rd_expense,operating_cash_flow --format table"
Enter
Sleep 7s

Sleep 2s
