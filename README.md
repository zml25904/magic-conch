# 神奇海螺 🐚 magic-conch

**Agent，你為什麼不問問神奇海螺呢？**

![海綿寶寶拿著紫色海螺：你為什麼不問問神奇海螺](assets/magic-conch.jpg)

Agent 卡住想問人？神奇海螺隨機給一句，精神自行領會，活接著幹。

Claude Code 可手動使用 `/give-conch [任務]`（給你海螺），完成後回到正常聊天；Codex 保留原本的 Stop hook 用法。兩者共用一支腳本，向[解答之書 API](https://answerbook.david888.com/answersOriginal?lang=zh-TW)取一句隨機答案，讓 agent 繼續原本的小任務。

```text
任何非 DONE 回覆 → Stop hook → 海螺隨機回答 → agent 續跑 → … → DONE
```

啟用海螺的任務只有 `DONE` 才放行正常 Stop。普通提問、進度與空回覆都會要求續跑，沒有次數上限；第三方答案只是提示，不能代替人類許可，也不擴大 agent 的權限。這仍是玩具協定，不保證任務真的完成。

## 先準備

需要 Python 3.9+（若設定續跑上限，標準庫需含 SQLite）、系統 `curl`，以及已可登入的 Codex 或 Claude Code。無須套件管理器、MCP 或 API key。

下載本專案到固定位置。Codex 或常駐 hook 用法需要把下列設定範例中的 `/absolute/path/to/magic-conch/magic_conch.py` 改成腳本的實際絕對路徑。路徑有空白時保留範例的雙引號。

可先做一次手動試問；它會向第三方 API 發送固定 GET，**不會傳送問題內容**：

```sh
printf '%s\n' '{"hook_event_name":"Stop","session_id":"manual-demo","last_assistant_message":"用什麼主題寫筆記？"}' | python3 magic_conch.py
```

非完成回覆會輸出 `{"decision":"block","reason":"…"}`；即使 API 失敗，也以固定提示要求續跑。只有明確的完成標記或非 Stop 事件輸出 `{}`。若設定了上限，達上限或設定有誤則另以診斷訊息停止。

## 接到 Codex

把 [codex-hooks.json](examples/codex-hooks.json) 的 `Stop` 區塊合併到使用中的 `hooks.json`。使用者設定預設位於 `$CODEX_HOME/hooks.json`；未設定 `CODEX_HOME` 時是 `~/.codex/hooks.json`。已有 hook 時請合併，勿覆蓋；若原本使用 `config.toml` 的 inline `[hooks]`，沿用該表示法，避免重複接線。

開啟 Codex，透過 `/hooks` 檢視並信任這個 hook。Hooks 需保持啟用；不要為此關掉 sandbox 或其他權限檢查。設定位置與信任流程見 [Codex 官方 hooks 文件](https://learn.chatgpt.com/docs/hooks)。

在測試工作區，把 [protocol.md](examples/protocol.md) 貼給 agent，再交付小任務，例如：「先問海螺筆記主題，收到答案後在目前目錄寫 `note.txt`，讀回確認後 DONE。」依原有 sandbox 與核准方式提供該檔案所需的寫入權限。

## Claude Code：手動指令「給你海螺」

Claude 的 custom command 已併入 skill；`/give-conch` 就是指令入口。使用 `disable-model-invocation: true`，Claude 不能自行決定啟用；一般對話不會掛上這個 Stop hook。底層是原生 `once: true`：非 DONE 用 stderr＋exit 2 要求續跑，DONE 用 exit 0 讓框架移除 hook，不需要自製 session 開關。

在 macOS、Linux 或 WSL，把本專案的完整 skill 目錄連到 Claude 的個人 skills 位置（請改成實際絕對路徑）：

```sh
mkdir -p "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills"
ln -s /absolute/path/to/magic-conch/skills/give-conch "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/give-conch"
```

若同名項目已存在，先確認內容，不要覆蓋。這是安裝手動 skill，**不必合併 `claude-settings.json` 或新增全域 Stop hook**。skill 目錄中的腳本連結指回本專案，請保留整個 checkout 與 symlink；不要只複製 SKILL.md。使用自訂 `CLAUDE_CONFIG_DIR` 時，安裝與啟動須使用同一目錄。安裝後重新開啟 Claude；可以從任何工作目錄啟動。

```text
/give-conch 在目前目錄寫一份三行的 note.txt，讀回確認後完成。
```

本次任務遇到正常 Stop 時會向海螺取提示、接著做；完成後以 `DONE: …` 回報並自動移除 hook。同一對話隨後可正常聊天，也能再輸入 `/give-conch 另一項任務`。不會另開 agent。只想討論用法時寫 `give-conch`（不帶斜線）；官方允許訊息中明確提及 `/give-conch` 成為當輪使用授權，這不算自動誤觸。未附任務時只提示用法並 DONE。

一般工具與人工核准機制照常。要中途取消，可使用 Claude 原生中斷；中斷不代表 once hook 已移除，需要在同一對話取消並恢復普通聊天時，接著要求「取消本次任務，以 DONE: 已取消 結束」。這仍需要模型回覆，不能取代 host 的即時停止控制。停用後續使用，移除剛建立的 `give-conch` 連結並重新開啟 Claude；已載入的 skill／hook 不會因移除磁碟檔案而自動卸載。

如果先前已依舊版範例安裝常駐 Stop hook，請自行移除**本工具那筆 handler**，或啟動時不帶舊版 `--settings`，避免完成後仍被舊 hook 攔住；不要刪除其他 hook。舊版 [claude-settings.json](examples/claude-settings.json) 留作明確需要常駐 hook 的進階用法，勿與新指令重複接線。

依據：[Claude skills 與手動限定](https://code.claude.com/docs/en/skills#control-who-invokes-a-skill)、[skill hooks 與 once](https://code.claude.com/docs/en/hooks#hooks-in-skills-and-agents)。不要用 `--disable-slash-commands`、`--restricted`、`--bare` 或 `--safe-mode` 啟動這個指令；這些模式可能限制本 skill 的發現或 hook。

## 完成標記與可選上限

忽略開頭空白後，只認大小寫敏感的 **`DONE`** 起首標記；後面必須接結尾、空白、標點或符號。`DONE`、`DONE: 完成`、`DONE：完成` 都有效；`done`、`Done`、`UNDONE`、`說到DONE`、`DONEish`、`DONE_soon`、`DONE完成` 都會繼續。請只在任務確實完成時使用標記。

預設所有其他正常 Stop 都續跑，不需要 `ASK:`。API 失敗、空答案、壞回應，以及無法確認完成的壞輸入，均回固定提示「繼續原任務，完成才回 DONE」。`curl` 最多 5 秒，Python 等待最多 6 秒，範例 hook timeout 為 8 秒。本版仍使用 API。

可用一個環境變數設定每個 session 的續跑上限；**未設定或留空就是無上限**，也不讀寫任何計數狀態：

```sh
MAGIC_CONCH_MAX_CONTINUATIONS=5 claude --model sonnet
# Codex 同樣可在啟動命令前加 MAGIC_CONCH_MAX_CONTINUATIONS=5
```

設定值必須是正整數。一次要求續跑就算一次，API 故障後的固定提示也計次；達上限是使用者配置的例外停止，不代表 DONE。非法值會附帶診斷停止（JSON hook 使用 `stopReason`，skill 使用可見的 `systemMessage` 並卸載），不會默默變成無上限；有限額時若缺 session ID 或計數無法讀寫，也會以診斷訊息停止。

只在有限額模式下，本機 cache 儲存 session ID 的 SHA-256 與次數，不儲存問題、答案或認證。預設 `${XDG_CACHE_HOME:-~/.cache}/magic-conch/attempts.sqlite3`，可用 `MAGIC_CONCH_CACHE_DIR` 指定目錄。相同 session 續用計數（包括再次手動 `/give-conch`），DONE 不重置；切回無上限會忽略舊計數，再設上限則繼續使用。沒有 hook 執行時刪除該 DB 可重置所有額度，新 session 則獨立計數。

Hook 只處理正常 Stop；使用者中斷、CLI 權限機制、外部 timeout 與 CLI 原生迴圈限制仍有效，不會自動核准操作或繞過它們。無上限可能持續產生模型與 API 請求，請保留中斷或外部 timeout 的控制方式。

停用 Codex：移除本工具的那筆 Stop handler，或透過 `/hooks` 停用。Claude 指令停用方式見上節；不要刪除其他 hook。

## 測試與授權

```sh
python3 -m unittest discover -s tests -v
```

單元測試用假的 `curl`，不連網；另以隔離 Claude 接真 API 驗證正式 skill：同一 session 兩次啟用，非 DONE 自動續跑，DONE 後普通聊天不再觸發 hook。已於 Codex 0.162.0 與 Claude Code 2.1.304 驗證 Stop 自動續跑；測試涵蓋連續兩次非 DONE 回覆後，寫入並讀回產物，最後 DONE。

程式碼依 [MIT License](LICENSE) 提供。梗圖來自 [memes.tw 搜尋結果](https://memes.tw/wtf?q=%E4%BD%A0%E7%82%BA%E4%BB%80%E9%BA%BC%E4%B8%8D%E5%95%8F%E5%95%8F)（[圖片原址](https://memeprod.sgp1.digitaloceanspaces.com/user-wtf/1650873918786.jpg)），**圖片不在 MIT 授權範圍內**。原梗可看 [SpongeBob 官方片段](https://www.youtube.com/watch?v=ZHmtvR-1ivw)。
