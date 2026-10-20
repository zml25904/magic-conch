# 神奇海螺 🐚 magic-conch

**Agent，你為什麼不問問神奇海螺呢？**

![海綿寶寶拿著紫色海螺：你為什麼不問問神奇海螺](assets/magic-conch.jpg)

Agent 卡住想問人？神奇海螺隨機給一句，精神自行領會，活接著幹。

一支供 Codex 與 Claude Code 使用的 Stop hook，向[解答之書 API](https://answerbook.david888.com/answersOriginal?lang=zh-TW)取一句隨機答案，讓 agent 繼續原本的小任務。

```text
ASK: 筆記該用什麼主題？ → 停下 → 海螺隨機回答 → agent 自行領會、續跑 → DONE
```

這是明確標記的 ASK／DONE 玩具協定，不保證完成任務。第三方答案只是提示，不能代替人類許可，也不擴大 agent 的權限。

## 先準備

需要 Python 3.9+（標準庫含 SQLite）、系統 `curl`，以及已可登入的 Codex 或 Claude Code。無須套件管理器、MCP 或 API key。

下載本專案到固定位置，把下列設定範例中的 `/absolute/path/to/magic-conch/magic_conch.py` 改成腳本的實際絕對路徑。路徑有空白時保留範例的雙引號。

可先做一次手動試問；它會向第三方 API 發送固定 GET，**不會傳送問題內容**：

```sh
printf '%s\n' '{"hook_event_name":"Stop","session_id":"manual-demo","last_assistant_message":"ASK: 用什麼主題寫筆記？"}' | python3 magic_conch.py
```

成功時輸出 `{"decision":"block","reason":"…"}`；不符合協定、額度耗盡或故障時輸出 `{}`，讓 agent 正常停止。

## 接到 Codex

把 [codex-hooks.json](examples/codex-hooks.json) 的 `Stop` 區塊合併到使用中的 `hooks.json`。使用者設定預設位於 `$CODEX_HOME/hooks.json`；未設定 `CODEX_HOME` 時是 `~/.codex/hooks.json`。已有 hook 時請合併，勿覆蓋；若原本使用 `config.toml` 的 inline `[hooks]`，沿用該表示法，避免重複接線。

開啟 Codex，透過 `/hooks` 檢視並信任這個 hook。Hooks 需保持啟用；不要為此關掉 sandbox 或其他權限檢查。設定位置與信任流程見 [Codex 官方 hooks 文件](https://learn.chatgpt.com/docs/hooks)。

在測試工作區，把 [protocol.md](examples/protocol.md) 貼給 agent，再交付小任務，例如：「先問海螺筆記主題，收到答案後在目前目錄寫 `note.txt`，讀回確認後 DONE。」依原有 sandbox 與核准方式提供該檔案所需的寫入權限。

## 接到 Claude Code

[claude-settings.json](examples/claude-settings.json) 使用 Claude 的 `--settings` 接線；不必寫入全域設定。在可信任的測試工作區執行：

```sh
claude --model sonnet --settings /absolute/path/to/magic-conch/examples/claude-settings.json
```

同樣貼上 [protocol.md](examples/protocol.md)，再交付上面的小任務。工具寫入仍遵循正常權限；headless 模式需事先提供所需 allow rule。Claude 檔案規則使用 `Edit(path)`，涵蓋 Write 工具，不能寫成 `Write(path)`。

`--settings` 會與既有設定合併。若想只測這個 hook，可加 `--setting-sources '' --strict-mcp-config --mcp-config '{"mcpServers":{}}' --disable-slash-commands`，並在獨立工作區及獨立 `CLAUDE_CONFIG_DIR` 執行；這些旗標本身不是完整環境隔離。不要使用 `--bare` 或 `--safe-mode`，它們也會停用這個 hook。格式見 [Claude 官方 hooks 文件](https://code.claude.com/docs/en/hooks)。

## 上限、停用與重置

只有最後一則訊息以 `ASK:` 開頭且後面有問題時才取答案；`DONE` 與其他回覆均放行。真正需要人類決策或授權時，請正常提問，不要加 `ASK:`。

每個 session 最多嘗試 **3 次**；API 失敗也占一次額度。`curl` 最多 5 秒，Python 等待最多 6 秒，範例 hook timeout 為 8 秒。壞輸入、網路錯誤或狀態無法寫入都不要求續跑。主程式的整體執行時間由你的 CLI／執行器管理。

只在本機 cache 儲存 session ID 的 SHA-256 與次數，不儲存問題、答案或認證。預設是 `${XDG_CACHE_HOME:-~/.cache}/magic-conch/attempts.sqlite3`，也可用 `MAGIC_CONCH_CACHE_DIR` 指定另一個 cache 目錄。不同 session 分開計數；重新啟動同一 session 不會重置。

停用：Codex 移除本工具的那筆 Stop handler，或透過 `/hooks` 停用；Claude 下一次啟動時不帶此 `--settings`（若已合併進其他設定，移除本工具的 handler）。不要刪除其他 hook。

重置：沒有 hook 執行時，刪除上述 `attempts.sqlite3` 即清除所有 session 的額度；開新 session 則自然取得新額度。Cache 不會自動清理，可在不使用時一併刪除整個 `magic-conch` cache 目錄。

## 測試與授權

```sh
python3 -m unittest discover -s tests -v
```

測試用假的 `curl`，不連網。原型已於 Codex 0.162.0 與 Claude Code 2.1.304 實測 ASK→Stop→隨機答案→自動續跑→檔案產物→DONE；本專案把相同接線整理成單一腳本。

程式碼依 [MIT License](LICENSE) 提供。梗圖來自 [memes.tw 搜尋結果](https://memes.tw/wtf?q=%E4%BD%A0%E7%82%BA%E4%BB%80%E9%BA%BC%E4%B8%8D%E5%95%8F%E5%95%8F)（[圖片原址](https://memeprod.sgp1.digitaloceanspaces.com/user-wtf/1650873918786.jpg)），**圖片不在 MIT 授權範圍內**。原梗可看 [SpongeBob 官方片段](https://www.youtube.com/watch?v=ZHmtvR-1ivw)。
