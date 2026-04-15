# edgarpack: Chinese AI labs + US giants comparison demo
#
# Render with:
#   vhs demo/china-ai-labs.tape
# Produces: demo/china-ai-labs.gif

Output demo/china-ai-labs.gif

Set Theme "Catppuccin Mocha"
Set FontSize 16
Set FontFamily "Berkeley Mono"
Set Width 1400
Set Height 820
Set Padding 24
Set TypingSpeed 35ms

# Fresh clean prompt
Hide
Type "clear"
Enter
Sleep 400ms
Show

# --- Beat 1: single-company query with cites ---
Type "# Pull one 20-F filer. All cited, deep-linked to iXBRL anchors."
Enter
Sleep 1200ms

Type "edgarpack query BIDU revenue,net_income,rd_expense,operating_cash_flow"
Enter
Sleep 5s

# --- Beat 2: US search + AI giants comp ---
Type "# Side-by-side with Alphabet and Nvidia. R&D spend + cash flow tells the story."
Enter
Sleep 1200ms

Type "edgarpack compare BIDU GOOGL NVDA --metrics revenue,rd_expense,operating_cash_flow,free_cash_flow --format table"
Enter
Sleep 6s

# --- Beat 3: the headline comp ---
Type "# Now the part nobody has done: Chinese AI tiger labs next to their public peers."
Enter
Sleep 1200ms

Type "edgarpack compare minimax zhipu BIDU GOOGL --metrics revenue,net_income --format table"
Enter
Sleep 7s

# --- Beat 4: lab-to-lab with more signal ---
Type "# Pure-play AI lab comp with margin + cash burn signal."
Enter
Sleep 1200ms

Type "edgarpack compare minimax zhipu --metrics revenue,gross_profit,net_income,cash_and_equivalents,operating_cash_flow"
Enter
Sleep 7s

# Let the final frame sit
Sleep 2s
